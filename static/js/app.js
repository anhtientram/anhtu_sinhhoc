import {
  api,
  clientCache,
  formatDateTimeVN,
  formatDuration,
  formatTimeShort,
  getStoredSessionId,
  getToken,
  parseServerDate,
  sendBeaconCheckout,
  setStoredSessionId,
  setToken,
  withBase,
} from "./api.js";
import { mountInteractiveDiagram } from "./diagrams.js";
import { initContentGuard, setContentGuardAdmin } from "./content_guard.js?v=20261128-v13";
import { escapeHtml, formatBioHtml } from "./format.js";
import {
  bindInteractiveExerciseEvents,
  collectInteractiveUnitIds,
  renderDocumentBlocksInteractive,
  renderInteractiveToolbar,
} from "./interactive_blocks.js";
import { mountMockExamSection, stopMockExamTimers } from "./mock_exam.js";
import { mountQuizSection } from "./quiz.js";
import { parseRoute, resetUrlToHome, syncBrowserUrl } from "./router.js";
import { mountTeacherDashboard } from "./teacher.js";
import { mountYoutubeLibrary } from "./youtube_videos.js";

const appEl = document.getElementById("app");
const toastContainer = document.getElementById("toast-container");

const ICONS = {
  dna: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 15c6.667-6 13.333 0 20-6"/><path d="M9 22c1.798-1.998 2.518-3.995 2.807-5.993"/><path d="M15 2c-1.798 1.998-2.518 3.995-2.807 5.993"/><path d="M17 6l-2.5-2.5"/><path d="M14 8l-1-1"/><path d="M7 18l2.5 2.5"/><path d="M6.5 12.5l1 1"/><path d="M16.5 10.5l1 1"/></svg>`,
  book: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>`,
  layers: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
  checkSquare: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`,
  award: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg>`,
  barChart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
  user: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  menu: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>`,
  panelLeft: `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>`,
  chevronLeft: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>`,
  chevronRight: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>`,
  feather: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"/><line x1="16" y1="8" x2="2" y2="22"/><line x1="17.5" y1="15" x2="9" y2="15"/></svg>`,
  helixBg: `<svg class="bio-helix-watermark" viewBox="0 0 180 120" fill="none" aria-hidden="true"><path d="M12 18 C46 18, 52 102, 88 102 C124 102, 130 18, 168 18" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"/><path d="M12 102 C46 102, 52 18, 88 18 C124 18, 130 102, 168 102" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-dasharray="4 4"/><line x1="34" y1="32" x2="34" y2="88" stroke="currentColor" stroke-width="2"/><line x1="56" y1="54" x2="56" y2="66" stroke="currentColor" stroke-width="2"/><line x1="88" y1="22" x2="88" y2="98" stroke="currentColor" stroke-width="2"/><line x1="120" y1="54" x2="120" y2="66" stroke="currentColor" stroke-width="2"/><line x1="142" y1="32" x2="142" y2="88" stroke="currentColor" stroke-width="2"/><circle cx="34" cy="32" r="3.5" fill="currentColor"/><circle cx="88" cy="22" r="3.5" fill="currentColor"/><circle cx="142" cy="88" r="3.5" fill="currentColor"/></svg>`,
};

function readStoredRailCollapsed() {
  try {
    return localStorage.getItem("sh12_rail_collapsed") === "1";
  } catch {
    return false;
  }
}

function saveStoredRailCollapsed(val) {
  try {
    localStorage.setItem("sh12_rail_collapsed", val ? "1" : "0");
  } catch { }
}

const state = {
  user: null,
  topicsList: [],
  topicCache: {},
  topicLoading: false,
  loadingTopicId: "",
  activeTopicId: "chu-de-1",
  activeTopic: null,
  activeTab: "theory", // 'theory' | 'knowledge' | 'review' | 'mock_exam' | 'teacher' | 'profile'
  theoryMode: "lessons", // 'lessons' | 'youtube'
  activeLessonId: "",
  knowledgeMode: "source", // 'source' | 'mindmap'
  knowledgeUnitIdx: 0,
  teacherSubtab: "members",
  teacherContentSubMode: "add_topic",
  teacherExamMixerMode: "word",
  pendingInitialRoute: parseRoute(),
  teacherPreviewAsStudent: false,
  presentationMode: false,
  mobileMenuOpen: false,
  topicsRailCollapsed: readStoredRailCollapsed(),
  railScrollTop: 0,

  activeSession: null,
  sessionElapsedSeconds: 0,
  sessionTickTimer: null,
  heartbeatTimer: null,
  lastHeartbeatTs: 0,

  completedLessonIds: new Set(),
  mySessions: [],

  loginRole: "admin", // 'admin' | 'teacher' | 'student'
};

function isStaffRole(role) {
  return role === "admin" || role === "teacher";
}

function applyRouteGuardForUser(route, user) {
  if (!route) return route;
  const guarded = { ...route };
  if (!isStaffRole(user?.role) && guarded.activeTab === "teacher") {
    guarded.activeTab = "theory";
  }
  if (
    user?.role !== "admin" &&
    guarded.activeTab === "teacher" &&
    (guarded.teacherSubtab === "content" || guarded.teacherSubtab === "pw_alerts")
  ) {
    guarded.teacherSubtab = "members";
  }
  return guarded;
}

function syncCurrentUrl(replace = false) {
  if (!state.user || state.user.must_change_password) return;
  syncBrowserUrl(
    {
      activeTab: state.activeTab,
      topicId: state.activeTopicId,
      lessonId: state.activeLessonId,
      theoryMode: state.theoryMode,
      knowledgeMode: state.knowledgeMode,
      knowledgeUnitIdx: state.knowledgeUnitIdx,
      teacherSubtab: state.teacherSubtab,
      teacherContentSubMode: state.teacherContentSubMode,
      teacherExamMixerMode: state.teacherExamMixerMode,
    },
    { replace }
  );
}

function roleDisplayName(role) {
  if (role === "admin") return "Quản trị viên";
  if (role === "teacher") return "Giáo viên";
  return "Học sinh";
}

function showToast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  toastContainer.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.25s";
    setTimeout(() => el.remove(), 260);
  }, 3200);
}

