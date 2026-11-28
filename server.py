#!/usr/bin/env python3
"""
Web App Giảng dạy Sinh học 12 (CT GDPT 2018)
Backend Server (Python 3 stdlib + SQLite) — Không cần cài đặt thư viện ngoài.
Chạy lệnh: python3 server.py
"""
import base64
import errno
import gzip
import hashlib
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import traceback
import unicodedata
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from database import (
    ADMIN_USERNAME,
    DB_BACKEND,
    DB_LOCK,
    DEFAULT_USER_PASSWORD,
    TEACHER_INVITE_CODE,
    build_curriculum_catalog,
    build_student_learning_report,
    create_token,
    describe_db,
    export_learning_analytics_csv,
    export_sessions_csv,
    get_conn,
    get_user_by_token,
    hash_password,
    init_db,
    invalidate_token_cache,
    now_iso,
    now_vn,
    parse_quiz_attempt_enriched,
    parse_vn_datetime,
    record_login,
    record_password_change,
    sanitize_user,
    to_vn_iso,
    upsert_exercise_record,
    upsert_lesson_progress,
    upsert_theory_read,
    upsert_topic,
    verify_password,
)
from cache_layer import app_cache
from content_standardizer import apply_answer_pdf_to_topic, discover_reference_pdfs, standardize_topic_content
from exam_generator import (
    build_exam_pool_summary,
    generate_shuffled_exam_from_content,
    generate_shuffled_exam_package,
    normalize_exam_codes,
)
from importer import build_sample_docx_template, cleanup_topic_uploads, parse_document_to_topic
from mock_exam_parser import (
    compute_exam_max_score,
    grade_mock_exam_submission,
    parse_mock_exam_document,
)
from student_excel import (
    build_student_import_template_xlsx,
    parse_students_from_file,
    validate_username,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
PORT = int(os.environ.get("PORT", "8080"))
_raw_base = os.environ.get("BASE_PATH", "sinhhoc12").strip("/")
BASE_PATH = f"/{_raw_base}" if _raw_base else "/"
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "lms.bachanhtu")
EXTRA_UPLOADS_DIR = os.environ.get("UPLOADS_DIR", "").strip()
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", str(100 * 1024 * 1024)))


class _PayloadTooLargeError(Exception):
    pass


class _IncompleteUploadError(Exception):
    pass

# Bộ nhớ tạm lưu các gói đề trộn (.docx + .xlsx) vừa tạo để tải xuống nhanh
EXAM_EXPORTS = {}

_BANNER_PREFIX = "banner_"
_MAX_BANNER_BYTES = 8 * 1024 * 1024


def _detect_banner_ext(file_bytes: bytes, filename: str = "") -> str:
    """Kiểm tra magic bytes của ảnh banner hợp lệ (.png, .jpg, .webp, .gif)."""
    if not file_bytes or len(file_bytes) < 12:
        return ""
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return ".webp"
    if file_bytes.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    return ""


def _topic_uploads_dirs(topic_id: str) -> list[str]:
    dirs = []
    if EXTRA_UPLOADS_DIR:
        dirs.append(os.path.join(EXTRA_UPLOADS_DIR, topic_id))
    static_dir = os.path.join(STATIC_DIR, "uploads", topic_id)
    if static_dir not in dirs:
        dirs.append(static_dir)
    return dirs


def _remove_topic_banner_files(topic_id: str) -> int:
    """Xoá mọi file banner cũ của chủ đề để mỗi chủ đề chỉ lưu duy nhất 1 ảnh banner."""
    removed = 0
    for d in _topic_uploads_dirs(topic_id):
        if not os.path.isdir(d):
            continue
        try:
            for fn in os.listdir(d):
                if fn.startswith(_BANNER_PREFIX):
                    try:
                        os.remove(os.path.join(d, fn))
                        removed += 1
                    except OSError:
                        pass
        except OSError:
            pass
    return removed


def _save_topic_banner_file(topic_id: str, file_bytes: bytes, filename: str = "") -> str:
    """Lưu duy nhất 1 ảnh banner cho chủ đề (tự xoá ảnh banner cũ trước khi ghi)."""
    if not file_bytes:
        raise ValueError("Tệp ảnh banner trống.")
    if len(file_bytes) > _MAX_BANNER_BYTES:
        raise ValueError("Ảnh banner vượt quá giới hạn 8 MB.")
    ext = _detect_banner_ext(file_bytes, filename)
    if not ext:
        raise ValueError("Định dạng ảnh không hợp lệ (chỉ hỗ trợ PNG, JPG, WebP, GIF).")
    _remove_topic_banner_files(topic_id)
    root_dir = EXTRA_UPLOADS_DIR or os.path.join(STATIC_DIR, "uploads")
    target_dir = os.path.join(root_dir, topic_id)
    os.makedirs(target_dir, exist_ok=True)
    digest = hashlib.sha1(file_bytes).hexdigest()[:10]
    fname = f"{_BANNER_PREFIX}{digest}{ext}"
    with open(os.path.join(target_dir, fname), "wb") as f:
        f.write(file_bytes)
    return f"/uploads/{topic_id}/{fname}"


def _extract_banner_from_json(content_json: str) -> str:
    if not content_json:
        return ""
    try:
        obj = json.loads(content_json)
        val = obj.get("banner_image") if isinstance(obj, dict) else ""
        return str(val or "").strip()
    except Exception:
        return ""


def _find_sample_exams_dir() -> str:
    """Tìm thư mục 'FILE ĐỀ MẪU' (hỗ trợ cả Unicode NFC/NFD, chữ đ/Đ, dấu cách thừa, hoặc nằm trong data/)."""
    candidates = [BASE_DIR, os.path.join(BASE_DIR, "data")]
    for root in candidates:
        if not os.path.isdir(root):
            continue
        try:
            for entry in os.listdir(root):
                full = os.path.join(root, entry)
                if os.path.isdir(full):
                    norm = unicodedata.normalize("NFC", entry).strip().lower()
                    no_d = norm.replace("đ", "d")
                    ascii_norm = re.sub(
                        r"\s+",
                        " ",
                        unicodedata.normalize("NFKD", no_d).encode("ascii", "ignore").decode("ascii"),
                    ).strip()
                    if "đề mẫu" in norm or "de mau" in ascii_norm or "de_mau" in ascii_norm or "mau" in ascii_norm and "de" in ascii_norm:
                        return full
        except Exception:
            continue
    return ""


def _list_sample_exam_files() -> list:
    sdir = _find_sample_exams_dir()
    if not sdir:
        return []
    out = []
    abs_sdir = os.path.abspath(sdir)
    try:
        for dirpath, dirnames, filenames in os.walk(abs_sdir):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__MACOSX")
            for fn in sorted(filenames):
                if fn.startswith(".") or fn.startswith("~$"):
                    continue
                if not fn.lower().endswith(".docx"):
                    continue
                fpath = os.path.join(dirpath, fn)
                if not os.path.isfile(fpath):
                    continue
                rel = os.path.relpath(fpath, abs_sdir).replace("\\", "/")
                rel_nfc = unicodedata.normalize("NFC", rel)
                sz_kb = round(os.path.getsize(fpath) / 1024.0, 1)
                out.append({"filename": rel_nfc, "raw_name": rel, "size_kb": sz_kb})
    except Exception:
        return []
    return out


def _resolve_sample_exam_path(requested_name: str) -> str:
    sdir = _find_sample_exams_dir()
    if not sdir or not requested_name:
        return ""
    abs_sdir = os.path.abspath(sdir)
    req_norm = unicodedata.normalize("NFC", requested_name.replace("\\", "/")).strip().lstrip("/")
    if ".." in req_norm.split("/"):
        return ""
    for item in _list_sample_exam_files():
        if item["filename"] == req_norm or os.path.basename(item["filename"]) == os.path.basename(req_norm):
            fpath = os.path.abspath(os.path.join(abs_sdir, item["raw_name"]))
            if os.path.commonpath([fpath, abs_sdir]) == abs_sdir and os.path.isfile(fpath):
                return fpath
    return ""

# Bộ nhớ đệm tĩnh trong RAM cho CSS/JS/HTML/ảnh nhỏ (tránh đọc ổ đĩa liên tục khi lớp đông học sinh)
_STATIC_CACHE_LOCK = threading.Lock()
_STATIC_CACHE = OrderedDict()  # path -> (mtime, size, raw_bytes, gz_bytes, etag, mime)
_STATIC_CACHE_MAX_BYTES = 24 * 1024 * 1024
_STATIC_CACHE_TOTAL = 0


def _get_cached_static(safe_path: str, mime: str):
    global _STATIC_CACHE_TOTAL
    st = os.stat(safe_path)
    mtime, size = st.st_mtime, st.st_size
    with _STATIC_CACHE_LOCK:
        entry = _STATIC_CACHE.get(safe_path)
        if entry and entry[0] == mtime and entry[1] == size:
            _STATIC_CACHE.move_to_end(safe_path)
            return entry[2], entry[3], entry[4], entry[5]

    with open(safe_path, "rb") as f:
        raw = f.read()
    etag = f'W/"{hashlib.sha1(f"{mtime}:{size}".encode()).hexdigest()[:14]}"'
    compressible = (
        mime.startswith("text/")
        or "javascript" in mime
        or "json" in mime
        or "svg" in mime
    )
    gz = gzip.compress(raw, compresslevel=6) if (compressible and len(raw) >= 512) else b""

    if size <= 1024 * 1024:
        with _STATIC_CACHE_LOCK:
            old = _STATIC_CACHE.pop(safe_path, None)
            if old:
                _STATIC_CACHE_TOTAL -= len(old[2]) + len(old[3])
            _STATIC_CACHE[safe_path] = (mtime, size, raw, gz, etag, mime)
            _STATIC_CACHE_TOTAL += len(raw) + len(gz)
            while _STATIC_CACHE_TOTAL > _STATIC_CACHE_MAX_BYTES and _STATIC_CACHE:
                _, evicted = _STATIC_CACHE.popitem(last=False)
                _STATIC_CACHE_TOTAL -= len(evicted[2]) + len(evicted[3])

    return raw, gz, etag, mime


def strip_base_path(path: str) -> str:
    """Hỗ trợ truy cập cả ở /sinhhoc12/... lẫn /..."""
    if BASE_PATH and BASE_PATH != "/":
        if path == BASE_PATH:
            return "/"
        if path.startswith(BASE_PATH + "/"):
            return path[len(BASE_PATH) :]
    return path


def parse_iso_seconds(ts: str):
    return parse_vn_datetime(ts)


def calc_duration_seconds(enter_time: str, end_time: str) -> int:
    t1 = parse_iso_seconds(enter_time)
    t2 = parse_iso_seconds(end_time)
    if not t1 or not t2:
        return 0
    return max(0, int((t2 - t1).total_seconds()))


