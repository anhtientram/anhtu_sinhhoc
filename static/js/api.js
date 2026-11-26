// API Client + Session Attendance Tracker (Vào lớp / Heartbeat / Rời lớp)

const TOKEN_KEY = "sinhhoc12_auth_token";
const SESSION_KEY = "sinhhoc12_active_session_id";
const TOPIC_STORAGE_PREFIX = "sh12_topic_v1:";

const _topicMemCache = new Map();
const _attemptsMemCache = new Map();
const _teacherMemState = {
  overview: null,
  cacheInfo: null,
  examPool: null,
  loadedAt: 0,
  subtab: "members",
  contentSubMode: "add_topic",
};

export const clientCache = {
  getTopic(id, expectedUpdatedAt = "") {
    if (!id) return null;
    const mem = _topicMemCache.get(id);
    if (mem && (!expectedUpdatedAt || !mem.updated_at || mem.updated_at === expectedUpdatedAt)) {
      return mem;
    }
    try {
      const raw = sessionStorage.getItem(TOPIC_STORAGE_PREFIX + id);
      if (raw) {
        const parsed = JSON.parse(raw);
        const topic = parsed?.topic;
        if (topic && (!expectedUpdatedAt || !topic.updated_at || topic.updated_at === expectedUpdatedAt)) {
          _topicMemCache.set(id, topic);
          return topic;
        }
      }
    } catch {}
    return null;
  },

  setTopic(id, topic) {
    if (!id || !topic) return;
    _topicMemCache.set(id, topic);
    const payload = JSON.stringify({ updated_at: topic.updated_at || "", topic });
    try {
      sessionStorage.setItem(TOPIC_STORAGE_PREFIX + id, payload);
    } catch {
      try {
        for (let i = 0; i < sessionStorage.length; i++) {
          const k = sessionStorage.key(i);
          if (k && k.startsWith(TOPIC_STORAGE_PREFIX) && k !== TOPIC_STORAGE_PREFIX + id) {
            sessionStorage.removeItem(k);
            break;
          }
        }
        sessionStorage.setItem(TOPIC_STORAGE_PREFIX + id, payload);
      } catch {}
    }
  },

  invalidateTopic(id = "") {
    if (id) {
      _topicMemCache.delete(id);
      try {
        sessionStorage.removeItem(TOPIC_STORAGE_PREFIX + id);
      } catch {}
      return;
    }
    _topicMemCache.clear();
    try {
      const keys = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        if (k && k.startsWith(TOPIC_STORAGE_PREFIX)) keys.push(k);
      }
      keys.forEach((k) => sessionStorage.removeItem(k));
    } catch {}
  },

  getAttempts(topicId = "") {
    return _attemptsMemCache.get(topicId || "__all__") || null;
  },

  setAttempts(topicId = "", attempts = []) {
    _attemptsMemCache.set(topicId || "__all__", attempts);
  },

  invalidateAttempts(topicId = "") {
    if (topicId) _attemptsMemCache.delete(topicId);
    else _attemptsMemCache.clear();
  },

  getTeacherData() {
    return _teacherMemState;
  },

  setTeacherData(partial) {
    Object.assign(_teacherMemState, partial || {});
  },

  invalidateTeacherData() {
    _teacherMemState.overview = null;
    _teacherMemState.cacheInfo = null;
    _teacherMemState.examPool = null;
    _teacherMemState.loadedAt = 0;
  },

  clearAll() {
    this.invalidateTopic("");
    _attemptsMemCache.clear();
    this.invalidateTeacherData();
    _teacherMemState.subtab = "members";
    _teacherMemState.contentSubMode = "add_topic";
  },
};

export const BASE_PATH = window.location.pathname.startsWith("/sinhhoc12") ? "/sinhhoc12" : "";

export function withBase(path) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  if (BASE_PATH && path.startsWith(BASE_PATH + "/")) return path;
  if (path.startsWith("/")) return `${BASE_PATH}${path}`;
  return `${BASE_PATH}/${path}`;
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getStoredSessionId() {
  const val = localStorage.getItem(SESSION_KEY);
  return val ? Number(val) : null;
}

export function setStoredSessionId(id) {
  if (id) localStorage.setItem(SESSION_KEY, String(id));
  else localStorage.removeItem(SESSION_KEY);
}

