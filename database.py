import csv
import hashlib
import io
import json
import os
import queue
import secrets
import sqlite3
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

try:
    import pymysql
except ImportError:
    pymysql = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLED_TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.environ.get("DB_PATH") or os.path.join(DATA_DIR, "sinhhoc12.db")
TOPIC1_PATH = os.path.join(BUNDLED_TOPICS_DIR, "chu_de_1.json")

ADMIN_USERNAME = "bachanhtu"
ADMIN_DEFAULT_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD", "123456789@")
DEFAULT_USER_PASSWORD = os.environ.get("DEFAULT_USER_PASSWORD", "123456@")
TEACHER_INVITE_CODE = os.environ.get("TEACHER_INVITE_CODE", "GV-SINH12")

# Tự động nhận diện MySQL (trên Wasmer Edge khi bật Enable Database) hoặc SQLite (local)
DB_HOST = (os.environ.get("DB_HOST") or "").strip()
DB_ENGINE = (os.environ.get("DB_ENGINE") or "").strip().lower()
IS_MYSQL = (DB_ENGINE == "mysql") or (
    DB_ENGINE != "sqlite" and bool(DB_HOST) and not DB_HOST.startswith("${")
)
DB_BACKEND = "mysql" if IS_MYSQL else "sqlite"

DB_PORT = int(os.environ.get("DB_PORT") or "3306")
DB_NAME = (os.environ.get("DB_NAME") or os.environ.get("DB_DATABASE") or "").strip()
DB_USER = (os.environ.get("DB_USERNAME") or os.environ.get("DB_USER") or "").strip()
DB_PASSWORD = os.environ.get("DB_PASSWORD") or ""
DB_SSL = (os.environ.get("DB_SSL") or "auto").strip().lower()