function getInitials(name = "") {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "U";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// ================== SESSION ATTENDANCE LIFECYCLE ==================
function stopSessionTimers() {
  if (state.sessionTickTimer) {
    clearInterval(state.sessionTickTimer);
    state.sessionTickTimer = null;
  }
  if (state.heartbeatTimer) {
    clearInterval(state.heartbeatTimer);
    state.heartbeatTimer = null;
  }
}

function startSessionTimers() {
  stopSessionTimers();
  if (!state.activeSession) return;

  const enterMs = parseServerDate(state.activeSession.enter_time).getTime();
  state.sessionElapsedSeconds = Number.isNaN(enterMs)
    ? state.activeSession.duration_seconds || 0
    : Math.max(0, Math.floor((Date.now() - enterMs) / 1000));

  state.sessionTickTimer = setInterval(() => {
    state.sessionElapsedSeconds += 1;
    const clockEl = document.getElementById("live-session-clock");
    if (clockEl) {
      clockEl.textContent = formatDuration(state.sessionElapsedSeconds);
    }
  }, 1000);

  state.heartbeatTimer = setInterval(async () => {
    if (!state.activeSession) return;
    try {
      state.lastHeartbeatTs = Date.now();
      await api.heartbeatSession(state.activeSession.id, state.activeTopicId, state.activeTab);
    } catch { }
  }, 45000);
}

function sendThrottledHeartbeat(topicId, tab) {
  if (!state.activeSession) return;
  const nowMs = Date.now();
  if (nowMs - (state.lastHeartbeatTs || 0) < 20000) return;
  state.lastHeartbeatTs = nowMs;
  api.heartbeatSession(state.activeSession.id, topicId, tab).catch(() => { });
}

async function ensureStudentCheckedIn() {
  if (!state.user || state.user.role !== "student") return;
  if (state.activeSession && state.activeSession.status === "active") {
    startSessionTimers();
    return;
  }
  try {
    const res = await api.checkinSession(state.activeTopicId, state.activeTab);
    state.activeSession = res.session;
    setStoredSessionId(res.session.id);
    startSessionTimers();
    showToast(`Đã ghi nhận vào lớp lúc ${formatTimeShort(res.session.enter_time)}`, "success");
  } catch (err) {
    console.error("Check-in error:", err);
  }
}

async function handleLeaveClass(shouldLogout = false) {
  if (state.activeSession) {
    try {
      const res = await api.checkoutSession(state.activeSession.id, state.activeTab);
      const dur = res.session?.duration_seconds ?? state.sessionElapsedSeconds;
      showToast(`Đã ghi nhận rời lớp học (${formatDuration(dur)})`, "success");
    } catch { }
    state.activeSession = null;
    setStoredSessionId(null);
    stopSessionTimers();
  }

  if (shouldLogout) {
    stopMockExamTimers();
    try {
      await api.logout();
    } catch { }
    setToken("");
    clientCache.clearAll();
    state.user = null;
    state.topicsList = [];
    state.topicCache = {};
    state.activeTopic = null;
    state.activeTab = "theory";
    state.theoryMode = "lessons";
    state.knowledgeMode = "source";
    state.knowledgeUnitIdx = 0;
    state.teacherSubtab = "members";
    state.teacherContentSubMode = "add_topic";
    state.teacherExamMixerMode = "word";
    state.teacherPreviewAsStudent = false;
    document.body.classList.remove("presentation-mode");
    resetUrlToHome();
    render();
  } else {
    render();
  }
}

window.addEventListener("pagehide", () => {
  if (state.user?.role === "student" && state.activeSession?.id) {
    sendBeaconCheckout(state.activeSession.id, state.activeTab);
  }
});

// ================== DATA LOADERS ==================
async function loadTopicsAndActive(
  topicId = state.activeTopicId,
  forceRefresh = false,
  preferredLessonId = ""
) {
  if (!state.topicsList.length || forceRefresh) {
    const listRes = await api.listTopics();
    state.topicsList = listRes.topics || [];
  }
  const chosenId =
    (topicId && state.topicsList.some((t) => t.id === topicId) ? topicId : state.topicsList[0]?.id) ||
    "chu-de-1";
  state.activeTopicId = chosenId;
  const topicMeta = state.topicsList.find((t) => t.id === chosenId);
  const cached = !forceRefresh ? (state.topicCache[chosenId] || clientCache.getTopic(chosenId, topicMeta?.updated_at)) : null;

  if (cached) {
    state.activeTopic = cached;
    state.topicCache[chosenId] = cached;
  } else {
    const detailRes = await api.getTopic(chosenId);
    state.activeTopic = detailRes.topic;
    state.topicCache[chosenId] = detailRes.topic;
    clientCache.setTopic(chosenId, detailRes.topic);
  }

  const lessons = state.activeTopic?.lessons || [];
  if (lessons.length) {
    if (preferredLessonId && lessons.some((l) => l.id === preferredLessonId)) {
      state.activeLessonId = preferredLessonId;
    } else {
      state.activeLessonId = lessons[0].id;
    }
  } else {
    state.activeLessonId = "";
  }
}

async function switchTopicSmoothly(targetId, preferredLessonId = "", skipUrlSync = false) {
  if (!targetId) return;
  if (
    targetId === state.activeTopicId &&
    state.activeTopic &&
    !state.topicLoading &&
    !preferredLessonId
  ) {
    if (!skipUrlSync) syncCurrentUrl(false);
    return;
  }

  state.mobileMenuOpen = false;
  const topicMeta = state.topicsList.find((t) => t.id === targetId);
  const cached = state.topicCache[targetId] || clientCache.getTopic(targetId, topicMeta?.updated_at);

  // Cache hit: đổi chủ đề tức thì, 0 request GET /api/topics/<id>
  if (cached) {
    state.topicCache[targetId] = cached;
    state.activeTopicId = targetId;
    state.activeTopic = cached;
    state.topicLoading = false;
    state.loadingTopicId = "";
    const lessons = cached?.lessons || [];
    state.activeLessonId =
      preferredLessonId && lessons.some((l) => l.id === preferredLessonId)
        ? preferredLessonId
        : lessons[0]?.id || "";
    state.knowledgeUnitIdx = 0;
    sendThrottledHeartbeat(targetId, state.activeTab);
    if (!skipUrlSync) syncCurrentUrl(false);
    renderMainShell();
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }

  state.activeTopicId = targetId;
  state.loadingTopicId = targetId;
  state.topicLoading = true;
  if (!skipUrlSync) syncCurrentUrl(false);
  renderMainShell();

  try {
    const detailRes = await api.getTopic(targetId);

    // Tránh race-condition nếu người dùng bấm đổi sang chủ đề khác trong lúc đang tải
    if (state.activeTopicId !== targetId) return;

    state.activeTopic = detailRes.topic;
    state.topicCache[targetId] = detailRes.topic;
    clientCache.setTopic(targetId, detailRes.topic);
    const lessons = detailRes.topic?.lessons || [];
    state.activeLessonId =
      preferredLessonId && lessons.some((l) => l.id === preferredLessonId)
        ? preferredLessonId
        : lessons[0]?.id || "";
    state.knowledgeUnitIdx = 0;
    sendThrottledHeartbeat(targetId, state.activeTab);
    if (!skipUrlSync) syncCurrentUrl(true);
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    if (state.activeTopicId === targetId) {
      state.topicLoading = false;
      state.loadingTopicId = "";
      renderMainShell();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }
}

async function loadMyProgressAndSessions() {
  try {
    const [progRes, sessRes] = await Promise.all([api.myProgress(), api.mySessions()]);
    state.completedLessonIds = new Set(
      (progRes.progress || []).filter((p) => p.completed).map((p) => p.lesson_id)
    );
    state.mySessions = sessRes.sessions || [];
  } catch { }
}

// ================== AUTH VIEW (3 PHÂN QUYỀN RIÊNG BIỆT) ==================
function renderAuthView() {
  const roleMeta = {
    admin: {
      title: "Đăng nhập Quản trị viên",
      desc: "Toàn quyền quản trị hệ thống, thêm/xoá giáo viên, thêm học sinh, trộn đề và theo dõi báo cáo đổi mật khẩu.",
      placeholder: "bachanhtu",
    },
    teacher: {
      title: "Đăng nhập Giáo viên",
      desc: "Quản lý lớp học, thêm học sinh (Excel/thủ công), chỉnh sửa nội dung, trộn đề theo ma trận và theo dõi điểm.",
      placeholder: "Tên đăng nhập do Quản trị viên cấp",
    },
    student: {
      title: "Đăng nhập Học sinh",
      desc: "Học lý thuyết, hệ thống kiến thức, làm bài ôn tập 3 phần và ghi nhận thời gian vào/rời lớp.",
      placeholder: "Tên đăng nhập viết liền không dấu",
    },
  };
  const cur = roleMeta[state.loginRole] || roleMeta.student;

  appEl.innerHTML = `
    <div class="auth-page">
      <section class="auth-hero">
        <div class="auth-brand">
          <div class="brand-mark">${ICONS.dna}</div>
          <div>
            <div style="font-weight:700;font-size:1rem;">Sinh học 12</div>
            <div style="font-size:0.78rem;color:#94a3b8;">Chương trình GDPT 2018</div>
          </div>
        </div>

        <div class="auth-hero-main">
          <span class="pill" style="background:rgba(20,184,166,0.18);color:#5eead4;border-color:rgba(94,234,212,0.3);">
            Hệ thống Giảng dạy &amp; Ôn tập
          </span>
          <h1>Nền tảng học tập khoa học bộ môn Sinh học 12</h1>
          <p>
            Phân quyền chặt chẽ cho 3 nhóm tài khoản: Quản trị viên, Giáo viên và Học sinh xuyên suốt các chủ đề di truyền học và biến dị.
          </p>

          <div class="hero-points">
            <div class="hero-point">
              <span class="hero-point-num">1</span>
              <div><strong>Quản trị viên:</strong> Toàn quyền quản trị hệ thống, cấp/xoá tài khoản Giáo viên &amp; Học sinh và nhận thông báo đổi mật khẩu.</div>
            </div>
            <div class="hero-point">
              <span class="hero-point-num">2</span>
              <div><strong>Giáo viên sử dụng:</strong> Quản lý lớp học, nhập danh sách Học sinh bằng Excel hoặc thủ công, biên soạn nội dung và trộn đề Ma trận 3×3.</div>
            </div>
            <div class="hero-point">
              <span class="hero-point-num">3</span>
              <div><strong>Học sinh:</strong> Học lý thuyết, làm phiếu hệ thống kiến thức và ôn tập 3 phần theo thang điểm chuẩn Bộ GD&amp;ĐT.</div>
            </div>
          </div>
        </div>

        <div class="auth-author-bar">
          <div class="auth-author-chip">
            ${ICONS.feather}
            <span>Tác giả: <strong>Thầy Bạch Anh Tú</strong></span>
          </div>
          <div style="font-size:0.76rem;color:#94a3b8;">
            Bộ môn Sinh học 12 (CT GDPT 2018) · Hệ thống cấp phát tài khoản tập trung
          </div>
        </div>
      </section>

      <section class="auth-panel-wrap">
        <div class="auth-card">
          <div style="font-size:0.78rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">
            Chọn quyền đăng nhập
          </div>

          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:18px;">
            <button type="button" class="role-option ${state.loginRole === "admin" ? "selected" : ""}" data-login-role="admin" style="padding:10px 8px;text-align:center;">
              <strong style="font-size:0.86rem;">Quản trị viên</strong>
              <small style="font-size:0.72rem;">Toàn quyền</small>
            </button>
            <button type="button" class="role-option ${state.loginRole === "teacher" ? "selected" : ""}" data-login-role="teacher" style="padding:10px 8px;text-align:center;">
              <strong style="font-size:0.86rem;">Giáo viên</strong>
              <small style="font-size:0.72rem;">Quản lý lớp</small>
            </button>
            <button type="button" class="role-option ${state.loginRole === "student" ? "selected" : ""}" data-login-role="student" style="padding:10px 8px;text-align:center;">
              <strong style="font-size:0.86rem;">Học sinh</strong>
              <small style="font-size:0.72rem;">Học &amp; Ôn tập</small>
            </button>
          </div>

          <h2 style="margin:0 0 4px;font-size:1.18rem;font-weight:700;">${cur.title}</h2>
          <p style="margin:0 0 18px;font-size:0.84rem;color:var(--text-muted);line-height:1.5;">
            ${cur.desc}
          </p>

          <form id="login-form">
            <div class="form-group">
              <label>Tên đăng nhập</label>
              <input class="form-control" name="identifier" required autocomplete="username" placeholder="${cur.placeholder}" />
            </div>
            <div class="form-group">
              <label>Mật khẩu</label>
              <input type="password" class="form-control" name="password" required autocomplete="current-password" placeholder="Nhập mật khẩu" />
            </div>
            <button type="submit" class="btn btn-primary btn-lg" style="width:100%;margin-top:4px;">
              Đăng nhập (${roleDisplayName(state.loginRole)})
            </button>
          </form>

          <div class="demo-box" style="margin-top:18px;">
            <p style="margin:0;line-height:1.5;">
              Tài khoản <strong>Giáo viên</strong> do Quản trị viên cấp; tài khoản <strong>Học sinh</strong> do Quản trị viên hoặc Giáo viên cấp (mật khẩu mặc định lần đầu: <code>123456@</code>). Khi đăng nhập lần đầu, hệ thống sẽ yêu cầu cập nhật thông tin và đổi mật khẩu mới.
            </p>
          </div>
        </div>
      </section>
    </div>
  `;

  document.querySelectorAll("[data-login-role]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.loginRole = btn.dataset.loginRole;
      render();
    });
  });

  document.getElementById("login-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await performLogin(fd.get("identifier"), fd.get("password"), state.loginRole);
  });
}