export async function apiRequest(path, options = {}) {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const method = (options.method || "GET").toUpperCase();
  const maxAttempts = method === "GET" ? 2 : 1;
  let lastErr = null;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await fetch(withBase(path), {
        ...options,
        headers,
      });

      const text = await res.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { raw: text };
      }

      if (!res.ok) {
        if (attempt < maxAttempts && [500, 502, 503, 504].includes(res.status)) {
          await new Promise((r) => setTimeout(r, 600));
          continue;
        }
        throw new Error(data.error || `Lỗi máy chủ (${res.status})`);
      }
      return data;
    } catch (err) {
      lastErr = err;
      if (attempt < maxAttempts && (err instanceof TypeError || /50[0234]/.test(String(err.message)))) {
        await new Promise((r) => setTimeout(r, 600));
        continue;
      }
      throw err;
    }
  }
  throw lastErr || new Error("Không thể kết nối máy chủ.");
}

async function apiBinaryUpload(path, file, onProgress = null) {
  const token = getToken();
  const fullUrl = withBase(path);

  if (typeof onProgress === "function" && typeof XMLHttpRequest !== "undefined") {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", fullUrl, true);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable && ev.total > 0) {
          const percent = Math.min(99, Math.round((ev.loaded / ev.total) * 100));
          onProgress({ phase: "uploading", loaded: ev.loaded, total: ev.total, percent });
        }
      };
      xhr.upload.onload = () => {
        onProgress({ phase: "processing", loaded: file.size || 0, total: file.size || 0, percent: 100 });
      };
      xhr.onload = () => {
        const text = xhr.responseText || "";
        let data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          data = { raw: text };
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error(data.error || `Lỗi máy chủ (${xhr.status})`));
        }
      };
      xhr.onerror = () => reject(new Error("Lỗi kết nối khi tải file lên máy chủ."));
      xhr.ontimeout = () => reject(new Error("Quá thời gian xử lý file trên máy chủ."));
      xhr.send(file);
    });
  }

  const headers = { "Content-Type": "application/octet-stream" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(fullUrl, {
    method: "POST",
    headers,
    body: file,
  });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    throw new Error(data.error || `Lỗi máy chủ (${res.status})`);
  }
  return data;
}