class _NoOpLock:
    """Không cần khóa tiến trình khi chạy MySQL Server để tối đa xử lý song song."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


# Khoá đồng bộ tiến trình cho SQLite tránh lỗi "database is locked"
DB_LOCK = _NoOpLock() if IS_MYSQL else threading.RLock()
_DB_DIR_READY = False
_MYSQL_POOL = queue.LifoQueue(maxsize=16)

# Bộ nhớ đệm nhẹ cho auth token (TTL 30s) giúp giảm >80% truy vấn DB khi lớp đông học sinh
_TOKEN_CACHE_LOCK = threading.Lock()
_TOKEN_CACHE = {}  # token -> (expire_ts, user_dict)
_TOKEN_CACHE_TTL = 30.0
_TOKEN_CACHE_MAX = 512


def describe_db() -> str:
    if IS_MYSQL:
        return f"MySQL ({DB_HOST}:{DB_PORT}/{DB_NAME})"
    return f"SQLite ({DB_PATH})"


def invalidate_token_cache(token: str = None, user_id: int = None):
    with _TOKEN_CACHE_LOCK:
        if token:
            _TOKEN_CACHE.pop(token, None)
        if user_id is not None:
            for k in [tk for tk, (_, u) in _TOKEN_CACHE.items() if u.get("id") == user_id]:
                _TOKEN_CACHE.pop(k, None)
        if token is None and user_id is None:
            _TOKEN_CACHE.clear()


def now_vn() -> datetime:
    """Luôn trả về thời điểm hiện tại theo múi giờ Việt Nam (Asia/Ho_Chi_Minh, UTC+07:00)."""
    return datetime.now(VN_TZ)


def now_iso() -> str:
    """Chuỗi ISO-8601 chuẩn theo múi giờ Việt Nam (+07:00), không phụ thuộc múi giờ máy chủ (UTC)."""
    return now_vn().isoformat(timespec="seconds")


def parse_vn_datetime(ts: str):
    """Chuyển chuỗi ISO (có Z, có +07:00 hoặc không có offset) về datetime aware múi giờ Việt Nam (+07:00)."""
    if not ts:
        return None
    s = str(ts).strip()
    if not s:
        return None
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=VN_TZ)
    return dt.astimezone(VN_TZ)


def to_vn_iso(ts: str) -> str:
    dt = parse_vn_datetime(ts)
    if not dt:
        return ""
    return dt.isoformat(timespec="seconds")


def format_vn_display(ts: str) -> str:
    dt = parse_vn_datetime(ts)
    if not dt:
        return str(ts or "")
    return dt.strftime("%d/%m/%Y %H:%M:%S")


class CompatRow(dict):
    """Hỗ trợ truy cập cả row['col'], row[0], dict(row) và row.keys() giống sqlite3.Row."""

    def __init__(self, columns, values):
        self._values = tuple(values)
        super().__init__(zip(columns, self._values))

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return super().__getitem__(key)


def _translate_qmarks_to_mysql(sql: str, has_params: bool) -> str:
    """Chuyển placeholder '?' của SQLite sang '%s' của PyMySQL, giữ nguyên '?' trong chuỗi literal."""
    out = []
    in_single = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if in_single:
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("''")
                    i += 2
                    continue
                in_single = False
                out.append(ch)
            elif ch == "%" and has_params:
                out.append("%%")
            else:
                out.append(ch)
        else:
            if ch == "'":
                in_single = True
                out.append(ch)
            elif ch == "?":
                out.append("%s")
            elif ch == "%" and has_params:
                out.append("%%")
            else:
                out.append(ch)
        i += 1
    return "".join(out)


class MySQLCompatCursor:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor

    def execute(self, sql: str, params=None):
        has_params = bool(params is not None and len(params) > 0)
        translated = _translate_qmarks_to_mysql(sql, has_params)
        if has_params:
            self._cur.execute(translated, tuple(params))
        else:
            self._cur.execute(translated)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in (self._cur.description or ())]
        return CompatRow(cols, row)

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        cols = [d[0] for d in (self._cur.description or ())]
        return [CompatRow(cols, r) for r in rows]

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


class MySQLCompatConnection:
    def __init__(self, raw_conn):
        self._raw = raw_conn
        self._cursors = []
        self._closed = False

    def cursor(self):
        cur = MySQLCompatCursor(self._raw.cursor())
        self._cursors.append(cur)
        return cur

    def execute(self, sql: str, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        for cur in self._cursors:
            cur.close()
        self._cursors.clear()
        try:
            # Xoá snapshot/giao dịch dở để kết nối trong pool luôn thấy dữ liệu mới nhất
            self._raw.rollback()
            _MYSQL_POOL.put_nowait(self._raw)
        except Exception:
            try:
                self._raw.close()
            except Exception:
                pass


def _build_mysql_ssl_context():
    use_ssl = DB_SSL in ("1", "true", "yes", "require", "required") or (
        DB_SSL == "auto" and DB_HOST not in ("localhost", "127.0.0.1")
    )
    if not use_ssl:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _open_mysql_raw_conn():
    if pymysql is None:
        raise RuntimeError(
            "Thiếu thư viện PyMySQL để kết nối MySQL. Hãy cài đặt 'PyMySQL>=1.1.0'."
        )
    kwargs = {
        "host": DB_HOST,
        "port": DB_PORT,
        "database": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "charset": "utf8mb4",
        "autocommit": False,
        "connect_timeout": 10,
        "read_timeout": 20,
        "write_timeout": 20,
    }
    ssl_ctx = _build_mysql_ssl_context()
    if ssl_ctx is not None:
        kwargs["ssl"] = ssl_ctx
    return pymysql.connect(**kwargs)


def _get_mysql_conn() -> MySQLCompatConnection:
    while True:
        try:
            raw = _MYSQL_POOL.get_nowait()
        except queue.Empty:
            break
        try:
            raw.ping(reconnect=True)
            return MySQLCompatConnection(raw)
        except Exception:
            try:
                raw.close()
            except Exception:
                pass
    return MySQLCompatConnection(_open_mysql_raw_conn())


def get_conn():
    """
    Trả về kết nối DB tương thích cả hai môi trường:
    - Wasmer Edge (có DB_HOST): dùng MySQL v8.4 qua pool kết nối PyMySQL.
    - Máy local: dùng SQLite (data/sinhhoc12.db).
    """
    if IS_MYSQL:
        return _get_mysql_conn()

    global _DB_DIR_READY
    if not _DB_DIR_READY:
        os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
        _DB_DIR_READY = True
    conn = sqlite3.connect(DB_PATH, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 8000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn


def _configure_sqlite_once(conn):
    """Cấu hình journal_mode & synchronous 1 lần duy nhất lúc khởi động server SQLite."""
    env_mode = (os.environ.get("SQLITE_JOURNAL_MODE") or "").strip().upper()
    if env_mode in ("DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"):
        target_mode = env_mode
    elif os.path.abspath(DB_PATH).startswith("/data"):
        target_mode = "DELETE"
    else:
        target_mode = "WAL"
    try:
        conn.execute(f"PRAGMA journal_mode = {target_mode};")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -8000;")
    except sqlite3.Error:
        pass


def hash_password(password: str, salt: str = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
        return secrets.compare_digest(hash_password(password, salt), stored)
    except Exception:
        return False


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'teacher', 'student')),
    class_name TEXT DEFAULT '',
    school_name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    avatar_color TEXT DEFAULT '#0f766e',
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    order_index INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    subtitle TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'published',
    content_json TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(updated_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS study_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic_id TEXT DEFAULT 'chu-de-1',
    enter_time TEXT NOT NULL,
    last_heartbeat TEXT NOT NULL,
    leave_time TEXT,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    last_tab TEXT DEFAULT 'theory',
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON study_sessions(user_id, enter_time DESC);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    quiz_type TEXT NOT NULL,
    score REAL NOT NULL,
    max_score REAL NOT NULL,
    correct_count INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 0,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    answers_json TEXT NOT NULL DEFAULT '{}',
    submitted_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_quiz_user ON quiz_attempts(user_id, submitted_at DESC);

CREATE TABLE IF NOT EXISTS lesson_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    checkpoint_score INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, topic_id, lesson_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS login_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    login_time TEXT NOT NULL,
    ip_address TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_login_logs_user ON login_logs(user_id, login_time DESC);

CREATE TABLE IF NOT EXISTS password_change_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    school_name TEXT DEFAULT '',
    class_name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    changed_at TEXT NOT NULL,
    reason TEXT DEFAULT 'user_update',
    is_read INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pw_logs_time ON password_change_logs(changed_at DESC);

CREATE TABLE IF NOT EXISTS mock_exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number INTEGER NOT NULL,
    header_label TEXT NOT NULL DEFAULT 'PHÒNG LUYỆN TẬP',
    title TEXT NOT NULL,
    subtitle TEXT NOT NULL DEFAULT '',
    duration_minutes INTEGER NOT NULL DEFAULT 45,
    source_filename TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL,
    question_count INTEGER NOT NULL DEFAULT 0,
    max_score REAL NOT NULL DEFAULT 10.0,
    created_by INTEGER,
    created_by_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_mock_exams_order ON mock_exams(order_number ASC);

CREATE TABLE IF NOT EXISTS mock_exam_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    score REAL NOT NULL,
    max_score REAL NOT NULL DEFAULT 10.0,
    part1_score REAL NOT NULL DEFAULT 0,
    part2_score REAL NOT NULL DEFAULT 0,
    part3_score REAL NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 0,
    answers_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(exam_id) REFERENCES mock_exams(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mock_attempts_exam_user ON mock_exam_attempts(exam_id, user_id, submitted_at DESC);

CREATE TABLE IF NOT EXISTS student_theory_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    lesson_number TEXT NOT NULL DEFAULT '',
    lesson_title TEXT NOT NULL DEFAULT '',
    section_key TEXT NOT NULL,
    section_heading TEXT NOT NULL DEFAULT '',
    time_spent_seconds INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 1,
    first_viewed_at TEXT NOT NULL,
    last_viewed_at TEXT NOT NULL,
    UNIQUE(user_id, topic_id, lesson_id, section_key),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_theory_reads_user ON student_theory_reads(user_id, topic_id, lesson_id);

CREATE TABLE IF NOT EXISTS student_exercise_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    source_tab TEXT NOT NULL DEFAULT 'knowledge',
    lesson_label TEXT NOT NULL DEFAULT '',
    unit_id TEXT NOT NULL,
    unit_title TEXT NOT NULL DEFAULT '',
    correct_count INTEGER NOT NULL DEFAULT 0,
    answered_count INTEGER NOT NULL DEFAULT 0,
    total_items INTEGER NOT NULL DEFAULT 0,
    accuracy_pct REAL NOT NULL DEFAULT 0.0,
    best_accuracy_pct REAL NOT NULL DEFAULT 0.0,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, topic_id, unit_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_exercise_rec_user ON student_exercise_records(user_id, topic_id, updated_at DESC);
"""