class Bio12Handler(BaseHTTPRequestHandler):
    server_version = "SinhHoc12WebApp/1.0"

    def setup(self):
        super().setup()
        try:
            self.request.settimeout(60.0)
        except Exception:
            pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except OSError as exc:
            if getattr(exc, "errno", None) in (
                errno.EBADF,
                errno.ECONNRESET,
                errno.EPIPE,
                errno.ENOTCONN,
            ):
                self.close_connection = True
                return
            raise

    def log_message(self, fmt, *args):
        sys.stdout.write(f"[{now_vn().strftime('%H:%M:%S')}] {self.address_string()} - {fmt % args}\n")
        sys.stdout.flush()

    def _client_accepts_gzip(self) -> bool:
        ae = (self.headers.get("Accept-Encoding") or "").lower()
        return "gzip" in ae

    def _safe_write(self, data: bytes):
        if not data:
            return
        mv = memoryview(data)
        chunk_size = 65536
        try:
            for offset in range(0, len(mv), chunk_size):
                self.wfile.write(mv[offset : offset + chunk_size])
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            pass

    def send_json(self, status: int, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        use_gz = self._client_accepts_gzip() and len(payload) >= 1024
        body = gzip.compress(payload, compresslevel=5) if use_gz else payload
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if use_gz:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, If-None-Match")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, HEAD")
        self.end_headers()
        if self.command != "HEAD":
            self._safe_write(body)

    def send_cached_json(self, cache_key: str, builder_fn, ttl: int = 300):
        """Phục vụ JSON qua bộ nhớ đệm đa tầng L1 + Redis kèm Gzip dựng sẵn & HTTP ETag (304)."""
        payload, gz_payload, etag, source = app_cache.get_payload_with_gzip(cache_key)
        if payload is None:
            data = builder_fn()
            if data is None:
                return False
            payload, gz_payload, etag = app_cache.set_json_with_gzip(cache_key, data, ttl=ttl)
            source = "MISS"

        req_etag = (self.headers.get("If-None-Match") or "").strip()
        if req_etag and etag and req_etag == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("X-Cache", source)
            self.send_header("Cache-Control", "private, max-age=0, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return True

        use_gz = self._client_accepts_gzip() and bool(gz_payload)
        body = gz_payload if use_gz else payload
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if use_gz:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        self.send_header("X-Cache", source)
        self.send_header("Cache-Control", "private, max-age=0, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, If-None-Match")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, HEAD")
        self.end_headers()
        if self.command != "HEAD":
            self._safe_write(body)
        return True

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
        self._safe_write(payload)

    def read_raw_body(self) -> bytes:
        chunk_size = 65536
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            buf = bytearray()
            while True:
                line = self.rfile.readline(256)
                if not line:
                    break
                size_hex = line.split(b";", 1)[0].strip()
                if not size_hex:
                    continue
                sz = int(size_hex, 16)
                if sz == 0:
                    while True:
                        tr = self.rfile.readline(256)
                        if not tr or tr in (b"\r\n", b"\n"):
                            break
                    break
                if len(buf) + sz > MAX_BODY_BYTES:
                    raise _PayloadTooLargeError()
                rem = sz
                while rem > 0:
                    piece = self.rfile.read(min(rem, chunk_size))
                    if not piece:
                        break
                    buf.extend(piece)
                    rem -= len(piece)
                # Tiêu thụ CRLF kết thúc chunk
                self.rfile.readline(4)
            return bytes(buf)

        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return b""
        if length > MAX_BODY_BYTES:
            raise _PayloadTooLargeError()
        buf = bytearray()
        remaining = length
        while remaining > 0:
            piece = self.rfile.read(min(remaining, chunk_size))
            if not piece:
                break
            buf.extend(piece)
            remaining -= len(piece)
        if remaining > 0:
            raise _IncompleteUploadError(
                f"Tải file bị gián đoạn giữa chừng (thiếu {remaining} bytes). Vui lòng thử lại."
            )
        return bytes(buf)

    def read_json_body(self):
        raw = self.read_raw_body()
        if not raw:
            return {}
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

    def do_HEAD(self):
        return self.do_GET()

    # ---------------------- GET ROUTES ----------------------
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            raw_path = parsed.path
            qs = parse_qs(parsed.query)

            # Chuyển hướng gọn /sinhhoc12 -> /sinhhoc12/ để các tệp tĩnh tương đối hoạt động chuẩn
            if BASE_PATH != "/" and raw_path == BASE_PATH:
                self.send_response(302)
                self.send_header("Location", BASE_PATH + "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            path = strip_base_path(raw_path)

            if path.startswith("/api/"):
                return self.handle_api_get(path, qs)
            return self.serve_static(path, raw_path=raw_path)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except Exception as e:
            traceback.print_exc()
            try:
                self.send_json(500, {"error": f"Hệ thống đang bận, vui lòng thử lại ({type(e).__name__})."})
            except Exception:
                pass

    def handle_api_get(self, path, qs):
        # 1. Các route KHÔNG cần mở SQLite khi đã có sẵn trong L1 RAM Cache (tốc độ < 1ms, không khóa DB)
        if path == "/api/health":
            return self.send_json(
                200,
                {"ok": True, "time": now_iso(), "app": "Sinh học 12", "db": DB_BACKEND},
            )

        if path == "/api/topics":
            def _load_topics_list():
                c = get_conn()
                try:
                    rows = c.execute(
                        "SELECT id, order_index, title, subtitle, status, content_json, updated_at FROM topics ORDER BY order_index ASC"
                    ).fetchall()
                    return {
                        "topics": [
                            {
                                "id": r["id"],
                                "order_index": r["order_index"],
                                "title": r["title"],
                                "subtitle": r["subtitle"],
                                "status": r["status"],
                                "updated_at": r["updated_at"],
                                "banner_image": _extract_banner_from_json(r["content_json"]),
                            }
                            for r in rows
                        ]
                    }
                finally:
                    c.close()

            self.send_cached_json("topics:list", _load_topics_list, ttl=600)
            return

        m_topic = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)$", path)
        if m_topic:
            tid = m_topic.group(1)

            def _load_topic_detail():
                c = get_conn()
                try:
                    row = c.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
                    if not row:
                        return None
                    content = json.loads(row["content_json"])
                    content["updated_at"] = row["updated_at"]
                    return {"topic": content}
                finally:
                    c.close()

            found = self.send_cached_json(f"topic:{tid}", _load_topic_detail, ttl=900)
            if not found:
                return self.send_json(404, {"error": "Không tìm thấy chủ đề."})
            return

        conn = get_conn()
        try:
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

                # Auto-close stale sessions whose last heartbeat was > 10 minutes ago (múi giờ Việt Nam +07:00)
                cutoff = now_vn().timestamp() - 600
                active_rows = conn.execute("SELECT * FROM study_sessions WHERE status = 'active'").fetchall()
                stale_updates = []
                for ar in active_rows:
                    hb = parse_iso_seconds(ar["last_heartbeat"])
                    if hb and hb.timestamp() < cutoff:
                        dur = calc_duration_seconds(ar["enter_time"], ar["last_heartbeat"])
                        stale_updates.append((ar["last_heartbeat"], dur, ar["id"]))
                if stale_updates:
                    with DB_LOCK:
                        for hb_ts, dur, sid in stale_updates:
                            conn.execute(
                                "UPDATE study_sessions SET status = 'completed', leave_time = ?, duration_seconds = ? WHERE id = ?",
                                (hb_ts, dur, sid),
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

                attempts_asc = conn.execute(
                    """
                    SELECT a.*, u.full_name, u.username, u.class_name
                    FROM quiz_attempts a
                    JOIN users u ON u.id = a.user_id
                    ORDER BY a.submitted_at ASC, a.id ASC
                    """
                ).fetchall()

                catalog = build_curriculum_catalog(conn)
                topic_title_map = catalog["topic_title_map"]

                # Đánh số đợt làm bài (Đợt #1, Đợt #2...) chính xác theo từng học sinh
                round_counter = {}
                enriched_attempts_asc = []
                attempts_by_user = {}
                for ar in attempts_asc:
                    uid = ar["user_id"]
                    round_counter[uid] = round_counter.get(uid, 0) + 1
                    item = parse_quiz_attempt_enriched(dict(ar), topic_title_map, round_number=round_counter[uid])
                    enriched_attempts_asc.append(item)
                    attempts_by_user.setdefault(uid, []).append(item)
                enriched_attempts_desc = list(reversed(enriched_attempts_asc))

                # Tải tiến độ đọc mục lý thuyết & bài tập vận dụng (không N+1)
                lp_rows = conn.execute(
                    "SELECT user_id, lesson_id, completed FROM lesson_progress WHERE completed = 1"
                ).fetchall()
                lp_done_by_user = {}
                for r in lp_rows:
                    lp_done_by_user.setdefault(r["user_id"], set()).add(r["lesson_id"])

                tr_rows = conn.execute(
                    "SELECT user_id, lesson_id, section_key FROM student_theory_reads WHERE completed = 1"
                ).fetchall()
                reads_by_user = {}
                for r in tr_rows:
                    reads_by_user.setdefault(r["user_id"], {}).setdefault(r["lesson_id"], set()).add(r["section_key"])

                ex_rows = conn.execute(
                    "SELECT user_id, correct_count, total_items, accuracy_pct FROM student_exercise_records"
                ).fetchall()
                ex_by_user = {}
                for r in ex_rows:
                    ex_by_user.setdefault(r["user_id"], []).append(dict(r))

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

                # Aggregate per-student stats (tiến độ lý thuyết, bài tập LT/HTKT, và từng đợt Hệ thống ôn tập)
                student_list = []
                total_catalog_lessons = catalog["total_lessons"]
                total_catalog_sections = catalog["total_sections"]
                total_catalog_ex = catalog["total_exercise_units"]

                for st in students:
                    uid = st["id"]
                    st_sessions = [s for s in sessions if s["user_id"] == uid]
                    st_attempts = attempts_by_user.get(uid, [])
                    total_sec = sum((s["duration_seconds"] or 0) for s in st_sessions)
                    is_online = any(s["status"] == "active" for s in st_sessions)

                    # Tính chính xác % Lý thuyết đã học (đồng nhất 100% với build_student_learning_report)
                    done_ls_set = lp_done_by_user.get(uid, set())
                    u_reads = reads_by_user.get(uid, {})
                    studied_lessons = 0
                    studied_sections = 0
                    for tp in catalog["topics"]:
                        for ls in tp["lessons"]:
                            lid = ls["id"]
                            secs = ls["sections"]
                            if lid in done_ls_set:
                                studied_lessons += 1
                                studied_sections += len(secs)
                            else:
                                rset = u_reads.get(lid, set())
                                c_sec = sum(1 for sc in secs if sc["key"] in rset)
                                studied_sections += c_sec
                                if c_sec > 0:
                                    studied_lessons += 1
                    theory_pct = round(studied_sections * 100.0 / total_catalog_sections, 1) if total_catalog_sections > 0 else 0.0

                    # Tính chính xác % Bài tập vận dụng LT & HTKT
                    u_ex = ex_by_user.get(uid, [])
                    ex_done = len(u_ex)
                    ex_completion_pct = round(ex_done * 100.0 / total_catalog_ex, 1) if total_catalog_ex > 0 else 0.0
                    ex_corr = sum(int(e["correct_count"] or 0) for e in u_ex)
                    ex_tot = sum(int(e["total_items"] or 0) for e in u_ex)
                    ex_accuracy_pct = round(ex_corr * 100.0 / ex_tot, 1) if ex_tot > 0 else None

                    # Tính chính xác kết quả Hệ thống ôn tập qua các đợt
                    rev_corr = sum(int(a["correct_count"] or 0) for a in st_attempts)
                    rev_tot = sum(int(a["total_questions"] or 0) for a in st_attempts)
                    rev_accuracy_pct = round(rev_corr * 100.0 / rev_tot, 1) if rev_tot > 0 else None
                    avg_pct = 0.0
                    if st_attempts:
                        avg_pct = round(
                            sum(a["score_pct"] for a in st_attempts) / len(st_attempts),
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
                            "studied_lessons": studied_lessons,
                            "total_lessons": total_catalog_lessons,
                            "studied_sections": studied_sections,
                            "total_sections": total_catalog_sections,
                            "theory_pct": theory_pct,
                            "exercises_done": ex_done,
                            "exercises_total": total_catalog_ex,
                            "exercise_completion_pct": ex_completion_pct,
                            "exercise_correct": ex_corr,
                            "exercise_items_total": ex_tot,
                            "exercise_accuracy_pct": ex_accuracy_pct,
                            "review_rounds_count": len(st_attempts),
                            "review_correct_total": rev_corr,
                            "review_questions_total": rev_tot,
                            "review_accuracy_pct": rev_accuracy_pct,
                            "last_enter": st_sessions[0]["enter_time"] if st_sessions else None,
                            "last_leave": st_sessions[0]["leave_time"] if st_sessions else None,
                        }
                    )
                    student_list.append(item)

                online_count = sum(1 for s in student_list if s["is_online"])
                total_study_minutes = round(sum(s["total_seconds"] for s in student_list) / 60.0, 1)
                total_student_logins = sum(s["login_count"] for s in student_list)
                avg_theory_pct = round(sum(s["theory_pct"] for s in student_list) / len(student_list), 1) if student_list else 0.0
                avg_ex_comp_pct = round(sum(s["exercise_completion_pct"] for s in student_list) / len(student_list), 1) if student_list else 0.0
                ex_accs = [s["exercise_accuracy_pct"] for s in student_list if s["exercise_accuracy_pct"] is not None]
                avg_ex_acc_pct = round(sum(ex_accs) / len(ex_accs), 1) if ex_accs else None
                rev_accs = [a["accuracy_pct"] for a in enriched_attempts_asc if a.get("total_questions", 0) > 0]
                avg_rev_acc_pct = round(sum(rev_accs) / len(rev_accs), 1) if rev_accs else None

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
                            "total_attempts": len(enriched_attempts_desc),
                            "total_study_minutes": total_study_minutes,
                            "unread_password_changes": unread_pw,
                            "avg_theory_pct": avg_theory_pct,
                            "avg_exercise_completion_pct": avg_ex_comp_pct,
                            "avg_exercise_accuracy_pct": avg_ex_acc_pct,
                            "avg_review_accuracy_pct": avg_rev_acc_pct,
                        },
                        "curriculum_summary": {
                            "total_topics": catalog["total_topics"],
                            "total_lessons": catalog["total_lessons"],
                            "total_sections": catalog["total_sections"],
                            "total_exercise_units": catalog["total_exercise_units"],
                            "topics": [
                                {"id": t["id"], "title": t["title"], "order_index": t["order_index"]}
                                for t in catalog["topics"]
                            ],
                        },
                        "students": student_list,
                        "teachers": [sanitize_user(t) for t in teachers],
                        "sessions": [dict(s) for s in sessions],
                        "login_logs": [dict(l) for l in login_logs],
                        "attempts": enriched_attempts_desc[:200],
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
                    self._safe_write(xlsx_bytes)
                    return
                except Exception as e:
                    return self.send_json(500, {"error": f"Không thể tạo file Excel mẫu: {e}"})

            if path == "/api/admin/exam-pool":
                teacher = self.require_teacher(conn, qs)
                if not teacher:
                    return

                def _load_exam_pool():
                    rows = conn.execute("SELECT content_json FROM topics ORDER BY order_index ASC").fetchall()
                    topics_data = [json.loads(r["content_json"]) for r in rows]
                    return {"topics": build_exam_pool_summary(topics_data)}

                self.send_cached_json("admin:exam_pool", _load_exam_pool, ttl=300)
                return

            if path == "/api/admin/cache-status":
                teacher = self.require_teacher(conn, qs)
                if not teacher:
                    return
                return self.send_json(200, {"ok": True, "cache": app_cache.stats()})

            if path == "/api/staff/reference-status":
                staff = self.require_teacher(conn, qs)
                if not staff:
                    return
                refs = discover_reference_pdfs()
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "sgk_pdfs": [os.path.basename(p) for p in refs["sgk_pdfs"]],
                        "answer_pdfs": [os.path.basename(p) for p in refs["answer_pdfs"]],
                    },
                )

            if path == "/api/staff/exam-mixer/sample-files":
                staff = self.require_teacher(conn, qs)
                if not staff:
                    return
                sdir = _find_sample_exams_dir()
                files = [{"filename": f["filename"], "size_kb": f["size_kb"]} for f in _list_sample_exam_files()]
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "dir_found": bool(sdir),
                        "dir_name": unicodedata.normalize("NFC", os.path.basename(sdir)) if sdir else "",
                        "files": files,
                    },
                )

            if path == "/api/staff/exam-mixer/sample-files/download":
                staff = self.require_teacher(conn, qs)
                if not staff:
                    return
                fname = (qs.get("filename", [""])[0] or "").strip()
                fpath = _resolve_sample_exam_path(fname)
                if not fpath:
                    return self.send_json(404, {"error": "Không tìm thấy tệp đề mẫu trong thư mục FILE ĐỀ MẪU."})
                with open(fpath, "rb") as f:
                    raw_bytes = f.read()
                safe_dl = re.sub(r"[^a-zA-Z0-9._-]+", "_", unicodedata.normalize("NFKD", os.path.basename(fpath)).encode("ascii", "ignore").decode("ascii")) or "de-mau.docx"
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                self.send_header("Content-Length", str(len(raw_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Disposition", f'attachment; filename="{safe_dl}"')
                self.end_headers()
                self._safe_write(raw_bytes)
                return

            m_ex_dl = re.match(r"^/api/admin/exam-download/([a-zA-Z0-9_-]+)/(zip|docx|xlsx|file)$", path)
            if m_ex_dl:
                teacher = self.require_teacher(conn, qs)
                if not teacher:
                    return
                job_id, fmt = m_ex_dl.group(1), m_ex_dl.group(2)
                pkg = EXAM_EXPORTS.get(job_id)
                if not pkg:
                    return self.send_json(404, {"error": "File đề trộn đã hết hạn, vui lòng nhấn Tạo & Trộn đề lại."})
                if fmt == "zip":
                    raw_bytes = pkg.get("zip")
                    if not raw_bytes:
                        return self.send_json(404, {"error": "Không tìm thấy gói nén (.zip), vui lòng trộn lại đề."})
                    ctype = "application/zip"
                    fname = f"{pkg['filename_base']}-tron-bo.zip"
                elif fmt == "file":
                    req_name = (qs.get("name", [""])[0] or "").strip()
                    indiv = pkg.get("individual_files") or {}
                    if not req_name or req_name not in indiv:
                        return self.send_json(404, {"error": "Không tìm thấy tệp đề yêu cầu."})
                    raw_bytes = indiv[req_name]
                    if req_name.lower().endswith(".xlsx"):
                        ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    else:
                        ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    fname = req_name
                elif fmt == "docx":
                    raw_bytes = pkg["docx"]
                    ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    fname = f"{pkg['filename_base']}-de-tron.docx"
                else:
                    raw_bytes = pkg["xlsx"]
                    ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    fname = f"{pkg['filename_base']}-dap-an.xlsx"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.end_headers()
                self._safe_write(raw_bytes)
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

            if path == "/api/my/learning-report":
                user = self.require_user(conn, qs)
                if not user:
                    return
                rep = build_student_learning_report(conn, user["id"])
                return self.send_json(200, rep)

            m_st_rep = re.match(r"^/api/staff/students/(\d+)/learning-report$", path)
            if m_st_rep:
                staff = self.require_teacher(conn, qs)
                if not staff:
                    return
                uid = int(m_st_rep.group(1))
                rep = build_student_learning_report(conn, uid)
                if not rep:
                    return self.send_json(404, {"error": "Không tìm thấy học sinh."})
                return self.send_json(200, rep)

            m_qa_one = re.match(r"^/api/staff/quiz-attempts/(\d+)$", path)
            if m_qa_one:
                user = self.require_user(conn, qs)
                if not user:
                    return
                att_id = int(m_qa_one.group(1))
                row = conn.execute(
                    """
                    SELECT a.*, u.full_name, u.username, u.class_name, u.school_name
                    FROM quiz_attempts a
                    JOIN users u ON u.id = a.user_id
                    WHERE a.id = ?
                    """,
                    (att_id,),
                ).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy đợt làm bài này."})
                if row["user_id"] != user["id"] and user["role"] not in ("admin", "teacher"):
                    return self.send_json(403, {"error": "Bạn không có quyền xem chi tiết đợt làm bài này."})
                round_row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM quiz_attempts
                    WHERE user_id = ? AND (submitted_at < ? OR (submitted_at = ? AND id <= ?))
                    """,
                    (row["user_id"], row["submitted_at"], row["submitted_at"], row["id"]),
                ).fetchone()
                round_num = int(round_row["cnt"] if round_row else 1)
                t_rows = conn.execute("SELECT id, title FROM topics").fetchall()
                t_map = {r["id"]: r["title"] for r in t_rows}
                enriched = parse_quiz_attempt_enriched(dict(row), t_map, round_number=round_num)
                raw_ans = {}
                try:
                    raw_ans = json.loads(row["answers_json"] or "{}")
                except Exception:
                    raw_ans = {}
                meta = raw_ans.get("meta") if isinstance(raw_ans, dict) and isinstance(raw_ans.get("meta"), dict) else {}
                return self.send_json(
                    200,
                    {
                        "attempt": enriched,
                        "meta": meta,
                        "items": meta.get("items") or [],
                    },
                )

            if path == "/api/staff/learning-report/export":
                staff = self.require_teacher(conn, qs)
                if not staff:
                    return
                class_filter = qs.get("class_name", [""])[0]
                csv_data = export_learning_analytics_csv(conn, class_filter)
                return self.send_text(
                    200,
                    csv_data,
                    content_type="text/csv; charset=utf-8",
                    extra_headers={
                        "Content-Disposition": 'attachment; filename="bao-cao-hoc-tap-sinh12.csv"'
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
                    self._safe_write(docx_bytes)
                    return
                except Exception as e:
                    return self.send_json(500, {"error": f"Không thể tạo file mẫu: {e}"})

            # ------------------ THI THỬ TỐT NGHIỆP THPT (GET) ------------------
            if path == "/api/mock-exams":
                user = self.require_user(conn, qs)
                if not user:
                    return
                rows = conn.execute(
                    """
                    SELECT id, order_number, header_label, title, subtitle, duration_minutes,
                           source_filename, content_json, question_count, max_score,
                           created_by, created_by_name, created_at, updated_at
                    FROM mock_exams
                    ORDER BY order_number ASC, id ASC
                    """
                ).fetchall()
                my_stats_rows = conn.execute(
                    """
                    SELECT exam_id, COUNT(*) AS cnt, MAX(score) AS best_score, MAX(id) AS last_id
                    FROM mock_exam_attempts
                    WHERE user_id = ?
                    GROUP BY exam_id
                    """,
                    (user["id"],),
                ).fetchall()
                my_map = {r["exam_id"]: r for r in my_stats_rows}

                all_cnt_map = {}
                if user["role"] in ("admin", "teacher"):
                    all_rows = conn.execute(
                        "SELECT exam_id, COUNT(*) AS cnt FROM mock_exam_attempts GROUP BY exam_id"
                    ).fetchall()
                    all_cnt_map = {r["exam_id"]: r["cnt"] for r in all_rows}

                exams = []
                for r in rows:
                    try:
                        c = json.loads(r["content_json"])
                    except Exception:
                        c = {"mcq": [], "true_false": [], "short_answer": []}
                    ms = my_map.get(r["id"])
                    exams.append({
                        "id": r["id"],
                        "order_number": r["order_number"],
                        "header_label": r["header_label"] or "PHÒNG LUYỆN TẬP",
                        "title": r["title"] or f"Đề số {r['order_number']}",
                        "subtitle": r["subtitle"] or "",
                        "duration_minutes": r["duration_minutes"] or 45,
                        "source_filename": r["source_filename"] or "",
                        "question_count": r["question_count"],
                        "mcq_count": len(c.get("mcq") or []),
                        "tf_count": len(c.get("true_false") or []),
                        "sa_count": len(c.get("short_answer") or []),
                        "max_score": r["max_score"],
                        "created_by": r["created_by"],
                        "created_by_name": r["created_by_name"] or "",
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "my_attempt_count": int(ms["cnt"]) if ms else 0,
                        "my_best_score": float(ms["best_score"]) if (ms and ms["best_score"] is not None) else None,
                        "my_last_attempt_id": int(ms["last_id"]) if (ms and ms["last_id"] is not None) else None,
                        "total_attempts": int(all_cnt_map.get(r["id"], 0)),
                    })
                return self.send_json(200, {"exams": exams})

            m_me_att_one = re.match(r"^/api/mock-exams/attempts/(\d+)$", path)
            if m_me_att_one:
                user = self.require_user(conn, qs)
                if not user:
                    return
                att_id = int(m_me_att_one.group(1))
                att = conn.execute(
                    """
                    SELECT a.*, u.full_name, u.username, u.class_name, u.role AS user_role
                    FROM mock_exam_attempts a
                    JOIN users u ON u.id = a.user_id
                    WHERE a.id = ?
                    """,
                    (att_id,),
                ).fetchone()
                if not att:
                    return self.send_json(404, {"error": "Không tìm thấy bài làm."})
                if att["user_id"] != user["id"] and user["role"] not in ("admin", "teacher"):
                    return self.send_json(403, {"error": "Bạn không có quyền xem bài làm này."})
                exam_row = conn.execute("SELECT * FROM mock_exams WHERE id = ?", (att["exam_id"],)).fetchone()
                if not exam_row:
                    return self.send_json(404, {"error": "Đề thi không còn tồn tại."})
                content = json.loads(exam_row["content_json"])
                answers = json.loads(att["answers_json"] or "{}")
                result = grade_mock_exam_submission(content, answers)
                return self.send_json(
                    200,
                    {
                        "attempt": {
                            "id": att["id"],
                            "exam_id": att["exam_id"],
                            "user_id": att["user_id"],
                            "full_name": att["full_name"],
                            "username": att["username"],
                            "class_name": att["class_name"],
                            "started_at": att["started_at"],
                            "submitted_at": att["submitted_at"],
                            "duration_seconds": att["duration_seconds"],
                            "score": att["score"],
                            "max_score": att["max_score"],
                            "part1_score": att["part1_score"],
                            "part2_score": att["part2_score"],
                            "part3_score": att["part3_score"],
                            "correct_count": att["correct_count"],
                            "total_questions": att["total_questions"],
                            "answers": answers,
                        },
                        "exam": {
                            "id": exam_row["id"],
                            "order_number": exam_row["order_number"],
                            "header_label": exam_row["header_label"] or "PHÒNG LUYỆN TẬP",
                            "title": exam_row["title"],
                            "subtitle": exam_row["subtitle"] or "",
                            "duration_minutes": exam_row["duration_minutes"] or 45,
                            "content": content,
                        },
                        "result": result,
                    },
                )

            m_me_atts = re.match(r"^/api/mock-exams/(\d+)/attempts$", path)
            if m_me_atts:
                user = self.require_user(conn, qs)
                if not user:
                    return
                exam_id = int(m_me_atts.group(1))
                if user["role"] in ("admin", "teacher"):
                    rows = conn.execute(
                        """
                        SELECT a.id, a.exam_id, a.user_id, a.started_at, a.submitted_at,
                               a.duration_seconds, a.score, a.max_score, a.part1_score,
                               a.part2_score, a.part3_score, a.correct_count, a.total_questions,
                               u.full_name, u.username, u.class_name, u.role AS user_role
                        FROM mock_exam_attempts a
                        JOIN users u ON u.id = a.user_id
                        WHERE a.exam_id = ?
                        ORDER BY a.submitted_at DESC
                        """,
                        (exam_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT a.id, a.exam_id, a.user_id, a.started_at, a.submitted_at,
                               a.duration_seconds, a.score, a.max_score, a.part1_score,
                               a.part2_score, a.part3_score, a.correct_count, a.total_questions,
                               u.full_name, u.username, u.class_name, u.role AS user_role
                        FROM mock_exam_attempts a
                        JOIN users u ON u.id = a.user_id
                        WHERE a.exam_id = ? AND a.user_id = ?
                        ORDER BY a.submitted_at DESC
                        """,
                        (exam_id, user["id"]),
                    ).fetchall()
                return self.send_json(200, {"attempts": [dict(r) for r in rows]})

            m_me_one = re.match(r"^/api/mock-exams/(\d+)$", path)
            if m_me_one:
                user = self.require_user(conn, qs)
                if not user:
                    return
                exam_id = int(m_me_one.group(1))
                row = conn.execute("SELECT * FROM mock_exams WHERE id = ?", (exam_id,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy đề thi thử."})
                content = json.loads(row["content_json"])
                include_keys = (qs.get("include_keys", ["0"])[0] == "1") and user["role"] in ("admin", "teacher")
                if not include_keys:
                    # Ẩn hoàn toàn đáp án & lời giải khi học sinh đang làm bài
                    sanitized = {
                        "mcq": [
                            {
                                "id": q.get("id"),
                                "orig_num": q.get("orig_num"),
                                "question": q.get("question", ""),
                                "images": q.get("images") or [],
                                "tables": q.get("tables") or [],
                                "options": q.get("options") or [],
                            }
                            for q in (content.get("mcq") or [])
                        ],
                        "true_false": [
                            {
                                "id": q.get("id"),
                                "orig_num": q.get("orig_num"),
                                "question": q.get("question", ""),
                                "images": q.get("images") or [],
                                "tables": q.get("tables") or [],
                                "statements": [
                                    {"key": st.get("key"), "text": st.get("text", "")}
                                    for st in (q.get("statements") or [])
                                ],
                            }
                            for q in (content.get("true_false") or [])
                        ],
                        "short_answer": [
                            {
                                "id": q.get("id"),
                                "orig_num": q.get("orig_num"),
                                "question": q.get("question", ""),
                                "images": q.get("images") or [],
                                "tables": q.get("tables") or [],
                            }
                            for q in (content.get("short_answer") or [])
                        ],
                    }
                    content_out = sanitized
                else:
                    content_out = content

                return self.send_json(
                    200,
                    {
                        "exam": {
                            "id": row["id"],
                            "order_number": row["order_number"],
                            "header_label": row["header_label"] or "PHÒNG LUYỆN TẬP",
                            "title": row["title"] or f"Đề số {row['order_number']}",
                            "subtitle": row["subtitle"] or "",
                            "duration_minutes": row["duration_minutes"] or 45,
                            "source_filename": row["source_filename"] or "",
                            "question_count": row["question_count"],
                            "max_score": row["max_score"],
                            "created_by_name": row["created_by_name"] or "",
                            "created_at": row["created_at"],
                            "content": content_out,
                        }
                    },
                )

            return self.send_json(404, {"error": "API endpoint không tồn tại."})
        finally:
            conn.close()

    # ---------------------- POST ROUTES ----------------------
    def do_POST(self):
        try:
            self._handle_post()
        except _PayloadTooLargeError:
            self.send_json(413, {"error": "File vượt quá giới hạn dung lượng cho phép (tối đa 100 MB)."})
        except _IncompleteUploadError as e:
            self.send_json(400, {"error": str(e)})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except Exception as e:
            traceback.print_exc()
            try:
                self.send_json(500, {"error": f"Hệ thống đang bận, vui lòng thử lại ({type(e).__name__})."})
            except Exception:
                pass

    def _parse_upload_request(self, qs):
        ctype = (self.headers.get("Content-Type") or "").lower()
        if "application/octet-stream" in ctype:
            file_bytes = self.read_raw_body()
            filename = (qs.get("filename", [""])[0] or "").strip()
            meta = {
                "filename": filename,
                "order_index": qs.get("order_index", [""])[0],
                "title": (qs.get("title", [""])[0] or "").strip(),
                "subtitle": (qs.get("subtitle", [""])[0] or "").strip(),
                "id": (qs.get("id", [""])[0] or "").strip(),
                "preview_only": qs.get("preview_only", ["1"])[0] not in ("0", "false", "False"),
                "replace_review": qs.get("replace_review", ["1"])[0] not in ("0", "false", "False"),
            }
            sec_raw = qs.get("sections", [""])[0]
            if sec_raw:
                try:
                    meta["sections"] = json.loads(sec_raw)
                except Exception:
                    pass
            return meta, file_bytes

        body = self.read_json_body()
        content_b64 = body.get("content_base64") or ""
        file_bytes = base64.b64decode(content_b64) if content_b64 else b""
        return body, file_bytes

    def _handle_post(self):
        parsed = urlparse(self.path)
        path = strip_base_path(parsed.path)
        qs = parse_qs(parsed.query)

        # Xử lý đọc & phân tích file Word/PDF NGOÀI DB_LOCK để không làm nghẽn request của học sinh
        if path == "/api/topics/preview-new-file":
            meta, file_bytes = self._parse_upload_request(qs)
            return self._handle_preview_new_topic_file(meta, file_bytes, qs)

        if path == "/api/mock-exams/parse":
            meta, file_bytes = self._parse_upload_request(qs)
            return self._handle_parse_mock_exam_file(meta, file_bytes, qs)

        if path == "/api/staff/exam-mixer/parse-docx":
            meta, file_bytes = self._parse_upload_request(qs)
            return self._handle_parse_word_exam_for_mixer(meta, file_bytes, qs)

        if path == "/api/staff/exam-mixer/load-sample":
            body = self.read_json_body()
            return self._handle_load_sample_exam_for_mixer(body, qs)

        m_imp = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)/import-file$", path)
        if m_imp:
            meta, file_bytes = self._parse_upload_request(qs)
            return self._handle_import_topic_file(m_imp.group(1), meta, file_bytes, qs)

        m_banner = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)/banner$", path)
        if m_banner:
            meta, file_bytes = self._parse_upload_request(qs)
            return self._handle_upload_topic_banner(m_banner.group(1), meta, file_bytes, qs)

        body = self.read_json_body()

        with DB_LOCK:
            conn = get_conn()
            try:
                self._dispatch_post(conn, path, qs, body)
            finally:
                conn.close()

    def _handle_upload_topic_banner(self, tid: str, body, file_bytes: bytes, qs):
        filename = (body.get("filename") or "banner.png").strip()
        with DB_LOCK:
            conn = get_conn()
            try:
                staff = self.require_admin(conn, qs, body)
                if not staff:
                    return
                row = conn.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy chủ đề."})
                try:
                    banner_url = _save_topic_banner_file(tid, file_bytes, filename)
                except ValueError as ve:
                    return self.send_json(400, {"error": str(ve)})
                content = json.loads(row["content_json"])
                content["id"] = tid
                content["banner_image"] = banner_url
                ts = now_iso()
                conn.execute(
                    "UPDATE topics SET content_json = ?, updated_by = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(content, ensure_ascii=False), staff["id"], ts, tid),
                )
                conn.commit()
                app_cache.invalidate_topics(tid)
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "topic_id": tid,
                        "banner_image": banner_url,
                        "updated_at": ts,
                        "message": f"Đã cập nhật ảnh banner cho '{row['title']}'!",
                    },
                )
            finally:
                conn.close()

    def _handle_parse_mock_exam_file(self, body, file_bytes: bytes, qs):
        filename = (body.get("filename") or "").strip()
        if not filename or not file_bytes:
            return self.send_json(400, {"error": "Vui lòng chọn tệp đề thi Word (.docx) hoặc PDF (.pdf)."})

        conn = get_conn()
        try:
            staff = self.require_teacher(conn, qs, body)
            if not staff:
                return
            row = conn.execute("SELECT COALESCE(MAX(order_number), 0) AS mx FROM mock_exams").fetchone()
            next_order = int((row["mx"] if row else 0) or 0) + 1
        finally:
            conn.close()

        try:
            parsed = parse_mock_exam_document(file_bytes, filename, next_order_number=next_order)
        except Exception as e:
            return self.send_json(400, {"error": f"Lỗi khi phân tích đề thi: {e}"})

        return self.send_json(200, {"ok": True, **parsed})

    def _handle_parse_word_exam_for_mixer(self, body, file_bytes: bytes, qs):
        """Phân tích file Word (.docx) đề kiểm tra để Quản trị viên / Giáo viên trộn đề (nhận diện gạch chân, A., Giải chi tiết)."""
        filename = (body.get("filename") or "").strip()
        if not filename or not file_bytes:
            return self.send_json(400, {"error": "Vui lòng chọn tệp đề kiểm tra Word (.docx)."})
        ext = os.path.splitext(filename)[1].lower()
        if ext != ".docx":
            return self.send_json(400, {"error": "Tính năng trộn đề kiểm tra hỗ trợ tệp định dạng Word (.docx)."})

        conn = get_conn()
        try:
            staff = self.require_teacher(conn, qs, body)
            if not staff:
                return
        finally:
            conn.close()

        try:
            parsed = parse_mock_exam_document(file_bytes, filename, next_order_number=1)
        except Exception as e:
            return self.send_json(400, {"error": f"Lỗi khi đọc & phân tích file Word: {e}"})

        return self.send_json(
            200,
            {
                "ok": True,
                "source_filename": filename,
                "content": parsed["draft"]["content"],
                "stats": parsed["stats"],
                "warnings": parsed.get("warnings") or [],
                "spelling_report": parsed.get("spelling_report") or {},
            },
        )

    def _handle_load_sample_exam_for_mixer(self, body, qs):
        """Nạp trực tiếp 1 tệp đề mẫu từ thư mục FILE ĐỀ MẪU để Quản trị viên / Giáo viên kiểm tra & trộn thử."""
        conn = get_conn()
        try:
            staff = self.require_teacher(conn, qs, body)
            if not staff:
                return
        finally:
            conn.close()

        fname = (body.get("filename") or "").strip()
        fpath = _resolve_sample_exam_path(fname)
        if not fpath:
            return self.send_json(404, {"error": "Không tìm thấy tệp đề mẫu trong thư mục FILE ĐỀ MẪU."})

        try:
            with open(fpath, "rb") as f:
                file_bytes = f.read()
            parsed = parse_mock_exam_document(file_bytes, os.path.basename(fpath), next_order_number=1)
        except Exception as e:
            return self.send_json(400, {"error": f"Lỗi khi phân tích file đề mẫu: {e}"})

        return self.send_json(
            200,
            {
                "ok": True,
                "source_filename": unicodedata.normalize("NFC", os.path.basename(fpath)),
                "content": parsed["draft"]["content"],
                "stats": parsed["stats"],
                "warnings": parsed.get("warnings") or [],
                "spelling_report": parsed.get("spelling_report") or {},
            },
        )

    def _handle_preview_new_topic_file(self, body, file_bytes: bytes, qs):
        filename = (body.get("filename") or "").strip()
        if not filename or not file_bytes:
            return self.send_json(400, {"error": "Vui lòng chọn file Word (.docx) hoặc PDF (.pdf)."})

        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".docx", ".pdf", ".txt", ".md"):
            return self.send_json(400, {"error": "Chỉ hỗ trợ file Word (.docx), PDF (.pdf) hoặc văn bản (.txt)."})

        conn = get_conn()
        try:
            teacher = self.require_admin(conn, qs, body)
            if not teacher:
                return
            max_ord = conn.execute("SELECT COALESCE(MAX(order_index), 0) FROM topics").fetchone()[0]
            order_index = int(body.get("order_index") or (max_ord + 1))
            tid = (body.get("id") or "").strip()
            if not tid:
                base_tid = f"chu-de-{order_index}"
                if conn.execute("SELECT id FROM topics WHERE id = ?", (base_tid,)).fetchone():
                    tid = f"{base_tid}-{secrets.token_hex(2)}"
                else:
                    tid = base_tid
        finally:
            conn.close()

        custom_title = (body.get("title") or "").strip()
        custom_subtitle = (body.get("subtitle") or "").strip()

        try:
            parsed = parse_document_to_topic(
                file_bytes,
                filename,
                tid,
                {"id": tid, "order_index": order_index, "title": custom_title},
            )
        except Exception as e:
            return self.send_json(400, {"error": f"Lỗi khi đọc & trích xuất file: {e}"})

        extracted = parsed["extracted"]
        extracted["id"] = tid
        extracted["order_index"] = order_index
        if custom_title:
            extracted["title"] = custom_title
        elif not re.match(r"^Chủ đề\s*\d+", extracted["title"], re.IGNORECASE):
            extracted["title"] = f"Chủ đề {order_index}. {extracted['title']}"
        if custom_subtitle:
            extracted["subtitle"] = custom_subtitle

        return self.send_json(
            200,
            {
                "ok": True,
                "topic_id": tid,
                "order_index": order_index,
                "preview": parsed,
            },
        )

    def _handle_import_topic_file(self, tid: str, body, file_bytes: bytes, qs):
        filename = (body.get("filename") or "").strip()
        preview_only = bool(body.get("preview_only", True))
        sections = body.get("sections") or {
            "theory": True,
            "knowledge": True,
            "video": True,
            "review": True,
        }
        replace_review = bool(body.get("replace_review", True))

        if not filename or not file_bytes:
            return self.send_json(400, {"error": "Vui lòng chọn file tài liệu (.docx, .pdf hoặc .txt)."})

        conn = get_conn()
        try:
            teacher = self.require_admin(conn, qs, body)
            if not teacher:
                return
            row = conn.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
            if not row:
                return self.send_json(404, {"error": "Không tìm thấy chủ đề."})
            existing = json.loads(row["content_json"])
            teacher_id = teacher["id"]
        finally:
            conn.close()

        try:
            parsed = parse_document_to_topic(file_bytes, filename, tid, existing)
        except Exception as e:
            return self.send_json(400, {"error": f"Lỗi khi đọc & trích xuất file: {e}"})

        if preview_only:
            return self.send_json(200, {"ok": True, "preview": parsed})

        ext_data = parsed["extracted"]
        with DB_LOCK:
            conn = get_conn()
            try:
                row = conn.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy chủ đề."})
                merged = json.loads(row["content_json"])
                merged["status"] = "published"
                merged["source_note"] = ext_data["source_note"]

                if sections.get("theory") and ext_data["lessons"]:
                    merged["title"] = ext_data["title"] or merged["title"]
                    merged["lessons"] = ext_data["lessons"]
                if sections.get("knowledge"):
                    ks = ext_data["knowledge_system"]
                    if ks.get("mindmap", {}).get("branches") or ks.get("comparison_tables") or ks.get("units"):
                        merged["knowledge_system"] = ks
                if sections.get("video") and (ext_data.get("interactive_video") or {}).get("scenes"):
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
                    (merged["title"], json.dumps(merged, ensure_ascii=False), teacher_id, ts, tid),
                )
                conn.commit()
                app_cache.invalidate_topics(tid)
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "topic": merged,
                        "stats": parsed["stats"],
                        "message": f"Đã trích xuất và cập nhật 100% dữ liệu từ file '{filename}'!",
                    },
                )
            finally:
                conn.close()

    def _dispatch_post(self, conn, path, qs, body):
        if True:
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
                invalidate_token_cache(user_id=user["id"])
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
                    invalidate_token_cache(token=token)
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

                upsert_lesson_progress(conn, user["id"], topic_id, lesson_id, completed, checkpoint_score, ts)
                conn.commit()
                return self.send_json(200, {"ok": True})

            # Ghi nhận tự động các mục Lý thuyết học sinh đã đọc trong phiên học
            if path == "/api/analytics/theory-read":
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                topic_id = (body.get("topic_id") or "").strip()
                lesson_id = (body.get("lesson_id") or "").strip()
                lesson_number = (body.get("lesson_number") or "").strip()
                lesson_title = (body.get("lesson_title") or "").strip()
                sections = body.get("sections") or []
                mark_lesson_done = bool(body.get("mark_lesson_done"))
                if not topic_id or not lesson_id:
                    return self.send_json(400, {"error": "Thiếu topic_id hoặc lesson_id."})
                ts = now_iso()
                saved = 0
                for sec in sections:
                    if not isinstance(sec, dict):
                        continue
                    skey = str(sec.get("key") or "").strip()
                    if not skey:
                        continue
                    shead = str(sec.get("heading") or skey).strip()
                    dur_d = int(sec.get("duration_delta") or 0)
                    comp = 1 if sec.get("completed", True) else 0
                    upsert_theory_read(
                        conn,
                        user["id"],
                        topic_id,
                        lesson_id,
                        lesson_number,
                        lesson_title,
                        skey,
                        shead,
                        duration_delta=dur_d,
                        completed=comp,
                        ts=ts,
                    )
                    saved += 1
                if mark_lesson_done:
                    upsert_lesson_progress(conn, user["id"], topic_id, lesson_id, 1, 1, ts)
                conn.commit()
                return self.send_json(200, {"ok": True, "saved": saved})

            # Ghi nhận tự động kết quả làm Bài tập vận dụng trong Lý thuyết & Hệ thống kiến thức
            if path == "/api/analytics/exercise-check":
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                topic_id = (body.get("topic_id") or "").strip()
                source_tab = (body.get("source_tab") or "theory").strip()
                lesson_label = (body.get("lesson_label") or "").strip()
                records = body.get("records") or []
                if not topic_id or not isinstance(records, list):
                    return self.send_json(400, {"error": "Thiếu topic_id hoặc danh sách kết quả bài tập."})
                ts = now_iso()
                saved = 0
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    uid_key = str(rec.get("unit_id") or "").strip()
                    if not uid_key:
                        continue
                    upsert_exercise_record(
                        conn,
                        user["id"],
                        topic_id,
                        source_tab,
                        str(rec.get("lesson_label") or lesson_label),
                        uid_key,
                        str(rec.get("unit_title") or uid_key),
                        int(rec.get("correct_count") or 0),
                        int(rec.get("answered_count") or 0),
                        int(rec.get("total_items") or 1),
                        ts=ts,
                    )
                    saved += 1
                conn.commit()
                return self.send_json(200, {"ok": True, "saved": saved})

            # Admin: Create new topic
            if path == "/api/topics":
                teacher = self.require_admin(conn, qs, body)
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
                upsert_topic(
                    conn,
                    tid,
                    order_index,
                    title,
                    subtitle,
                    content.get("status", "published"),
                    json.dumps(content, ensure_ascii=False),
                    teacher["id"],
                    ts,
                )
                conn.commit()
                app_cache.invalidate_topics(tid)
                return self.send_json(201, {"topic": content})

            # Admin: Cập nhật & Lưu Chủ đề MỚI đã xem trước vào SQLite + xoá cache
            if path == "/api/topics/publish-new":
                teacher = self.require_admin(conn, qs, body)
                if not teacher:
                    return
                topic_obj = body.get("topic")
                if not isinstance(topic_obj, dict):
                    return self.send_json(400, {"error": "Thiếu dữ liệu Chủ đề cần lưu."})

                title = (topic_obj.get("title") or "").strip()
                if not title:
                    return self.send_json(400, {"error": "Vui lòng nhập tên Chủ đề."})

                max_ord = conn.execute("SELECT COALESCE(MAX(order_index), 0) FROM topics").fetchone()[0]
                order_index = int(topic_obj.get("order_index") or (max_ord + 1))
                tid = (topic_obj.get("id") or "").strip()
                if not tid:
                    tid = f"chu-de-{order_index}"
                    if conn.execute("SELECT id FROM topics WHERE id = ?", (tid,)).fetchone():
                        tid = f"{tid}-{secrets.token_hex(2)}"

                subtitle = (topic_obj.get("subtitle") or "").strip()
                topic_obj["id"] = tid
                topic_obj["order_index"] = order_index
                topic_obj["title"] = title
                topic_obj["subtitle"] = subtitle
                topic_obj["status"] = "published"
                topic_obj["source_note"] = ""
                topic_obj.setdefault("lessons", [])
                topic_obj.setdefault(
                    "knowledge_system",
                    {"overview": "", "units": [], "mindmap": {"root": title.upper(), "branches": []}, "comparison_tables": [], "formulas": [], "flashcards": []},
                )
                topic_obj.setdefault("youtube_videos", [])
                topic_obj.setdefault("review", {"mcq": [], "true_false": [], "short_answer": []})

                # Chuẩn hoá lại chính tả & công thức trước khi xuất bản
                try:
                    standardize_topic_content(topic_obj)
                except Exception:
                    pass

                ts = now_iso()
                upsert_topic(
                    conn,
                    tid,
                    order_index,
                    title,
                    subtitle,
                    "published",
                    json.dumps(topic_obj, ensure_ascii=False),
                    teacher["id"],
                    ts,
                )
                conn.commit()
                app_cache.invalidate_topics(tid)
                return self.send_json(
                    201,
                    {
                        "ok": True,
                        "topic": topic_obj,
                        "message": f"Đã lưu và xuất bản '{title}' lên hệ thống!",
                    },
                )

            # Admin: Xoá Chủ đề (giữ lại ít nhất 1 chủ đề)
            m_del_tp = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)/delete$", path)
            if m_del_tp:
                staff = self.require_admin(conn, qs, body)
                if not staff:
                    return
                tid = m_del_tp.group(1)
                row = conn.execute("SELECT id, title FROM topics WHERE id = ?", (tid,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy chủ đề."})
                total_cnt = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
                if total_cnt <= 1:
                    return self.send_json(400, {"error": "Không thể xoá chủ đề cuối cùng của hệ thống."})
                conn.execute("DELETE FROM topics WHERE id = ?", (tid,))
                conn.commit()
                app_cache.invalidate_topics(tid)
                cleanup_topic_uploads(tid)
                return self.send_json(200, {"ok": True, "message": f"Đã xoá '{row['title']}'."})

            # Admin: Dọn ảnh nháp nếu huỷ/đổi file xem trước chưa xuất bản
            m_clean_draft = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)/cleanup-draft$", path)
            if m_clean_draft:
                staff = self.require_admin(conn, qs, body)
                if not staff:
                    return
                tid = m_clean_draft.group(1)
                exists = conn.execute("SELECT id FROM topics WHERE id = ?", (tid,)).fetchone()
                if exists:
                    return self.send_json(200, {"ok": True, "cleaned": False})
                cleaned = cleanup_topic_uploads(tid)
                return self.send_json(200, {"ok": True, "cleaned": cleaned})

            # Admin: Xoá ảnh banner của Chủ đề
            m_del_banner = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)/banner/delete$", path)
            if m_del_banner:
                staff = self.require_admin(conn, qs, body)
                if not staff:
                    return
                tid = m_del_banner.group(1)
                row = conn.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy chủ đề."})
                _remove_topic_banner_files(tid)
                content = json.loads(row["content_json"])
                content.pop("banner_image", None)
                ts = now_iso()
                conn.execute(
                    "UPDATE topics SET content_json = ?, updated_by = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(content, ensure_ascii=False), staff["id"], ts, tid),
                )
                conn.commit()
                app_cache.invalidate_topics(tid)
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "topic_id": tid,
                        "banner_image": "",
                        "updated_at": ts,
                        "message": f"Đã xoá ảnh banner của '{row['title']}'.",
                    },
                )

            # Staff: Xoá toàn bộ cache Redis + L1 Memory thủ công
            if path == "/api/admin/cache-clear":
                teacher = self.require_teacher(conn, qs, body)
                if not teacher:
                    return
                app_cache.clear_all()
                return self.send_json(
                    200,
                    {"ok": True, "cache": app_cache.stats(), "message": "Đã làm mới toàn bộ bộ nhớ đệm (Cache)!"},
                )

            # Admin: Đối chiếu & khớp đáp án từ file PDF "Đáp án" vào bản nháp Chủ đề mới
            if path == "/api/topics/apply-answer-pdf":
                admin = self.require_admin(conn, qs, body)
                if not admin:
                    return
                topic_obj = body.get("topic")
                pdf_b64 = body.get("pdf_base64") or ""
                pdf_name = (body.get("pdf_filename") or "dap-an.pdf").strip()
                if not isinstance(topic_obj, dict) or not pdf_b64:
                    return self.send_json(400, {"error": "Thiếu dữ liệu Chủ đề hoặc tệp PDF Đáp án."})
                try:
                    pdf_bytes = base64.b64decode(pdf_b64)
                    overwrite = bool(body.get("overwrite", True))
                    report = apply_answer_pdf_to_topic(topic_obj, pdf_bytes, pdf_name, overwrite=overwrite)
                except Exception as e:
                    return self.send_json(400, {"error": f"Không thể đọc file PDF Đáp án: {e}"})
                rev = topic_obj.get("review") or {}
                if report.get("is_scanned_pdf") and report["total_matched"] == 0 and not report.get("ocr_used"):
                    msg_txt = (
                        f"File '{pdf_name}' là bản PDF scan/ảnh chụp (không có lớp văn bản) nên máy chủ trực tuyến không đọc chữ trực tiếp được. "
                        "Thầy vui lòng xuất PDF có văn bản từ Word hoặc chạy đối chiếu trên máy cục bộ (có OCR tiếng Việt tích hợp)."
                    )
                else:
                    ocr_note = " (tự động OCR bản scan)" if report.get("ocr_used") else ""
                    msg_txt = (
                        f"Đã đối chiếu '{pdf_name}'{ocr_note}: khớp {report['total_matched']} đáp án "
                        f"(TN: {report['matched_mcq']}, Đ/S: {report['matched_tf']}, TLN: {report['matched_sa']})."
                    )
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "topic": topic_obj,
                        "report": report,
                        "keyed_counts": {
                            "mcq_keyed": sum(1 for q in (rev.get("mcq") or []) if q.get("answer_key_ready")),
                            "true_false_keyed": sum(1 for q in (rev.get("true_false") or []) if q.get("answer_key_ready")),
                            "short_answer_keyed": sum(1 for q in (rev.get("short_answer") or []) if q.get("answer_key_ready")),
                        },
                        "message": msg_txt,
                    },
                )

            # Admin & Teacher: Trộn đề kiểm tra từ file Word (.docx) & xuất Word (.docx) + Excel (.xlsx)
            if path == "/api/staff/exam-mixer/generate-from-docx":
                staff = self.require_teacher(conn, qs, body)
                if not staff:
                    return
                content = body.get("content")
                if not isinstance(content, dict):
                    return self.send_json(400, {"error": "Thiếu nội dung câu hỏi từ file Word để trộn đề."})
                exam_count = max(1, min(30, int(body.get("exam_count") or 4)))
                codes = normalize_exam_codes(body.get("exam_codes") or [], exam_count, default_start=1001)

                meta = {
                    "school_name": (body.get("school_name") or "").strip(),
                    "exam_period": (body.get("exam_period") or body.get("title") or "KIỂM TRA ĐỊNH KÌ").strip(),
                    "school_year": (body.get("school_year") or "2026 - 2027").strip(),
                    "subject": (body.get("subject") or "").strip(),
                    "duration_minutes": max(5, min(180, int(body.get("duration_minutes") or 45))),
                }
                meta["title"] = meta["exam_period"]

                try:
                    pkg = generate_shuffled_exam_from_content(content, codes, meta)
                except Exception as e:
                    return self.send_json(400, {"error": str(e)})

                job_id = secrets.token_urlsafe(12)
                stamp = now_vn().strftime("%Y%m%d-%H%M")
                EXAM_EXPORTS[job_id] = {
                    "zip": pkg["zip_bytes"],
                    "docx": pkg["docx_bytes"],
                    "xlsx": pkg["xlsx_bytes"],
                    "individual_files": pkg.get("individual_files") or {},
                    "filename_base": f"de-tron-sinhhoc12-{stamp}",
                    "created_at": now_iso(),
                }
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

            # Admin & Teacher: Trộn đề trắc nghiệm theo Ma trận 3x3 & xuất Word (.docx) + Excel (.xlsx)
            if path == "/api/admin/generate-exam":
                teacher = self.require_teacher(conn, qs, body)
                if not teacher:
                    return
                selected_lesson_ids = body.get("selected_lesson_ids") or []
                matrix = body.get("matrix") or {}
                exam_count = max(1, min(30, int(body.get("exam_count") or 4)))
                codes = normalize_exam_codes(body.get("exam_codes") or [], exam_count, default_start=1001)

                meta = {
                    "title": (body.get("exam_period") or body.get("title") or "KIỂM TRA ĐỊNH KÌ").strip(),
                    "exam_period": (body.get("exam_period") or body.get("title") or "KIỂM TRA ĐỊNH KÌ").strip(),
                    "school_name": (body.get("school_name") or "").strip(),
                    "school_year": (body.get("school_year") or "2026 - 2027").strip(),
                    "subject": (body.get("subject") or "").strip(),
                    "duration_minutes": max(5, min(180, int(body.get("duration_minutes") or 45))),
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
                stamp = now_vn().strftime("%Y%m%d-%H%M")
                EXAM_EXPORTS[job_id] = {
                    "zip": pkg["zip_bytes"],
                    "docx": pkg["docx_bytes"],
                    "xlsx": pkg["xlsx_bytes"],
                    "individual_files": pkg.get("individual_files") or {},
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

            # Admin ONLY: Đặt lại mật khẩu thành viên theo tên đăng nhập về mặc định 123456@
            if path == "/api/admin/users/reset-by-username":
                admin = self.require_admin(conn, qs, body)
                if not admin:
                    return
                uname = (body.get("username") or "").strip().lstrip("@").lower()
                if not uname:
                    return self.send_json(400, {"error": "Vui lòng nhập hoặc chọn tên đăng nhập thành viên cần reset mật khẩu."})
                target = conn.execute("SELECT * FROM users WHERE lower(username) = ?", (uname,)).fetchone()
                if not target:
                    return self.send_json(404, {"error": f"Không tìm thấy thành viên có tên đăng nhập '@{uname}'."})
                if target["role"] == "admin" or target["username"].lower() == ADMIN_USERNAME:
                    return self.send_json(403, {"error": "Không thể reset mật khẩu tài khoản Quản trị viên tại đây."})
                ts = now_iso()
                conn.execute(
                    "UPDATE users SET password_hash = ?, must_change_password = 1, updated_at = ? WHERE id = ?",
                    (hash_password(DEFAULT_USER_PASSWORD), ts, target["id"]),
                )
                conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (target["id"],))
                conn.commit()
                invalidate_token_cache(user_id=target["id"])
                updated_target = conn.execute("SELECT * FROM users WHERE id = ?", (target["id"],)).fetchone()
                record_password_change(conn, updated_target, reason="admin_reset")
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "default_password": DEFAULT_USER_PASSWORD,
                        "message": f"Đã đặt lại mật khẩu của '{target['full_name']}' (@{target['username']}) về mật khẩu mặc định {DEFAULT_USER_PASSWORD}.",
                    },
                )

            # Admin ONLY: Đặt lại mật khẩu thành viên (Giáo viên / Học sinh) về mật khẩu mặc định 123456@
            m_reset = re.match(r"^/api/admin/users/(\d+)/reset-password$", path)
            if m_reset:
                admin = self.require_admin(conn, qs, body)
                if not admin:
                    return
                uid = int(m_reset.group(1))
                target = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
                if not target:
                    return self.send_json(404, {"error": "Không tìm thấy thành viên."})
                if target["role"] == "admin" or target["username"].lower() == ADMIN_USERNAME:
                    return self.send_json(403, {"error": "Không thể reset mật khẩu tài khoản Quản trị viên tại đây."})
                ts = now_iso()
                conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?, must_change_password = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (hash_password(DEFAULT_USER_PASSWORD), ts, uid),
                )
                conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (uid,))
                conn.commit()
                invalidate_token_cache(user_id=uid)
                updated_target = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
                record_password_change(conn, updated_target, reason="admin_reset")
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "default_password": DEFAULT_USER_PASSWORD,
                        "message": f"Đã đặt lại mật khẩu của '{target['full_name']}' (@{target['username']}) về mật khẩu mặc định {DEFAULT_USER_PASSWORD}.",
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

            # ------------------ THI THỬ TỐT NGHIỆP THPT (POST) ------------------
            if path == "/api/mock-exams":
                # Cả Quản trị viên (admin) và Giáo viên (teacher) đều được quyền thêm đề thi mới
                staff = self.require_teacher(conn, qs, body)
                if not staff:
                    return
                content = body.get("content")
                if not isinstance(content, dict):
                    return self.send_json(400, {"error": "Nội dung đề thi không hợp lệ."})
                total_q, max_score = compute_exam_max_score(content)
                if total_q <= 0:
                    return self.send_json(400, {"error": "Đề thi phải có ít nhất 1 câu hỏi."})

                row_mx = conn.execute("SELECT COALESCE(MAX(order_number), 0) AS mx FROM mock_exams").fetchone()
                order_num = int((row_mx["mx"] if row_mx else 0) or 0) + 1
                header_label = "PHÒNG LUYỆN TẬP"
                title = (body.get("title") or "").strip() or f"Đề số {order_num}"
                subtitle = (body.get("subtitle") or "").strip()
                duration_minutes = int(body.get("duration_minutes") or 45)
                if duration_minutes < 5 or duration_minutes > 180:
                    duration_minutes = 45
                source_filename = (body.get("source_filename") or "").strip()
                ts = now_iso()

                cur = conn.execute(
                    """
                    INSERT INTO mock_exams
                    (order_number, header_label, title, subtitle, duration_minutes, source_filename,
                     content_json, question_count, max_score, created_by, created_by_name, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_num,
                        header_label,
                        title,
                        subtitle,
                        duration_minutes,
                        source_filename,
                        json.dumps(content, ensure_ascii=False),
                        total_q,
                        max_score,
                        staff["id"],
                        staff["full_name"],
                        ts,
                        ts,
                    ),
                )
                conn.commit()
                new_id = cur.lastrowid
                return self.send_json(
                    201,
                    {
                        "ok": True,
                        "exam": {
                            "id": new_id,
                            "order_number": order_num,
                            "header_label": header_label,
                            "title": title,
                            "subtitle": subtitle,
                            "duration_minutes": duration_minutes,
                            "question_count": total_q,
                            "max_score": max_score,
                            "created_by_name": staff["full_name"],
                            "created_at": ts,
                        },
                        "message": f"Đã tạo thành công {header_label} — Đề số {order_num} ({total_q} câu, {duration_minutes} phút)!",
                    },
                )

            m_me_sub = re.match(r"^/api/mock-exams/(\d+)/submit$", path)
            if m_me_sub:
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                exam_id = int(m_me_sub.group(1))
                row = conn.execute("SELECT * FROM mock_exams WHERE id = ?", (exam_id,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy đề thi thử."})
                content = json.loads(row["content_json"])
                answers = body.get("answers") or {}
                auto_timeout = bool(body.get("auto_submitted_timeout"))

                # Kiểm tra bắt buộc làm hết 100% câu hỏi mới được bấm Nộp bài (trừ khi hết giờ 45 phút tự nộp)
                if not auto_timeout:
                    ans_mcq = answers.get("mcq") or {}
                    ans_tf = answers.get("true_false") or {}
                    ans_sa = answers.get("short_answer") or {}
                    missing = []
                    for i, q in enumerate(content.get("mcq") or [], start=1):
                        v = ans_mcq.get(q.get("id"))
                        if v is None or str(v) == "":
                            missing.append(f"Phần I - Câu {i}")
                    for i, q in enumerate(content.get("true_false") or [], start=1):
                        for st in (q.get("statements") or []):
                            if ans_tf.get(f"{q.get('id')}:{st.get('key')}") is None:
                                missing.append(f"Phần II - Câu {i} ({st.get('key')})")
                                break
                    for i, q in enumerate(content.get("short_answer") or [], start=1):
                        if not str(ans_sa.get(q.get("id")) or "").strip():
                            missing.append(f"Phần III - Câu {i}")
                    if missing:
                        return self.send_json(
                            400,
                            {
                                "error": f"Bạn cần hoàn thành tất cả các câu hỏi trước khi nộp bài (còn thiếu {len(missing)} câu: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''})."
                            },
                        )

                result = grade_mock_exam_submission(content, answers)
                ts_now = now_iso()
                started_at = to_vn_iso(body.get("started_at") or "") or ts_now
                duration_seconds = max(0, int(body.get("duration_seconds") or 0))

                cur = conn.execute(
                    """
                    INSERT INTO mock_exam_attempts
                    (exam_id, user_id, started_at, submitted_at, duration_seconds,
                     score, max_score, part1_score, part2_score, part3_score,
                     correct_count, total_questions, answers_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        exam_id,
                        user["id"],
                        started_at,
                        ts_now,
                        duration_seconds,
                        result["score"],
                        result["max_score"],
                        result["part1_score"],
                        result["part2_score"],
                        result["part3_score"],
                        result["correct_count"],
                        result["total_questions"],
                        json.dumps(answers, ensure_ascii=False),
                    ),
                )
                conn.commit()
                return self.send_json(
                    201,
                    {
                        "ok": True,
                        "attempt_id": cur.lastrowid,
                        "started_at": started_at,
                        "submitted_at": ts_now,
                        "duration_seconds": duration_seconds,
                        "result": result,
                        "exam": {
                            "id": row["id"],
                            "order_number": row["order_number"],
                            "header_label": row["header_label"] or "PHÒNG LUYỆN TẬP",
                            "title": row["title"],
                            "subtitle": row["subtitle"] or "",
                            "duration_minutes": row["duration_minutes"] or 45,
                            "content": content,
                        },
                    },
                )

            m_me_del = re.match(r"^/api/mock-exams/(\d+)/delete$", path)
            if m_me_del:
                # CHỈ Quản trị viên (admin) mới được quyền xoá đề thi đã upload; Giáo viên bị chặn 403!
                user = self.require_user(conn, qs, body)
                if not user:
                    return
                if user["role"] != "admin":
                    return self.send_json(
                        403,
                        {
                            "error": "Giáo viên chỉ được quyền thêm đề thi, không được quyền xoá đề đã tải lên. Chỉ Quản trị viên mới có quyền xoá."
                        },
                    )
                exam_id = int(m_me_del.group(1))
                row = conn.execute("SELECT id, order_number, title FROM mock_exams WHERE id = ?", (exam_id,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy đề thi cần xoá."})
                conn.execute("DELETE FROM mock_exam_attempts WHERE exam_id = ?", (exam_id,))
                conn.execute("DELETE FROM mock_exams WHERE id = ?", (exam_id,))
                conn.commit()
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "deleted_id": exam_id,
                        "message": f"Đã xoá Đề số {row['order_number']} khỏi Phòng luyện tập.",
                    },
                )

            return self.send_json(404, {"error": "API endpoint không tồn tại."})

    # ---------------------- PUT ROUTES ----------------------
    def do_PUT(self):
        try:
            self._handle_put()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except Exception as e:
            traceback.print_exc()
            try:
                self.send_json(500, {"error": f"Hệ thống đang bận, vui lòng thử lại ({type(e).__name__})."})
            except Exception:
                pass

    def _handle_put(self):
        parsed = urlparse(self.path)
        path = strip_base_path(parsed.path)
        qs = parse_qs(parsed.query)
        body = self.read_json_body()

        with DB_LOCK:
            conn = get_conn()
            try:
                self._dispatch_put(conn, path, qs, body)
            finally:
                conn.close()

    def _dispatch_put(self, conn, path, qs, body):
        if True:
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
                invalidate_token_cache(user_id=user["id"])
                updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
                if new_password and updated["role"] in ("teacher", "student"):
                    record_password_change(conn, updated, reason="profile_change")
                return self.send_json(200, {"user": sanitize_user(updated), "message": "Đã cập nhật hồ sơ thành công!"})

            # Admin: Chỉnh sửa nhanh tên / mô tả / thứ tự Chủ đề tại mục Quản trị hệ thống
            m_meta = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)/meta$", path)
            if m_meta:
                teacher = self.require_admin(conn, qs, body)
                if not teacher:
                    return
                tid = m_meta.group(1)
                row = conn.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy chủ đề."})

                new_title = (body.get("title") or "").strip()
                if not new_title:
                    return self.send_json(400, {"error": "Tên Chủ đề không được để trống."})
                new_subtitle = (body.get("subtitle") if "subtitle" in body else (row["subtitle"] or "")).strip()
                new_order = int(body.get("order_index") or row["order_index"] or 1)
                ts = now_iso()

                content = json.loads(row["content_json"])
                content["title"] = new_title
                content["subtitle"] = new_subtitle
                content["order_index"] = new_order

                conn.execute(
                    """
                    UPDATE topics
                    SET order_index = ?, title = ?, subtitle = ?, content_json = ?, updated_by = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (new_order, new_title, new_subtitle, json.dumps(content, ensure_ascii=False), teacher["id"], ts, tid),
                )
                conn.commit()
                app_cache.invalidate_topics(tid)
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "topic": {
                            "id": tid,
                            "order_index": new_order,
                            "title": new_title,
                            "subtitle": new_subtitle,
                            "status": row["status"],
                            "updated_at": ts,
                        },
                        "message": f"Đã cập nhật tên Chủ đề thành '{new_title}'.",
                    },
                )

            # Admin: Cập nhật đề thi thử Tốt nghiệp THPT đã tải lên
            m_me_put = re.match(r"^/api/mock-exams/(\d+)$", path)
            if m_me_put:
                admin = self.require_admin(conn, qs, body)
                if not admin:
                    return
                exam_id = int(m_me_put.group(1))
                row = conn.execute("SELECT * FROM mock_exams WHERE id = ?", (exam_id,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy đề thi thử."})
                content = body.get("content")
                if not isinstance(content, dict):
                    return self.send_json(400, {"error": "Nội dung đề thi không hợp lệ."})
                total_q, max_score = compute_exam_max_score(content)
                if total_q <= 0:
                    return self.send_json(400, {"error": "Đề thi phải có ít nhất 1 câu hỏi."})
                title = (body.get("title") or row["title"]).strip()
                subtitle = (body.get("subtitle") if "subtitle" in body else (row["subtitle"] or "")).strip()
                duration_minutes = int(body.get("duration_minutes") or row["duration_minutes"] or 45)
                ts = now_iso()
                conn.execute(
                    """
                    UPDATE mock_exams
                    SET title = ?, subtitle = ?, duration_minutes = ?, content_json = ?,
                        question_count = ?, max_score = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        title,
                        subtitle,
                        duration_minutes,
                        json.dumps(content, ensure_ascii=False),
                        total_q,
                        max_score,
                        ts,
                        exam_id,
                    ),
                )
                conn.commit()
                return self.send_json(
                    200,
                    {
                        "ok": True,
                        "message": f"Đã cập nhật Đề số {row['order_number']} ({total_q} câu).",
                    },
                )

            # Admin: Update topic content (lessons, interactive video, knowledge system, quiz bank)
            m = re.match(r"^/api/topics/([a-zA-Z0-9_-]+)$", path)
            if m:
                teacher = self.require_admin(conn, qs, body)
                if not teacher:
                    return
                tid = m.group(1)
                row = conn.execute("SELECT * FROM topics WHERE id = ?", (tid,)).fetchone()
                if not row:
                    return self.send_json(404, {"error": "Không tìm thấy chủ đề."})

                content = body.get("content")
                if not isinstance(content, dict):
                    return self.send_json(400, {"error": "Dữ liệu chủ đề không hợp lệ."})

                old_content = {}
                try:
                    old_content = json.loads(row["content_json"]) or {}
                except Exception:
                    old_content = {}
                if "banner_image" not in content and old_content.get("banner_image"):
                    content["banner_image"] = old_content["banner_image"]

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
                app_cache.invalidate_topics(tid)
                return self.send_json(200, {"ok": True, "topic": content, "updated_at": ts})

            return self.send_json(404, {"error": "API endpoint không tồn tại."})

    # ---------------------- STATIC FILE SERVING ----------------------
    def serve_static(self, path, raw_path: str = ""):
        if path == "/" or path == "":
            rel = "index.html"
        else:
            rel = path.lstrip("/")

        if rel.startswith("uploads/") and EXTRA_UPLOADS_DIR:
            abs_extra = os.path.abspath(EXTRA_UPLOADS_DIR)
            candidate = os.path.abspath(
                os.path.normpath(os.path.join(abs_extra, rel[len("uploads/") :]))
            )
            try:
                in_extra = os.path.commonpath([candidate, abs_extra]) == abs_extra
            except ValueError:
                in_extra = False
            if in_extra and os.path.isfile(candidate):
                safe_path = candidate
            else:
                safe_path = os.path.normpath(os.path.join(STATIC_DIR, rel))
        else:
            safe_path = os.path.normpath(os.path.join(STATIC_DIR, rel))

        abs_static = os.path.abspath(STATIC_DIR)
        abs_safe = os.path.abspath(safe_path)
        try:
            in_static = os.path.commonpath([abs_safe, abs_static]) == abs_static
        except ValueError:
            in_static = False
        in_extra_ok = bool(
            EXTRA_UPLOADS_DIR
            and os.path.commonpath([abs_safe, os.path.abspath(EXTRA_UPLOADS_DIR)])
            == os.path.abspath(EXTRA_UPLOADS_DIR)
        )
        if not in_static and not in_extra_ok:
            self.send_error(403, "Forbidden")
            return

        if not os.path.isfile(safe_path):
            # SPA fallback to index.html for non-asset paths
            if "." not in os.path.basename(rel):
                safe_path = os.path.join(STATIC_DIR, "index.html")
                rel = "index.html"
            elif rel in (
                "favicon.ico",
                "apple-touch-icon.png",
                "apple-touch-icon-precomposed.png",
            ):
                self.send_response(204)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            else:
                self.send_error(404, "Not Found")
                return

        mime, _ = mimetypes.guess_type(safe_path)
        if not mime:
            mime = "application/octet-stream"
        if mime.startswith("text/") or mime in ("application/javascript", "application/json", "image/svg+xml"):
            mime = f"{mime}; charset=utf-8"

        try:
            raw, gz, etag, mime_out = _get_cached_static(safe_path, mime)
            if rel == "index.html":
                if BASE_PATH != "/" and (
                    raw_path == BASE_PATH or raw_path.startswith(BASE_PATH + "/")
                ):
                    base_href = BASE_PATH.rstrip("/") + "/"
                else:
                    base_href = "/"
                html_str = raw.decode("utf-8", errors="replace")
                if "<base " not in html_str.lower():
                    html_str = html_str.replace(
                        "<head>", f'<head>\n  <base href="{base_href}" />', 1
                    )
                    raw = html_str.encode("utf-8")
                    gz = gzip.compress(raw, compresslevel=6) if len(raw) >= 512 else b""
                    etag = f'W/"{hashlib.sha1(raw).hexdigest()[:14]}"'
            is_upload_img = rel.startswith("uploads/")
            if is_upload_img and raw:
                # Khớp đúng Content-Type theo magic bytes thực tế (tránh lỗi ảnh .png chứa dữ liệu JPEG trên mobile/Chrome)
                if raw[:3] == b"\xff\xd8\xff":
                    mime_out = "image/jpeg"
                elif raw[:8] == b"\x89PNG\r\n\x1a\n":
                    mime_out = "image/png"
                elif raw[:4] == b"GIF8":
                    mime_out = "image/gif"
                elif len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
                    mime_out = "image/webp"
            if is_upload_img:
                cache_hdr = "public, max-age=604800, immutable"
            elif rel == "index.html" or rel.endswith(".js") or rel.endswith(".css"):
                cache_hdr = "no-store, no-cache, must-revalidate"
            else:
                cache_hdr = "public, max-age=60, must-revalidate"

            req_etag = (self.headers.get("If-None-Match") or "").strip()
            if req_etag and req_etag == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", cache_hdr)
                self.end_headers()
                return

            use_gz = self._client_accepts_gzip() and bool(gz)
            body = gz if use_gz else raw
            self.send_response(200)
            self.send_header("Content-Type", mime_out)
            if use_gz:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_hdr)
            self.end_headers()
            if self.command != "HEAD":
                self._safe_write(body)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except Exception as e:
            traceback.print_exc()
            self.send_error(500, str(e))


