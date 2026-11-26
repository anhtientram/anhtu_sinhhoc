// API Client + Session Attendance Tracker (Vào lớp / Heartbeat / Rời lớp)

const TOKEN_KEY = "sinhhoc12_auth_token";
const SESSION_KEY = "sinhhoc12_active_session_id";

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

  importTopicFile: (id, payload) =>
    apiRequest(`/api/topics/${id}/import-file`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  previewNewTopicFile: (payload) =>
    apiRequest("/api/topics/preview-new-file", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

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
