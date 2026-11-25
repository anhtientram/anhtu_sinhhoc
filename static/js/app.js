import {
  api,
  formatDateTimeVN,
  formatDuration,
  formatTimeShort,
  getStoredSessionId,
  getToken,
  sendBeaconCheckout,
  setStoredSessionId,
  setToken,
  withBase,
} from "./api.js";
import { mountInteractiveDiagram } from "./diagrams.js";
import { escapeHtml, formatBioHtml } from "./format.js";
import { mountQuizSection } from "./quiz.js";
import { mountTeacherDashboard } from "./teacher.js";
import { mountYoutubeLibrary } from "./youtube_videos.js";

const appEl = document.getElementById("app");
const toastContainer = document.getElementById("toast-container");

const ICONS = {
  dna: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 15c6.667-6 13.333 0 20-6"/><path d="M9 22c1.798-1.998 2.518-3.995 2.807-5.993"/><path d="M15 2c-1.798 1.998-2.518 3.995-2.807 5.993"/><path d="M17 6l-2.5-2.5"/><path d="M14 8l-1-1"/><path d="M7 18l2.5 2.5"/><path d="M6.5 12.5l1 1"/><path d="M16.5 10.5l1 1"/></svg>`,
  book: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>`,
  layers: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
  checkSquare: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`,
  barChart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
  user: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  menu: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>`,
};

const state = {
  user: null,
  topicsList: [],
  activeTopicId: "chu-de-1",
  activeTopic: null,
  activeTab: "theory", // 'theory' | 'knowledge' | 'review' | 'teacher' | 'profile'
  theoryMode: "lessons", // 'lessons' | 'youtube'
  activeLessonId: "",
  teacherPreviewAsStudent: false,
  presentationMode: false,
  mobileMenuOpen: false,

  activeSession: null,
  sessionElapsedSeconds: 0,
  sessionTickTimer: null,
  heartbeatTimer: null,

  completedLessonIds: new Set(),
  mySessions: [],

  loginRole: "admin", // 'admin' | 'teacher' | 'student'
};

function isStaffRole(role) {
  return role === "admin" || role === "teacher";
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

  const enterMs = new Date(state.activeSession.enter_time).getTime();
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
      await api.heartbeatSession(state.activeSession.id, state.activeTopicId, state.activeTab);
    } catch {}
  }, 25000);
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
    } catch {}
    state.activeSession = null;
    setStoredSessionId(null);
    stopSessionTimers();
  }

  if (shouldLogout) {
    try {
      await api.logout();
    } catch {}
    setToken("");
    state.user = null;
    state.activeTab = "theory";
    state.teacherPreviewAsStudent = false;
    document.body.classList.remove("presentation-mode");
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
async function loadTopicsAndActive(topicId = state.activeTopicId) {
  const listRes = await api.listTopics();
  state.topicsList = listRes.topics || [];
  const chosenId = topicId || state.topicsList[0]?.id || "chu-de-1";
  state.activeTopicId = chosenId;
  const detailRes = await api.getTopic(chosenId);
  state.activeTopic = detailRes.topic;
  if (state.activeTopic?.lessons?.length) {
    state.activeLessonId = state.activeTopic.lessons[0].id;
  }
}

async function loadMyProgressAndSessions() {
  try {
    const [progRes, sessRes] = await Promise.all([api.myProgress(), api.mySessions()]);
    state.completedLessonIds = new Set(
      (progRes.progress || []).filter((p) => p.completed).map((p) => p.lesson_id)
    );
    state.mySessions = sessRes.sessions || [];
  } catch {}
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

        <div style="font-size:0.78rem;color:#94a3b8;">
          Bộ môn Sinh học 12 — Hệ thống cấp phát tài khoản tập trung
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
            <input class="form-control" name="full_name" required placeholder="${isTeacher ? "VD: Nguyễn Thị Minh" : "VD: Trần Văn An"}" />
          </div>

          ${
            isTeacher
              ? `
                <div class="form-row-2">
                  <div class="form-group">
                    <label>Trường *</label>
                    <input class="form-control" name="school_name" required placeholder="VD: Trường THPT Lê Hồng Phong" />
                  </div>
                  <div class="form-group">
                    <label>Số điện thoại *</label>
                    <input type="tel" class="form-control" name="phone" required placeholder="09xx xxx xxx" />
                  </div>
                </div>
              `
              : `
                <div class="form-row-2">
                  <div class="form-group">
                    <label>Lớp *</label>
                    <input class="form-control" name="class_name" required placeholder="VD: 12A1" />
                  </div>
                  <div class="form-group">
                    <label>Số điện thoại *</label>
                    <input type="tel" class="form-control" name="phone" required placeholder="09xx xxx xxx" />
                  </div>
                </div>
                <div class="form-group">
                  <label>Trường *</label>
                  <input class="form-control" name="school_name" required placeholder="VD: Trường THPT Lê Hồng Phong" />
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
  await loadTopicsAndActive(state.activeTopicId);
  await loadMyProgressAndSessions();
  if (state.user.role === "student") {
    await ensureStudentCheckedIn();
  }
  render();
}