class PooledHTTPServer(ThreadingHTTPServer):
    """
    Máy chủ HTTP đa luồng có giới hạn số luồng đồng thời & hàng đợi lớn (128),
    chống tràn RAM / lỗi 500 khi hàng chục học sinh truy cập cùng lúc.
    """

    request_queue_size = 128
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, max_workers: int = 24):
        super().__init__(server_address, RequestHandlerClass)
        self._pool = ThreadPoolExecutor(max_workers=max_workers)

    def process_request(self, request, client_address):
        self._pool.submit(self.process_request_thread, request, client_address)

    def server_close(self):
        try:
            self._pool.shutdown(wait=False)
        except Exception:
            pass
        super().server_close()


def prewarm_caches():
    """Nạp sẵn danh sách Chủ đề + nội dung các Chủ đề (đã nén Gzip) vào L1 RAM ngay khi khởi động."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, order_index, title, subtitle, status, content_json, updated_at FROM topics ORDER BY order_index ASC"
        ).fetchall()
        list_items = [
            {
                "id": r["id"],
                "order_index": r["order_index"],
                "title": r["title"],
                "subtitle": r["subtitle"],
                "status": r["status"],
                "updated_at": r["updated_at"],
                "banner_image": _extract_banner_from_json(r["content_json"]),
            }
            for r in rows
        ]
        app_cache.set_json_with_gzip("topics:list", {"topics": list_items}, ttl=600)
        for r in rows:
            try:
                content = json.loads(r["content_json"])
                content["updated_at"] = r["updated_at"]
                app_cache.set_json_with_gzip(f"topic:{r['id']}", {"topic": content}, ttl=900)
            except Exception:
                pass
    finally:
        conn.close()


def main():
    init_db()
    try:
        prewarm_caches()
    except Exception as exc:
        sys.stderr.write(f"[prewarm_caches] Bỏ qua lỗi tạm thời khi nạp cache lúc khởi động: {exc}\n")
        sys.stderr.flush()
    max_workers = int(os.environ.get("MAX_WORKERS", "24"))
    server = PooledHTTPServer(("0.0.0.0", PORT), Bio12Handler, max_workers=max_workers)
    port_suffix = "" if PORT == 80 else f":{PORT}"
    base_display = "" if BASE_PATH == "/" else BASE_PATH
    print(f"============================================================")
    print(f"  WEB APP GIẢNG DẠY SINH HỌC 12 (CT GDPT 2018)")
    print(f"  Địa chỉ nội bộ:   http://localhost{port_suffix}{base_display or '/'}")
    print(f"  Địa chỉ tên miền: http://{PUBLIC_HOST}{port_suffix}{base_display or '/'}")
    print(f"  Cơ sở dữ liệu:    {describe_db()}")
    print(f"  Mã đăng ký Giáo viên mặc định: {TEACHER_INVITE_CODE}")
    print(f"  Tối ưu tải cao:   ThreadPool({max_workers}) + Gzip + L1 Prewarm")
    print(f"============================================================")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng máy chủ.")
        server.server_close()


if __name__ == "__main__":
    main()