MYSQL_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(191) UNIQUE NOT NULL,
        email VARCHAR(191) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        role VARCHAR(32) NOT NULL,
        class_name VARCHAR(120) NOT NULL DEFAULT '',
        school_name VARCHAR(255) NOT NULL DEFAULT '',
        phone VARCHAR(64) NOT NULL DEFAULT '',
        bio VARCHAR(1000) NOT NULL DEFAULT '',
        avatar_color VARCHAR(32) NOT NULL DEFAULT '#0f766e',
        must_change_password TINYINT(1) NOT NULL DEFAULT 0,
        created_by INT NULL,
        created_at VARCHAR(40) NOT NULL,
        updated_at VARCHAR(40) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_tokens (
        token VARCHAR(191) PRIMARY KEY,
        user_id INT NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        expires_at VARCHAR(40) NOT NULL,
        INDEX idx_auth_tokens_user (user_id),
        CONSTRAINT fk_auth_tokens_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS topics (
        id VARCHAR(120) PRIMARY KEY,
        order_index INT NOT NULL DEFAULT 1,
        title VARCHAR(500) NOT NULL,
        subtitle VARCHAR(500) NOT NULL DEFAULT '',
        status VARCHAR(32) NOT NULL DEFAULT 'published',
        content_json LONGTEXT NOT NULL,
        updated_by INT NULL,
        updated_at VARCHAR(40) NOT NULL,
        CONSTRAINT fk_topics_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS study_sessions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        topic_id VARCHAR(120) NOT NULL DEFAULT 'chu-de-1',
        enter_time VARCHAR(40) NOT NULL,
        last_heartbeat VARCHAR(40) NOT NULL,
        leave_time VARCHAR(40) NULL,
        duration_seconds INT NOT NULL DEFAULT 0,
        last_tab VARCHAR(64) NOT NULL DEFAULT 'theory',
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        INDEX idx_sessions_user (user_id, enter_time),
        CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        topic_id VARCHAR(120) NOT NULL,
        quiz_type VARCHAR(64) NOT NULL,
        score DOUBLE NOT NULL,
        max_score DOUBLE NOT NULL,
        correct_count INT NOT NULL DEFAULT 0,
        total_questions INT NOT NULL DEFAULT 0,
        duration_seconds INT NOT NULL DEFAULT 0,
        answers_json LONGTEXT NOT NULL,
        submitted_at VARCHAR(40) NOT NULL,
        INDEX idx_quiz_user (user_id, submitted_at),
        CONSTRAINT fk_quiz_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS lesson_progress (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        topic_id VARCHAR(120) NOT NULL,
        lesson_id VARCHAR(120) NOT NULL,
        completed TINYINT(1) NOT NULL DEFAULT 0,
        checkpoint_score INT NOT NULL DEFAULT 0,
        updated_at VARCHAR(40) NOT NULL,
        UNIQUE KEY uq_lesson_progress (user_id, topic_id, lesson_id),
        CONSTRAINT fk_progress_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS login_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        login_time VARCHAR(40) NOT NULL,
        ip_address VARCHAR(120) NOT NULL DEFAULT '',
        user_agent VARCHAR(255) NOT NULL DEFAULT '',
        INDEX idx_login_logs_user (user_id, login_time),
        CONSTRAINT fk_login_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS password_change_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        username VARCHAR(191) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        role VARCHAR(32) NOT NULL,
        school_name VARCHAR(255) NOT NULL DEFAULT '',
        class_name VARCHAR(120) NOT NULL DEFAULT '',
        phone VARCHAR(64) NOT NULL DEFAULT '',
        changed_at VARCHAR(40) NOT NULL,
        reason VARCHAR(64) NOT NULL DEFAULT 'user_update',
        is_read TINYINT(1) NOT NULL DEFAULT 0,
        INDEX idx_pw_logs_time (changed_at),
        CONSTRAINT fk_pw_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS mock_exams (
        id INT AUTO_INCREMENT PRIMARY KEY,
        order_number INT NOT NULL,
        header_label VARCHAR(120) NOT NULL DEFAULT 'PHÒNG LUYỆN TẬP',
        title VARCHAR(255) NOT NULL,
        subtitle VARCHAR(500) NOT NULL DEFAULT '',
        duration_minutes INT NOT NULL DEFAULT 45,
        source_filename VARCHAR(255) NOT NULL DEFAULT '',
        content_json LONGTEXT NOT NULL,
        question_count INT NOT NULL DEFAULT 0,
        max_score DOUBLE NOT NULL DEFAULT 10.0,
        created_by INT NULL,
        created_by_name VARCHAR(255) NOT NULL DEFAULT '',
        created_at VARCHAR(40) NOT NULL,
        updated_at VARCHAR(40) NOT NULL,
        INDEX idx_mock_exams_order (order_number),
        CONSTRAINT fk_mock_exams_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS mock_exam_attempts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        exam_id INT NOT NULL,
        user_id INT NOT NULL,
        started_at VARCHAR(40) NOT NULL,
        submitted_at VARCHAR(40) NOT NULL,
        duration_seconds INT NOT NULL DEFAULT 0,
        score DOUBLE NOT NULL,
        max_score DOUBLE NOT NULL DEFAULT 10.0,
        part1_score DOUBLE NOT NULL DEFAULT 0,
        part2_score DOUBLE NOT NULL DEFAULT 0,
        part3_score DOUBLE NOT NULL DEFAULT 0,
        correct_count INT NOT NULL DEFAULT 0,
        total_questions INT NOT NULL DEFAULT 0,
        answers_json LONGTEXT NOT NULL,
        INDEX idx_mock_attempts_exam_user (exam_id, user_id, submitted_at),
        CONSTRAINT fk_mock_attempts_exam FOREIGN KEY (exam_id) REFERENCES mock_exams(id) ON DELETE CASCADE,
        CONSTRAINT fk_mock_attempts_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS student_theory_reads (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        topic_id VARCHAR(120) NOT NULL,
        lesson_id VARCHAR(120) NOT NULL,
        lesson_number VARCHAR(40) NOT NULL DEFAULT '',
        lesson_title VARCHAR(300) NOT NULL DEFAULT '',
        section_key VARCHAR(160) NOT NULL,
        section_heading VARCHAR(300) NOT NULL DEFAULT '',
        time_spent_seconds INT NOT NULL DEFAULT 0,
        completed TINYINT(1) NOT NULL DEFAULT 1,
        first_viewed_at VARCHAR(40) NOT NULL,
        last_viewed_at VARCHAR(40) NOT NULL,
        UNIQUE KEY uq_theory_read (user_id, topic_id, lesson_id, section_key),
        INDEX idx_theory_reads_user (user_id, topic_id, lesson_id),
        CONSTRAINT fk_theory_reads_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS student_exercise_records (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        topic_id VARCHAR(120) NOT NULL,
        source_tab VARCHAR(32) NOT NULL DEFAULT 'knowledge',
        lesson_label VARCHAR(120) NOT NULL DEFAULT '',
        unit_id VARCHAR(160) NOT NULL,
        unit_title VARCHAR(300) NOT NULL DEFAULT '',
        correct_count INT NOT NULL DEFAULT 0,
        answered_count INT NOT NULL DEFAULT 0,
        total_items INT NOT NULL DEFAULT 0,
        accuracy_pct DOUBLE NOT NULL DEFAULT 0.0,
        best_accuracy_pct DOUBLE NOT NULL DEFAULT 0.0,
        attempt_count INT NOT NULL DEFAULT 1,
        updated_at VARCHAR(40) NOT NULL,
        UNIQUE KEY uq_exercise_rec (user_id, topic_id, unit_id),
        INDEX idx_exercise_rec_user (user_id, topic_id, updated_at),
        CONSTRAINT fk_exercise_rec_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def _ensure_admin_account(conn):
    ts = now_iso()
    admin = conn.execute("SELECT id FROM users WHERE lower(username) = ?", (ADMIN_USERNAME,)).fetchone()
    if not admin:
        insert_prefix = "INSERT IGNORE INTO" if IS_MYSQL else "INSERT INTO"
        conn.execute(
            f"""
            {insert_prefix} users
            (username, email, password_hash, full_name, role, class_name, school_name, phone, bio, avatar_color, must_change_password, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'admin', 'Quản trị hệ thống', 'Sinh học 12', '', 'Quản trị viên hệ thống Sinh học 12', '#0f766e', 0, ?, ?)
            """,
            (
                ADMIN_USERNAME,
                f"{ADMIN_USERNAME}@admin.sinhhoc12.local",
                hash_password(ADMIN_DEFAULT_PASSWORD),
                "Quản trị viên (Bạch Anh Tú)",
                ts,
                ts,
            ),
        )
        conn.commit()


def wipe_all_access_data_and_migrate():
    """
    Xoá toàn bộ dữ liệu truy cập, tài khoản cũ, nhật ký, điểm ôn tập và nâng cấp bảng users
    lên mô hình 3 quyền (admin / teacher / student), chỉ giữ lại 100% nội dung các Chủ đề
    và khởi tạo duy nhất tài khoản Quản trị viên: bachanhtu / 123456789@.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        if IS_MYSQL:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            has_topics = cur.execute("SHOW TABLES LIKE 'topics'").fetchone()
            if has_topics:
                cur.execute("UPDATE topics SET updated_by = NULL")
            for tbl in (
                "password_change_logs",
                "login_logs",
                "lesson_progress",
                "quiz_attempts",
                "study_sessions",
                "auth_tokens",
                "users",
            ):
                cur.execute(f"DROP TABLE IF EXISTS {tbl}")
            for stmt in MYSQL_SCHEMA_STATEMENTS:
                cur.execute(stmt)
            conn.commit()
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        else:
            conn.execute("PRAGMA foreign_keys = OFF;")
            has_topics = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='topics'"
            ).fetchone()
            if has_topics:
                cur.execute("UPDATE topics SET updated_by = NULL")
            for tbl in (
                "password_change_logs",
                "login_logs",
                "lesson_progress",
                "quiz_attempts",
                "study_sessions",
                "auth_tokens",
                "users",
            ):
                cur.execute(f"DROP TABLE IF EXISTS {tbl}")
            cur.executescript(SCHEMA_SQL)
            conn.commit()
            conn.execute("PRAGMA foreign_keys = ON;")

        seed_initial_data(conn)
    finally:
        conn.close()


def init_db():
    with DB_LOCK:
        conn = get_conn()
        try:
            cur = conn.cursor()
            if IS_MYSQL:
                for stmt in MYSQL_SCHEMA_STATEMENTS:
                    cur.execute(stmt)
                conn.commit()
            else:
                _configure_sqlite_once(conn)
                cur.executescript(SCHEMA_SQL)
                conn.commit()
            seed_initial_data(conn)
        finally:
            conn.close()


def seed_initial_data(conn):
    cur = conn.cursor()
    ts = now_iso()

    # Seed all available topics from data/topics/chu_de_*.json (hỗ trợ mở rộng Chủ đề 5, 6, 7...)
    topics_dir = BUNDLED_TOPICS_DIR
    if os.path.isdir(topics_dir):
        json_files = sorted(
            [fn for fn in os.listdir(topics_dir) if fn.startswith("chu_de_") and fn.endswith(".json")],
            key=lambda fn: int("".join(ch for ch in fn if ch.isdigit()) or "999"),
        )
    else:
        json_files = []
    insert_prefix = "INSERT IGNORE INTO" if IS_MYSQL else "INSERT INTO"
    for idx, fn in enumerate(json_files, 1):
        tpath = os.path.join(topics_dir, fn)
        if os.path.exists(tpath):
            with open(tpath, "r", encoding="utf-8") as f:
                tdata = json.load(f)
            existing = cur.execute(
                "SELECT id, content_json FROM topics WHERE id = ?", (tdata["id"],)
            ).fetchone()
            if not existing:
                cur.execute(
                    f"""
                    {insert_prefix} topics (id, order_index, title, subtitle, status, content_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tdata["id"],
                        tdata.get("order_index", idx),
                        tdata["title"],
                        tdata.get("subtitle", ""),
                        tdata.get("status", "published"),
                        json.dumps(tdata, ensure_ascii=False),
                        ts,
                    ),
                )
            else:
                # Tự động đồng bộ dữ liệu SGK mới khi phiên bản bundled_version trong JSON tăng lên
                # (vẫn giữ nguyên danh sách youtube_videos giáo viên đã nhúng trên máy chủ)
                bundled_ver = tdata.get("bundled_version")
                if bundled_ver:
                    try:
                        old_data = json.loads(existing["content_json"])
                    except Exception:
                        old_data = {}
                    if old_data.get("bundled_version") != bundled_ver:
                        merged = dict(tdata)
                        if old_data.get("youtube_videos") and not merged.get("youtube_videos"):
                            merged["youtube_videos"] = old_data["youtube_videos"]
                        cur.execute(
                            """
                            UPDATE topics
                            SET order_index = ?, title = ?, subtitle = ?, status = ?, content_json = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                merged.get("order_index", idx),
                                merged["title"],
                                merged.get("subtitle", ""),
                                merged.get("status", "published"),
                                json.dumps(merged, ensure_ascii=False),
                                ts,
                                merged["id"],
                            ),
                        )

    conn.commit()
    _ensure_admin_account(conn)


def upsert_lesson_progress(conn, user_id: int, topic_id: str, lesson_id: str, completed: int, checkpoint_score: int, ts: str):
    """Lưu hoặc cập nhật tiến độ bài học tương thích cả SQLite và MySQL."""
    if IS_MYSQL:
        conn.execute(
            """
            INSERT INTO lesson_progress (user_id, topic_id, lesson_id, completed, checkpoint_score, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                completed = VALUES(completed),
                checkpoint_score = GREATEST(checkpoint_score, VALUES(checkpoint_score)),
                updated_at = VALUES(updated_at)
            """,
            (user_id, topic_id, lesson_id, completed, checkpoint_score, ts),
        )
    else:
        conn.execute(
            """
            INSERT INTO lesson_progress (user_id, topic_id, lesson_id, completed, checkpoint_score, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, topic_id, lesson_id)
            DO UPDATE SET completed = excluded.completed,
                          checkpoint_score = MAX(lesson_progress.checkpoint_score, excluded.checkpoint_score),
                          updated_at = excluded.updated_at
            """,
            (user_id, topic_id, lesson_id, completed, checkpoint_score, ts),
        )


def upsert_topic(conn, tid: str, order_index: int, title: str, subtitle: str, status: str, content_json_str: str, updated_by, ts: str):
    """Thêm mới hoặc ghi đè Chủ đề tương thích cả SQLite và MySQL."""
    if IS_MYSQL:
        conn.execute(
            """
            INSERT INTO topics (id, order_index, title, subtitle, status, content_json, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                order_index = VALUES(order_index),
                title = VALUES(title),
                subtitle = VALUES(subtitle),
                status = VALUES(status),
                content_json = VALUES(content_json),
                updated_by = VALUES(updated_by),
                updated_at = VALUES(updated_at)
            """,
            (tid, order_index, title, subtitle, status, content_json_str, updated_by, ts),
        )
    else:
        conn.execute(
            """
            INSERT OR REPLACE INTO topics (id, order_index, title, subtitle, status, content_json, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, order_index, title, subtitle, status, content_json_str, updated_by, ts),
        )


def sanitize_user(row):
    if not row:
        return None
    keys = row.keys()
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "full_name": row["full_name"],
        "role": row["role"],
        "class_name": row["class_name"],
        "school_name": row["school_name"],
        "phone": row["phone"],
        "bio": row["bio"],
        "avatar_color": row["avatar_color"],
        "must_change_password": bool(row["must_change_password"]) if "must_change_password" in keys else False,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def record_login(conn, user_id: int, ip_address: str = "", user_agent: str = ""):
    conn.execute(
        "INSERT INTO login_logs (user_id, login_time, ip_address, user_agent) VALUES (?, ?, ?, ?)",
        (user_id, now_iso(), ip_address or "", (user_agent or "")[:240]),
    )
    conn.commit()


def record_password_change(conn, user_row, reason: str = "profile_update"):
    conn.execute(
        """
        INSERT INTO password_change_logs
        (user_id, username, full_name, role, school_name, class_name, phone, changed_at, reason, is_read)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            user_row["id"],
            user_row["username"],
            user_row["full_name"],
            user_row["role"],
            user_row["school_name"] or "",
            user_row["class_name"] or "",
            user_row["phone"] or "",
            now_iso(),
            reason,
        ),
    )
    conn.commit()


def create_token(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    ts = now_iso()
    exp = (now_vn() + timedelta(days=7)).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO auth_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, ts, exp),
    )
    conn.commit()
    return token


def get_user_by_token(conn, token: str):
    if not token:
        return None
    now_t = time.time()
    with _TOKEN_CACHE_LOCK:
        cached = _TOKEN_CACHE.get(token)
        if cached and cached[0] > now_t:
            return cached[1]
        if cached:
            _TOKEN_CACHE.pop(token, None)

    row = conn.execute(
        """
        SELECT u.*, t.expires_at AS _token_expires_at FROM auth_tokens t
        JOIN users u ON u.id = t.user_id
        WHERE t.token = ?
        """,
        (token,),
    ).fetchone()
    if not row:
        return None
    exp_dt = parse_vn_datetime(row["_token_expires_at"])
    if exp_dt is not None and exp_dt <= now_vn():
        return None
    user_dict = {k: v for k, v in dict(row).items() if k != "_token_expires_at"}
    with _TOKEN_CACHE_LOCK:
        if len(_TOKEN_CACHE) >= _TOKEN_CACHE_MAX:
            _TOKEN_CACHE.clear()
        _TOKEN_CACHE[token] = (now_t + _TOKEN_CACHE_TTL, user_dict)
    return user_dict


def export_sessions_csv(conn, class_filter: str = "") -> str:
    query = """
        SELECT s.id, u.full_name, u.username, u.class_name, u.school_name, u.phone,
               s.topic_id, s.enter_time, s.leave_time, s.last_heartbeat,
               s.duration_seconds, s.last_tab, s.status
        FROM study_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE u.role = 'student'
    """
    params = []
    if class_filter:
        query += " AND u.class_name = ?"
        params.append(class_filter)
    query += " ORDER BY s.enter_time DESC"

    rows = conn.execute(query, params).fetchall()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Mã phiên",
            "Họ và tên",
            "Tên đăng nhập",
            "Lớp",
            "Trường",
            "Số điện thoại",
            "Chủ đề",
            "Thời gian vào lớp",
            "Thời gian rời lớp",
            "Thời lượng (phút)",
            "Thẻ học gần nhất",
            "Trạng thái",
        ]
    )
    for r in rows:
        mins = round((r["duration_seconds"] or 0) / 60.0, 1)
        enter_display = format_vn_display(r["enter_time"])
        leave_display = (
            format_vn_display(r["leave_time"])
            if r["leave_time"]
            else f"Đang học (cập nhật: {format_vn_display(r['last_heartbeat'])})"
        )
        status_vn = "Đang trong lớp" if r["status"] == "active" else "Đã rời lớp"
        writer.writerow(
            [
                r["id"],
                r["full_name"],
                r["username"],
                r["class_name"],
                r["school_name"],
                r["phone"],
                r["topic_id"],
                enter_display,
                leave_display,
                mins,
                r["last_tab"],
                status_vn,
            ]
        )
    return output.getvalue()


def upsert_theory_read(
    conn,
    user_id: int,
    topic_id: str,
    lesson_id: str,
    lesson_number: str,
    lesson_title: str,
    section_key: str,
    section_heading: str,
    duration_delta: int = 0,
    completed: int = 1,
    ts: str = None,
):
    ts = ts or now_iso()
    delta = max(0, int(duration_delta or 0))
    comp = 1 if completed else 0
    if IS_MYSQL:
        conn.execute(
            """
            INSERT INTO student_theory_reads
            (user_id, topic_id, lesson_id, lesson_number, lesson_title, section_key, section_heading,
             time_spent_seconds, completed, first_viewed_at, last_viewed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              lesson_number = VALUES(lesson_number),
              lesson_title = VALUES(lesson_title),
              section_heading = VALUES(section_heading),
              time_spent_seconds = time_spent_seconds + VALUES(time_spent_seconds),
              completed = GREATEST(completed, VALUES(completed)),
              last_viewed_at = VALUES(last_viewed_at)
            """,
            (
                user_id,
                topic_id,
                lesson_id,
                lesson_number[:40],
                lesson_title[:300],
                section_key[:160],
                section_heading[:300],
                delta,
                comp,
                ts,
                ts,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO student_theory_reads
            (user_id, topic_id, lesson_id, lesson_number, lesson_title, section_key, section_heading,
             time_spent_seconds, completed, first_viewed_at, last_viewed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, topic_id, lesson_id, section_key) DO UPDATE SET
              lesson_number = excluded.lesson_number,
              lesson_title = excluded.lesson_title,
              section_heading = excluded.section_heading,
              time_spent_seconds = student_theory_reads.time_spent_seconds + excluded.time_spent_seconds,
              completed = MAX(student_theory_reads.completed, excluded.completed),
              last_viewed_at = excluded.last_viewed_at
            """,
            (
                user_id,
                topic_id,
                lesson_id,
                lesson_number[:40],
                lesson_title[:300],
                section_key[:160],
                section_heading[:300],
                delta,
                comp,
                ts,
                ts,
            ),
        )


def upsert_exercise_record(
    conn,
    user_id: int,
    topic_id: str,
    source_tab: str,
    lesson_label: str,
    unit_id: str,
    unit_title: str,
    correct_count: int,
    answered_count: int,
    total_items: int,
    ts: str = None,
):
    ts = ts or now_iso()
    tot = max(1, int(total_items or 0))
    corr = max(0, min(tot, int(correct_count or 0)))
    ans = max(0, min(tot, int(answered_count or 0)))
    pct = round(corr * 100.0 / tot, 1)
    if IS_MYSQL:
        conn.execute(
            """
            INSERT INTO student_exercise_records
            (user_id, topic_id, source_tab, lesson_label, unit_id, unit_title,
             correct_count, answered_count, total_items, accuracy_pct, best_accuracy_pct, attempt_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON DUPLICATE KEY UPDATE
              source_tab = VALUES(source_tab),
              lesson_label = VALUES(lesson_label),
              unit_title = VALUES(unit_title),
              correct_count = VALUES(correct_count),
              answered_count = VALUES(answered_count),
              total_items = VALUES(total_items),
              accuracy_pct = VALUES(accuracy_pct),
              best_accuracy_pct = GREATEST(best_accuracy_pct, VALUES(accuracy_pct)),
              attempt_count = attempt_count + 1,
              updated_at = VALUES(updated_at)
            """,
            (
                user_id,
                topic_id,
                source_tab[:32],
                lesson_label[:120],
                unit_id[:160],
                unit_title[:300],
                corr,
                ans,
                tot,
                pct,
                pct,
                ts,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO student_exercise_records
            (user_id, topic_id, source_tab, lesson_label, unit_id, unit_title,
             correct_count, answered_count, total_items, accuracy_pct, best_accuracy_pct, attempt_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(user_id, topic_id, unit_id) DO UPDATE SET
              source_tab = excluded.source_tab,
              lesson_label = excluded.lesson_label,
              unit_title = excluded.unit_title,
              correct_count = excluded.correct_count,
              answered_count = excluded.answered_count,
              total_items = excluded.total_items,
              accuracy_pct = excluded.accuracy_pct,
              best_accuracy_pct = MAX(student_exercise_records.best_accuracy_pct, excluded.accuracy_pct),
              attempt_count = student_exercise_records.attempt_count + 1,
              updated_at = excluded.updated_at
            """,
            (
                user_id,
                topic_id,
                source_tab[:32],
                lesson_label[:120],
                unit_id[:160],
                unit_title[:300],
                corr,
                ans,
                tot,
                pct,
                pct,
                ts,
            ),
        )


def _collect_unit_ids_from_blocks(blocks):
    ids = set()
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        inter = b.get("interactive")
        if isinstance(inter, dict) and inter.get("id"):
            ids.add(inter["id"])
        ex = b.get("exercise")
        if isinstance(ex, dict) and ex.get("group"):
            ids.add(ex["group"])
        eg = b.get("exercise_group")
        if isinstance(eg, dict) and eg.get("id"):
            ids.add(eg["id"])
    return ids


def build_curriculum_catalog(conn) -> dict:
    """Tổng hợp danh mục thật của toàn bộ Chủ đề -> Bài -> Mục lý thuyết & Bài tập tương tác để tính % chính xác."""
    rows = conn.execute(
        "SELECT id, order_index, title, content_json FROM topics ORDER BY order_index ASC"
    ).fetchall()
    topics = []
    total_lessons = 0
    total_sections = 0
    total_exercise_units = 0

    for r in rows:
        try:
            content = json.loads(r["content_json"])
        except Exception:
            content = {}
        lessons_meta = []
        topic_ex_units = set()
        for ls in content.get("lessons") or []:
            sec_list = []
            for s_idx, sec in enumerate(ls.get("sections") or []):
                heading = (sec.get("heading") or f"Mục {s_idx + 1}").strip()
                sec_key = f"sec-{s_idx}"
                sec_list.append({"key": sec_key, "heading": heading})
                topic_ex_units.update(_collect_unit_ids_from_blocks(sec.get("blocks")))
            total_lessons += 1
            total_sections += len(sec_list)
            lessons_meta.append(
                {
                    "id": ls.get("id", ""),
                    "number": ls.get("number", ""),
                    "title": ls.get("title", ""),
                    "sections": sec_list,
                }
            )
        ks = content.get("knowledge_system") or {}
        for u in ks.get("units") or []:
            topic_ex_units.update(_collect_unit_ids_from_blocks(u.get("blocks")))
        total_exercise_units += len(topic_ex_units)
        topics.append(
            {
                "id": r["id"],
                "order_index": r["order_index"],
                "title": r["title"],
                "lessons": lessons_meta,
                "section_count": sum(len(l["sections"]) for l in lessons_meta),
                "exercise_unit_count": len(topic_ex_units),
            }
        )

    return {
        "topics": topics,
        "topic_title_map": {t["id"]: t["title"] for t in topics},
        "total_topics": len(topics),
        "total_lessons": total_lessons,
        "total_sections": total_sections,
        "total_exercise_units": total_exercise_units,
    }


def parse_quiz_attempt_enriched(row_dict: dict, topic_title_map: dict, round_number: int = 1) -> dict:
    """Gắn thông tin chi tiết cho từng đợt làm bài tại mục Hệ thống ôn tập."""
    raw_ans = {}
    try:
        raw_ans = json.loads(row_dict.get("answers_json") or "{}")
    except Exception:
        raw_ans = {}
    meta = raw_ans.get("meta") if isinstance(raw_ans, dict) and isinstance(raw_ans.get("meta"), dict) else {}
    total_q = int(row_dict.get("total_questions") or 0)
    corr = int(row_dict.get("correct_count") or 0)
    score = float(row_dict.get("score") or 0)
    max_score = float(row_dict.get("max_score") or 0)
    accuracy_pct = (
        float(meta.get("accuracy_pct"))
        if meta.get("accuracy_pct") is not None
        else (round(corr * 100.0 / total_q, 1) if total_q > 0 else (round(score * 100.0 / max_score, 1) if max_score > 0 else 0.0))
    )
    score_pct = round(score * 100.0 / max_score, 1) if max_score > 0 else 0.0
    tid = row_dict.get("topic_id") or ""
    return {
        "id": row_dict.get("id"),
        "round_number": round_number,
        "user_id": row_dict.get("user_id"),
        "full_name": row_dict.get("full_name", ""),
        "username": row_dict.get("username", ""),
        "class_name": row_dict.get("class_name", ""),
        "topic_id": tid,
        "topic_title": meta.get("topic_title") or topic_title_map.get(tid, tid),
        "quiz_type": row_dict.get("quiz_type") or "mcq",
        "lesson_filter_label": meta.get("lesson_filter_label") or "Toàn chủ đề",
        "score": score,
        "max_score": max_score,
        "score_pct": score_pct,
        "correct_count": corr,
        "total_questions": total_q,
        "accuracy_pct": accuracy_pct,
        "duration_seconds": int(row_dict.get("duration_seconds") or 0),
        "submitted_at": row_dict.get("submitted_at") or "",
        "parts": meta.get("parts") or None,
        "by_lesson": meta.get("by_lesson") or [],
        "has_item_details": bool(meta.get("items")),
        "items_count": len(meta.get("items") or []),
    }


def build_student_learning_report(conn, user_id: int, catalog: dict = None) -> dict:
    """
    Báo cáo học tập toàn diện cho 1 học sinh:
      - Chính xác đã học những Chủ đề / Bài / Mục lý thuyết nào (% đã học)
      - Đã làm những bài tập vận dụng (Lý thuyết + HTKT) nào với tỉ lệ đúng bao nhiêu %
      - Kết quả chính xác từng đợt làm bài Hệ thống ôn tập (Đợt 1, 2, 3...) + tỉ lệ đúng theo từng bài
      - Kết quả Thi thử Tốt nghiệp THPT
    """
    if catalog is None:
        catalog = build_curriculum_catalog(conn)

    user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user_row:
        return {}

    lp_rows = conn.execute(
        "SELECT topic_id, lesson_id, completed, updated_at FROM lesson_progress WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    completed_lesson_map = {r["lesson_id"]: r["updated_at"] for r in lp_rows if r["completed"]}

    tr_rows = conn.execute(
        """
        SELECT topic_id, lesson_id, lesson_number, lesson_title, section_key, section_heading,
               time_spent_seconds, completed, first_viewed_at, last_viewed_at
        FROM student_theory_reads
        WHERE user_id = ?
        ORDER BY last_viewed_at DESC
        """,
        (user_id,),
    ).fetchall()
    reads_by_lesson = {}
    for r in tr_rows:
        reads_by_lesson.setdefault(r["lesson_id"], {})[r["section_key"]] = dict(r)

    ex_rows = conn.execute(
        """
        SELECT topic_id, source_tab, lesson_label, unit_id, unit_title,
               correct_count, answered_count, total_items, accuracy_pct, best_accuracy_pct,
               attempt_count, updated_at
        FROM student_exercise_records
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (user_id,),
    ).fetchall()
    exercises = [dict(r) for r in ex_rows]

    qa_rows = conn.execute(
        """
        SELECT a.*, u.full_name, u.username, u.class_name
        FROM quiz_attempts a
        JOIN users u ON u.id = a.user_id
        WHERE a.user_id = ?
        ORDER BY a.submitted_at ASC
        """,
        (user_id,),
    ).fetchall()
    # Đánh số đợt theo thứ tự thời gian (Đợt 1, Đợt 2...) rồi đảo ngược để đợt mới nhất lên đầu
    review_rounds = []
    for idx, r in enumerate(qa_rows, start=1):
        review_rounds.append(parse_quiz_attempt_enriched(dict(r), catalog["topic_title_map"], round_number=idx))
    review_rounds.reverse()

    mock_rows = conn.execute(
        """
        SELECT a.id, a.exam_id, a.started_at, a.submitted_at, a.duration_seconds,
               a.score, a.max_score, a.part1_score, a.part2_score, a.part3_score,
               a.correct_count, a.total_questions, m.order_number, m.title AS exam_title
        FROM mock_exam_attempts a
        JOIN mock_exams m ON m.id = a.exam_id
        WHERE a.user_id = ?
        ORDER BY a.submitted_at DESC
        """,
        (user_id,),
    ).fetchall()
    mock_attempts = [dict(r) for r in mock_rows]

    sess_rows = conn.execute(
        "SELECT id, topic_id, enter_time, leave_time, duration_seconds, last_tab, status FROM study_sessions WHERE user_id = ? ORDER BY enter_time DESC LIMIT 30",
        (user_id,),
    ).fetchall()
    sessions = [dict(r) for r in sess_rows]
    total_study_seconds = sum(int(s.get("duration_seconds") or 0) for s in sessions)

    # Xây dựng cây tiến độ Chủ đề -> Bài -> Mục lý thuyết
    topics_breakdown = []
    total_studied_sections = 0
    total_studied_lessons = 0
    for tp in catalog["topics"]:
        tp_studied_sec = 0
        tp_studied_ls = 0
        lessons_out = []
        for ls in tp["lessons"]:
            lid = ls["id"]
            is_marked_done = lid in completed_lesson_map
            sec_map = reads_by_lesson.get(lid, {})
            sections_out = []
            ls_sec_done = 0
            for sc in ls["sections"]:
                rec = sec_map.get(sc["key"])
                done = bool(is_marked_done or (rec and rec.get("completed")))
                if done:
                    ls_sec_done += 1
                sections_out.append(
                    {
                        "key": sc["key"],
                        "heading": sc["heading"],
                        "studied": done,
                        "time_spent_seconds": int(rec["time_spent_seconds"]) if rec else 0,
                        "last_viewed_at": rec["last_viewed_at"] if rec else (completed_lesson_map.get(lid) if is_marked_done else None),
                    }
                )
            sec_tot = len(ls["sections"])
            ls_pct = round(ls_sec_done * 100.0 / sec_tot, 1) if sec_tot > 0 else (100.0 if is_marked_done else 0.0)
            ls_studied = is_marked_done or (sec_tot > 0 and ls_sec_done > 0)
            if ls_studied:
                tp_studied_ls += 1
            tp_studied_sec += ls_sec_done
            lessons_out.append(
                {
                    "id": lid,
                    "number": ls["number"],
                    "title": ls["title"],
                    "completed": is_marked_done or (sec_tot > 0 and ls_sec_done == sec_tot),
                    "studied_sections": ls_sec_done,
                    "total_sections": sec_tot,
                    "progress_pct": ls_pct,
                    "sections": sections_out,
                }
            )
        total_studied_sections += tp_studied_sec
        total_studied_lessons += tp_studied_ls
        tp_ex = [e for e in exercises if e["topic_id"] == tp["id"]]
        tp_rev = [a for a in review_rounds if a["topic_id"] == tp["id"]]
        tp_sec_pct = round(tp_studied_sec * 100.0 / tp["section_count"], 1) if tp["section_count"] > 0 else 0.0
        tp_ex_pct = round(len(tp_ex) * 100.0 / tp["exercise_unit_count"], 1) if tp["exercise_unit_count"] > 0 else 0.0
        tp_ex_acc = round(sum(e["accuracy_pct"] for e in tp_ex) / len(tp_ex), 1) if tp_ex else None
        tp_rev_acc = round(sum(a["accuracy_pct"] for a in tp_rev) / len(tp_rev), 1) if tp_rev else None
        topics_breakdown.append(
            {
                "id": tp["id"],
                "order_index": tp["order_index"],
                "title": tp["title"],
                "studied_lessons": tp_studied_ls,
                "total_lessons": len(tp["lessons"]),
                "studied_sections": tp_studied_sec,
                "total_sections": tp["section_count"],
                "theory_pct": tp_sec_pct,
                "exercise_done": len(tp_ex),
                "exercise_total": tp["exercise_unit_count"],
                "exercise_completion_pct": tp_ex_pct,
                "exercise_accuracy_pct": tp_ex_acc,
                "review_rounds_count": len(tp_rev),
                "review_accuracy_pct": tp_rev_acc,
                "lessons": lessons_out,
            }
        )

    theory_pct = round(total_studied_sections * 100.0 / catalog["total_sections"], 1) if catalog["total_sections"] > 0 else 0.0
    ex_completion_pct = round(len(exercises) * 100.0 / catalog["total_exercise_units"], 1) if catalog["total_exercise_units"] > 0 else 0.0
    ex_total_corr = sum(int(e["correct_count"] or 0) for e in exercises)
    ex_total_items = sum(int(e["total_items"] or 0) for e in exercises)
    ex_accuracy_pct = round(ex_total_corr * 100.0 / ex_total_items, 1) if ex_total_items > 0 else None

    rev_total_corr = sum(int(a["correct_count"] or 0) for a in review_rounds)
    rev_total_q = sum(int(a["total_questions"] or 0) for a in review_rounds)
    rev_accuracy_pct = round(rev_total_corr * 100.0 / rev_total_q, 1) if rev_total_q > 0 else None
    rev_avg_score_pct = round(sum(a["score_pct"] for a in review_rounds) / len(review_rounds), 1) if review_rounds else None

    return {
        "student": sanitize_user(user_row),
        "summary": {
            "session_count": len(sessions),
            "total_study_seconds": total_study_seconds,
            "studied_lessons": total_studied_lessons,
            "total_lessons": catalog["total_lessons"],
            "studied_sections": total_studied_sections,
            "total_sections": catalog["total_sections"],
            "theory_pct": theory_pct,
            "exercises_done": len(exercises),
            "exercises_total": catalog["total_exercise_units"],
            "exercise_completion_pct": ex_completion_pct,
            "exercise_correct": ex_total_corr,
            "exercise_items_total": ex_total_items,
            "exercise_accuracy_pct": ex_accuracy_pct,
            "review_rounds_count": len(review_rounds),
            "review_correct_total": rev_total_corr,
            "review_questions_total": rev_total_q,
            "review_accuracy_pct": rev_accuracy_pct,
            "review_avg_score_pct": rev_avg_score_pct,
            "mock_attempts_count": len(mock_attempts),
        },
        "topics": topics_breakdown,
        "exercises": exercises,
        "review_rounds": review_rounds,
        "mock_attempts": mock_attempts,
        "sessions": sessions,
    }


def export_learning_analytics_csv(conn, class_filter: str = "") -> str:
    """Xuất báo cáo tổng hợp % học tập & kết quả từng đợt Hệ thống ôn tập ra file CSV chuẩn Excel."""
    catalog = build_curriculum_catalog(conn)
    query = "SELECT * FROM users WHERE role = 'student'"
    params = []
    if class_filter:
        query += " AND class_name = ?"
        params.append(class_filter)
    query += " ORDER BY class_name, full_name"
    students = conn.execute(query, params).fetchall()

    out = io.StringIO()
    out.write("\ufeff")
    w = csv.writer(out)
    w.writerow(
        [
            "Họ và tên",
            "Tên đăng nhập",
            "Lớp",
            "Số phiên học",
            "Tổng thời gian (phút)",
            "Bài lý thuyết đã học",
            "Mục lý thuyết đã đọc",
            "% Lý thuyết đã học",
            "Bài tập LT/HTKT đã làm",
            "Tỉ lệ đúng bài tập (%)",
            "Số đợt Hệ thống ôn tập",
            "Đúng / Tổng câu Ôn tập",
            "Tỉ lệ đúng Ôn tập (%)",
            "Các mục lý thuyết đã học (tóm tắt)",
        ]
    )
    for st in students:
        rep = build_student_learning_report(conn, st["id"], catalog)
        sm = rep["summary"]
        learned_labels = []
        for tp in rep["topics"]:
            for ls in tp["lessons"]:
                if ls["studied_sections"] > 0 or ls["completed"]:
                    learned_labels.append(f"{ls['number']} ({ls['studied_sections']}/{ls['total_sections']} mục)")
        w.writerow(
            [
                st["full_name"],
                st["username"],
                st["class_name"],
                sm["session_count"],
                round(sm["total_study_seconds"] / 60.0, 1),
                f"{sm['studied_lessons']}/{sm['total_lessons']}",
                f"{sm['studied_sections']}/{sm['total_sections']}",
                f"{sm['theory_pct']}%",
                f"{sm['exercises_done']}/{sm['exercises_total']}",
                f"{sm['exercise_accuracy_pct']}%" if sm["exercise_accuracy_pct"] is not None else "—",
                sm["review_rounds_count"],
                f"{sm['review_correct_total']}/{sm['review_questions_total']}",
                f"{sm['review_accuracy_pct']}%" if sm["review_accuracy_pct"] is not None else "—",
                "; ".join(learned_labels) if learned_labels else "Chưa học mục nào",
            ]
        )
    return out.getvalue()