// ================== BẮT BUỘC CẬP NHẬT THÔNG TIN & ĐỔI MẬT KHẨU LẦN ĐẦU ==================
function renderFirstLoginSetupView() {
  const user = state.user;
  const isTeacher = user.role === "teacher";

  appEl.innerHTML = `
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;background:var(--bg);">
      <div class="card" style="width:100%;max-width:540px;padding:28px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px;">
          <span class="pill pill-amber">Yêu cầu kích hoạt tài khoản lần đầu</span>
          <button type="button" class="btn btn-ghost btn-sm" id="btn-first-logout">Đăng xuất</button>
        </div>

        <h2 style="margin:0 0 6px;font-size:1.28rem;">
          Cập nhật thông tin ${isTeacher ? "Giáo viên" : "Học sinh"} &amp; Đổi mật khẩu mới
        </h2>
        <p style="margin:0 0 18px;font-size:0.86rem;color:var(--text-secondary);line-height:1.5;">
          Xin chào <strong>@${escapeHtml(user.username)}</strong>. Để bắt đầu sử dụng hệ thống, vui lòng hoàn tất thông tin cá nhân và thiết lập mật khẩu mới (khác <code>123456@</code>). Dữ liệu đổi mật khẩu sẽ được báo về cho Quản trị viên.
        </p>

        <form id="first-login-form">
          <div class="form-group">
            <label>${isTeacher ? "Họ, tên GV *" : "Họ, tên HS *"}</label>
            <input class="form-control" name="full_name" required value="${escapeHtml(/^(?:GV|HS)\s*\(/i.test(user.full_name || "") ? "" : user.full_name || "")}" placeholder="${isTeacher ? "VD: Nguyễn Thị Minh" : "VD: Trần Văn An"}" />
          </div>

          ${isTeacher
      ? `
                <div class="form-row-2">
                  <div class="form-group">
                    <label>Trường *</label>
                    <input class="form-control" name="school_name" required value="${escapeHtml(user.school_name || "")}" placeholder="VD: Trường THPT Lê Hồng Phong" />
                  </div>
                  <div class="form-group">
                    <label>Số điện thoại *</label>
                    <input type="tel" class="form-control" name="phone" required value="${escapeHtml(user.phone || "")}" placeholder="09xx xxx xxx" />
                  </div>
                </div>
              `
      : `
                <div class="form-row-2">
                  <div class="form-group">
                    <label>Lớp *</label>
                    <input class="form-control" name="class_name" required value="${escapeHtml(user.class_name || "")}" placeholder="VD: 12A1" />
                  </div>
                  <div class="form-group">
                    <label>Số điện thoại *</label>
                    <input type="tel" class="form-control" name="phone" required value="${escapeHtml(user.phone || "")}" placeholder="09xx xxx xxx" />
                  </div>
                </div>
                <div class="form-group">
                  <label>Trường *</label>
                  <input class="form-control" name="school_name" required value="${escapeHtml(user.school_name || "")}" placeholder="VD: Trường THPT Lê Hồng Phong" />
                </div>
              `
    }

          <div class="form-row-2">
            <div class="form-group">
              <label>Mật khẩu mới *</label>
              <input type="password" class="form-control" name="new_password" required minlength="6" placeholder="Tối thiểu 6 ký tự" />
            </div>
            <div class="form-group">
              <label>Xác nhận mật khẩu mới *</label>
              <input type="password" class="form-control" name="confirm_password" required minlength="6" placeholder="Nhập lại mật khẩu mới" />
            </div>
          </div>

          <button type="submit" class="btn btn-primary btn-lg" style="width:100%;margin-top:6px;">
            Lưu thông tin &amp; Vào hệ thống
          </button>
        </form>
      </div>
    </div>
  `;

  document.getElementById("btn-first-logout")?.addEventListener("click", () => handleLeaveClass(true));

  document.getElementById("first-login-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const newPwd = String(fd.get("new_password") || "");
    const confirmPwd = String(fd.get("confirm_password") || "");
    if (newPwd !== confirmPwd) {
      showToast("Mật khẩu xác nhận không khớp.", "error");
      return;
    }
    if (newPwd === "123456@") {
      showToast("Mật khẩu mới phải khác mật khẩu mặc định 123456@.", "error");
      return;
    }
    try {
      const res = await api.firstLoginSetup({
        full_name: fd.get("full_name"),
        class_name: fd.get("class_name") || "",
        school_name: fd.get("school_name"),
        phone: fd.get("phone"),
        new_password: newPwd,
      });
      state.user = res.user;
      showToast(res.message || "Cập nhật thông tin thành công!", "success");
      await enterAuthenticatedApp();
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

async function performLogin(identifier, password, role = "") {
  try {
    const res = await api.login(identifier, password, role);
    setToken(res.token);
    state.user = res.user;
    if (state.user.must_change_password) {
      showToast("Vui lòng cập nhật thông tin và mật khẩu mới để kích hoạt tài khoản.", "info");
      render();
      return;
    }
    showToast(`Xin chào ${res.user.full_name}`, "success");
    await enterAuthenticatedApp();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function enterAuthenticatedApp() {
  if (state.user?.must_change_password) {
    render();
    return;
  }
  const initialRoute = applyRouteGuardForUser(
    state.pendingInitialRoute || parseRoute(),
    state.user
  );
  state.pendingInitialRoute = null;

  if (initialRoute?.hasExplicitRoute) {
    state.activeTab = initialRoute.activeTab;
    state.theoryMode = initialRoute.theoryMode || "lessons";
    state.knowledgeMode = initialRoute.knowledgeMode || "source";
    state.knowledgeUnitIdx = initialRoute.knowledgeUnitIdx || 0;
    state.teacherSubtab = initialRoute.teacherSubtab || "members";
    state.teacherContentSubMode = initialRoute.teacherContentSubMode || "add_topic";
    state.teacherExamMixerMode = initialRoute.teacherExamMixerMode || "word";
    clientCache.setTeacherData({
      subtab: state.teacherSubtab,
      contentSubMode: state.teacherContentSubMode,
    });
  }

  await loadTopicsAndActive(
    initialRoute?.topicId || state.activeTopicId,
    false,
    initialRoute?.lessonId || ""
  );
  await loadMyProgressAndSessions();
  if (state.user.role === "student") {
    await ensureStudentCheckedIn();
  }
  syncCurrentUrl(true);
  render();
}

// ================== STICKY SCROLL NAVIGATION LIFECYCLE ==================
const _stickyObservers = [];
let _stickyResizeObserver = null;
let _stickyRefreshBound = false;

function cleanupStickyObservers() {
  while (_stickyObservers.length) {
    try {
      _stickyObservers.pop().disconnect();
    } catch { }
  }
  if (_stickyResizeObserver) {
    try {
      _stickyResizeObserver.disconnect();
    } catch { }
    _stickyResizeObserver = null;
  }
}

function renderQuickTabsMiniHtml(activeTab) {
  return `
    <div class="sticky-subnav-quick" aria-label="Chuyển nhanh mục học">
      <button type="button" class="sticky-qtab ${activeTab === "theory" ? "active" : ""}" data-quick-tab="theory" title="1. Lý thuyết">LT</button>
      <button type="button" class="sticky-qtab ${activeTab === "knowledge" ? "active" : ""}" data-quick-tab="knowledge" title="2. Hệ thống kiến thức">KT</button>
      <button type="button" class="sticky-qtab ${activeTab === "review" ? "active" : ""}" data-quick-tab="review" title="3. Hệ thống ôn tập">Ôn tập</button>
      <button type="button" class="sticky-qtab ${activeTab === "mock_exam" ? "active" : ""}" data-quick-tab="mock_exam" title="Thi thử TN THPT">Thi thử</button>
      <button type="button" class="sticky-qtab sticky-qtab-top" data-scroll-top title="Lên đầu trang">↑</button>
    </div>
  `;
}

let _delegatedQuickNavBound = false;

function ensureQuickNavDelegated() {
  if (_delegatedQuickNavBound || !appEl) return;
  _delegatedQuickNavBound = true;
  appEl.addEventListener("click", (e) => {
    const topBtn = e.target.closest("[data-scroll-top]");
    if (topBtn) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const qBtn = e.target.closest("[data-quick-tab]");
    if (qBtn) {
      const nextTab = qBtn.dataset.quickTab;
      if (!nextTab) return;
      if (state.activeTab === "mock_exam" && nextTab !== "mock_exam") {
        stopMockExamTimers();
      }
      if (state.activeTab === "theory" && nextTab !== "theory") {
        cleanupTheoryObserver();
      }
      state.mobileMenuOpen = false;
      state.activeTab = nextTab;
      sendThrottledHeartbeat(state.activeTopicId, state.activeTab);
      syncCurrentUrl(false);
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  });
}

function setupStickyNavigation() {
  cleanupStickyObservers();
  if (typeof window === "undefined") return;

  if (!_stickyRefreshBound) {
    _stickyRefreshBound = true;
    window.addEventListener("sh12:refresh-sticky", () => setupStickyNavigation());
  }

  const workspace = document.getElementById("workspace-body");
  const tabsBar = document.getElementById("center-tabs-bar");
  const hasSubnav = Boolean(document.querySelector(".sticky-subnav, .mock-sticky-clock-bar"));

  if (tabsBar) {
    tabsBar.classList.toggle("no-sticky", hasSubnav);
    if (hasSubnav) tabsBar.classList.remove("is-stuck");
  }

  const updateOffsets = () => {
    const barH = tabsBar ? Math.ceil(tabsBar.getBoundingClientRect().height) : 48;
    const subTop = hasSubnav ? 64 : 64 + barH + 6;
    if (workspace) {
      workspace.style.setProperty("--sticky-sub-top", `${subTop}px`);
      workspace.style.setProperty("--mock-palette-top", `${subTop + 120}px`);
    }
    return subTop;
  };

  const subTop = updateOffsets();
  if (tabsBar && !hasSubnav && typeof ResizeObserver !== "undefined") {
    _stickyResizeObserver = new ResizeObserver(() => updateOffsets());
    _stickyResizeObserver.observe(tabsBar);
  }

  if (typeof IntersectionObserver === "undefined") return;

  const mainSentinel = document.querySelector('[data-sticky-sentinel="center-tabs"]');
  if (mainSentinel && tabsBar && !hasSubnav) {
    const obsMain = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          tabsBar.classList.toggle("is-stuck", !entry.isIntersecting && entry.boundingClientRect.top < 70);
          updateOffsets();
        });
      },
      { threshold: 0, rootMargin: "-64px 0px 0px 0px" }
    );
    obsMain.observe(mainSentinel);
    _stickyObservers.push(obsMain);
  }

  document.querySelectorAll("[data-sticky-sub-sentinel]").forEach((sentinel) => {
    const subnav = sentinel.nextElementSibling;
    if (!subnav || !subnav.classList.contains("sticky-subnav")) return;
    const obsSub = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          subnav.classList.toggle(
            "is-stuck",
            !entry.isIntersecting && entry.boundingClientRect.top < subTop + 12
          );
        });
      },
      { threshold: 0, rootMargin: `-${subTop}px 0px 0px 0px` }
    );
    obsSub.observe(sentinel);
    _stickyObservers.push(obsSub);
  });
}