export const api = {
  login: (identifier, password, role = "") =>
    apiRequest("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password, role }),
    }),

  firstLoginSetup: (payload) =>
    apiRequest("/api/auth/first-login-setup", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  register: (payload) =>
    apiRequest("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  logout: () =>
    apiRequest("/api/auth/logout", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  me: () => apiRequest("/api/auth/me"),

  updateProfile: (payload) =>
    apiRequest("/api/profile", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  listTopics: () => apiRequest("/api/topics"),
  getTopic: (id) => apiRequest(`/api/topics/${id}`),
  createTopic: (payload) =>
    apiRequest("/api/topics", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateTopic: (id, content) =>
    apiRequest(`/api/topics/${id}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),

  importTopicFile: (id, fileOrPayload, meta = {}) => {
    if (typeof Blob !== "undefined" && fileOrPayload instanceof Blob) {
      const qs = new URLSearchParams({
        filename: fileOrPayload.name || meta.filename || "upload.docx",
        preview_only: meta.preview_only === false ? "0" : "1",
        replace_review: meta.replace_review === false ? "0" : "1",
      });
      if (meta.sections) qs.set("sections", JSON.stringify(meta.sections));
      return apiBinaryUpload(`/api/topics/${encodeURIComponent(id)}/import-file?${qs.toString()}`, fileOrPayload, meta.onProgress);
    }
    return apiRequest(`/api/topics/${encodeURIComponent(id)}/import-file`, {
      method: "POST",
      body: JSON.stringify(fileOrPayload),
    });
  },

  previewNewTopicFile: (fileOrPayload, meta = {}) => {
    if (typeof Blob !== "undefined" && fileOrPayload instanceof Blob) {
      const qs = new URLSearchParams({
        filename: fileOrPayload.name || meta.filename || "upload.docx",
        order_index: String(meta.order_index || ""),
        title: meta.title || "",
        subtitle: meta.subtitle || "",
      });
      return apiBinaryUpload(`/api/topics/preview-new-file?${qs.toString()}`, fileOrPayload, meta.onProgress);
    }
    return apiRequest("/api/topics/preview-new-file", {
      method: "POST",
      body: JSON.stringify(fileOrPayload),
    });
  },

  publishNewTopic: (payload) =>
    apiRequest("/api/topics/publish-new", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteTopic: (id) =>
    apiRequest(`/api/topics/${encodeURIComponent(id)}/delete`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  cleanupDraftTopic: (id) =>
    apiRequest(`/api/topics/${encodeURIComponent(id)}/cleanup-draft`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  cacheStatus: () => apiRequest("/api/admin/cache-status"),

  cacheClear: () =>
    apiRequest("/api/admin/cache-clear", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  checkinSession: (topic_id, tab) =>
    apiRequest("/api/sessions/checkin", {
      method: "POST",
      body: JSON.stringify({ topic_id, tab }),
    }),

  heartbeatSession: (session_id, topic_id, tab) =>
    apiRequest("/api/sessions/heartbeat", {
      method: "POST",
      body: JSON.stringify({ session_id, topic_id, tab }),
    }),

  checkoutSession: (session_id, tab) =>
    apiRequest("/api/sessions/checkout", {
      method: "POST",
      body: JSON.stringify({ session_id, tab }),
    }),

  mySessions: () => apiRequest("/api/sessions/my"),

  submitQuiz: (payload) =>
    apiRequest("/api/quiz/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  myQuizAttempts: (topic_id = "") =>
    apiRequest(`/api/quiz/my-attempts${topic_id ? `?topic_id=${encodeURIComponent(topic_id)}` : ""}`),

  saveProgress: (payload) =>
    apiRequest("/api/progress", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  myProgress: () => apiRequest("/api/progress/my"),

  teacherOverview: () => apiRequest("/api/teacher/overview"),

  adminExamPool: () => apiRequest("/api/admin/exam-pool"),

  adminGenerateExam: (payload) =>
    apiRequest("/api/admin/generate-exam", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  adminExamDownloadUrl: (jobId, fmt) => {
    const token = encodeURIComponent(getToken());
    return withBase(`/api/admin/exam-download/${encodeURIComponent(jobId)}/${encodeURIComponent(fmt)}?token=${token}`);
  },

  adminAddTeacher: (username, password = "123456@") =>
    apiRequest("/api/admin/teachers", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  adminDeleteUser: (userId) =>
    apiRequest(`/api/admin/users/${encodeURIComponent(userId)}/delete`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  adminMarkPasswordAlertsRead: () =>
    apiRequest("/api/admin/password-alerts/mark-read", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  staffAddStudents: (payload) =>
    apiRequest("/api/staff/students", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  staffImportStudentsExcel: (filename, content_base64) =>
    apiRequest("/api/staff/students/import-excel", {
      method: "POST",
      body: JSON.stringify({ filename, content_base64 }),
    }),

  studentImportTemplateUrl: () => {
    const token = encodeURIComponent(getToken());
    return withBase(`/api/staff/student-import-template?token=${token}`);
  },

  exportSessionsUrl: (className = "") => {
    const token = encodeURIComponent(getToken());
    const cls = className ? `&class_name=${encodeURIComponent(className)}` : "";
    return withBase(`/api/teacher/sessions/export?token=${token}${cls}`);
  },
};

/**
 * Gửi tín hiệu rời lớp học đáng tin cậy khi học sinh đóng tab / thoát trình duyệt
 */
export function sendBeaconCheckout(sessionId, currentTab) {
  const token = getToken();
  if (!token || !sessionId) return;
  const payload = JSON.stringify({
    token,
    session_id: sessionId,
    tab: currentTab,
  });
  try {
    const blob = new Blob([payload], { type: "application/json" });
    navigator.sendBeacon(withBase("/api/sessions/checkout"), blob);
  } catch {
    // Fallback
  }
}

export function formatDateTimeVN(isoStr) {
  if (!isoStr) return "—";
  const d = new Date(isoStr);
  if (Number.isNaN(d.getTime())) return isoStr;
  return d.toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function formatTimeShort(isoStr) {
  if (!isoStr) return "--:--";
  const d = new Date(isoStr);
  if (Number.isNaN(d.getTime())) return "--:--";
  return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export function formatDuration(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  if (hrs > 0) return `${hrs}g ${pad(mins)}p ${pad(secs)}s`;
  return `${pad(mins)}:${pad(secs)}`;
}
