import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLED_TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.environ.get("DB_PATH") or os.path.join(DATA_DIR, "sinhhoc12.db")
TOPIC1_PATH = os.path.join(BUNDLED_TOPICS_DIR, "chu_de_1.json")

ADMIN_USERNAME = "bachanhtu"
ADMIN_DEFAULT_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD", "123456789@")
DEFAULT_USER_PASSWORD = os.environ.get("DEFAULT_USER_PASSWORD", "123456@")
TEACHER_INVITE_CODE = os.environ.get("TEACHER_INVITE_CODE", "GV-SINH12")


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def get_conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.Error:
        pass
    return conn


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
"""


def _ensure_admin_account(conn):
    ts = now_iso()
    admin = conn.execute("SELECT id FROM users WHERE lower(username) = ?", (ADMIN_USERNAME,)).fetchone()
    if not admin:
        conn.execute(
            """
            INSERT INTO users
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
    conn.execute("PRAGMA foreign_keys = OFF;")
    cur = conn.cursor()

    # Giữ nguyên bảng topics, chỉ đặt updated_by = NULL trước khi tạo lại users
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
    conn.close()


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()
    seed_initial_data(conn)
    conn.close()


def seed_initial_data(conn):
    cur = conn.cursor()
    ts = now_iso()

    # Seed all available topics from data/topics/chu_de_*.json
    topics_dir = BUNDLED_TOPICS_DIR
    for idx in range(1, 5):
        tpath = os.path.join(topics_dir, f"chu_de_{idx}.json")
        if os.path.exists(tpath):
            with open(tpath, "r", encoding="utf-8") as f:
                tdata = json.load(f)
            existing = cur.execute(
                "SELECT id, content_json FROM topics WHERE id = ?", (tdata["id"],)
            ).fetchone()
            if not existing:
                cur.execute(
                    """
                    INSERT INTO topics (id, order_index, title, subtitle, status, content_json, updated_at)
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
    exp = (datetime.now() + timedelta(days=7)).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO auth_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, ts, exp),
    )
    conn.commit()
    return token


def get_user_by_token(conn, token: str):
    if not token:
        return None
    row = conn.execute(
        """
        SELECT u.* FROM auth_tokens t
        JOIN users u ON u.id = t.user_id
        WHERE t.token = ? AND t.expires_at > ?
        """,
        (token, now_iso()),
    ).fetchone()
    return row


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
        leave_display = r["leave_time"] or f"Đang học (cập nhật: {r['last_heartbeat']})"
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
                r["enter_time"].replace("T", " "),
                leave_display.replace("T", " "),
                mins,
                r["last_tab"],
                status_vn,
            ]
        )
    return output.getvalue()