// ================== MAIN WORKSPACE SHELL (LEFT CONTRASTING TOPICS + HIDDEN MENU DRAWER + CENTERED TABS) ==================
function renderMainShell() {
  ensureQuickNavDelegated();
  const user = state.user;
  const isStaff = isStaffRole(user.role);
  const isAdmin = user.role === "admin";
  const effectiveStudentView = !isStaff || state.teacherPreviewAsStudent;
  const isAdminView = !effectiveStudentView && state.activeTab === "teacher";
  const isTopicTab =
    state.activeTab === "theory" || state.activeTab === "knowledge" || state.activeTab === "review";
  const topic = state.activeTopic;
  const lessons = topic?.lessons || [];
  const topbarBadgeText = isAdminView
    ? isAdmin
      ? "Quản trị hệ thống"
      : "Quản lý lớp học"
    : state.activeTab === "mock_exam"
    ? "Thi thử Tốt nghiệp THPT"
    : state.activeTab === "profile"
    ? "Hồ sơ cá nhân"
    : topic?.title || "";

  // Ghi nhớ vị trí cuộn của thanh Chủ đề trước khi re-render
  const prevRailScroll = document.getElementById("topics-rail-scroll");
  if (prevRailScroll) {
    state.railScrollTop = prevRailScroll.scrollTop;
  }

  appEl.innerHTML = `
    <div class="app-root">
      ${state.topicLoading ? `<div class="topic-progress-bar" aria-hidden="true"></div>` : ""}
      <!-- Top Header with Menu & Collapsible Topics Rail Toggle -->
      <header class="app-topbar">
        <div class="topbar-left-group">
          <button class="menu-trigger-btn" id="btn-toggle-menu" aria-label="Mở thanh công cụ Menu">
            ${ICONS.menu}
            <span>Menu</span>
          </button>

          <button class="rail-toggle-btn ${state.topicsRailCollapsed ? "is-collapsed" : "is-open"}" id="btn-toggle-rail" aria-expanded="${!state.topicsRailCollapsed}" aria-controls="topics-rail" title="${state.topicsRailCollapsed ? "Hiện thanh Chủ đề Sinh học 12" : "Ẩn thanh Chủ đề Sinh học 12"}">
            ${ICONS.panelLeft}
            <span>${state.topicsRailCollapsed ? "Hiện Chủ đề" : "Ẩn Chủ đề"}</span>
          </button>

          <div class="topbar-brand-inline" id="btn-brand-home">
            <div class="brand-mark" style="width:32px;height:32px;">${ICONS.dna}</div>
            <div class="topbar-brand-text">
              <span class="topbar-brand-name">Sinh học 12</span>
              <span class="topbar-brand-sub">CT GDPT 2018</span>
            </div>
          </div>

          ${
            topbarBadgeText
              ? `<span class="topbar-current-topic" title="${escapeHtml(topbarBadgeText)}">${escapeHtml(topbarBadgeText)}</span>`
              : ""
          }
        </div>

        <div class="topbar-actions">
          <span class="topbar-author-badge" title="Tác giả biên soạn hệ thống">
            ${ICONS.feather}
            <span>Tác giả: <strong>Thầy Bạch Anh Tú</strong></span>
          </span>
          ${!isStaff
      ? state.activeSession
        ? `
                  <div class="attendance-pill" title="Tự động ghi nhận thời gian học tập">
                    <span class="pulse-dot"></span>
                    <span>Vào ${formatTimeShort(state.activeSession.enter_time)} · <span id="live-session-clock">${formatDuration(state.sessionElapsedSeconds)}</span></span>
                  </div>
                  <button class="btn btn-sm btn-danger" id="btn-leave-class">Rời lớp</button>
                `
        : `
                  <div class="attendance-pill paused"><span>Đã rời lớp</span></div>
                  <button class="btn btn-sm btn-primary" id="btn-reenter-class">Vào học lại</button>
                `
      : `
                ${
                  isAdminView
                    ? `<button type="button" class="topbar-back-study-btn" data-tab="theory" title="Quay lại giao diện bài học">← Về bài học</button>`
                    : ""
                }
                <button
                  type="button"
                  class="topbar-admin-btn ${state.activeTab === "teacher" ? "active" : ""}"
                  data-tab="teacher"
                  title="${isAdmin ? "Mở bảng Quản trị hệ thống" : "Mở bảng Quản lý lớp học"}"
                >
                  ${ICONS.barChart}
                  <span>${isAdmin ? "Quản trị hệ thống" : "Quản lý lớp học"}</span>
                </button>
                <span class="pill pill-primary topbar-role-pill">${state.teacherPreviewAsStudent ? "Xem như Học sinh" : roleDisplayName(user.role)}</span>
              `
    }
        </div>
      </header>

      <!-- Hidden Toolbar Drawer (Opens when clicking Menu) -->
      <div class="drawer-backdrop ${state.mobileMenuOpen ? "open" : ""}" id="drawer-backdrop"></div>
      <aside class="menu-drawer ${state.mobileMenuOpen ? "open" : ""}" id="menu-drawer" aria-label="Thanh công cụ đầy đủ">
        <div class="drawer-header">
          <div style="display:flex;align-items:center;gap:9px;">
            <div class="brand-mark" style="width:30px;height:30px;">${ICONS.dna}</div>
            <div>
              <div style="font-weight:700;font-size:0.94rem;">Menu công cụ</div>
              <div style="font-size:0.72rem;color:var(--text-muted);">Sinh học 12 · Thầy Bạch Anh Tú</div>
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" id="btn-close-menu">Đóng ✕</button>
        </div>

        <div class="drawer-section">
          <div class="drawer-section-title">Các thẻ nội dung</div>
          <nav class="drawer-nav">
            <button class="drawer-item ${state.activeTab === "theory" ? "active" : ""}" data-drawer-tab="theory">${ICONS.book}<span>1. Lý thuyết &amp; Video YouTube</span></button>
            <button class="drawer-item ${state.activeTab === "knowledge" ? "active" : ""}" data-drawer-tab="knowledge">${ICONS.layers}<span>2. Hệ thống kiến thức</span></button>
            <button class="drawer-item ${state.activeTab === "review" ? "active" : ""}" data-drawer-tab="review">${ICONS.checkSquare}<span>3. Hệ thống ôn tập (3 phần)</span></button>
            <button class="drawer-item ${state.activeTab === "mock_exam" ? "active" : ""}" data-drawer-tab="mock_exam">${ICONS.award}<span>Thi thử Tốt nghiệp THPT</span></button>
            ${!effectiveStudentView
      ? `<button class="drawer-item ${state.activeTab === "teacher" ? "active" : ""}" data-drawer-tab="teacher">${ICONS.barChart}<span>${isAdmin ? "Quản trị &amp; Quản lý lớp" : "Quản lý lớp học"}</span></button>`
      : ""
    }
            <button class="drawer-item ${state.activeTab === "profile" ? "active" : ""}" data-drawer-tab="profile">${ICONS.user}<span>Hồ sơ &amp; Đổi mật khẩu</span></button>
          </nav>
        </div>

        <div class="drawer-section">
          <div class="drawer-section-title">Tất cả Chủ đề (${state.topicsList.length})</div>
          <div class="drawer-nav">
            ${state.topicsList
      .map(
        (t, idx) => `
                <button class="drawer-item ${t.id === state.activeTopicId && isTopicTab ? "active" : ""}" data-select-topic="${t.id}">
                  <span style="font-weight:700;min-width:20px;">${t.order_index || idx + 1}.</span>
                  <span style="line-height:1.35;">${escapeHtml((t.title || "").replace(/^Chủ đề\s*\d+[\.\:]?\s*/i, ""))}</span>
                </button>
              `
      )
      .join("")}
          </div>
        </div>

        ${lessons.length
      ? `
              <div class="drawer-section">
                <div class="drawer-section-title">Bài học trong Chủ đề đang chọn</div>
                <div class="drawer-nav">
                  ${lessons
        .map(
          (l) => `
                      <button class="drawer-item ${l.id === state.activeLessonId && state.activeTab === "theory" ? "active" : ""}" data-drawer-lesson="${l.id}">
                        <span style="font-size:0.8rem;line-height:1.35;">${escapeHtml(l.number)}: ${escapeHtml(l.title)}</span>
                      </button>
                    `
        )
        .join("")}
                </div>
              </div>
            `
      : ""
    }

        ${isStaff
      ? `
              <div class="drawer-section">
                <div class="drawer-section-title">Công cụ ${roleDisplayName(user.role)}</div>
                <div style="display:flex;flex-direction:column;gap:6px;padding:0 6px;">
                  <button class="btn btn-sm ${state.teacherPreviewAsStudent ? "btn-primary" : "btn-secondary"}" id="btn-preview-student" style="width:100%;">
                    ${state.teacherPreviewAsStudent ? "Thoát chế độ Xem như Học sinh" : "Xem giao diện như Học sinh"}
                  </button>
                  <button class="btn btn-sm ${state.presentationMode ? "btn-primary" : "btn-secondary"}" id="btn-presentation" style="width:100%;">
                    ${state.presentationMode ? "Tắt chế độ trình chiếu" : "Bật chế độ trình chiếu lớp"}
                  </button>
                </div>
              </div>
            `
      : ""
    }

        <div class="drawer-footer">
          <div style="display:flex;align-items:center;gap:10px;padding:4px 6px;cursor:pointer;" id="btn-open-profile">
            <span class="avatar-circle" style="background:${user.avatar_color || "#0f766e"}">${getInitials(user.full_name)}</span>
            <div style="min-width:0;flex:1;">
              <div style="font-size:0.84rem;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(user.full_name)}</div>
              <div style="font-size:0.74rem;color:var(--text-muted);">${isStaff ? roleDisplayName(user.role) : `Học sinh · ${escapeHtml(user.class_name || "")}`}</div>
            </div>
          </div>
          <button class="btn btn-secondary btn-sm" id="btn-logout" style="width:100%;">Đăng xuất</button>
        </div>
      </aside>

      <!-- Floating Left Edge Reopen Button when Topics Rail is Collapsed -->
      <button class="rail-reopen-fab ${state.topicsRailCollapsed ? "visible" : ""}" id="btn-expand-rail-float" type="button" title="Mở thanh Chủ đề Sinh học 12" aria-label="Mở thanh Chủ đề Sinh học 12">
        ${ICONS.chevronRight}
        <span>Chủ đề</span>
      </button>

      <!-- Main 2-Column Body: Independently Scrollable Collapsible Topics Rail + Balanced Biology Content Workspace -->
      <div class="workspace-body ${state.topicsRailCollapsed ? "rail-collapsed" : ""}" id="workspace-body">
        <aside class="topics-rail ${state.topicsRailCollapsed ? "collapsed" : ""}" id="topics-rail" aria-label="Danh sách Chủ đề Sinh học 12">
          <div class="topics-rail-header">
            <div class="topics-rail-header-title">
              <span class="topics-rail-dna-dot" aria-hidden="true">${ICONS.dna}</span>
              <div>
                <div class="topics-rail-heading">Chủ đề Sinh học 12</div>
                <div class="topics-rail-sub">${state.topicsList.length} chủ đề · GDPT 2018</div>
              </div>
            </div>
            <button type="button" class="rail-collapse-icon-btn" id="btn-collapse-rail" title="Ẩn thanh Chủ đề" aria-label="Ẩn thanh Chủ đề">
              ${ICONS.chevronLeft}
            </button>
          </div>

          <div class="topics-rail-scroll" id="topics-rail-scroll">
            ${state.topicsList
      .map((t, i) => {
        const num = t.order_index || i + 1;
        const themeCls = `topic-theme-${((num - 1) % 8) + 1}`;
        const shortTitle = (t.title || "").replace(/^Chủ đề\s*\d+[\.\:]?\s*/i, "");
        const isLoadingThis = state.topicLoading && state.loadingTopicId === t.id;
        return `
                  <button class="topic-color-card ${themeCls} ${t.id === state.activeTopicId && isTopicTab ? "active" : ""} ${isLoadingThis ? "is-loading" : ""}" data-select-topic="${t.id}">
                    <span class="topic-color-badge">Chủ đề ${num}${isLoadingThis ? `<span class="topic-card-spinner" aria-hidden="true"></span>` : ""}</span>
                    <span class="topic-color-title">${escapeHtml(shortTitle || t.title)}</span>
                  </button>
                `;
      })
      .join("")}

            <div class="topics-rail-divider">Kỳ thi &amp; Luyện đề</div>
            <button class="topic-color-card topic-theme-mock ${state.activeTab === "mock_exam" ? "active" : ""}" data-tab="mock_exam">
              <span class="topic-color-badge">PHÒNG LUYỆN TẬP · 45 PHÚT</span>
              <span class="topic-color-title">Thi thử Tốt nghiệp THPT</span>
            </button>
          </div>

          <div class="topics-rail-footer">
            <div class="rail-author-card">
              <span class="rail-author-icon">${ICONS.feather}</span>
              <div class="rail-author-info">
                <span class="rail-author-label">Tác giả biên soạn</span>
                <strong class="rail-author-name">Thầy Bạch Anh Tú</strong>
              </div>
            </div>
          </div>
        </aside>

        <section class="center-stage">
          ${
            !isAdminView
              ? `
                <!-- Balanced Scientific Navigation Tabs Bar (Sticky when no subnav is present) -->
                <div class="sticky-sentinel" data-sticky-sentinel="center-tabs" aria-hidden="true"></div>
                <nav class="center-tabs-bar" id="center-tabs-bar" aria-label="Các thẻ nội dung">
                  <button class="center-tab-card ctab-theory ${state.activeTab === "theory" ? "active" : ""}" data-tab="theory">
                    ${ICONS.book}<span>1. Lý thuyết</span>
                  </button>
                  <button class="center-tab-card ctab-knowledge ${state.activeTab === "knowledge" ? "active" : ""}" data-tab="knowledge">
                    ${ICONS.layers}<span>2. Hệ thống kiến thức</span>
                  </button>
                  <button class="center-tab-card ctab-review ${state.activeTab === "review" ? "active" : ""}" data-tab="review">
                    ${ICONS.checkSquare}<span>3. Hệ thống ôn tập</span>
                  </button>
                  <button class="center-tab-card ctab-mock ${state.activeTab === "mock_exam" ? "active" : ""}" data-tab="mock_exam">
                    ${ICONS.award}<span>Thi thử TN THPT</span>
                  </button>
                </nav>
              `
              : ""
          }

          <div class="center-content-wrap" id="tab-view"></div>

          <footer class="bio-workspace-footer" aria-label="Thông tin tác giả và bản quyền">
            <div class="bio-footer-left">
              <span class="bio-footer-dna">${ICONS.dna}</span>
              <div>
                <div class="bio-footer-title">Hệ thống Giảng dạy &amp; Ôn tập Thông minh — Sinh học 12</div>
                <div class="bio-footer-sub">Chương trình Giáo dục Phổ thông 2018 · Học tập khoa học &amp; trực quan</div>
              </div>
            </div>
            <div class="bio-footer-author">
              ${ICONS.feather}
              <span>Tác giả: <strong>Thầy Bạch Anh Tú</strong></span>
            </div>
          </footer>
        </section>
      </div>
    </div>
  `;

  // Khôi phục vị trí cuộn độc lập của thanh Chủ đề
  const railScrollEl = document.getElementById("topics-rail-scroll");
  if (railScrollEl) {
    railScrollEl.scrollTop = state.railScrollTop || 0;
    railScrollEl.addEventListener("scroll", () => {
      state.railScrollTop = railScrollEl.scrollTop;
    }, { passive: true });
  }

  const setRailCollapsed = (collapsed) => {
    state.topicsRailCollapsed = Boolean(collapsed);
    saveStoredRailCollapsed(state.topicsRailCollapsed);
    document.getElementById("workspace-body")?.classList.toggle("rail-collapsed", state.topicsRailCollapsed);
    document.getElementById("topics-rail")?.classList.toggle("collapsed", state.topicsRailCollapsed);
    document.getElementById("btn-expand-rail-float")?.classList.toggle("visible", state.topicsRailCollapsed);
    const topBtn = document.getElementById("btn-toggle-rail");
    if (topBtn) {
      topBtn.classList.toggle("is-collapsed", state.topicsRailCollapsed);
      topBtn.classList.toggle("is-open", !state.topicsRailCollapsed);
      topBtn.setAttribute("aria-expanded", String(!state.topicsRailCollapsed));
      topBtn.title = state.topicsRailCollapsed ? "Hiện thanh Chủ đề Sinh học 12" : "Ẩn thanh Chủ đề Sinh học 12";
      const sp = topBtn.querySelector("span");
      if (sp) sp.textContent = state.topicsRailCollapsed ? "Hiện Chủ đề" : "Ẩn Chủ đề";
    }
  };

  document.getElementById("btn-toggle-rail")?.addEventListener("click", () => setRailCollapsed(!state.topicsRailCollapsed));
  document.getElementById("btn-collapse-rail")?.addEventListener("click", () => setRailCollapsed(true));
  document.getElementById("btn-expand-rail-float")?.addEventListener("click", () => setRailCollapsed(false));

  const setDrawer = (open) => {
    state.mobileMenuOpen = open;
    document.getElementById("menu-drawer")?.classList.toggle("open", open);
    document.getElementById("drawer-backdrop")?.classList.toggle("open", open);
  };

  document.getElementById("btn-toggle-menu")?.addEventListener("click", () => setDrawer(!state.mobileMenuOpen));
  document.getElementById("btn-close-menu")?.addEventListener("click", () => setDrawer(false));
  document.getElementById("drawer-backdrop")?.addEventListener("click", () => setDrawer(false));

  document.getElementById("btn-brand-home")?.addEventListener("click", () => {
    state.activeTab = "theory";
    syncCurrentUrl(false);
    render();
  });

  document.querySelectorAll("[data-select-topic]").forEach((btn) => {
    btn.addEventListener("click", () => {
      stopMockExamTimers();
      if (state.activeTab === "mock_exam" || state.activeTab === "teacher" || state.activeTab === "profile") {
        state.activeTab = "theory";
      }
      switchTopicSmoothly(btn.dataset.selectTopic);
    });
  });

  document.querySelectorAll("[data-drawer-lesson]").forEach((btn) => {
    btn.addEventListener("click", () => {
      stopMockExamTimers();
      state.mobileMenuOpen = false;
      state.activeTab = "theory";
      state.theoryMode = "lessons";
      state.activeLessonId = btn.dataset.drawerLesson;
      syncCurrentUrl(false);
      render();
    });
  });

  document.querySelectorAll("[data-tab], [data-drawer-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const nextTab = btn.dataset.tab || btn.dataset.drawerTab;
      if (state.activeTab === "mock_exam" && nextTab !== "mock_exam") {
        stopMockExamTimers();
      }
      if (state.activeTab === "theory" && nextTab !== "theory") {
        cleanupTheoryObserver();
      }
      state.mobileMenuOpen = false;
      state.activeTab = nextTab;
      sendThrottledHeartbeat(state.activeTopicId, state.activeTab);
      syncCurrentUrl(false);
      render();
    });
  });

  document.getElementById("btn-open-profile")?.addEventListener("click", () => {
    state.mobileMenuOpen = false;
    state.activeTab = "profile";
    syncCurrentUrl(false);
    render();
  });

  document.getElementById("btn-leave-class")?.addEventListener("click", () => handleLeaveClass(false));
  document.getElementById("btn-reenter-class")?.addEventListener("click", async () => {
    await ensureStudentCheckedIn();
    render();
  });
  document.getElementById("btn-logout")?.addEventListener("click", () => handleLeaveClass(true));

  document.getElementById("btn-preview-student")?.addEventListener("click", () => {
    state.mobileMenuOpen = false;
    state.teacherPreviewAsStudent = !state.teacherPreviewAsStudent;
    if (state.teacherPreviewAsStudent && state.activeTab === "teacher") {
      state.activeTab = "theory";
      syncCurrentUrl(false);
    }
    render();
  });

  document.getElementById("btn-presentation")?.addEventListener("click", () => {
    state.mobileMenuOpen = false;
    state.presentationMode = !state.presentationMode;
    document.body.classList.toggle("presentation-mode", state.presentationMode);
    render();
  });

  const tabView = document.getElementById("tab-view");
  if (state.topicLoading) {
    const targetMeta = state.topicsList.find((t) => t.id === state.loadingTopicId);
    tabView.innerHTML = `
      <div class="topic-loading-card" role="status" aria-live="polite">
        <div class="topic-loading-spinner"></div>
        <div>Đang tải ${escapeHtml(targetMeta?.title || "chủ đề mới")}...</div>
      </div>
    `;
    return;
  }

  tabView.classList.add("center-stage-fade");
  if (state.activeTab === "theory") renderTheoryTab(tabView);
  else if (state.activeTab === "knowledge") renderKnowledgeTab(tabView);
  else if (state.activeTab === "review") renderReviewTab(tabView);
  else if (state.activeTab === "mock_exam") {
    mountMockExamSection(tabView, {
      currentUser: state.user,
      effectiveStudentView,
      showToast,
    });
  } else if (state.activeTab === "teacher") {
    mountTeacherDashboard(
      tabView,
      state.activeTopic,
      (updatedTopic) => {
        state.activeTopic = updatedTopic;
        if (updatedTopic?.id) {
          state.topicCache[updatedTopic.id] = updatedTopic;
          clientCache.setTopic(updatedTopic.id, updatedTopic);
        }
      },
      showToast,
      {
        currentUser: state.user,
        topicsList: state.topicsList,
        initialSubtab: state.teacherSubtab,
        initialContentSubMode: state.teacherContentSubMode,
        initialExamMixerMode: state.teacherExamMixerMode,
        onSubRouteChange: (patch, replace = false) => {
          if (patch?.subtab) state.teacherSubtab = patch.subtab;
          if (patch?.contentSubMode) state.teacherContentSubMode = patch.contentSubMode;
          if (patch?.examMixerMode) state.teacherExamMixerMode = patch.examMixerMode;
          syncCurrentUrl(replace);
        },
        onSelectTopic: async (tid) => {
          state.activeTab = "theory";
          await switchTopicSmoothly(tid);
        },
        onTopicsReload: async (newTopicId, reloadOpts = {}) => {
          if (reloadOpts.deletedTopicId) {
            delete state.topicCache[reloadOpts.deletedTopicId];
            clientCache.invalidateTopic(reloadOpts.deletedTopicId);
          } else if (reloadOpts.changedTopicId) {
            delete state.topicCache[reloadOpts.changedTopicId];
            clientCache.invalidateTopic(reloadOpts.changedTopicId);
          }
          clientCache.invalidateTeacherData();
          await loadTopicsAndActive(newTopicId || state.activeTopicId, true);
          syncCurrentUrl(true);
          render();
        },
      }
    );
  } else if (state.activeTab === "profile") {
    renderProfileTab(tabView);
  }

  setupStickyNavigation();
}

