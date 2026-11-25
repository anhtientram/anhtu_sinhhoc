#!/usr/bin/env python3
"""
Web App Giảng dạy Sinh học 12 (CT GDPT 2018)
Backend Server (Python 3 stdlib + SQLite) — Không cần cài đặt thư viện ngoài.
Chạy lệnh: python3 server.py
"""
import base64
import json
import mimetypes
import os
import re
import secrets
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from database import (
    ADMIN_USERNAME,
    DEFAULT_USER_PASSWORD,
    TEACHER_INVITE_CODE,
    create_token,
    export_sessions_csv,
    get_conn,
    get_user_by_token,
    hash_password,
    init_db,
    now_iso,
    record_login,
    record_password_change,
    sanitize_user,
    verify_password,
)
from exam_generator import build_exam_pool_summary, generate_shuffled_exam_package
from importer import build_sample_docx_template, parse_document_to_topic
from student_excel import (
    build_student_import_template_xlsx,
    parse_students_from_file,
    validate_username,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
PORT = int(os.environ.get("PORT", "8080"))
BASE_PATH = "/" + os.environ.get("BASE_PATH", "sinhhoc12").strip("/")
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "lms.bachanhtu")

# Bộ nhớ tạm lưu các gói đề trộn (.docx + .xlsx) vừa tạo để tải xuống nhanh
EXAM_EXPORTS = {}


def strip_base_path(path: str) -> str:
    """Hỗ trợ truy cập cả ở /sinhhoc12/... lẫn /..."""
    if BASE_PATH and BASE_PATH != "/":
        if path == BASE_PATH:
            return "/"
        if path.startswith(BASE_PATH + "/"):
            return path[len(BASE_PATH) :]
    return path