// ================== MAIN WORKSPACE SHELL (LEFT CONTRASTING TOPICS + HIDDEN MENU DRAWER + CENTERED TABS) ==================
function renderMainShell() {
  const user = state.user;
  const isStaff = isStaffRole(user.role);
  const isAdmin = user.role === "admin";
  const effectiveStudentView = !isStaff || state.teacherPreviewAsStudent;
  const topic = state.activeTopic;
  const lessons = topic?.lessons || [];

  appEl.innerHTML = `
    <div class="app-root">
      <!-- Top Header with Menu Toggle -->
      <header class="app-topbar">
        <div class="topbar-left-group">
          <button class="menu-trigger-btn" id="btn-toggle-menu" aria-label="Mở thanh công cụ Menu">
            ${ICONS.menu}
            <span>Menu</span>
          </button>

          <div class="topbar-brand-inline" id="btn-brand-home">
            <div class="brand-mark" style="width:30px;height:30px;">${ICONS.dna}</div>
            <span>Sinh học 12</span>
          </div>

          ${
            topic
              ? `<span class="topbar-current-topic">${escapeHtml(topic.title)}</span>`
              : ""
          }
        </div>

        <div class="topbar-actions">
          ${
            !isStaff
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
                <span class="pill pill-primary">${state.teacherPreviewAsStudent ? "Xem như Học sinh" : roleDisplayName(user.role)}</span>
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
              <div style="font-size:0.72rem;color:var(--text-muted);">Sinh học 12 · GDPT 2018</div>
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
            ${
              !effectiveStudentView
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
                <button class="drawer-item ${t.id === state.activeTopicId ? "active" : ""}" data-select-topic="${t.id}">
                  <span style="font-weight:700;min-width:20px;">${t.order_index || idx + 1}.</span>
                  <span style="line-height:1.35;">${escapeHtml((t.title || "").replace(/^Chủ đề\s*\d+[\.\:]?\s*/i, ""))}</span>
                </button>
              `
              )
              .join("")}
          </div>
        </div>

        ${
          lessons.length
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

        ${
          isStaff
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

      <!-- Main 2-Column Body: Left Contrasting Topics + Centered Content Tabs & View -->
      <div class="workspace-body">
        <aside class="topics-rail" aria-label="Danh sách Chủ đề">
          <div class="topics-rail-heading">Chủ đề Sinh học 12</div>
          ${state.topicsList
            .map((t, i) => {
              const num = t.order_index || i + 1;
              const themeCls = `topic-theme-${((num - 1) % 4) + 1}`;
              const shortTitle = (t.title || "").replace(/^Chủ đề\s*\d+[\.\:]?\s*/i, "");
              return `
                <button class="topic-color-card ${themeCls} ${t.id === state.activeTopicId ? "active" : ""}" data-select-topic="${t.id}">
                  <span class="topic-color-badge">Chủ đề ${num}</span>
                  <span class="topic-color-title">${escapeHtml(shortTitle || t.title)}</span>
                </button>
              `;
            })
            .join("")}
        </aside>

        <section class="center-stage">
          <!-- Centered Contrasting Content Cards -->
          <nav class="center-tabs-bar" aria-label="Các thẻ nội dung">
            <button class="center-tab-card ctab-theory ${state.activeTab === "theory" ? "active" : ""}" data-tab="theory">
              ${ICONS.book}<span>1. Lý thuyết</span>
            </button>
            <button class="center-tab-card ctab-knowledge ${state.activeTab === "knowledge" ? "active" : ""}" data-tab="knowledge">
              ${ICONS.layers}<span>2. Hệ thống kiến thức</span>
            </button>
            <button class="center-tab-card ctab-review ${state.activeTab === "review" ? "active" : ""}" data-tab="review">
              ${ICONS.checkSquare}<span>3. Hệ thống ôn tập</span>
            </button>
            ${
              !effectiveStudentView
                ? `
                  <button class="center-tab-card ctab-teacher ${state.activeTab === "teacher" ? "active" : ""}" data-tab="teacher">
                    ${ICONS.barChart}<span>${isAdmin ? "Quản trị hệ thống" : "Quản lý lớp học"}</span>
                  </button>
                `
                : ""
            }
          </nav>

          <div class="center-content-wrap" id="tab-view"></div>
        </section>
      </div>
    </div>
  `;

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
    render();
  });

  document.querySelectorAll("[data-select-topic]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.mobileMenuOpen = false;
      try {
        await loadTopicsAndActive(btn.dataset.selectTopic);
        render();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });

  document.querySelectorAll("[data-drawer-lesson]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.mobileMenuOpen = false;
      state.activeTab = "theory";
      state.theoryMode = "lessons";
      state.activeLessonId = btn.dataset.drawerLesson;
      render();
    });
  });

  document.querySelectorAll("[data-tab], [data-drawer-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.mobileMenuOpen = false;
      state.activeTab = btn.dataset.tab || btn.dataset.drawerTab;
      if (state.activeSession) {
        api.heartbeatSession(state.activeSession.id, state.activeTopicId, state.activeTab).catch(() => {});
      }
      render();
    });
  });

  document.getElementById("btn-open-profile")?.addEventListener("click", () => {
    state.mobileMenuOpen = false;
    state.activeTab = "profile";
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
  if (state.activeTab === "theory") renderTheoryTab(tabView);
  else if (state.activeTab === "knowledge") renderKnowledgeTab(tabView);
  else if (state.activeTab === "review") renderReviewTab(tabView);
  else if (state.activeTab === "teacher") {
    mountTeacherDashboard(
      tabView,
      state.activeTopic,
      (updatedTopic) => {
        state.activeTopic = updatedTopic;
      },
      showToast,
      {
        currentUser: state.user,
        onTopicsReload: async (newTopicId) => {
          await loadTopicsAndActive(newTopicId || state.activeTopicId);
          render();
        },
      }
    );
  } else if (state.activeTab === "profile") {
    renderProfileTab(tabView);
  }
}

// ================== SHARED RICH CONTENT RENDERERS (với công thức chuẩn) ==================
function renderRichTable(rows, editableEmptyCells = false) {
  if (!rows || !rows.length) return "";
  const [header, ...body] = rows;
  return `
    <div class="data-table-wrap" style="margin:12px 0;">
      <table class="data-table">
        <thead>
          <tr>${header.map((c) => `<th>${formatBioHtml(c)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${body
            .map(
              (r) => `
              <tr>
                ${r
                  .map((c, ci) => {
                    const trimmed = (c || "").trim();
                    if (editableEmptyCells && (!trimmed || /^[\.\…\_\-]+$/.test(trimmed))) {
                      return `<td><input type="text" class="form-control form-control-sm" style="min-width:110px;" placeholder="Nhập nội dung..." /></td>`;
                    }
                    return ci === 0
                      ? `<td><strong>${formatBioHtml(c)}</strong></td>`
                      : `<td style="white-space:pre-line;">${formatBioHtml(c)}</td>`;
                  })
                  .join("")}
              </tr>
            `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderDocumentBlocks(blocks, editableEmptyCells = false) {
  if (!blocks || !blocks.length) return "";
  return blocks
    .map((b) => {
      if (b.type === "image") {
        return `
          <figure class="lesson-hero-figure">
            <img src="${withBase(b.src)}" alt="${escapeHtml(b.caption || "Hình minh họa Sinh học 12")}" loading="lazy" />
            ${b.caption ? `<figcaption>${formatBioHtml(b.caption)}</figcaption>` : ""}
          </figure>
        `;
      }
      if (b.type === "table") {
        const extraImgs = (b.images || [])
          .map(
            (src) => `
            <figure class="lesson-hero-figure" style="margin:10px 0;">
              <img src="${withBase(src)}" alt="Hình minh họa" loading="lazy" />
            </figure>
          `
          )
          .join("");
        return renderRichTable(b.rows, editableEmptyCells) + extraImgs;
      }
      const html = formatBioHtml(b.text || "");
      const isBullet = /^[-–+•]\s*/.test(b.text || "");
      if (b.is_bold) return `<p class="prose-p-bold">${html}</p>`;
      if (isBullet) return `<p class="prose-bullet">${html}</p>`;
      return `<p class="prose-p">${html}</p>`;
    })
    .join("");
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
  const canManageYt = isStaffRole(state.user?.role) && !state.teacherPreviewAsStudent;

  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1>${formatBioHtml(topic.title)}</h1>
        <p>${lessons.length} bài lý thuyết · ${ytCount} video YouTube đã nhúng</p>
      </div>
      <div class="segmented">
        <button class="seg-btn ${state.theoryMode === "lessons" ? "active" : ""}" id="mode-lessons">Nội dung bài học</button>
        <button class="seg-btn ${state.theoryMode === "youtube" ? "active" : ""}" id="mode-youtube">Video bài giảng YouTube (${ytCount})</button>
      </div>
    </div>

    <div id="theory-body"></div>
  `;

  container.querySelector("#mode-lessons")?.addEventListener("click", () => {
    state.theoryMode = "lessons";
    renderTheoryTab(container);
  });
  container.querySelector("#mode-youtube")?.addEventListener("click", () => {
    state.theoryMode = "youtube";
    renderTheoryTab(container);
  });

  const bodyEl = container.querySelector("#theory-body");

  if (state.theoryMode === "youtube") {
    mountYoutubeLibrary(bodyEl, topic, {
      canManage: canManageYt,
      onTopicUpdated: (updated) => {
        state.activeTopic = updated;
      },
      showToast,
    });
    return;
  }

  const isDone = state.completedLessonIds.has(activeLesson.id);
  bodyEl.innerHTML = `
    <div class="lesson-tabs-bar">
      ${lessons
        .map((l) => {
          const done = state.completedLessonIds.has(l.id);
          return `
            <button class="lesson-pill-tab ${l.id === activeLesson.id ? "active" : ""}" data-lesson-id="${l.id}">
              ${escapeHtml(l.number)}: ${escapeHtml(l.title)}${done ? " ✓" : ""}
            </button>
          `;
        })
        .join("")}
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

      ${(activeLesson.sections || [])
        .map(
          (sec) => `
          <section class="theory-section">
            <h3>${formatBioHtml(sec.heading)}</h3>
            ${
              (sec.blocks || []).length
                ? renderDocumentBlocks(sec.blocks, false)
                : `<ul style="margin:0;padding-left:20px;color:var(--text-secondary);">${(sec.points || []).map((pt) => `<li>${formatBioHtml(pt)}</li>`).join("")}</ul>`
            }
          </section>
        `
        )
        .join("")}

      <div id="lesson-interactive-sim"></div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:24px;padding-top:16px;border-top:1px solid var(--border);flex-wrap:wrap;gap:10px;">
        <button class="btn btn-secondary btn-sm" id="btn-open-yt-from-lesson">Xem Video YouTube của chủ đề</button>
        <button class="btn btn-primary btn-sm" id="btn-goto-review-from-lesson">Chuyển sang Hệ thống ôn tập →</button>
      </div>
    </article>
  `;

  if (activeLesson.interactive_diagram) {
    mountInteractiveDiagram(bodyEl.querySelector("#lesson-interactive-sim"), activeLesson.interactive_diagram);
  }

  bodyEl.querySelectorAll("[data-lesson-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeLessonId = btn.dataset.lessonId;
      renderTheoryTab(container);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  bodyEl.querySelector("#btn-mark-lesson")?.addEventListener("click", async () => {
    try {
      await api.saveProgress({
        topic_id: topic.id,
        lesson_id: activeLesson.id,
        completed: true,
        checkpoint_score: 1,
      });
      state.completedLessonIds.add(activeLesson.id);
      showToast(`Đã lưu tiến độ ${activeLesson.number}`, "success");
      renderTheoryTab(container);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  bodyEl.querySelector("#btn-open-yt-from-lesson")?.addEventListener("click", () => {
    state.theoryMode = "youtube";
    renderTheoryTab(container);
  });

  bodyEl.querySelector("#btn-goto-review-from-lesson")?.addEventListener("click", () => {
    state.activeTab = "review";
    render();
  });
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
  let ksMode = units.length ? "source" : "mindmap";
  let activeUnitIdx = 0;

  const draw = () => {
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Hệ thống kiến thức — ${formatBioHtml(topic.title)}</h1>
          <p>${units.length} phiếu bài học · ${(ks.flashcards || []).length} thẻ ghi nhớ</p>
        </div>
        <div class="segmented">
          ${units.length ? `<button class="seg-btn ${ksMode === "source" ? "active" : ""}" id="ks-mode-source">Phiếu hệ thống kiến thức</button>` : ""}
          <button class="seg-btn ${ksMode === "mindmap" ? "active" : ""}" id="ks-mode-mindmap">Sơ đồ &amp; Thẻ ghi nhớ</button>
        </div>
      </div>

      <div id="ks-body"></div>
    `;

    container.querySelector("#ks-mode-source")?.addEventListener("click", () => {
      ksMode = "source";
      draw();
    });
    container.querySelector("#ks-mode-mindmap")?.addEventListener("click", () => {
      ksMode = "mindmap";
      draw();
    });

    const bodyEl = container.querySelector("#ks-body");

    if (ksMode === "source" && units.length) {
      const unit = units[activeUnitIdx] || units[0];
      bodyEl.innerHTML = `
        <div class="lesson-tabs-bar">
          ${units
            .map(
              (u, i) => `
              <button class="lesson-pill-tab ${i === activeUnitIdx ? "active" : ""}" data-ks-unit="${i}">
                ${escapeHtml(u.lesson_number)}: ${escapeHtml(u.lesson_title)}
              </button>
            `
            )
            .join("")}
        </div>

        <article class="card prose-article">
          <div style="margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--border);">
            <span class="pill pill-primary">${escapeHtml(unit.lesson_number)}</span>
            <h2 style="margin:6px 0 4px;font-size:1.2rem;">${formatBioHtml(unit.lesson_title)}</h2>
            <p style="margin:0;font-size:0.84rem;color:var(--text-muted);">Học sinh có thể điền trực tiếp vào các ô trống trong bảng để tự tổng hợp kiến thức.</p>
          </div>
          ${renderDocumentBlocks(unit.blocks, true)}
        </article>
      `;

      bodyEl.querySelectorAll("[data-ks-unit]").forEach((btn) => {
        btn.addEventListener("click", () => {
          activeUnitIdx = Number(btn.dataset.ksUnit);
          draw();
        });
      });
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

        ${
          (ks.formulas || []).length
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

        ${
          (ks.flashcards || []).length
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
  const canEditKeys = isStaffRole(state.user?.role) && !state.teacherPreviewAsStudent;
  mountQuizSection(container, topic, state.user, showToast, {
    canEditKeys,
    onTopicUpdated: (updated) => {
      state.activeTopic = updated;
    },
  });
}

// ================== TAB 5: HỒ SƠ CÁ NHÂN ==================
async function renderProfileTab(container) {
  const user = state.user;
  await loadMyProgressAndSessions();
  const totalSec = state.mySessions.reduce((acc, s) => acc + (s.duration_seconds || 0), 0);
  const colors = ["#0f766e", "#0369a1", "#4f46e5", "#b45309", "#be123c", "#15803d"];

  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Hồ sơ cá nhân</h1>
        <p>Quản lý thông tin tài khoản và nhật ký tham gia lớp học</p>
      </div>
    </div>

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
              ${
                state.mySessions.length
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
function render() {
  if (!state.user) renderAuthView();
  else if (state.user.must_change_password) renderFirstLoginSetupView();
  else renderMainShell();
}

async function boot() {
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