// ================== SHARED RICH CONTENT RENDERERS (với bài tập tương tác & đối chiếu đáp án) ==================
function renderDocumentBlocks(blocks, editableEmptyCells = false) {
  return renderDocumentBlocksInteractive(blocks, editableEmptyCells);
}

function renderTopicBannerLayer(topic) {
  if (topic?.banner_image) {
    return `<div class="bio-header-banner-layer" aria-hidden="true"><img src="${escapeHtml(withBase(topic.banner_image))}" alt="" loading="lazy" /></div>`;
  }
  return ICONS.helixBg;
}

// ================== TAB 1: LÝ THUYẾT & THƯ VIỆN VIDEO YOUTUBE ==================
function renderTheoryTab(container) {
  const topic = state.activeTopic;
  if (!topic || !(topic.lessons || []).length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-state-title">Chủ đề chưa có nội dung bài học</div></div>`;
    return;
  }

  const lessons = topic.lessons;
  const activeLesson = lessons.find((l) => l.id === state.activeLessonId) || lessons[0];
  state.activeLessonId = activeLesson.id;
  const ytCount = (topic.youtube_videos || []).length;
  const canManageYt = state.user?.role === "admin" && !state.teacherPreviewAsStudent;

  const doneCount = lessons.filter((l) => state.completedLessonIds.has(l.id)).length;

  container.innerHTML = `
    <div class="page-header bio-page-header ${topic.banner_image ? "has-banner" : ""}">
      ${renderTopicBannerLayer(topic)}
      <div class="bio-page-header-main">
        <div class="bio-topic-kicker">
          <span class="bio-kicker-dot"></span>
          <span>SINH HỌC 12 · CHƯƠNG TRÌNH GDPT 2018</span>
        </div>
        <h1>${formatBioHtml(topic.title)}</h1>
        <div class="bio-header-meta">
          <span class="pill pill-primary">${lessons.length} bài lý thuyết</span>
          <span class="pill pill-muted">${ytCount} video YouTube</span>
          <span class="pill pill-green">Hoàn thành ${doneCount}/${lessons.length} bài</span>
        </div>
      </div>
      <div class="segmented bio-mode-segmented">
        <button class="seg-btn ${state.theoryMode === "lessons" ? "active" : ""}" id="mode-lessons">Nội dung bài học</button>
        <button class="seg-btn ${state.theoryMode === "youtube" ? "active" : ""}" id="mode-youtube">Video bài giảng YouTube (${ytCount})</button>
      </div>
    </div>

    <div id="theory-body"></div>
  `;

  container.querySelector("#mode-lessons")?.addEventListener("click", () => {
    state.theoryMode = "lessons";
    syncCurrentUrl(false);
    renderTheoryTab(container);
  });
  container.querySelector("#mode-youtube")?.addEventListener("click", () => {
    state.theoryMode = "youtube";
    syncCurrentUrl(false);
    renderTheoryTab(container);
  });

  const bodyEl = container.querySelector("#theory-body");

  if (state.theoryMode === "youtube") {
    mountYoutubeLibrary(bodyEl, topic, {
      canManage: canManageYt,
      onTopicUpdated: (updated) => {
        state.activeTopic = updated;
        if (updated?.id) state.topicCache[updated.id] = updated;
      },
      showToast,
    });
    return;
  }

  const isDone = state.completedLessonIds.has(activeLesson.id);
  const allLessonBlocks = (activeLesson.sections || []).flatMap((sec) => sec.blocks || []);
  const lessonInteractiveIds = collectInteractiveUnitIds(allLessonBlocks);

  bodyEl.innerHTML = `
    <div class="sticky-sentinel" data-sticky-sub-sentinel aria-hidden="true"></div>
    <div class="lesson-tabs-bar sticky-subnav">
      <div class="sticky-lessons-list">
        ${lessons
      .map((l) => {
        const done = state.completedLessonIds.has(l.id);
        return `
            <button class="lesson-pill-tab ${l.id === activeLesson.id ? "active" : ""}" data-lesson-id="${l.id}" title="${escapeHtml(l.number)}: ${escapeHtml(l.title)}">
              <span class="lesson-pill-short">${escapeHtml(l.number)}${done ? " ✓" : ""}</span>
              <span class="lesson-pill-full">${escapeHtml(l.number)}: ${escapeHtml(l.title)}${done ? " ✓" : ""}</span>
            </button>
          `;
      })
      .join("")}
      </div>
      ${renderQuickTabsMiniHtml("theory")}
    </div>

    <article class="card prose-article">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--border);">
        <div>
          <span class="pill pill-primary">${escapeHtml(activeLesson.number)}</span>
          <h2 style="margin:6px 0 0;font-size:1.25rem;font-weight:700;">${formatBioHtml(activeLesson.title)}</h2>
        </div>
        <button class="btn btn-sm ${isDone ? "btn-soft" : "btn-primary"}" id="btn-mark-lesson">
          ${isDone ? "Đã hoàn thành" : "Đánh dấu đã học"}
        </button>
      </div>

      ${renderInteractiveToolbar(lessonInteractiveIds, `bài ${activeLesson.number}`)}

      ${(activeLesson.sections || [])
      .map((sec, sIdx) => {
        const isYccd = /yêu cầu cần đạt/i.test(sec.heading || "");
        const secKey = `sec-${sIdx}`;
        const secHeading = (sec.heading || `Mục ${sIdx + 1}`).trim();
        return `
          <section class="theory-section ${isYccd ? "yccd-box" : ""}" data-section-key="${secKey}" data-section-heading="${escapeHtml(secHeading)}">
            <h3>${formatBioHtml(sec.heading)}</h3>
            ${(sec.blocks || []).length
            ? renderDocumentBlocks(sec.blocks, false)
            : `<ul style="margin:0;padding-left:20px;color:var(--text-secondary);">${(sec.points || []).map((pt) => `<li>${formatBioHtml(pt)}</li>`).join("")}</ul>`
          }
          </section>
        `;
      })
      .join("")}

      <div id="lesson-interactive-sim"></div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:24px;padding-top:16px;border-top:1px solid var(--border);flex-wrap:wrap;gap:10px;">
        <button class="btn btn-secondary btn-sm" id="btn-open-yt-from-lesson">Xem Video YouTube của chủ đề</button>
        <button class="btn btn-primary btn-sm" id="btn-goto-review-from-lesson">Chuyển sang Hệ thống ôn tập →</button>
      </div>
    </article>
  `;

  bindInteractiveExerciseEvents(bodyEl, lessonInteractiveIds, () => renderTheoryTab(container), {
    topicId: topic.id,
    sourceTab: "theory",
    lessonLabel: `${activeLesson.number}: ${activeLesson.title}`,
  });

  // Tự động theo dõi các mục Lý thuyết học sinh đã đọc trong phiên học
  setupTheorySectionObserver(bodyEl, topic, activeLesson);

  if (activeLesson.interactive_diagram) {
    mountInteractiveDiagram(bodyEl.querySelector("#lesson-interactive-sim"), activeLesson.interactive_diagram);
  }

  bodyEl.querySelectorAll("[data-lesson-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeLessonId = btn.dataset.lessonId;
      syncCurrentUrl(false);
      renderTheoryTab(container);
      const activePill = container.querySelector(`[data-lesson-id="${CSS.escape(state.activeLessonId)}"]`);
      activePill?.scrollIntoView({ inline: "nearest", block: "nearest" });
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  bodyEl.querySelector("#btn-mark-lesson")?.addEventListener("click", async () => {
    try {
      const allSectionsPayload = (activeLesson.sections || []).map((sec, sIdx) => ({
        key: `sec-${sIdx}`,
        heading: (sec.heading || `Mục ${sIdx + 1}`).trim(),
        duration_delta: 10,
        completed: 1,
      }));
      await Promise.all([
        api.saveProgress({
          topic_id: topic.id,
          lesson_id: activeLesson.id,
          completed: true,
          checkpoint_score: 1,
        }),
        api.recordTheoryReads({
          topic_id: topic.id,
          lesson_id: activeLesson.id,
          lesson_number: activeLesson.number || "",
          lesson_title: activeLesson.title || "",
          mark_lesson_done: true,
          sections: allSectionsPayload,
        }),
      ]);
      state.completedLessonIds.add(activeLesson.id);
      allSectionsPayload.forEach((s) => recordedTheorySectionKeys.add(`${activeLesson.id}::${s.key}`));
      clientCache.invalidateTeacherData();
      showToast(`Đã lưu tiến độ ${activeLesson.number} (${allSectionsPayload.length} mục lý thuyết)`, "success");
      renderTheoryTab(container);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  bodyEl.querySelector("#btn-open-yt-from-lesson")?.addEventListener("click", () => {
    state.theoryMode = "youtube";
    syncCurrentUrl(false);
    renderTheoryTab(container);
  });

  bodyEl.querySelector("#btn-goto-review-from-lesson")?.addEventListener("click", () => {
    state.activeTab = "review";
    syncCurrentUrl(false);
    render();
  });

  setupStickyNavigation();
}

// ================== TAB 2: HỆ THỐNG KIẾN THỨC ==================
function renderKnowledgeTab(container) {
  const topic = state.activeTopic;
  const ks = topic?.knowledge_system;
  if (!ks || (!(ks.units || []).length && !(ks.mindmap?.branches || []).length)) {
    container.innerHTML = `<div class="empty-state"><div class="empty-state-title">Chưa có dữ liệu Hệ thống kiến thức</div></div>`;
    return;
  }

  const units = ks.units || [];
  let ksMode = units.length
    ? state.knowledgeMode === "mindmap"
      ? "mindmap"
      : "source"
    : "mindmap";
  let activeUnitIdx = Math.min(Math.max(0, Number(state.knowledgeUnitIdx || 0)), Math.max(0, units.length - 1));
  state.knowledgeMode = ksMode;
  state.knowledgeUnitIdx = activeUnitIdx;

  const draw = () => {
    container.innerHTML = `
      <div class="page-header bio-page-header ${topic.banner_image ? "has-banner" : ""}">
        ${renderTopicBannerLayer(topic)}
        <div class="bio-page-header-main">
          <div class="bio-topic-kicker">
            <span class="bio-kicker-dot"></span>
            <span>HỆ THỐNG HOÁ KIẾN THỨC SINH HỌC 12</span>
          </div>
          <h1>${formatBioHtml(topic.title)}</h1>
          <div class="bio-header-meta">
            <span class="pill pill-primary">${units.length} phiếu bài học</span>
            <span class="pill pill-muted">${(ks.flashcards || []).length} thẻ ghi nhớ</span>
          </div>
        </div>
        <div class="segmented bio-mode-segmented">
          ${units.length ? `<button class="seg-btn ${ksMode === "source" ? "active" : ""}" id="ks-mode-source">Phiếu hệ thống kiến thức</button>` : ""}
          <button class="seg-btn ${ksMode === "mindmap" ? "active" : ""}" id="ks-mode-mindmap">Sơ đồ &amp; Thẻ ghi nhớ</button>
        </div>
      </div>

      <div id="ks-body"></div>
    `;

    container.querySelector("#ks-mode-source")?.addEventListener("click", () => {
      ksMode = "source";
      state.knowledgeMode = ksMode;
      syncCurrentUrl(false);
      draw();
    });
    container.querySelector("#ks-mode-mindmap")?.addEventListener("click", () => {
      ksMode = "mindmap";
      state.knowledgeMode = ksMode;
      syncCurrentUrl(false);
      draw();
    });

    const bodyEl = container.querySelector("#ks-body");

    if (ksMode === "source" && units.length) {
      const unit = units[activeUnitIdx] || units[0];
      const unitInteractiveIds = collectInteractiveUnitIds(unit.blocks || []);
      bodyEl.innerHTML = `
        <div class="sticky-sentinel" data-sticky-sub-sentinel aria-hidden="true"></div>
        <div class="lesson-tabs-bar sticky-subnav">
          <div class="sticky-lessons-list">
            ${units
          .map(
            (u, i) => `
              <button class="lesson-pill-tab ${i === activeUnitIdx ? "active" : ""}" data-ks-unit="${i}" title="${escapeHtml(u.lesson_number)}: ${escapeHtml(u.lesson_title)}">
                <span class="lesson-pill-short">${escapeHtml(u.lesson_number)}</span>
                <span class="lesson-pill-full">${escapeHtml(u.lesson_number)}: ${escapeHtml(u.lesson_title)}</span>
              </button>
            `
          )
          .join("")}
          </div>
          ${renderQuickTabsMiniHtml("knowledge")}
        </div>

        <article class="card prose-article prose-article-wide">
          <div style="margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--border);">
            <span class="pill pill-primary">${escapeHtml(unit.lesson_number)}</span>
            <h2 style="margin:6px 0 4px;font-size:1.2rem;">${formatBioHtml(unit.lesson_title)}</h2>
            <p style="margin:0;font-size:0.84rem;color:var(--text-muted);">Học sinh nhập đáp án trực tiếp vào các ô trả lời rồi bấm <strong>Kiểm tra đáp án</strong> để đối chiếu kết quả đúng ngay kế bên.</p>
          </div>
          ${renderInteractiveToolbar(unitInteractiveIds, `phiếu ${unit.lesson_number}`)}
          ${renderDocumentBlocks(unit.blocks, true)}
        </article>
      `;

      bindInteractiveExerciseEvents(bodyEl, unitInteractiveIds, draw, {
        topicId: topic.id,
        sourceTab: "knowledge",
        lessonLabel: `${unit.lesson_number || ""}: ${unit.lesson_title || ""}`.replace(/^:\s*/, ""),
      });

      bodyEl.querySelectorAll("[data-ks-unit]").forEach((btn) => {
        btn.addEventListener("click", () => {
          activeUnitIdx = Number(btn.dataset.ksUnit);
          state.knowledgeUnitIdx = activeUnitIdx;
          syncCurrentUrl(false);
          draw();
          const activePill = container.querySelector(`[data-ks-unit="${activeUnitIdx}"]`);
          activePill?.scrollIntoView({ inline: "nearest", block: "nearest" });
          window.scrollTo({ top: 0, behavior: "smooth" });
        });
      });
      setupStickyNavigation();
      return;
    }

    bodyEl.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:20px;">
        <section class="card">
          <h3 class="card-title">Sơ đồ tổng hợp theo bài</h3>
          <div class="mindmap-grid">
            ${(ks.mindmap?.branches || [])
        .map(
          (br) => `
                <div class="mindmap-branch">
                  <div class="mindmap-branch-head" data-toggle-branch="${br.id}">
                    <span>${formatBioHtml(br.title)}</span>
                    <span style="color:var(--text-muted);">▾</span>
                  </div>
                  <div class="mindmap-branch-body" id="branch-body-${br.id}">
                    <ul>
                      ${(br.nodes || []).map((n) => `<li>${formatBioHtml(n)}</li>`).join("")}
                    </ul>
                  </div>
                </div>
              `
        )
        .join("")}
          </div>
        </section>

        ${(ks.formulas || []).length
        ? `
              <section class="card">
                <h3 class="card-title">Công thức &amp; Quy tắc trọng tâm</h3>
                <div class="formula-grid">
                  ${ks.formulas
          .map(
            (f) => `
                      <div class="formula-card">
                        <strong style="font-size:0.86rem;">${formatBioHtml(f.name)}</strong>
                        <div class="formula-expr">${formatBioHtml(f.expression)}</div>
                      </div>
                    `
          )
          .join("")}
                </div>
              </section>
            `
        : ""
      }

        ${(ks.flashcards || []).length
        ? `
              <section class="card">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                  <h3 class="card-title" style="margin:0;">Thẻ ghi nhớ nhanh</h3>
                  <span class="pill pill-muted">Nhấn vào thẻ để lật</span>
                </div>
                <div class="flashcard-grid">
                  ${ks.flashcards
          .map(
            (fc, i) => `
                      <div class="flashcard" data-fc-idx="${i}">
                        <span class="pill pill-primary" data-fc-tag>Thẻ ${i + 1}</span>
                        <div style="font-weight:600;margin:10px 0;font-size:0.9rem;" data-fc-text>${formatBioHtml(fc.front)}</div>
                        <small style="color:var(--text-muted);" data-fc-hint>Xem nội dung</small>
                      </div>
                    `
          )
          .join("")}
                </div>
              </section>
            `
        : ""
      }
      </div>
    `;

    bodyEl.querySelectorAll("[data-toggle-branch]").forEach((head) => {
      head.addEventListener("click", () => {
        const body = bodyEl.querySelector(`#branch-body-${head.dataset.toggleBranch}`);
        if (body) body.style.display = body.style.display === "none" ? "block" : "none";
      });
    });

    bodyEl.querySelectorAll("[data-fc-idx]").forEach((card) => {
      const fc = ks.flashcards[Number(card.dataset.fcIdx)];
      let flipped = false;
      card.addEventListener("click", () => {
        flipped = !flipped;
        card.classList.toggle("flipped", flipped);
        card.querySelector("[data-fc-tag]").textContent = flipped ? "Trọng tâm" : `Thẻ ${Number(card.dataset.fcIdx) + 1}`;
        card.querySelector("[data-fc-text]").innerHTML = formatBioHtml(flipped ? fc.back : fc.front);
        card.querySelector("[data-fc-hint]").textContent = flipped ? "Lật lại" : "Xem nội dung";
      });
    });

    setupStickyNavigation();
  };

  draw();
}