def parse_iso_seconds(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def calc_duration_seconds(enter_time: str, end_time: str) -> int:
    t1 = parse_iso_seconds(enter_time)
    t2 = parse_iso_seconds(end_time)
    if not t1 or not t2:
        return 0
    return max(0, int((t2 - t1).total_seconds()))


class Bio12Handler(BaseHTTPRequestHandler):
    server_version = "SinhHoc12WebApp/1.0"

    def log_message(self, fmt, *args):
        sys.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} - {fmt % args}\n")
        sys.stdout.flush()

    def send_json(self, status: int, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, status: int, content: str, content_type="text/plain; charset=utf-8", extra_headers=None):
        payload = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def get_auth_token(self, query_params=None, body=None):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        if query_params and "token" in query_params:
            return query_params["token"][0]
        if body and isinstance(body, dict) and body.get("token"):
            return str(body.get("token"))
        return None

    def require_user(self, conn, query_params=None, body=None):
        token = self.get_auth_token(query_params, body)
        user = get_user_by_token(conn, token)
        if not user:
            self.send_json(401, {"error": "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại."})
            return None
        return user

    def require_teacher(self, conn, query_params=None, body=None):
        """Cho phép cả Quản trị viên (admin) và Giáo viên (teacher) truy cập quản lý lớp học."""
        user = self.require_user(conn, query_params, body)
        if not user:
            return None
        if user["role"] not in ("admin", "teacher"):
            self.send_json(403, {"error": "Chức năng này chỉ dành cho Quản trị viên hoặc Giáo viên."})
            return None
        return user

    def require_admin(self, conn, query_params=None, body=None):
        """Chỉ cho phép Quản trị viên (admin)."""
        user = self.require_user(conn, query_params, body)
        if not user:
            return None
        if user["role"] != "admin":
            self.send_json(403, {"error": "Chức năng này chỉ dành riêng cho Quản trị viên."})
            return None
        return user

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

    # ---------------------- GET ROUTES ----------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        raw_path = parsed.path
        qs = parse_qs(parsed.query)

        # Chuyển hướng gọn /sinhhoc12 -> /sinhhoc12/ để các tệp tĩnh tương đối hoạt động chuẩn
        if raw_path == BASE_PATH:
            self.send_response(302)
            self.send_header("Location", BASE_PATH + "/")
            self.end_headers()
            return

        path = strip_base_path(raw_path)

        if path.startswith("/api/"):
            return self.handle_api_get(path, qs)
        return self.serve_static(path)

    def handle_api_get(self, path, qs):
        conn = get_conn()
        try:
            if path == "/api/health":
                return self.send_json(200, {"ok": True, "time": now_iso(), "app": "Sinh học 12"})

            if path == "/api/auth/me":
                user = self.require_user(conn, qs)
                if not user:
                    return
                active_session = conn.execute(
                    "SELECT * FROM study_sessions WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                    (user["id"],),
                ).fetchone()
                return self.send_json(
                    200,
                    {
                        "user": sanitize_user(user),
                        "active_session": dict(active_session) if active_session else None,
                    },
                )

            if path == "/api/topics":
                rows = conn.execute(
                    "SELECT id, order_index, title, subtitle, status, updated_at FROM topics ORDER BY order_index ASC"
                ).fetchall()
                return self.send_json(200, {"topics": [dict(r) for r in rows]})

            m = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)$", path)
            if m:
                tid = m.group(1)
                row = conn.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy chủ đề."})
                content = json.loads(row["content_json"])
                content["updated_at"] = row["updated_at"]
                return self.send_json(200, {"topic": content})

            if path == "/api/sessions/my":
                user = self.require_user(conn, qs)
                if not user:
                    return
                rows = conn.execute(
                    "SELECT * FROM study_sessions WHERE user_id = ? ORDER BY enter_time DESC LIMIT 30",
                    (user["id"],),
                ).fetchall()
                total_seconds = sum((r["duration_seconds"] or 0) for r in rows)
                return self.send_json(
                    200,
                    {
                        "sessions": [dict(r) for r in rows],
                        "total_seconds": total_seconds,
                    },
                )

            if path == "/api/quiz/my-attempts":
                user = self.require_user(conn, qs)
                if not user:
                    return
                topic_id = qs.get("topic_id", [""])[0]
                if topic_id:
                    rows = conn.execute(
                        "SELECT * FROM quiz_attempts WHERE user_id = ? AND topic_id = ? ORDER BY submitted_at DESC LIMIT 50",
                        (user["id"], topic_id),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM quiz_attempts WHERE user_id = ? ORDER BY submitted_at DESC LIMIT 50",
                        (user["id"],),
                    ).fetchall()
                return self.send_json(200, {"attempts": [dict(r) for r in rows]})

            if path == "/api/progress/my":
                user = self.require_user(conn, qs)
                if not user:
                    return
                rows = conn.execute(
                    "SELECT * FROM lesson_progress WHERE user_id = ?",
                    (user["id"],),
                ).fetchall()
                return self.send_json(200, {"progress": [dict(r) for r in rows]})

            # Teacher-only endpoints
            if path == "/api/teacher/overview":
                teacher = self.require_teacher(conn, qs)
                if not teacher:
                    return

                # Auto-close stale sessions whose last heartbeat was > 10 minutes ago
                cutoff = datetime.now().timestamp() - 600
                active_rows = conn.execute("SELECT * FROM study_sessions WHERE status = 'active'").fetchall()
                for ar in active_rows:
                    hb = parse_iso_seconds(ar["last_heartbeat"])
                    if hb and hb.timestamp() < cutoff:
                        dur = calc_duration_seconds(ar["enter_time"], ar["last_heartbeat"])
                        conn.execute(
                            "UPDATE study_sessions SET status = 'completed', leave_time = ?, duration_seconds = ? WHERE id = ?",
                            (ar["last_heartbeat"], dur, ar["id"]),
                        )
                conn.commit()

                students = conn.execute(
                    "SELECT * FROM users WHERE role = 'student' ORDER BY class_name, full_name"
                ).fetchall()
                teachers = conn.execute(
                    "SELECT * FROM users WHERE role = 'teacher' ORDER BY full_name"
                ).fetchall()

                sessions = conn.execute(
                    """
                    SELECT s.*, u.full_name, u.username, u.class_name, u.avatar_color, u.role
                    FROM study_sessions s
                    JOIN users u ON u.id = s.user_id
                    ORDER BY s.enter_time DESC
                    LIMIT 150
                    """
                ).fetchall()

                attempts = conn.execute(
                    """
                    SELECT a.*, u.full_name, u.username, u.class_name
                    FROM quiz_attempts a
                    JOIN users u ON u.id = a.user_id
                    ORDER BY a.submitted_at DESC
                    LIMIT 150
                    """
                ).fetchall()

                login_counts_rows = conn.execute(
                    """
                    SELECT user_id, COUNT(*) AS cnt, MAX(login_time) AS last_login
                    FROM login_logs
                    GROUP BY user_id
                    """
                ).fetchall()
                login_count_map = {
                    r["user_id"]: {"count": r["cnt"], "last_login": r["last_login"]}
                    for r in login_counts_rows
                }

                login_logs = conn.execute(
                    """
                    SELECT l.*, u.full_name, u.username, u.class_name, u.school_name, u.phone, u.role
                    FROM login_logs l
                    JOIN users u ON u.id = l.user_id
                    ORDER BY l.login_time DESC
                    LIMIT 200
                    """
                ).fetchall()

                # Aggregate per-student stats
                student_list = []
                for st in students:
                    uid = st["id"]
                    st_sessions = [s for s in sessions if s["user_id"] == uid]
                    st_attempts = [a for a in attempts if a["user_id"] == uid]
                    total_sec = sum((s["duration_seconds"] or 0) for s in st_sessions)
                    is_online = any(s["status"] == "active" for s in st_sessions)
                    avg_pct = 0.0
                    if st_attempts:
                        avg_pct = round(
                            sum((a["score"] / a["max_score"] * 100.0) for a in st_attempts if a["max_score"] > 0)
                            / len(st_attempts),
                            1,
                        )
                    lg = login_count_map.get(uid, {"count": 0, "last_login": None})
                    item = sanitize_user(st)
                    item.update(
                        {
                            "session_count": len(st_sessions),
                            "login_count": lg["count"],
                            "last_login": lg["last_login"],
                            "total_seconds": total_sec,
                            "is_online": is_online,
                            "attempt_count": len(st_attempts),
                            "avg_percent": avg_pct,
                            "last_enter": st_sessions[0]["enter_time"] if st_sessions else None,
                            "last_leave": st_sessions[0]["leave_time"] if st_sessions else None,
                        }
                    )
                    student_list.append(item)

                online_count = sum(1 for s in student_list if s["is_online"])
                total_study_minutes = round(sum(s["total_seconds"] for s in student_list) / 60.0, 1)
                total_student_logins = sum(s["login_count"] for s in student_list)

                # Báo cáo đổi mật khẩu chỉ gửi về cho Quản trị viên (admin)
                pw_logs = []
                unread_pw = 0
                if teacher["role"] == "admin":
                    pw_rows = conn.execute(
                        "SELECT * FROM password_change_logs ORDER BY changed_at DESC LIMIT 150"
                    ).fetchall()
                    pw_logs = [dict(r) for r in pw_rows]
                    unread_pw = conn.execute(
                        "SELECT COUNT(*) FROM password_change_logs WHERE is_read = 0"
                    ).fetchone()[0]

                return self.send_json(
                    200,
                    {
                        "stats": {
                            "student_count": len(student_list),
                            "teacher_count": len(teachers),
                            "online_students": online_count,
                            "total_sessions": len([s for s in sessions if s["role"] == "student"]),
                            "total_logins": total_student_logins,
                            "total_attempts": len(attempts),
                            "total_study_minutes": total_study_minutes,
                            "unread_password_changes": unread_pw,
                        },
                        "students": student_list,
                        "teachers": [sanitize_user(t) for t in teachers],
                        "sessions": [dict(s) for s in sessions],
                        "login_logs": [dict(l) for l in login_logs],
                        "attempts": [dict(a) for a in attempts],
                        "password_change_logs": pw_logs,
                    },
                )

            if path == "/api/staff/student-import-template":
                staff = self.require_teacher(conn, qs)
                if not staff:
                    return
                try:
                    xlsx_bytes = build_student_import_template_xlsx()
                    self.send_response(200)
                    self.send_header(
                        "Content-Type",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                    self.send_header("Content-Length", str(len(xlsx_bytes)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header(
                        "Content-Disposition",
                        'attachment; filename="mau-nhap-hoc-sinh-sinhhoc12.xlsx"',
                    )
                    self.end_headers()
                    self.wfile.write(xlsx_bytes)
                    return
                except Exception as e:
                    return self.send_json(500, {"error": f"Không thể tạo file Excel mẫu: {e}"})

            if path == "/api/admin/exam-pool":
                teacher = self.require_teacher(conn, qs)
                if not teacher:
                    return
                rows = conn.execute("SELECT content_json FROM topics ORDER BY order_index ASC").fetchall()
                topics_data = [json.loads(r["content_json"]) for r in rows]
                return self.send_json(200, {"topics": build_exam_pool_summary(topics_data)})

            m_ex_dl = re.match(r"^/api/admin/exam-download/([a-zA-Z0-9_-]+)/(docx|xlsx)$", path)
            if m_ex_dl:
                teacher = self.require_teacher(conn, qs)
                if not teacher:
                    return
                job_id, fmt = m_ex_dl.group(1), m_ex_dl.group(2)
                pkg = EXAM_EXPORTS.get(job_id)
                if not pkg:
                    return self.send_json(404, {"error": "File đề trộn đã hết hạn, vui lòng nhấn Tạo & Trộn đề lại."})
                raw_bytes = pkg[fmt]
                if fmt == "docx":
                    ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    fname = f"{pkg['filename_base']}-de-tron.docx"
                else:
                    ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    fname = f"{pkg['filename_base']}-dap-an.xlsx"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.end_headers()
                self.wfile.write(raw_bytes)
                return

            if path == "/api/teacher/sessions/export":
                teacher = self.require_teacher(conn, qs)
                if not teacher:
                    return
                class_filter = qs.get("class_name", [""])[0]
                csv_data = export_sessions_csv(conn, class_filter)
                return self.send_text(
                    200,
                    csv_data,
                    content_type="text/csv; charset=utf-8",
                    extra_headers={
                        "Content-Disposition": 'attachment; filename="nhat-ky-hoc-tap-sinh12.csv"'
                    },
                )

            if path == "/api/import-template":
                try:
                    docx_bytes = build_sample_docx_template()
                    self.send_response(200)
                    self.send_header(
                        "Content-Type",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                    self.send_header("Content-Length", str(len(docx_bytes)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header(
                        "Content-Disposition",
                        'attachment; filename="mau-tai-lieu-chu-de-sinh12.docx"',
                    )
                    self.end_headers()
                    self.wfile.write(docx_bytes)
                    return
                except Exception as e:
                    return self.send_json(500, {"error": f"Không thể tạo file mẫu: {e}"})

            return self.send_json(404, {"error": "API endpoint không tồn tại."})
        finally:
            conn.close()

    # ---------------------- POST ROUTES ----------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = strip_base_path(parsed.path)
        qs = parse_qs(parsed.query)
        body = self.read_json_body()

        conn = get_conn()
        try:
            if path == "/api/auth/register":
                return self.send_json(
                    403,
                    {
                        "error": "Hệ thống không mở tự đăng ký. Tài khoản Giáo viên do Quản trị viên cấp; tài khoản Học sinh do Quản trị viên hoặc Giáo viên cấp."
                    },
                )

            if path == "/api/auth/login":
                identifier = (body.get("identifier") or body.get("username") or "").strip().lower()
                password = body.get("password") or ""
                expected_role = (body.get("role") or "").strip().lower()
                if not identifier or not password:
                    return self.send_json(400, {"error": "Vui lòng nhập tên đăng nhập và mật khẩu."})

                user_row = conn.execute(
                    "SELECT * FROM users WHERE lower(username) = ? OR lower(email) = ?",
                    (identifier, identifier),
                ).fetchone()
                if not user_row or not verify_password(password, user_row["password_hash"]):
                    return self.send_json(401, {"error": "Tên đăng nhập hoặc mật khẩu chưa chính xác."})

                role_names = {"admin": "Quản trị viên", "teacher": "Giáo viên", "student": "Học sinh"}
                if expected_role in role_names and user_row["role"] != expected_role:
                    return self.send_json(
                        403,
                        {
                            "error": f"Tài khoản '{user_row['username']}' thuộc quyền {role_names[user_row['role']]}. Vui lòng chọn đúng mục {role_names[user_row['role']]} để đăng nhập."
                        },
                    )

                token = create_token(conn, user_row["id"])
                record_login(conn, user_row["id"], self.client_address[0], self.headers.get("User-Agent", ""))
                return self.send_json(200, {"token": token, "user": sanitize_user(user_row)})

            if path == "/api/auth/first-login-setup":
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                full_name = (body.get("full_name") or "").strip()
                school_name = (body.get("school_name") or "").strip()
                class_name = (body.get("class_name") or "").strip()
                phone = (body.get("phone") or "").strip()
                new_password = body.get("new_password") or ""

                if user["role"] == "teacher":
                    if not full_name or not school_name or not phone or not new_password:
                        return self.send_json(
                            400,
                            {"error": "Giáo viên vui lòng nhập đầy đủ: Họ tên GV, Trường, Số điện thoại và Mật khẩu mới."},
                        )
                    if not class_name:
                        class_name = "Tổ Sinh học"
                elif user["role"] == "student":
                    if not full_name or not class_name or not school_name or not phone or not new_password:
                        return self.send_json(
                            400,
                            {"error": "Học sinh vui lòng nhập đầy đủ: Họ tên HS, Lớp, Trường, Số điện thoại và Mật khẩu mới."},
                        )
                else:
                    if not full_name or not new_password:
                        return self.send_json(400, {"error": "Vui lòng nhập đầy đủ thông tin và mật khẩu mới."})

                if len(new_password) < 6:
                    return self.send_json(400, {"error": "Mật khẩu mới cần tối thiểu 6 ký tự."})
                if new_password == DEFAULT_USER_PASSWORD:
                    return self.send_json(
                        400,
                        {"error": f"Mật khẩu mới phải khác mật khẩu mặc định ({DEFAULT_USER_PASSWORD})."},
                    )

                ts = now_iso()
                conn.execute(
                    """
                    UPDATE users
                    SET full_name = ?, class_name = ?, school_name = ?, phone = ?,
                        password_hash = ?, must_change_password = 0, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        full_name,
                        class_name,
                        school_name,
                        phone,
                        hash_password(new_password),
                        ts,
                        user["id"],
                    ),
                )
                conn.commit()
                updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
                if updated["role"] in ("teacher", "student"):
                    record_password_change(conn, updated, reason="first_login_setup")
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "user": sanitize_user(updated),
                        "message": "Đã cập nhật thông tin cá nhân và mật khẩu mới thành công!",
                    },
                )

            if path == "/api/auth/logout":
                token = self.get_auth_token(qs, body)
                if token:
                    user = get_user_by_token(conn, token)
                    if user:
                        # Automatically close active study sessions when logging out
                        ts = now_iso()
                        actives = conn.execute(
                            "SELECT * FROM study_sessions WHERE user_id = ? AND status = 'active'",
                            (user["id"],),
                        ).fetchall()
                        for s in actives:
                            dur = calc_duration_seconds(s["enter_time"], ts)
                            conn.execute(
                                "UPDATE study_sessions SET status = 'completed', leave_time = ?, last_heartbeat = ?, duration_seconds = ? WHERE id = ?",
                                (ts, ts, dur, s["id"]),
                            )
                    conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
                    conn.commit()
                return self.send_json(200, {"ok": True})

            # Session Attendance: Check-in (Vào lớp)
            if path == "/api/sessions/checkin":
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                topic_id = body.get("topic_id") or "chu-de-1"
                tab = body.get("tab") or "theory"
                ts = now_iso()

                # Close any lingering open session for this user first
                prev_actives = conn.execute(
                    "SELECT * FROM study_sessions WHERE user_id = ? AND status = 'active'",
                    (user["id"],),
                ).fetchall()
                for prev in prev_actives:
                    end_t = prev["last_heartbeat"] or ts
                    dur = calc_duration_seconds(prev["enter_time"], end_t)
                    conn.execute(
                        "UPDATE study_sessions SET status = 'completed', leave_time = ?, duration_seconds = ? WHERE id = ?",
                        (end_t, dur, prev["id"]),
                    )

                cur = conn.execute(
                    """
                    INSERT INTO study_sessions (user_id, topic_id, enter_time, last_heartbeat, duration_seconds, last_tab, status)
                    VALUES (?, ?, ?, ?, 0, ?, 'active')
                    """,
                    (user["id"], topic_id, ts, ts, tab),
                )
                conn.commit()
                sess = conn.execute("SELECT * FROM study_sessions WHERE id = ?", (cur.lastrowid,)).fetchone()
                return self.send_json(201, {"session": dict(sess)})

            # Session Attendance: Heartbeat
            if path == "/api/sessions/heartbeat":
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                session_id = body.get("session_id")
                tab = body.get("tab")
                topic_id = body.get("topic_id")
                ts = now_iso()

                sess = conn.execute(
                    "SELECT * FROM study_sessions WHERE id = ? AND user_id = ?",
                    (session_id, user["id"]),
                ).fetchone()
                if not sess:
                    return self.send_json(404, {"error": "Không tìm thấy phiên học."})

                dur = calc_duration_seconds(sess["enter_time"], ts)
                conn.execute(
                    """
                    UPDATE study_sessions
                    SET last_heartbeat = ?, duration_seconds = ?,
                        last_tab = COALESCE(?, last_tab),
                        topic_id = COALESCE(?, topic_id)
                    WHERE id = ?
                    """,
                    (ts, dur, tab, topic_id, session_id),
                )
                conn.commit()
                return self.send_json(200, {"ok": True, "duration_seconds": dur, "last_heartbeat": ts})

            # Session Attendance: Check-out (Rời lớp học — hỗ trợ cả navigator.sendBeacon)
            if path == "/api/sessions/checkout":
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                session_id = body.get("session_id")
                tab = body.get("tab")
                ts = now_iso()

                if session_id:
                    sess = conn.execute(
                        "SELECT * FROM study_sessions WHERE id = ? AND user_id = ?",
                        (session_id, user["id"]),
                    ).fetchone()
                else:
                    sess = conn.execute(
                        "SELECT * FROM study_sessions WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                        (user["id"],),
                    ).fetchone()

                if not sess:
                    return self.send_json(200, {"ok": True, "message": "Không có phiên đang mở."})

                dur = calc_duration_seconds(sess["enter_time"], ts)
                conn.execute(
                    """
                    UPDATE study_sessions
                    SET status = 'completed', leave_time = ?, last_heartbeat = ?, duration_seconds = ?,
                        last_tab = COALESCE(?, last_tab)
                    WHERE id = ?
                    """,
                    (ts, ts, dur, tab, sess["id"]),
                )
                conn.commit()
                updated = conn.execute("SELECT * FROM study_sessions WHERE id = ?", (sess["id"],)).fetchone()
                return self.send_json(200, {"ok": True, "session": dict(updated)})

            # Submit Quiz Attempt
            if path == "/api/quiz/submit":
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                topic_id = body.get("topic_id") or "chu-de-1"
                quiz_type = body.get("quiz_type") or "mcq"
                score = float(body.get("score") or 0)
                max_score = float(body.get("max_score") or 10)
                correct_count = int(body.get("correct_count") or 0)
                total_questions = int(body.get("total_questions") or 0)
                duration_seconds = int(body.get("duration_seconds") or 0)
                answers_json = json.dumps(body.get("answers") or {}, ensure_ascii=False)
                ts = now_iso()

                cur = conn.execute(
                    """
                    INSERT INTO quiz_attempts
                    (user_id, topic_id, quiz_type, score, max_score, correct_count, total_questions, duration_seconds, answers_json, submitted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user["id"],
                        topic_id,
                        quiz_type,
                        score,
                        max_score,
                        correct_count,
                        total_questions,
                        duration_seconds,
                        answers_json,
                        ts,
                    ),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM quiz_attempts WHERE id = ?", (cur.lastrowid,)).fetchone()
                return self.send_json(201, {"attempt": dict(row)})

            # Save lesson progress / checkpoint
            if path == "/api/progress":
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                topic_id = body.get("topic_id") or "chu-de-1"
                lesson_id = body.get("lesson_id") or ""
                completed = 1 if body.get("completed", True) else 0
                checkpoint_score = int(body.get("checkpoint_score") or 0)
                ts = now_iso()
                if not lesson_id:
                    return self.send_json(400, {"error": "Thiếu lesson_id."})

                conn.execute(
                    """
                    INSERT INTO lesson_progress (user_id, topic_id, lesson_id, completed, checkpoint_score, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, topic_id, lesson_id)
                    DO UPDATE SET completed = excluded.completed,
                                  checkpoint_score = MAX(lesson_progress.checkpoint_score, excluded.checkpoint_score),
                                  updated_at = excluded.updated_at
                    """,
                    (user["id"], topic_id, lesson_id, completed, checkpoint_score, ts),
                )
                conn.commit()
                return self.send_json(200, {"ok": True})

            # Teacher: Create new topic
            if path == "/api/topics":
                teacher = self.require_teacher(conn, qs, body)
                if not teacher:
                    return
                title = (body.get("title") or "").strip()
                if not title:
                    return self.send_json(400, {"error": "Vui lòng nhập tên chủ đề."})
                tid = (body.get("id") or "").strip()
                if not tid:
                    cnt = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] + 1
                    tid = f"chu-de-{cnt}"
                subtitle = (body.get("subtitle") or "").strip()
                order_index = int(body.get("order_index") or 5)
                content = body.get("content") or {
                    "id": tid,
                    "order_index": order_index,
                    "title": title,
                    "subtitle": subtitle,
                    "status": "published",
                    "source_note": f"Được tạo bởi {teacher['full_name']}.",
                    "interactive_video": {"title": f"Video tương tác — {title}", "description": "", "external_video_url": "", "external_checkpoints": [], "scenes": []},
                    "lessons": [],
                    "knowledge_system": {"overview": "", "mindmap": {"root": title, "branches": []}, "comparison_tables": [], "formulas": [], "flashcards": []},
                    "review": {"mcq": [], "true_false": [], "short_answer": []},
                }
                content["id"] = tid
                content["title"] = title
                content["subtitle"] = subtitle
                ts = now_iso()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO topics (id, order_index, title, subtitle, status, content_json, updated_by, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tid,
                        order_index,
                        title,
                        subtitle,
                        content.get("status", "published"),
                        json.dumps(content, ensure_ascii=False),
                        teacher["id"],
                        ts,
                    ),
                )
                conn.commit()
                return self.send_json(201, {"topic": content})

            # Teacher: Import & extract topic content from .docx / .pdf / .txt
            m_imp = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)/import-file$", path)
            if m_imp:
                teacher = self.require_teacher(conn, qs, body)
                if not teacher:
                    return
                tid = m_imp.group(1)
                row = conn.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy chủ đề."})

                filename = (body.get("filename") or "").strip()
                content_b64 = body.get("content_base64") or ""
                preview_only = bool(body.get("preview_only", True))
                sections = body.get("sections") or {
                    "theory": True,
                    "knowledge": True,
                    "video": True,
                    "review": True,
                }
                replace_review = bool(body.get("replace_review", True))

                if not filename or not content_b64:
                    return self.send_json(400, {"error": "Vui lòng chọn file tài liệu (.docx, .pdf hoặc .txt)."})

                try:
                    file_bytes = base64.b64decode(content_b64)
                    existing = json.loads(row["content_json"])
                    parsed = parse_document_to_topic(file_bytes, filename, tid, existing)
                except Exception as e:
                    return self.send_json(400, {"error": f"Lỗi khi đọc & trích xuất file: {e}"})

                if preview_only:
                    return self.send_json(200, {"ok": True, "preview": parsed})

                # Merge extracted data into existing topic based on selected sections
                ext_data = parsed["extracted"]
                merged = json.loads(row["content_json"])
                merged["status"] = "published"
                merged["source_note"] = ext_data["source_note"]

                if sections.get("theory") and ext_data["lessons"]:
                    merged["title"] = ext_data["title"] or merged["title"]
                    merged["lessons"] = ext_data["lessons"]
                if sections.get("knowledge"):
                    ks = ext_data["knowledge_system"]
                    if ks.get("mindmap", {}).get("branches") or ks.get("comparison_tables"):
                        merged["knowledge_system"] = ks
                if sections.get("video") and ext_data["interactive_video"].get("scenes"):
                    merged["interactive_video"] = ext_data["interactive_video"]
                if sections.get("review"):
                    rev = ext_data["review"]
                    if replace_review:
                        if rev["mcq"] or rev["true_false"] or rev["short_answer"]:
                            merged["review"] = rev
                    else:
                        merged.setdefault("review", {"mcq": [], "true_false": [], "short_answer": []})
                        merged["review"]["mcq"].extend(rev["mcq"])
                        merged["review"]["true_false"].extend(rev["true_false"])
                        merged["review"]["short_answer"].extend(rev["short_answer"])

                ts = now_iso()
                conn.execute(
                    """
                    UPDATE topics
                    SET title = ?, status = 'published', content_json = ?, updated_by = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (merged["title"], json.dumps(merged, ensure_ascii=False), teacher["id"], ts, tid),
                )
                conn.commit()
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "topic": merged,
                        "stats": parsed["stats"],
                        "message": f"Đã trích xuất và cập nhật 100% dữ liệu từ file '{filename}'!",
                    },
                )

            # Admin: Trộn đề trắc nghiệm theo Ma trận 3x3 & xuất Word (.docx) + Excel (.xlsx)
            if path == "/api/admin/generate-exam":
                teacher = self.require_teacher(conn, qs, body)
                if not teacher:
                    return
                selected_lesson_ids = body.get("selected_lesson_ids") or []
                matrix = body.get("matrix") or {}
                exam_count = max(1, min(30, int(body.get("exam_count") or 1)))
                raw_codes = body.get("exam_codes") or []
                if isinstance(raw_codes, str):
                    raw_codes = [c.strip() for c in re.split(r"[,;\s]+", raw_codes) if c.strip()]
                else:
                    raw_codes = [str(c).strip() for c in raw_codes if str(c).strip()]

                # Đồng bộ danh sách mã đề với số lượng đề trộn
                codes = []
                if raw_codes:
                    codes = list(raw_codes[:exam_count])
                    if len(codes) < exam_count:
                        last_code = codes[-1]
                        if last_code.isdigit():
                            base_num = int(last_code)
                            width = len(last_code)
                            while len(codes) < exam_count:
                                base_num += 1
                                codes.append(str(base_num).zfill(width))
                        else:
                            idx = 1
                            while len(codes) < exam_count:
                                codes.append(f"{last_code}-{idx}")
                                idx += 1
                else:
                    codes = [str(101 + i) for i in range(exam_count)]

                meta = {
                    "title": (body.get("title") or "ĐỀ KIỂM TRA MÔN SINH HỌC 12").strip(),
                    "school_name": (body.get("school_name") or teacher["school_name"] or "TRƯỜNG THPT").strip(),
                    "duration_minutes": max(5, min(180, int(body.get("duration_minutes") or 50))),
                }

                rows = conn.execute("SELECT content_json FROM topics ORDER BY order_index ASC").fetchall()
                topics_data = [json.loads(r["content_json"]) for r in rows]

                try:
                    pkg = generate_shuffled_exam_package(
                        topics_data,
                        selected_lesson_ids,
                        matrix,
                        codes,
                        meta,
                    )
                except Exception as e:
                    return self.send_json(400, {"error": str(e)})

                job_id = secrets.token_urlsafe(12)
                stamp = datetime.now().strftime("%Y%m%d-%H%M")
                EXAM_EXPORTS[job_id] = {
                    "docx": pkg["docx_bytes"],
                    "xlsx": pkg["xlsx_bytes"],
                    "filename_base": f"sinhhoc12-{stamp}",
                    "created_at": now_iso(),
                }
                # Giữ tối đa 20 gói đề gần nhất trong bộ nhớ
                if len(EXAM_EXPORTS) > 20:
                    oldest_key = next(iter(EXAM_EXPORTS.keys()))
                    EXAM_EXPORTS.pop(oldest_key, None)

                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "job_id": job_id,
                        "summary": pkg["summary"],
                    },
                )

            # Admin ONLY: Thêm Giáo viên mới (tên đăng nhập + mật khẩu mặc định 123456@)
            if path == "/api/admin/teachers":
                admin = self.require_admin(conn, qs, body)
                if not admin:
                    return
                uname, err = validate_username(body.get("username") or "")
                if err:
                    return self.send_json(400, {"error": err})
                password = (body.get("password") or DEFAULT_USER_PASSWORD).strip() or DEFAULT_USER_PASSWORD
                exists = conn.execute("SELECT id FROM users WHERE lower(username) = ?", (uname,)).fetchone()
                if exists:
                    return self.send_json(409, {"error": f"Tên đăng nhập '{uname}' đã tồn tại trong hệ thống."})

                ts = now_iso()
                colors = ["#0f766e", "#0369a1", "#4f46e5", "#b45309", "#be123c", "#15803d"]
                avatar_color = colors[sum(ord(c) for c in uname) % len(colors)]
                cur = conn.execute(
                    """
                    INSERT INTO users
                    (username, email, password_hash, full_name, role, class_name, school_name, phone, bio, avatar_color, must_change_password, created_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'teacher', 'Tổ Sinh học', '', '', '', ?, 1, ?, ?, ?)
                    """,
                    (
                        uname,
                        f"{uname}@giaovien.sinhhoc12.local",
                        hash_password(password),
                        f"GV ({uname})",
                        avatar_color,
                        admin["id"],
                        ts,
                        ts,
                    ),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
                return self.send_json(
                    201,
                    {
                        "ok": True,
                        "user": sanitize_user(row),
                        "message": f"Đã tạo tài khoản Giáo viên '{uname}' (mật khẩu mặc định: {password}).",
                    },
                )

            # Admin ONLY: Xoá thành viên (Giáo viên hoặc Học sinh; không được xoá tài khoản Quản trị viên)
            m_del = re.match(r"^/api/admin/users/(\d+)/delete$", path)
            if m_del:
                admin = self.require_admin(conn, qs, body)
                if not admin:
                    return
                uid = int(m_del.group(1))
                target = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
                if not target:
                    return self.send_json(404, {"error": "Không tìm thấy thành viên."})
                if target["role"] == "admin" or target["username"].lower() == ADMIN_USERNAME:
                    return self.send_json(403, {"error": "Không thể xoá tài khoản Quản trị viên."})
                conn.execute("DELETE FROM users WHERE id = ?", (uid,))
                conn.commit()
                return self.send_json(
                    200,
                    {"ok": True, "message": f"Đã xoá tài khoản '{target['username']}' khỏi hệ thống."},
                )

            # Admin ONLY: Đánh dấu đã đọc thông báo đổi mật khẩu
            if path == "/api/admin/password-alerts/mark-read":
                admin = self.require_admin(conn, qs, body)
                if not admin:
                    return
                conn.execute("UPDATE password_change_logs SET is_read = 1 WHERE is_read = 0")
                conn.commit()
                return self.send_json(200, {"ok": True})

            # Admin & Teacher: Thêm Học sinh thủ công (1 hoặc nhiều dòng: tên đăng nhập viết liền không dấu + mật khẩu mặc định 123456@)
            if path == "/api/staff/students":
                staff = self.require_teacher(conn, qs, body)
                if not staff:
                    return
                items = body.get("students")
                if not isinstance(items, list):
                    items = [{"username": body.get("username") or "", "password": body.get("password") or DEFAULT_USER_PASSWORD}]

                created = []
                skipped = []
                errors = []
                ts = now_iso()
                colors = ["#0f766e", "#0369a1", "#4f46e5", "#b45309", "#be123c", "#15803d"]

                for idx, it in enumerate(items, 1):
                    raw_u = (it.get("username") if isinstance(it, dict) else str(it)) or ""
                    raw_p = (it.get("password") if isinstance(it, dict) else "") or DEFAULT_USER_PASSWORD
                    uname, err = validate_username(raw_u)
                    if err:
                        errors.append(f"Dòng {idx}: {err}")
                        continue
                    exists = conn.execute("SELECT id FROM users WHERE lower(username) = ?", (uname,)).fetchone()
                    if exists:
                        skipped.append(uname)
                        continue
                    pwd = raw_p.strip() or DEFAULT_USER_PASSWORD
                    avatar_color = colors[sum(ord(c) for c in uname) % len(colors)]
                    conn.execute(
                        """
                        INSERT INTO users
                        (username, email, password_hash, full_name, role, class_name, school_name, phone, bio, avatar_color, must_change_password, created_by, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 'student', '', '', '', '', ?, 1, ?, ?, ?)
                        """,
                        (
                            uname,
                            f"{uname}@hocsinh.sinhhoc12.local",
                            hash_password(pwd),
                            f"HS ({uname})",
                            avatar_color,
                            staff["id"],
                            ts,
                            ts,
                        ),
                    )
                    created.append(uname)

                conn.commit()
                if not created and errors:
                    return self.send_json(400, {"error": errors[0], "errors": errors, "skipped": skipped})
                if not created and skipped:
                    return self.send_json(409, {"error": f"Tài khoản đã tồn tại: {', '.join(skipped)}", "skipped": skipped})
                return self.send_json(
                    201,
                    {
                        "ok": True,
                        "created_count": len(created),
                        "created_usernames": created,
                        "skipped": skipped,
                        "errors": errors,
                        "message": f"Đã tạo {len(created)} tài khoản học sinh (mật khẩu mặc định: {DEFAULT_USER_PASSWORD}).",
                    },
                )

            # Admin & Teacher: Nhập danh sách Học sinh từ file Excel (.xlsx) hoặc CSV (.csv)
            if path == "/api/staff/students/import-excel":
                staff = self.require_teacher(conn, qs, body)
                if not staff:
                    return
                filename = (body.get("filename") or "").strip()
                content_b64 = body.get("content_base64") or ""
                if not filename or not content_b64:
                    return self.send_json(400, {"error": "Vui lòng chọn file Excel (.xlsx) hoặc CSV."})
                try:
                    raw_bytes = base64.b64decode(content_b64)
                    rows = parse_students_from_file(raw_bytes, filename)
                except Exception as e:
                    return self.send_json(400, {"error": f"Không thể đọc file Excel: {e}"})

                if not rows:
                    return self.send_json(400, {"error": "Không tìm thấy dòng học sinh nào trong file."})

                created = []
                skipped = []
                errors = []
                ts = now_iso()
                colors = ["#0f766e", "#0369a1", "#4f46e5", "#b45309", "#be123c", "#15803d"]

                for item in rows:
                    uname, err = validate_username(item["username"])
                    if err:
                        errors.append(f"Dòng {item['row_num']}: {err}")
                        continue
                    exists = conn.execute("SELECT id FROM users WHERE lower(username) = ?", (uname,)).fetchone()
                    if exists:
                        skipped.append(uname)
                        continue
                    pwd = (item.get("password") or DEFAULT_USER_PASSWORD).strip() or DEFAULT_USER_PASSWORD
                    avatar_color = colors[sum(ord(c) for c in uname) % len(colors)]
                    conn.execute(
                        """
                        INSERT INTO users
                        (username, email, password_hash, full_name, role, class_name, school_name, phone, bio, avatar_color, must_change_password, created_by, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 'student', '', '', '', '', ?, 1, ?, ?, ?)
                        """,
                        (
                            uname,
                            f"{uname}@hocsinh.sinhhoc12.local",
                            hash_password(pwd),
                            f"HS ({uname})",
                            avatar_color,
                            staff["id"],
                            ts,
                            ts,
                        ),
                    )
                    created.append(uname)

                conn.commit()
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "created_count": len(created),
                        "created_usernames": created,
                        "skipped": skipped,
                        "errors": errors,
                        "message": f"Đã nhập thành công {len(created)} học sinh từ '{filename}' (bỏ qua {len(skipped)} trùng, {len(errors)} lỗi).",
                    },
                )

            return self.send_json(404, {"error": "API endpoint không tồn tại."})
        finally:
            conn.close()

    # ---------------------- PUT ROUTES ----------------------
    def do_PUT(self):
        parsed = urlparse(self.path)
        path = strip_base_path(parsed.path)
        qs = parse_qs(parsed.query)
        body = self.read_json_body()

        conn = get_conn()
        try:
            # Update user profile (Student or Teacher)
            if path == "/api/profile":
                user = self.require_user(conn, qs, body)
                if not user:
                    return

                full_name = (body.get("full_name") or user["full_name"]).strip()
                email = (body.get("email") or user["email"]).strip().lower()
                class_name = (body.get("class_name") if "class_name" in body else user["class_name"]).strip()
                school_name = (body.get("school_name") if "school_name" in body else user["school_name"]).strip()
                phone = (body.get("phone") if "phone" in body else user["phone"]).strip()
                bio = (body.get("bio") if "bio" in body else user["bio"]).strip()
                avatar_color = (body.get("avatar_color") or user["avatar_color"]).strip()

                # Check email uniqueness
                dup = conn.execute(
                    "SELECT id FROM users WHERE lower(email) = ? AND id != ?", (email, user["id"])
                ).fetchone()
                if dup:
                    return self.send_json(409, {"error": "Email này đã được sử dụng bởi tài khoản khác."})

                # Optional password update
                new_password = body.get("new_password") or ""
                current_password = body.get("current_password") or ""
                password_hash = user["password_hash"]
                if new_password:
                    if len(new_password) < 4:
                        return self.send_json(400, {"error": "Mật khẩu mới cần tối thiểu 4 ký tự."})
                    if not verify_password(current_password, user["password_hash"]):
                        return self.send_json(400, {"error": "Mật khẩu hiện tại không đúng."})
                    password_hash = hash_password(new_password)

                ts = now_iso()
                conn.execute(
                    """
                    UPDATE users
                    SET full_name = ?, email = ?, class_name = ?, school_name = ?,
                        phone = ?, bio = ?, avatar_color = ?, password_hash = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        full_name,
                        email,
                        class_name,
                        school_name,
                        phone,
                        bio,
                        avatar_color,
                        password_hash,
                        ts,
                        user["id"],
                    ),
                )
                conn.commit()
                updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
                if new_password and updated["role"] in ("teacher", "student"):
                    record_password_change(conn, updated, reason="profile_change")
                return self.send_json(200, {"user": sanitize_user(updated), "message": "Đã cập nhật hồ sơ thành công!"})

            # Teacher: Update topic content (lessons, interactive video, knowledge system, quiz bank)
            m = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)$", path)
            if m:
                teacher = self.require_teacher(conn, qs, body)
                if not teacher:
                    return
                tid = m.group(1)
                row = conn.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy chủ đề."})

                content = body.get("content")
                if not isinstance(content, dict):
                    return self.send_json(400, {"error": "Dữ liệu chủ đề không hợp lệ."})

                content["id"] = tid
                title = (content.get("title") or row["title"]).strip()
                subtitle = (content.get("subtitle") or row["subtitle"]).strip()
                status = content.get("status") or row["status"]
                ts = now_iso()

                conn.execute(
                    """
                    UPDATE topics
                    SET title = ?, subtitle = ?, status = ?, content_json = ?, updated_by = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (title, subtitle, status, json.dumps(content, ensure_ascii=False), teacher["id"], ts, tid),
                )
                conn.commit()
                return self.send_json(200, {"ok": True, "topic": content, "updated_at": ts})

            return self.send_json(404, {"error": "API endpoint không tồn tại."})
        finally:
            conn.close()

    # ---------------------- STATIC FILE SERVING ----------------------
    def serve_static(self, path):
        if path == "/" or path == "":
            rel = "index.html"
        else:
            rel = path.lstrip("/")

        safe_path = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not safe_path.startswith(os.path.abspath(STATIC_DIR)):
            self.send_error(403, "Forbidden")
            return

        if not os.path.isfile(safe_path):
            # SPA fallback to index.html for non-asset paths
            if "." not in os.path.basename(rel):
                safe_path = os.path.join(STATIC_DIR, "index.html")
            else:
                self.send_error(404, "Not Found")
                return

        mime, _ = mimetypes.guess_type(safe_path)
        if not mime:
            mime = "application/octet-stream"
        if mime.startswith("text/") or mime in ("application/javascript", "application/json", "image/svg+xml"):
            mime = f"{mime}; charset=utf-8"

        try:
            with open(safe_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, str(e))


def main():
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Bio12Handler)
    port_suffix = "" if PORT == 80 else f":{PORT}"
    print(f"============================================================")
    print(f"  WEB APP GIẢNG DẠY SINH HỌC 12 (CT GDPT 2018)")
    print(f"  Địa chỉ nội bộ:   http://localhost{port_suffix}{BASE_PATH}")
    print(f"  Địa chỉ tên miền: http://{PUBLIC_HOST}{port_suffix}{BASE_PATH}")
    print(f"  Cơ sở dữ liệu:    data/sinhhoc12.db")
    print(f"  Mã đăng ký Giáo viên mặc định: {TEACHER_INVITE_CODE}")
    print(f"============================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng máy chủ.")
        server.server_close()


if __name__ == "__main__":
    main()
