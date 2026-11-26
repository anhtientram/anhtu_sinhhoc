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