// ================== TAB 3: HỆ THỐNG ÔN TẬP ==================
function renderReviewTab(container) {
  const topic = state.activeTopic;
  if (!topic || !topic.review) {
    container.innerHTML = `<div class="empty-state"><div class="empty-state-title">Chưa có câu hỏi ôn tập</div></div>`;
    return;
  }
  const canEditKeys = state.user?.role === "admin" && !state.teacherPreviewAsStudent;
  mountQuizSection(container, topic, state.user, showToast, {
    canEditKeys,
    onTopicUpdated: (updated) => {
      state.activeTopic = updated;
    },
  });
}

// ================== THEO DÕI TỰ ĐỘNG CÁC MỤC LÝ THUYẾT ĐÃ HỌC ==================
let _activeTheoryObserver = null;
const _theorySectionTimers = new Map();
const recordedTheorySectionKeys = new Set();

function cleanupTheoryObserver() {
  if (_activeTheoryObserver) {
    try {
      _activeTheoryObserver.disconnect();
    } catch { }
    _activeTheoryObserver = null;
  }
  _theorySectionTimers.forEach((t) => clearTimeout(t));
  _theorySectionTimers.clear();
}

function setupTheorySectionObserver(bodyEl, topic, activeLesson) {
  cleanupTheoryObserver();
  if (!state.user || !bodyEl || !topic?.id || !activeLesson?.id) return;

  const pendingBatch = new Map();
  let flushTimer = null;

  const flushBatch = () => {
    if (!pendingBatch.size) return;
    const sections = Array.from(pendingBatch.values());
    pendingBatch.clear();
    api
      .recordTheoryReads({
        topic_id: topic.id,
        lesson_id: activeLesson.id,
        lesson_number: activeLesson.number || "",
        lesson_title: activeLesson.title || "",
        sections,
      })
      .then(() => clientCache.invalidateTeacherData())
      .catch(() => { });
  };

  const queueSection = (secKey, secHeading, durSec = 5) => {
    const uniq = `${activeLesson.id}::${secKey}`;
    if (recordedTheorySectionKeys.has(uniq)) return;
    recordedTheorySectionKeys.add(uniq);
    pendingBatch.set(secKey, {
      key: secKey,
      heading: secHeading,
      duration_delta: durSec,
      completed: 1,
    });
    if (flushTimer) clearTimeout(flushTimer);
    flushTimer = setTimeout(flushBatch, 600);
  };

  const secEls = Array.from(bodyEl.querySelectorAll("section.theory-section[data-section-key]"));
  if (!secEls.length) return;

  if (typeof IntersectionObserver === "undefined") {
    const first = secEls[0];
    queueSection(first.dataset.sectionKey, first.dataset.sectionHeading || "", 5);
    return;
  }

  _activeTheoryObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const el = entry.target;
        const secKey = el.dataset.sectionKey;
        const secHeading = el.dataset.sectionHeading || secKey;
        const uniq = `${activeLesson.id}::${secKey}`;
        if (recordedTheorySectionKeys.has(uniq)) return;

        if (entry.isIntersecting) {
          if (!_theorySectionTimers.has(uniq)) {
            const tm = setTimeout(() => {
              _theorySectionTimers.delete(uniq);
              queueSection(secKey, secHeading, 5);
            }, 1200);
            _theorySectionTimers.set(uniq, tm);
          }
        } else if (_theorySectionTimers.has(uniq)) {
          clearTimeout(_theorySectionTimers.get(uniq));
          _theorySectionTimers.delete(uniq);
        }
      });
    },
    { threshold: 0.1 }
  );

  secEls.forEach((el) => _activeTheoryObserver.observe(el));
}

