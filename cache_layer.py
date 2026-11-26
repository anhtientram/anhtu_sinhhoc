"""
Bộ nhớ đệm đa tầng tối ưu cho Web App Sinh học 12:
- Tầng L1: In-Process LRU + TTL Cache (bộ nhớ RAM, thread-safe, phản hồi < 0.1ms)
- Tầng L2: Redis Cache (tự động kích hoạt khi cấu hình biến môi trường REDIS_URL)
  + Ưu tiên dùng thư viện `redis` nếu đã cài; nếu chưa cài tự động dùng client RESP2 thuần Python
    (hỗ trợ redis:// và rediss://, không phát sinh phụ thuộc ngoài, tự fallback an toàn về L1 khi Redis ngoại tuyến).
- Hỗ trợ sinh ETag mạnh cho HTTP 304 Not Modified và xoá cache theo mẫu ngay khi có dữ liệu mới.
"""
import gzip
import hashlib
import json
import os
import socket
import ssl
import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple
from urllib.parse import urlparse


class _PurePythonRedis:
    """Client Redis RESP2 siêu nhẹ (thuần stdlib) hỗ trợ AUTH, SELECT, PING, GET, SETEX, DEL, KEYS."""

    def __init__(self, url: str, timeout: float = 2.0):
        parsed = urlparse(url)
        self.scheme = (parsed.scheme or "redis").lower()
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 6379
        self.username = parsed.username or None
        self.password = parsed.password or None
        self.db = int((parsed.path or "/0").lstrip("/") or "0")
        self.timeout = timeout
        self._lock = threading.Lock()
        self._sock = None
        self._rfile = None

    def _close(self):
        try:
            if self._rfile:
                self._rfile.close()
        except Exception:
            pass
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        self._rfile = None

    def _connect(self):
        if self._sock is not None:
            return
        raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.scheme == "rediss":
            ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=self.host)
        raw.settimeout(self.timeout)
        self._sock = raw
        self._rfile = raw.makefile("rb")
        if self.password:
            if self.username:
                self._cmd_unlocked("AUTH", self.username, self.password)
            else:
                self._cmd_unlocked("AUTH", self.password)
        if self.db:
            self._cmd_unlocked("SELECT", str(self.db))

    def _encode_cmd(self, *parts: str) -> bytes:
        chunks = [f"*{len(parts)}\r\n".encode("utf-8")]
        for p in parts:
            b = p.encode("utf-8") if isinstance(p, str) else bytes(p)
            chunks.append(f"${len(b)}\r\n".encode("utf-8"))
            chunks.append(b + b"\r\n")
        return b"".join(chunks)

    def _read_resp(self):
        line = self._rfile.readline()
        if not line:
            raise ConnectionError("Redis closed connection")
        prefix = line[:1]
        payload = line[1:].rstrip(b"\r\n")
        if prefix == b"+":
            return payload.decode("utf-8", errors="replace")
        if prefix == b"-":
            raise RuntimeError(payload.decode("utf-8", errors="replace"))
        if prefix == b":":
            return int(payload)
        if prefix == b"$":
            n = int(payload)
            if n < 0:
                return None
            data = self._rfile.read(n + 2)
            return data[:-2]
        if prefix == b"*":
            n = int(payload)
            if n < 0:
                return None
            return [self._read_resp() for _ in range(n)]
        raise RuntimeError(f"Unexpected RESP prefix: {prefix!r}")

    def _cmd_unlocked(self, *parts):
        self._sock.sendall(self._encode_cmd(*parts))
        return self._read_resp()

    def execute(self, *parts):
        with self._lock:
            for attempt in range(2):
                try:
                    self._connect()
                    return self._cmd_unlocked(*parts)
                except Exception:
                    self._close()
                    if attempt == 1:
                        raise

    def ping(self) -> bool:
        return self.execute("PING") == "PONG"

    def get(self, key: str) -> Optional[bytes]:
        return self.execute("GET", key)

    def setex(self, key: str, ttl: int, value: bytes):
        self.execute("SETEX", key, str(int(ttl)), value)

    def delete(self, *keys: str):
        if keys:
            self.execute("DEL", *keys)

    def delete_prefix(self, prefix: str):
        keys = self.execute("KEYS", f"{prefix}*") or []
        if keys:
            str_keys = [k.decode("utf-8", errors="ignore") if isinstance(k, bytes) else str(k) for k in keys]
            self.execute("DEL", *str_keys)