// ================== TAB 5: HỒ SƠ CÁ NHÂN ==================
async function renderProfileTab(container) {
  const user = state.user;
  const [, myReport] = await Promise.all([
    loadMyProgressAndSessions(),
    api.myLearningReport().catch(() => null),
  ]);
  const totalSec = state.mySessions.reduce((acc, s) => acc + (s.duration_seconds || 0), 0);
  const colors = ["#0f766e", "#0369a1", "#4f46e5", "#b45309", "#be123c", "#15803d"];
  const sm = myReport?.summary || null;

  const progressSummaryHtml = sm
    ? `
      <div class="card" style="margin-bottom:20px;border-color:var(--primary-border);background:linear-gradient(135deg,#f0fdfa 0%,#ffffff 100%);">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px;">
          <div>
            <h3 class="card-title" style="margin:0 0 2px;">Tiến độ học tập &amp; Tỉ lệ làm bài của bạn</h3>
            <p style="margin:0;font-size:0.83rem;color:var(--text-secondary);">Thống kê tự động các mục Lý thuyết đã học, Bài tập vận dụng đã làm và Kết quả từng đợt Hệ thống ôn tập.</p>
          </div>
          <span class="pill pill-primary">${sm.session_count || 0} phiên học · ${formatDuration(sm.total_study_seconds || totalSec)}</span>
        </div>
        <div class="stats-grid" style="margin-bottom:14px;">
          <div class="stat-card" style="background:#fff;">
            <div class="stat-label">Lý thuyết đã học</div>
            <div class="stat-value" style="color:var(--primary);">${sm.theory_pct}%</div>
            <div class="progress-bar-track"><div class="progress-bar-fill" style="width:${Math.min(100, sm.theory_pct)}%;"></div></div>
            <small style="color:var(--text-muted);">${sm.studied_lessons}/${sm.total_lessons} bài · ${sm.studied_sections}/${sm.total_sections} mục</small>
          </div>
          <div class="stat-card" style="background:#fff;">
            <div class="stat-label">Bài tập LT &amp; HTKT</div>
            <div class="stat-value" style="color:#0369a1;">${sm.exercise_completion_pct}%</div>
            <div class="progress-bar-track"><div class="progress-bar-fill fill-blue" style="width:${Math.min(100, sm.exercise_completion_pct)}%;"></div></div>
            <small style="color:var(--text-muted);">${sm.exercises_done}/${sm.exercises_total} bài · Đúng: <strong>${sm.exercise_accuracy_pct !== null ? `${sm.exercise_accuracy_pct}%` : "—"}</strong></small>
          </div>
          <div class="stat-card" style="background:#fff;">
            <div class="stat-label">Hệ thống ôn tập</div>
            <div class="stat-value" style="color:#15803d;">${sm.review_accuracy_pct !== null ? `${sm.review_accuracy_pct}%` : "—"}</div>
            <div class="progress-bar-track"><div class="progress-bar-fill fill-green" style="width:${Math.min(100, sm.review_accuracy_pct || 0)}%;"></div></div>
            <small style="color:var(--text-muted);">${sm.review_rounds_count} đợt · Đúng ${sm.review_correct_total}/${sm.review_questions_total} câu/ý</small>
          </div>
        </div>
        ${(myReport.topics || []).length
      ? `
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;">
                ${myReport.topics
        .map(
          (tp) => `
                    <div style="padding:10px 12px;border-radius:10px;background:#fff;border:1px solid var(--border);font-size:0.82rem;">
                      <div style="font-weight:700;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${escapeHtml(tp.title)}">${escapeHtml(tp.title)}</div>
                      <div class="progress-bar-track" style="margin-bottom:6px;"><div class="progress-bar-fill" style="width:${Math.min(100, tp.theory_pct)}%;"></div></div>
                      <div style="display:flex;justify-content:space-between;color:var(--text-secondary);gap:6px;">
                        <span>LT: <strong>${tp.theory_pct}%</strong> (${tp.studied_sections}/${tp.total_sections} mục)</span>
                        <span>Ôn tập: <strong>${tp.review_accuracy_pct !== null ? `${tp.review_accuracy_pct}%` : "—"}</strong></span>
                      </div>
                    </div>
                  `
        )
        .join("")}
              </div>
            `
      : ""
    }
      </div>
    `
    : "";

  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Hồ sơ cá nhân</h1>
        <p>Quản lý thông tin tài khoản, tiến độ học tập và nhật ký tham gia lớp học</p>
      </div>
    </div>

    ${progressSummaryHtml}

    <div style="display:grid;grid-template-columns:1.1fr 1fr;gap:20px;align-items:start;">
      <div class="card">
        <div style="display:flex;align-items:center;gap:14px;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--border);">
          <span class="avatar-circle" style="width:48px;height:48px;font-size:1.05rem;background:${user.avatar_color};">${getInitials(user.full_name)}</span>
          <div>
            <div style="font-weight:700;font-size:1.05rem;">${escapeHtml(user.full_name)}</div>
            <div style="font-size:0.82rem;color:var(--text-muted);">${roleDisplayName(user.role)} · @${escapeHtml(user.username)}</div>
          </div>
        </div>

        <form id="profile-update-form">
          <div class="form-row-2">
            <div class="form-group">
              <label>Họ và tên</label>
              <input class="form-control" name="full_name" required value="${escapeHtml(user.full_name || "")}" />
            </div>
            <div class="form-group">
              <label>${user.role === "teacher" ? "Tổ chuyên môn" : "Lớp học"}</label>
              <input class="form-control" name="class_name" value="${escapeHtml(user.class_name || "")}" />
            </div>
          </div>

          <div class="form-row-2">
            <div class="form-group">
              <label>Email</label>
              <input type="email" class="form-control" name="email" required value="${escapeHtml(user.email || "")}" />
            </div>
            <div class="form-group">
              <label>Số điện thoại</label>
              <input class="form-control" name="phone" value="${escapeHtml(user.phone || "")}" />
            </div>
          </div>

          <div class="form-group">
            <label>Trường THPT</label>
            <input class="form-control" name="school_name" value="${escapeHtml(user.school_name || "")}" />
          </div>

          <div class="form-group">
            <label>Giới thiệu / Ghi chú</label>
            <textarea class="form-control" name="bio" rows="2">${escapeHtml(user.bio || "")}</textarea>
          </div>

          <div class="form-group">
            <label>Màu ảnh đại diện</label>
            <div style="display:flex;gap:8px;">
              ${colors
      .map(
        (c) => `
                  <label style="cursor:pointer;">
                    <input type="radio" name="avatar_color" value="${c}" ${user.avatar_color === c ? "checked" : ""} style="display:none;" />
                    <span style="display:inline-block;width:24px;height:24px;border-radius:50%;background:${c};border:2.5px solid ${user.avatar_color === c ? "#0f172a" : "transparent"};"></span>
                  </label>
                `
      )
      .join("")}
            </div>
          </div>

          <hr style="border:none;border-top:1px solid var(--border);margin:16px 0;" />
          <p style="margin:0 0 10px;font-size:0.82rem;color:var(--text-muted);font-weight:600;">
            Đổi mật khẩu (bỏ trống nếu giữ nguyên${user.role !== "admin" ? " · dữ liệu đổi mật khẩu sẽ được báo về Quản trị viên" : ""})
          </p>
          <div class="form-row-2">
            <div class="form-group">
              <label>Mật khẩu hiện tại</label>
              <input type="password" class="form-control" name="current_password" />
            </div>
            <div class="form-group">
              <label>Mật khẩu mới</label>
              <input type="password" class="form-control" name="new_password" />
            </div>
          </div>

          <button type="submit" class="btn btn-primary">Lưu thay đổi</button>
        </form>
      </div>

      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px;">
          <h3 class="card-title" style="margin:0;">Lịch sử vào &amp; rời lớp</h3>
          <span class="pill pill-primary">${state.mySessions.length} buổi · ${formatDuration(totalSec)}</span>
        </div>

        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>Vào lớp</th><th>Rời lớp</th><th>Thời lượng</th><th>Trạng thái</th></tr>
            </thead>
            <tbody>
              ${state.mySessions.length
      ? state.mySessions
        .slice(0, 12)
        .map(
          (s) => `
                        <tr>
                          <td>${formatDateTimeVN(s.enter_time)}</td>
                          <td>${s.leave_time ? formatDateTimeVN(s.leave_time) : "Đang học"}</td>
                          <td><strong>${formatDuration(s.duration_seconds)}</strong></td>
                          <td>${s.status === "active" ? `<span class="pill pill-green">Đang học</span>` : `<span class="pill pill-muted">Hoàn thành</span>`}</td>
                        </tr>
                      `
        )
        .join("")
      : `<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:18px;">Chưa có phiên học.</td></tr>`
    }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  container.querySelectorAll('input[name="avatar_color"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      state.user.avatar_color = radio.value;
      renderProfileTab(container);
    });
  });

  container.querySelector("#profile-update-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const res = await api.updateProfile({
        full_name: fd.get("full_name"),
        class_name: fd.get("class_name"),
        email: fd.get("email"),
        phone: fd.get("phone"),
        school_name: fd.get("school_name"),
        bio: fd.get("bio"),
        avatar_color: fd.get("avatar_color") || user.avatar_color,
        current_password: fd.get("current_password") || "",
        new_password: fd.get("new_password") || "",
      });
      state.user = res.user;
      showToast(res.message || "Đã cập nhật hồ sơ.", "success");
      render();
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

// ================== ROOT RENDER & BOOTSTRAP ==================
window.addEventListener("popstate", async () => {
  if (!state.user || state.user.must_change_password) return;
  const route = applyRouteGuardForUser(parseRoute(), state.user);
  if (state.activeTab === "mock_exam" && route.activeTab !== "mock_exam") {
    stopMockExamTimers();
  }
  if (state.activeTab === "theory" && route.activeTab !== "theory") {
    cleanupTheoryObserver();
  }
  state.mobileMenuOpen = false;
  state.activeTab = route.activeTab;
  state.theoryMode = route.theoryMode || "lessons";
  state.knowledgeMode = route.knowledgeMode || "source";
  state.knowledgeUnitIdx = route.knowledgeUnitIdx || 0;
  state.teacherSubtab = route.teacherSubtab || "members";
  state.teacherContentSubMode = route.teacherContentSubMode || "add_topic";
  state.teacherExamMixerMode = route.teacherExamMixerMode || "word";
  clientCache.setTeacherData({
    subtab: state.teacherSubtab,
    contentSubMode: state.teacherContentSubMode,
  });

  if (
    route.topicId &&
    route.topicId !== state.activeTopicId &&
    state.topicsList.some((t) => t.id === route.topicId)
  ) {
    await switchTopicSmoothly(route.topicId, route.lessonId || "", true);
    return;
  }

  if (route.lessonId && (state.activeTopic?.lessons || []).some((l) => l.id === route.lessonId)) {
    state.activeLessonId = route.lessonId;
  }
  sendThrottledHeartbeat(state.activeTopicId, state.activeTab);
  render();
});

function render() {
  setContentGuardAdmin(
    Boolean(state.user && state.user.role === "admin" && !state.teacherPreviewAsStudent)
  );
  if (!state.user) renderAuthView();
  else if (state.user.must_change_password) renderFirstLoginSetupView();
  else renderMainShell();
}

async function boot() {
  initContentGuard(showToast);
  const token = getToken();
  if (token) {
    try {
      const meRes = await api.me();
      state.user = meRes.user;
      if (meRes.active_session) {
        state.activeSession = meRes.active_session;
        setStoredSessionId(meRes.active_session.id);
      } else {
        if (getStoredSessionId()) setStoredSessionId(null);
      }
      await enterAuthenticatedApp();
      return;
    } catch {
      setToken("");
    }
  }
  render();
}

boot();