class HybridCache:
    """
    Cache đa tầng L1 (LRU RAM) + L2 (Redis qua REDIS_URL).
    Tối ưu lưu sẵn JSON bytes + ETag để phục vụ HTTP 304 Not Modified cực nhanh.
    """

    def __init__(self, max_l1_items: int = 256, default_ttl: int = 300):
        self.prefix = os.environ.get("CACHE_PREFIX", "sinhhoc12:")
        self.max_l1_items = max_l1_items
        self.default_ttl = default_ttl
        self._lock = threading.Lock()
        # key -> (expire_ts, raw_bytes, gz_bytes, etag)
        self._l1: OrderedDict[str, Tuple[float, bytes, bytes, str]] = OrderedDict()

        self.redis_url = (os.environ.get("REDIS_URL") or "").strip()
        self._redis = None
        self._redis_connected = False
        self._redis_lib = "none"
        self._last_redis_check = 0.0

        self._stats = {
            "l1_hits": 0,
            "redis_hits": 0,
            "misses": 0,
            "writes": 0,
            "invalidations": 0,
            "redis_errors": 0,
        }

        if self.redis_url:
            self._init_redis()

    def _init_redis(self):
        try:
            import redis as redis_pkg  # type: ignore

            client = redis_pkg.from_url(
                self.redis_url,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
                decode_responses=False,
            )
            client.ping()
            self._redis = client
            self._redis_connected = True
            self._redis_lib = "redis-py"
            return
        except Exception:
            pass

        try:
            client = _PurePythonRedis(self.redis_url, timeout=2.0)
            if client.ping():
                self._redis = client
                self._redis_connected = True
                self._redis_lib = "stdlib-resp2"
        except Exception:
            self._redis = None
            self._redis_connected = False

    def _make_etag(self, payload_bytes: bytes) -> str:
        digest = hashlib.sha1(payload_bytes).hexdigest()[:16]
        return f'W/"{digest}"'

    def _full_key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def _compress(self, data: bytes) -> bytes:
        if len(data) < 512:
            return b""
        return gzip.compress(data, compresslevel=6)

    def get_payload(self, key: str) -> Tuple[Optional[bytes], Optional[str], str]:
        """Trả về (json_bytes, etag, source) trong đó source là HIT-L1 | HIT-REDIS | MISS."""
        raw, _gz, etag, source = self.get_payload_with_gzip(key)
        return raw, etag, source

    def get_payload_with_gzip(self, key: str) -> Tuple[Optional[bytes], Optional[bytes], Optional[str], str]:
        """Trả về (raw_bytes, gz_bytes, etag, source) để phản hồi Gzip cực nhanh không tốn CPU."""
        now = time.time()
        with self._lock:
            entry = self._l1.get(key)
            if entry is not None:
                exp, data, gz_data, etag = entry
                if exp > now:
                    self._l1.move_to_end(key)
                    self._stats["l1_hits"] += 1
                    return data, gz_data, etag, "HIT-L1"
                self._l1.pop(key, None)

        # Thử đọc tầng L2 Redis nếu đã cấu hình
        if self._redis is not None:
            try:
                raw = self._redis.get(self._full_key(key))
                if raw is not None:
                    data = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
                    gz_data = self._compress(data)
                    etag = self._make_etag(data)
                    with self._lock:
                        self._put_l1_unlocked(key, data, gz_data, etag, self.default_ttl)
                        self._stats["redis_hits"] += 1
                    return data, gz_data, etag, "HIT-REDIS"
            except Exception:
                with self._lock:
                    self._stats["redis_errors"] += 1
                self._redis_connected = False

        with self._lock:
            self._stats["misses"] += 1
        return None, None, None, "MISS"

    def _put_l1_unlocked(self, key: str, data: bytes, gz_data: bytes, etag: str, ttl: int):
        self._l1[key] = (time.time() + ttl, data, gz_data, etag)
        self._l1.move_to_end(key)
        while len(self._l1) > self.max_l1_items:
            self._l1.popitem(last=False)

    def set_json(self, key: str, obj: Any, ttl: Optional[int] = None) -> Tuple[bytes, str]:
        """Serialize object -> UTF-8 JSON bytes, nén sẵn Gzip, tính ETag và ghi vào L1 + L2 Redis."""
        raw, _gz, etag = self.set_json_with_gzip(key, obj, ttl=ttl)
        return raw, etag

    def set_json_with_gzip(self, key: str, obj: Any, ttl: Optional[int] = None) -> Tuple[bytes, bytes, str]:
        ttl_s = int(ttl or self.default_ttl)
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        gz_payload = self._compress(payload)
        etag = self._make_etag(payload)

        with self._lock:
            self._put_l1_unlocked(key, payload, gz_payload, etag, ttl_s)
            self._stats["writes"] += 1

        if self._redis is not None:
            try:
                # L2 Redis giữ TTL gấp đôi L1
                self._redis.setex(self._full_key(key), ttl_s * 2, payload)
                self._redis_connected = True
            except Exception:
                with self._lock:
                    self._stats["redis_errors"] += 1
                self._redis_connected = False

        return payload, gz_payload, etag

    def invalidate_keys(self, *keys: str):
        with self._lock:
            for k in keys:
                self._l1.pop(k, None)
            self._stats["invalidations"] += 1

        if self._redis is not None and keys:
            try:
                fulls = [self._full_key(k) for k in keys]
                self._redis.delete(*fulls)
            except Exception:
                pass

    def invalidate_prefix(self, prefix: str):
        with self._lock:
            to_del = [k for k in self._l1.keys() if k.startswith(prefix)]
            for k in to_del:
                self._l1.pop(k, None)
            self._stats["invalidations"] += 1

        if self._redis is not None:
            try:
                if hasattr(self._redis, "delete_prefix"):
                    self._redis.delete_prefix(self._full_key(prefix))
                else:
                    matched = self._redis.keys(self._full_key(prefix) + "*")
                    if matched:
                        self._redis.delete(*matched)
            except Exception:
                pass

    def invalidate_topics(self, topic_id: Optional[str] = None):
        keys = ["topics:list", "admin:exam_pool"]
        if topic_id:
            keys.append(f"topic:{topic_id}")
            self.invalidate_keys(*keys)
        else:
            self.invalidate_keys(*keys)
            self.invalidate_prefix("topic:")

    def clear_all(self):
        with self._lock:
            self._l1.clear()
            self._stats["invalidations"] += 1
        if self._redis is not None:
            try:
                if hasattr(self._redis, "delete_prefix"):
                    self._redis.delete_prefix(self.prefix)
                else:
                    matched = self._redis.keys(self.prefix + "*")
                    if matched:
                        self._redis.delete(*matched)
            except Exception:
                pass

    def stats(self) -> dict:
        with self._lock:
            total_reads = self._stats["l1_hits"] + self._stats["redis_hits"] + self._stats["misses"]
            hits = self._stats["l1_hits"] + self._stats["redis_hits"]
            hit_rate = round((hits / total_reads) * 100.0, 1) if total_reads > 0 else 100.0
            l1_count = len(self._l1)
            l1_keys = list(self._l1.keys())
            st = dict(self._stats)

        if self.redis_url and self._redis_connected:
            mode = f"Redis ({self._redis_lib}) + L1 LRU RAM"
        elif self.redis_url:
            mode = "L1 LRU RAM (Redis tạm ngoại tuyến — tự fallback)"
        else:
            mode = "L1 LRU RAM + HTTP ETag (sẵn sàng kết nối REDIS_URL)"

        return {
            "backend": mode,
            "redis_configured": bool(self.redis_url),
            "redis_connected": bool(self._redis_connected),
            "l1_entries": l1_count,
            "cached_keys": l1_keys[:20],
            "hit_rate_percent": hit_rate,
            **st,
        }


# Singleton cache dùng chung toàn bộ server
app_cache = HybridCache(max_l1_items=256, default_ttl=300)
