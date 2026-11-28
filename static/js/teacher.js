// Bảng điều khiển Quản trị viên (Giáo viên):
// - Nhật ký Vào/Rời lớp & Lịch sử đăng nhập (đếm số lần truy cập từng học sinh)
// - Trộn đề trắc nghiệm theo Ma trận 3x3 (chọn nhiều bài trong nhiều chủ đề, xuất Word .docx & Excel .xlsx)
// - Chỉnh sửa & Thêm nội dung mới (Chủ đề, Bài học Lý thuyết, Câu hỏi mới, Video YouTube, Nhập file Word)
// - Kết quả Ôn tập & Danh sách Thành viên

import { api, clientCache, formatDateTimeVN, formatDuration, withBase } from "./api.js";
import { slimDocxFile } from "./docx_slim.js";
import { escapeHtml, formatBioHtml } from "./format.js";
import { openTopicPreviewModal } from "./topic_preview.js";
import { mountYoutubeLibrary } from "./youtube_videos.js";

const AVATAR_PALETTE = ["#0f766e", "#0369a1", "#4f46e5", "#b45309", "#be123c", "#15803d"];

function initialsOf(name = "") {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "U";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function compactDateVN(iso) {
  const full = formatDateTimeVN(iso);
  if (!full || full === "—" || full === "-") return "—";
  const m = String(full).match(/(\d{2}:\d{2})(?::\d{2})?\s*[,·-]?\s*(\d{2}\/\d{2})/);
  if (m) return `${m[2]} ${m[1]}`;
  const m2 = String(full).match(/(\d{2}\/\d{2})(?:\/\d{4})?\s+(\d{2}:\d{2})/);
  if (m2) return `${m2[1]} ${m2[2]}`;
  return String(full).slice(0, 14);
}

function accBadgeClass(pct) {
  if (pct === null || pct === undefined) return "is-slate";
  if (pct >= 80) return "is-green";
  if (pct >= 65) return "is-teal";
  if (pct >= 50) return "is-amber";
  return "is-red";
}

function kebabButtonHtml(dataAttrs) {
  return `
    <button type="button" class="rt-kebab-btn" aria-haspopup="menu" aria-expanded="false" title="Thao tác" ${dataAttrs}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <circle cx="12" cy="5" r="1.8"></circle>
        <circle cx="12" cy="12" r="1.8"></circle>
        <circle cx="12" cy="19" r="1.8"></circle>
      </svg>
    </button>
  `;
}

let _activeMenuAnchor = null;
let _menuGlobalBound = false;

function closeRowActionMenu() {
  const portal = document.getElementById("rt-action-menu-portal");
  if (portal) portal.remove();
  if (_activeMenuAnchor) {
    _activeMenuAnchor.classList.remove("is-open");
    _activeMenuAnchor.setAttribute("aria-expanded", "false");
    _activeMenuAnchor = null;
  }
}

function _ensureMenuGlobalListeners() {
  if (_menuGlobalBound || typeof document === "undefined") return;
  _menuGlobalBound = true;
  document.addEventListener("click", (e) => {
    const portal = document.getElementById("rt-action-menu-portal");
    if (!portal) return;
    if (portal.contains(e.target)) return;
    if (_activeMenuAnchor && _activeMenuAnchor.contains(e.target)) return;
    closeRowActionMenu();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeRowActionMenu();
  });
  window.addEventListener("scroll", closeRowActionMenu, true);
  window.addEventListener("resize", closeRowActionMenu);
}

function openRowActionMenu(anchorBtn, items = []) {
  _ensureMenuGlobalListeners();
  if (_activeMenuAnchor === anchorBtn && document.getElementById("rt-action-menu-portal")) {
    closeRowActionMenu();
    return;
  }
  closeRowActionMenu();

  const portal = document.createElement("div");
  portal.id = "rt-action-menu-portal";
  portal.className = "rt-action-menu";
  portal.setAttribute("role", "menu");

  items.forEach((item) => {
    if (!item) return;
    if (item.divider) {
      const div = document.createElement("div");
      div.className = "rt-action-divider";
      portal.appendChild(div);
      return;
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `rt-action-item${item.danger ? " is-danger" : ""}`;
    btn.setAttribute("role", "menuitem");
    btn.textContent = item.label;
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      closeRowActionMenu();
      item.onClick?.();
    });
    portal.appendChild(btn);
  });

  document.body.appendChild(portal);
  _activeMenuAnchor = anchorBtn;
  anchorBtn.classList.add("is-open");
  anchorBtn.setAttribute("aria-expanded", "true");

  const rect = anchorBtn.getBoundingClientRect();
  const menuRect = portal.getBoundingClientRect();
  const pad = 8;
  let left = rect.right - menuRect.width;
  if (left < pad) left = pad;
  if (left + menuRect.width > window.innerWidth - pad) {
    left = Math.max(pad, window.innerWidth - menuRect.width - pad);
  }
  let top = rect.bottom + 4;
  if (top + menuRect.height > window.innerHeight - pad) {
    top = Math.max(pad, rect.top - menuRect.height - 4);
  }
  portal.style.left = `${Math.round(left)}px`;
  portal.style.top = `${Math.round(top)}px`;
}

export function mountTeacherDashboard(container, activeTopic, onTopicUpdated, showToast, opts = {}) {
  const onTopicsReload = opts.onTopicsReload || (async () => {});
  const onSelectTopic = opts.onSelectTopic || null;
  const onSubRouteChange = opts.onSubRouteChange || null;
  const topicsList = Array.isArray(opts.topicsList) ? opts.topicsList : [];
  const currentUser = opts.currentUser || { role: "teacher" };
  const isAdmin = currentUser.role === "admin";
  const cachedTeacher = clientCache.getTeacherData();

  let subtab = opts.initialSubtab || cachedTeacher.subtab || "members"; // 'members' | 'attendance' | 'exam_mixer' | 'content' | 'scores' | 'pw_alerts'
  if (!isAdmin && (subtab === "content" || subtab === "pw_alerts")) {
    subtab = "members";
  }
  let overview = cachedTeacher.overview || null;
  let classFilter = "";
  let searchFilter = "";
  let memberClassFilter = "";
  let memberSearchFilter = "";
  let reportTopicFilter = "";
  let reportStudentFilter = "";
  let reportModal = null; // null | { kind: 'student'|'attempt', loading, error, data, tab, prevStudentId }
  let studentExcelResult = null;
  let studentExcelLoading = false;

  // Trạng thái Trộn đề Kiểm tra (Chế độ 1: Từ file Word .docx | Chế độ 2: Từ Ngân hàng Ma trận 3x3)
  let examMixerMode = opts.initialExamMixerMode || "word"; // 'word' | 'matrix'
  let examPool = cachedTeacher.examPool || null; // [{id, title, lessons: [{id, number, title, counts}]}]
  let selectedLessonIds = new Set();
  let matrix = {
    mcq: { nhan_biet: 8, thong_hieu: 6, van_dung: 4 },
    true_false: { nhan_biet: 1, thong_hieu: 2, van_dung: 1 },
    short_answer: { nhan_biet: 1, thong_hieu: 2, van_dung: 3 },
  };
  let examConfig = {
    school_name: "",
    exam_period: "KIỂM TRA GIỮA KÌ I",
    school_year: "2026 - 2027",
    subject: "",
    title: "KIỂM TRA GIỮA KÌ I",
    duration_minutes: 45,
    exam_count: 4,
    exam_codes: "1001, 1002, 1003, 1004",
  };
  let examGenerating = false;
  let examResult = null; // { job_id, summary }

  // Trạng thái Trộn đề trực tiếp từ file Word (.docx)
  let wordMixer = {
    file: null,
    loading: false,
    parsed: null, // { source_filename, content, stats, warnings, spelling_report }
    showPreview: false,
    generating: false,
    result: null, // { job_id, summary }
    sampleFiles: null, // null | [{filename, size_kb}]
    loadingSampleName: "",
  };

  async function ensureSampleExamsLoaded() {
    if (wordMixer.sampleFiles !== null) return;
    try {
      const res = await api.getExamMixerSamples();
      wordMixer.sampleFiles = res.files || [];
    } catch {
      wordMixer.sampleFiles = [];
    }
    if (subtab === "exam_mixer" && examMixerMode === "word") {
      render();
    }
  }

  let answerPdfApplying = false;
  let answerPdfReport = null;

  function buildDefault4DigitCodes(count, base = 1001) {
    const n = Math.max(1, Math.min(30, parseInt(count || "4", 10) || 4));
    const arr = [];
    for (let i = 0; i < n; i++) {
      arr.push(String(base + i).padStart(4, "0"));
    }
    return arr.join(", ");
  }

  function buildRandom4DigitCodes(count) {
    const n = Math.max(1, Math.min(30, parseInt(count || "4", 10) || 4));
    const set = new Set();
    while (set.size < n) {
      const code = String(1000 + Math.floor(Math.random() * 8999));
      set.add(code);
    }
    return Array.from(set).sort().join(", ");
  }

  // Trạng thái Chỉnh sửa / Thêm nội dung
  let contentSubMode = opts.initialContentSubMode || cachedTeacher.contentSubMode || "add_topic"; // 'add_topic' | 'add_question' | 'edit_lesson' | 'youtube' | 'import'
  let newQuestionType = "mcq";
  let editLessonId = (activeTopic?.lessons || [])[0]?.id || "__new__";

  const maxTopicOrder = topicsList.length
    ? Math.max(...topicsList.map((x) => Number(x.order_index || 0)), topicsList.length) + 1
    : 5;

  // Trạng thái Tạo Chủ đề mới từ file Word (.docx) / PDF (.pdf) kèm Xem trước & Đẩy dữ liệu
  let newTopicDraft = {
    order_index: maxTopicOrder,
    title: "",
    subtitle: "",
    file: null,
    loading: false,
    publishing: false,
    preview: null, // { stats, detected_title, extracted }
  };

  let cacheInfo = cachedTeacher.cacheInfo || null;
  let cacheClearing = false;
  let deletingTopicId = "";
  let editingTopicId = "";
  let editingTopicTitle = "";
  let editingTopicSubtitle = "";
  let savingTopicMetaId = "";

  let importState = {
    file: null,
    base64: "",
    preview: null,
    loading: false,
    sections: { theory: true, knowledge: true, review: true },
    replaceReview: true,
  };

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        const idx = result.indexOf(",");
        resolve(idx >= 0 ? result.slice(idx + 1) : result);
      };
      reader.onerror = () => reject(new Error("Không đọc được file từ máy."));
      reader.readAsDataURL(file);
    });
  }

  async function loadOverview(force = false) {
    const cached = clientCache.getTeacherData();
    if (!force && cached.overview && Date.now() - (cached.loadedAt || 0) < 60000) {
      overview = cached.overview;
      if (cached.cacheInfo) cacheInfo = cached.cacheInfo;
      return;
    }
    try {
      const [ov, cs] = await Promise.all([
        api.teacherOverview(),
        api.cacheStatus().catch(() => null),
      ]);
      overview = ov;
      if (cs?.cache) cacheInfo = cs.cache;
      clientCache.setTeacherData({
        overview: ov,
        cacheInfo,
        loadedAt: Date.now(),
      });
      render();
    } catch (err) {
      container.innerHTML = `<div class="card"><p style="color:var(--red);">${escapeHtml(err.message)}</p></div>`;
    }
  }

  async function ensureExamPoolLoaded() {
    if (examPool) return;
    try {
      const res = await api.adminExamPool();
      examPool = res.topics || [];
      clientCache.setTeacherData({ examPool });
      // Mặc định chọn tất cả các bài trong chủ đề đang mở
      if (selectedLessonIds.size === 0 && examPool.length) {
        const activeTp = examPool.find((t) => t.id === activeTopic?.id) || examPool[0];
        (activeTp.lessons || []).forEach((l) => selectedLessonIds.add(l.id));
      }
      render();
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function getUniqueClasses() {
    if (!overview) return [];
    return Array.from(new Set((overview.students || []).map((s) => s.class_name).filter(Boolean))).sort();
  }

  function computeAvailablePool() {
    const avail = {
      mcq: { nhan_biet: 0, thong_hieu: 0, van_dung: 0 },
      true_false: { nhan_biet: 0, thong_hieu: 0, van_dung: 0 },
      short_answer: { nhan_biet: 0, thong_hieu: 0, van_dung: 0 },
    };
    if (!examPool) return avail;
    examPool.forEach((tp) => {
      (tp.lessons || []).forEach((ls) => {
        if (!selectedLessonIds.has(ls.id)) return;
        ["mcq", "true_false", "short_answer"].forEach((k) => {
          ["nhan_biet", "thong_hieu", "van_dung"].forEach((lv) => {
            avail[k][lv] += ls.counts?.[k]?.[lv] || 0;
          });
        });
      });
    });
    return avail;
  }

  function render() {
    closeRowActionMenu();
    if (!overview) {
      container.innerHTML = `<div class="card" style="text-align:center;padding:40px;"><div class="spinner" style="margin:0 auto 12px;"></div>Đang tải dữ liệu quản trị...</div>`;
      return;
    }

    const st = overview.stats || {};
    const classes = getUniqueClasses();
    const unreadPw = st.unread_password_changes || 0;

    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1>${isAdmin ? "Quản trị hệ thống &amp; Quản lý lớp học" : "Quản lý lớp học (Giáo viên)"}</h1>
          <p>${
            isAdmin
              ? "Toàn quyền quản trị: thêm/xoá giáo viên, thêm học sinh (Excel/thủ công), nhận báo cáo đổi mật khẩu, trộn đề Ma trận 3×3 và biên soạn nội dung"
              : "Quản lý lớp học: thêm học sinh (Excel/thủ công), theo dõi truy cập, xem kết quả ôn tập và trộn đề Ma trận 3×3"
          }</p>
        </div>
        <button class="btn btn-secondary btn-sm" id="teacher-refresh-btn">Làm mới dữ liệu</button>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">Học sinh</div>
          <div class="stat-value">${st.student_count || 0}</div>
          <small style="color:var(--green);font-weight:600;">${st.online_students || 0} đang học</small>
        </div>
        <div class="stat-card">
          <div class="stat-label">Tổng lượt truy cập</div>
          <div class="stat-value">${st.total_logins || 0}</div>
          <small style="color:var(--text-muted)">${st.total_sessions || 0} phiên vào lớp · ${st.total_study_minutes || 0} phút</small>
        </div>
        <div class="stat-card">
          <div class="stat-label">Bài ôn tập đã nộp</div>
          <div class="stat-value">${st.total_attempts || 0}</div>
          <small style="color:var(--text-muted)">Tự động chấm điểm</small>
        </div>
        <div class="stat-card">
          <div class="stat-label">${isAdmin ? "Giáo viên &amp; Cảnh báo MK" : "Giáo viên"}</div>
          <div class="stat-value">${st.teacher_count || 0}</div>
          <small style="color:${isAdmin && unreadPw > 0 ? "var(--red)" : "var(--text-muted)"};font-weight:${isAdmin && unreadPw > 0 ? "700" : "400"};">
            ${isAdmin ? (unreadPw > 0 ? `${unreadPw} lượt đổi mật khẩu mới` : "Không có cảnh báo mới") : "Tài khoản giảng dạy"}
          </small>
        </div>
      </div>

      <div style="margin-bottom:18px;overflow-x:auto;">
        <div class="segmented" style="flex-wrap:wrap;">
          <button class="seg-btn ${subtab === "members" ? "active" : ""}" data-tsub="members">Quản lý thành viên</button>
          <button class="seg-btn ${subtab === "attendance" ? "active" : ""}" data-tsub="attendance">Nhật ký &amp; Lượt truy cập</button>
          <button class="seg-btn ${subtab === "exam_mixer" ? "active" : ""}" data-tsub="exam_mixer">Trộn đề kiểm tra</button>
          ${
            isAdmin
              ? `<button class="seg-btn ${subtab === "content" ? "active" : ""}" data-tsub="content">Chỉnh sửa &amp; Thêm nội dung</button>`
              : ""
          }
          <button class="seg-btn ${subtab === "scores" ? "active" : ""}" data-tsub="scores">Báo cáo học tập &amp; Ôn tập</button>
          ${
            isAdmin
              ? `<button class="seg-btn ${subtab === "pw_alerts" ? "active" : ""}" data-tsub="pw_alerts">
                   Báo cáo đổi mật khẩu${unreadPw > 0 ? ` (${unreadPw})` : ""}
                 </button>`
              : ""
          }
        </div>
      </div>

      <div id="teacher-subview">
        ${
          subtab === "attendance"
            ? renderAttendanceView(classes)
            : subtab === "exam_mixer"
            ? renderExamMixerView()
            : subtab === "content" && isAdmin
            ? renderContentStudio()
            : subtab === "scores"
            ? renderScoresView(classes)
            : subtab === "pw_alerts" && isAdmin
            ? renderPasswordAlertsView()
            : renderMembersView()
        }
      </div>
      ${renderAnalyticsModal()}
    `;

    container.querySelectorAll("[data-tsub]").forEach((btn) => {
      btn.addEventListener("click", () => {
        subtab = btn.dataset.tsub;
        clientCache.setTeacherData({ subtab });
        onSubRouteChange?.({ subtab, contentSubMode, examMixerMode });
        if (subtab === "exam_mixer" && examMixerMode === "matrix" && !examPool) {
          render();
          ensureExamPoolLoaded();
        } else if (subtab === "exam_mixer" && examMixerMode === "word" && wordMixer.sampleFiles === null) {
          render();
          ensureSampleExamsLoaded();
        } else {
          render();
        }
      });
    });

    container.querySelector("#teacher-refresh-btn")?.addEventListener("click", () => {
      examPool = null;
      clientCache.invalidateTeacherData();
      loadOverview(true);
      if (subtab === "exam_mixer") ensureExamPoolLoaded();
      showToast("Đã làm mới dữ liệu.", "success");
    });

    bindSubviewEvents();
  }

  // ================== 1. NHẬT KÝ VÀO/RỜI LỚP & ĐĂNG NHẬP ==================
  function renderAttendanceView(classes) {
    const sessions = (overview.sessions || []).filter((s) => {
      if (s.role !== "student") return false;
      if (classFilter && s.class_name !== classFilter) return false;
      if (searchFilter && !`${s.full_name} ${s.username}`.toLowerCase().includes(searchFilter.toLowerCase())) return false;
      return true;
    });

    const loginLogs = (overview.login_logs || []).filter((l) => {
      if (l.role !== "student") return false;
      if (classFilter && l.class_name !== classFilter) return false;
      if (searchFilter && !`${l.full_name} ${l.username}`.toLowerCase().includes(searchFilter.toLowerCase())) return false;
      return true;
    });

    const tabNames = { theory: "Lý thuyết", knowledge: "Hệ thống kiến thức", review: "Ôn tập", profile: "Hồ sơ" };

    return `
      <div style="display:flex;flex-direction:column;gap:18px;">
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px;">
            <h3 class="card-title" style="margin:0;">Nhật ký thời gian vào học &amp; rời lớp</h3>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <select id="att-class-filter" class="form-control form-control-sm" style="width:auto;">
                <option value="">Tất cả các lớp</option>
                ${classes.map((c) => `<option value="${c}" ${classFilter === c ? "selected" : ""}>Lớp ${escapeHtml(c)}</option>`).join("")}
              </select>
              <input id="att-search" class="form-control form-control-sm" style="width:190px;" placeholder="Tìm học sinh..." value="${escapeHtml(searchFilter)}" />
              <a class="btn btn-primary btn-sm" href="${api.exportSessionsUrl(classFilter)}" target="_blank">Xuất CSV</a>
            </div>
          </div>

          <div class="data-table-wrap">
            <table class="data-table">
              <thead>
                <tr><th>Học sinh</th><th>Lớp</th><th>Vào học</th><th>Rời lớp</th><th>Thời lượng</th><th>Mục gần nhất</th><th>Trạng thái</th></tr>
              </thead>
              <tbody>
                ${
                  sessions.length
                    ? sessions
                        .map(
                          (s) => `
                          <tr>
                            <td><strong>${escapeHtml(s.full_name)}</strong><br/><small style="color:var(--text-muted)">@${escapeHtml(s.username)}</small></td>
                            <td>${escapeHtml(s.class_name || "—")}</td>
                            <td>${formatDateTimeVN(s.enter_time)}</td>
                            <td>${s.leave_time ? formatDateTimeVN(s.leave_time) : `<span style="color:var(--green);font-weight:600;">Đang trong lớp</span>`}</td>
                            <td><strong>${formatDuration(s.duration_seconds)}</strong></td>
                            <td>${tabNames[s.last_tab] || escapeHtml(s.last_tab)}</td>
                            <td>${s.status === "active" ? `<span class="pill pill-green">Đang học</span>` : `<span class="pill pill-muted">Đã rời lớp</span>`}</td>
                          </tr>
                        `
                        )
                        .join("")
                    : `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:22px;">Không có dữ liệu phù hợp.</td></tr>`
                }
              </tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <h3 class="card-title">Lịch sử đăng nhập hệ thống của Học sinh (${loginLogs.length} lượt gần nhất)</h3>
          <div class="data-table-wrap">
            <table class="data-table">
              <thead>
                <tr><th>Họ và tên</th><th>Tên đăng nhập</th><th>Trường</th><th>Lớp</th><th>Số điện thoại</th><th>Thời điểm đăng nhập</th></tr>
              </thead>
              <tbody>
                ${
                  loginLogs.length
                    ? loginLogs
                        .slice(0, 60)
                        .map(
                          (l) => `
                          <tr>
                            <td><strong>${escapeHtml(l.full_name)}</strong></td>
                            <td>@${escapeHtml(l.username)}</td>
                            <td>${escapeHtml(l.school_name || "—")}</td>
                            <td>${escapeHtml(l.class_name || "—")}</td>
                            <td>${escapeHtml(l.phone || "—")}</td>
                            <td>${formatDateTimeVN(l.login_time)}</td>
                          </tr>
                        `
                        )
                        .join("")
                    : `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:20px;">Chưa có lịch sử đăng nhập mới.</td></tr>`
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }

  // ================== 2. TRỘN ĐỀ KIỂM TRA (TỪ FILE WORD .DOCX HOẶC MA TRẬN 3x3) ==================
  function renderExamMixerView() {
    const modeSwitcher = `
      <div class="segmented" style="margin-bottom:16px;flex-wrap:wrap;">
        <button type="button" class="seg-btn ${examMixerMode === "word" ? "active" : ""}" data-em-mode="word">
          📄 Trộn đề từ file Word (.docx)
        </button>
        <button type="button" class="seg-btn ${examMixerMode === "matrix" ? "active" : ""}" data-em-mode="matrix">
          🧮 Trộn đề từ Ngân hàng (Ma trận 3×3)
        </button>
      </div>
    `;

    if (examMixerMode === "word") {
      const wp = wordMixer.parsed;
      const ws = wp?.stats;
      const wc = wp?.content || { mcq: [], true_false: [], short_answer: [] };
      const letters = ["A", "B", "C", "D"];
      const codePreviewList = (examConfig.exam_codes || "")
        .split(/[,;\s]+/)
        .map((c) => c.trim())
        .filter(Boolean);

      return `
        <div>
          ${modeSwitcher}
          <div style="display:flex;flex-direction:column;gap:18px;">
            <!-- Bước 1: Tải file Word (.docx) & Nhận diện đáp án thông minh -->
            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
                <div>
                  <h3 class="card-title" style="margin:0 0 3px;">Bước 1. Tải đề kiểm tra gốc từ file Word (.docx)</h3>
                  <p style="margin:0;font-size:0.83rem;color:var(--text-secondary);">
                    Dành cho <strong>Quản trị viên</strong> và <strong>Giáo viên</strong>: hệ thống tự đọc câu hỏi, hình ảnh, công thức, kiểm tra chính tả và nhận diện đáp án thông minh trước khi trộn.
                  </p>
                </div>
              </div>

              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;margin-bottom:14px;">
                <!-- Hướng dẫn 1: Quy ước câu hỏi & đáp án (chuẩn Young Mix / Bộ GD&ĐT) -->
                <div style="padding:14px 16px;border-radius:12px;border:1.5px dashed #94a3b8;background:#f8fafc;font-size:0.82rem;line-height:1.58;color:var(--text);">
                  <div style="font-weight:700;color:var(--primary);margin-bottom:8px;">📋 Hướng dẫn định dạng Câu hỏi &amp; Đáp án trong file Word (.docx)</div>
                  <ul style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:5px;">
                    <li>Câu hỏi bắt đầu bằng chữ <strong>"Câu"</strong> (VD: <code>Câu 1</code>, <code>Câu 2</code>,...) hoặc chữ <strong>"Question"</strong> (VD: <code>Question 1</code>, <code>Question 2</code>,...).</li>
                    <li>Phải <strong>xuống dòng (gõ Enter)</strong> trước khi gõ các đáp án.</li>
                    <li>Các đáp án bắt đầu bằng <strong>"A."</strong>, <strong>"B."</strong>, <strong>"C."</strong>, <strong>"D."</strong>. Nếu cần <strong>cố định đáp án</strong> nào thì đặt thêm dấu <code><strong>#</strong></code> liền trước, ví dụ: <code><strong>#A.</strong></code>, <code><strong>#D.</strong></code>.</li>
                    <li>Mỗi đáp án nên nằm trên một dòng để hệ thống nhận dạng chính xác nhất.</li>
                    <li><strong>Đáp án đúng:</strong> tô <strong style="color:#dc2626;">Đỏ</strong> (<strong style="color:#dc2626;">A.</strong> hoặc <strong style="color:#dc2626;">#A.</strong>) hoặc <u><strong>gạch chân</strong></u> (<u>A.</u> hoặc <u>#A.</u>). Với <strong>Phần II (Đúng/Sai)</strong>: gạch chân hoặc tô đỏ <u>a)</u> là <strong>Đúng</strong>, không đánh dấu là <strong>Sai</strong>. Với <strong>Phần III (Trả lời ngắn)</strong>: đáp án ghi sau <code><strong>A.</strong></code>. Gợi ý ghi sau <code><strong>Giải chi tiết</strong></code>.</li>
                    <li>Các câu hỏi và đáp án có <strong>Hình ảnh</strong> cần để ở chế độ <strong>Inline With Text</strong> để khi hoán vị hình ảnh không bị nhảy lung tung.</li>
                  </ul>
                </div>

                <!-- Hướng dẫn 2: Quy ước thẻ nhóm trộn <g0>..<#g3> & 2 dạng đề hỗ trợ -->
                <div style="display:flex;flex-direction:column;gap:10px;">
                  <div style="padding:14px 16px;border-radius:12px;border:1.5px dashed #94a3b8;background:#f8fafc;font-size:0.82rem;line-height:1.55;color:var(--text);">
                    <div style="font-weight:700;color:var(--primary);margin-bottom:8px;">🧩 Quy ước thẻ nhóm câu hỏi khi trộn (tuỳ chọn)</div>
                    <div style="display:flex;flex-direction:column;gap:5px;">
                      <div><code><strong>&lt;g0&gt;</strong></code> — Nhóm câu hỏi <strong>không cần trộn</strong> (giữ nguyên thứ tự câu hỏi và đáp án).</div>
                      <div><code><strong>&lt;g1&gt;</strong></code> — Nhóm câu hỏi <strong>chỉ cần hoán vị các câu hỏi</strong> (giữ nguyên đáp án).</div>
                      <div><code><strong>&lt;g2&gt;</strong></code> — Nhóm câu hỏi <strong>chỉ cần hoán vị các đáp án</strong> (giữ nguyên câu hỏi).</div>
                      <div><code><strong>&lt;g3&gt;</strong></code> — Nhóm câu hỏi <strong>cần hoán vị cả các câu hỏi và các đáp án</strong> (mặc định).</div>
                      <div style="margin-top:3px;padding-top:6px;border-top:1px dashed var(--border);">
                        • Khi cần <strong>cố định vị trí nhóm</strong>, thêm dấu <code><strong>#</strong></code> liền trước: <code><strong>&lt;#g0&gt;</strong></code>, <code><strong>&lt;#g1&gt;</strong></code>, <code><strong>&lt;#g2&gt;</strong></code> hoặc <code><strong>&lt;#g3&gt;</strong></code>.
                      </div>
                    </div>
                  </div>

                  <div style="padding:11px 14px;border-radius:10px;border:1px solid var(--primary-border);background:#f0fdfa;font-size:0.81rem;line-height:1.5;">
                    <div style="font-weight:700;color:var(--primary);margin-bottom:4px;">✅ Tự động nhận diện 2 dạng đề chuẩn:</div>
                    <div><strong>• Dạng 1:</strong> Đề TN gồm <strong>3 phần chuẩn 2025</strong> (Phần I: 4 đáp án · Phần II: Đúng/Sai · Phần III: Trả lời ngắn).</div>
                    <div><strong>• Dạng 2:</strong> Đề TN gồm <strong>1 phần chỉ có 40 câu trắc nghiệm 4 đáp án</strong> (thang 10 điểm).</div>
                  </div>
                </div>
              </div>

              ${
                Array.isArray(wordMixer.sampleFiles) && wordMixer.sampleFiles.length
                  ? `
                    <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;border:1px solid var(--border);background:#fff;">
                      <div style="font-size:0.82rem;font-weight:700;color:var(--text);margin-bottom:8px;">
                        📁 Kho tệp trong thư mục <code>FILE ĐỀ MẪU</code> (${wordMixer.sampleFiles.length} tệp — bấm Nạp thử để trộn ngay hoặc Tải về tham khảo):
                      </div>
                      <div style="display:flex;flex-wrap:wrap;gap:8px;">
                        ${wordMixer.sampleFiles
                          .map((sf) => {
                            const isLoadingThis = wordMixer.loadingSampleName === sf.filename;
                            return `
                              <div style="display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface-subtle);font-size:0.8rem;">
                                <span style="font-weight:600;">📄 ${escapeHtml(sf.filename)}</span>
                                <small style="color:var(--text-muted);">(${sf.size_kb} KB)</small>
                                <button type="button" class="btn btn-primary btn-sm" style="padding:3px 8px;font-size:0.75rem;" data-load-sample-exam="${escapeHtml(sf.filename)}" ${wordMixer.loading ? "disabled" : ""}>
                                  ${isLoadingThis ? "Đang nạp..." : "⚡ Nạp thử"}
                                </button>
                                <a class="btn btn-secondary btn-sm" style="padding:3px 8px;font-size:0.75rem;" href="${api.downloadExamMixerSampleUrl(sf.filename)}" target="_blank">⬇ Tải mẫu</a>
                              </div>
                            `;
                          })
                          .join("")}
                      </div>
                    </div>
                  `
                  : ""
              }

              <div style="padding:16px;border:1.5px dashed var(--primary-border);border-radius:12px;background:var(--surface-tint);display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                <label class="btn btn-primary" style="cursor:pointer;">
                  ${wordMixer.loading ? "Đang phân tích file Word..." : "📄 Tải lên file Word (.docx)"}
                  <input type="file" id="word-mixer-file-input" accept=".docx" style="display:none;" ${wordMixer.loading ? "disabled" : ""} />
                </label>
                <span id="word-mixer-upload-text" style="font-size:0.85rem;color:var(--text-secondary);">
                  ${
                    wordMixer.loading
                      ? "Đang tải lên và nhận diện câu hỏi, hình ảnh & đáp án..."
                      : wp
                      ? `Đã phân tích xong: <strong>${escapeHtml(wp.source_filename || wordMixer.file?.name || "đề-gốc.docx")}</strong>`
                      : "Chọn tệp Word (.docx) đề kiểm tra gốc của Thầy/Cô"
                  }
                </span>
              </div>

              ${
                wp && ws
                  ? `
                    <div style="margin-top:14px;padding:14px 16px;border-radius:12px;border:1px solid var(--primary-border);background:#fff;">
                      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px;">
                        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                          ${ws.exam_format_label ? `<span class="pill pill-primary">${escapeHtml(ws.exam_format_label)}</span>` : ""}
                          <span class="pill pill-green">Tổng ${ws.total_questions} câu · ${ws.max_score} điểm</span>
                          ${ws.mcq_count ? `<span class="pill pill-muted">Phần I (TN): ${ws.mcq_count} câu (${ws.mcq_keyed}/${ws.mcq_count} có ĐA)</span>` : ""}
                          ${ws.tf_count ? `<span class="pill pill-muted">Phần II (Đ/S): ${ws.tf_count} câu (${ws.tf_keyed}/${ws.tf_count} có ĐA)</span>` : ""}
                          ${ws.sa_count ? `<span class="pill pill-muted">Phần III (TLN): ${ws.sa_count} câu (${ws.sa_keyed}/${ws.sa_count} có ĐA)</span>` : ""}
                          ${ws.images_count ? `<span class="pill pill-muted">${ws.images_count} hình ảnh</span>` : ""}
                          ${ws.fixed_options_count ? `<span class="pill pill-amber">${ws.fixed_options_count} đáp án cố định (#)</span>` : ""}
                          ${ws.spelling_auto_fixed ? `<span class="pill pill-amber">Đã chuẩn hoá ${ws.spelling_auto_fixed} lỗi chính tả/thuật ngữ</span>` : ""}
                        </div>
                        <button type="button" class="btn btn-secondary btn-sm" id="btn-toggle-word-preview">
                          ${wordMixer.showPreview ? "Ẩn danh sách câu hỏi" : "👁 Xem trước câu hỏi & đáp án đã nhận diện"}
                        </button>
                      </div>
                      ${
                        Array.isArray(ws.groups_summary) && ws.groups_summary.length > 0
                          ? `
                            <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px;font-size:0.78rem;">
                              <strong style="color:var(--text-secondary);">Nhóm trộn đã nhận diện:</strong>
                              ${ws.groups_summary
                                .map(
                                  (g) =>
                                    `<span class="pill pill-muted">${escapeHtml(g.part)} · <code>${escapeHtml(g.tag)}</code> (${g.count} câu)</span>`
                                )
                                .join("")}
                            </div>
                          `
                          : ""
                      }

                      ${
                        (wp.warnings || []).length
                          ? `<div class="mock-warning-box" style="margin-top:0;margin-bottom:8px;">
                               ${wp.warnings.map((w) => `<div>⚠️ ${escapeHtml(w)}</div>`).join("")}
                             </div>`
                          : ""
                      }

                      ${
                        wordMixer.showPreview
                          ? `
                            <div class="data-table-wrap" style="margin-top:10px;max-height:360px;overflow-y:auto;">
                              <table class="data-table">
                                <thead>
                                  <tr><th style="width:90px;">Phần / Câu</th><th>Nội dung câu hỏi</th><th style="width:180px;">Đáp án đã nhận diện</th></tr>
                                </thead>
                                <tbody>
                                  ${(wc.mcq || [])
                                    .map((q, idx) => {
                                      const fixedBadge = (q.fixed_options || []).length
                                        ? `<span class="pill pill-amber" style="margin-left:4px;font-size:0.7rem;">Cố định ${(q.fixed_options || []).map((i) => `#${letters[i]}`).join(",")}</span>`
                                        : "";
                                      return `
                                      <tr>
                                        <td>
                                          <strong>${ws.exam_format === "format_1part_mcq" ? `Câu ${idx + 1}` : `Phần I · C${idx + 1}`}</strong>
                                          ${q.group_tag ? `<br/><small style="color:var(--text-muted);"><code>${escapeHtml(q.group_tag)}</code></small>` : ""}
                                        </td>
                                        <td style="font-size:0.82rem;">${formatBioHtml((q.question || "").slice(0, 180))}</td>
                                        <td>
                                          ${
                                            q.correct_index !== null && q.correct_index !== undefined
                                              ? `<span class="pill pill-green">Đáp án ${letters[q.correct_index] || "?"}</span>`
                                              : `<span class="pill pill-red">Chưa nhận diện</span>`
                                          }${fixedBadge}
                                        </td>
                                      </tr>
                                    `;
                                    })
                                    .join("")}
                                  ${(wc.true_false || [])
                                    .map((q, idx) => {
                                      const stSummary = (q.statements || [])
                                        .map((s) => `${s.fixed ? "#" : ""}${s.key}-${s.answer === true ? "Đ" : s.answer === false ? "S" : "?"}`)
                                        .join(" · ");
                                      const allReady = (q.statements || []).every((s) => s.answer !== null && s.answer !== undefined);
                                      return `
                                        <tr>
                                          <td>
                                            <strong>Phần II · C${idx + 1}</strong>
                                            ${q.group_tag ? `<br/><small style="color:var(--text-muted);"><code>${escapeHtml(q.group_tag)}</code></small>` : ""}
                                          </td>
                                          <td style="font-size:0.82rem;">${formatBioHtml((q.question || q.stem || "").slice(0, 180))}</td>
                                          <td><span class="pill ${allReady ? "pill-green" : "pill-amber"}">${escapeHtml(stSummary)}</span></td>
                                        </tr>
                                      `;
                                    })
                                    .join("")}
                                  ${(wc.short_answer || [])
                                    .map(
                                      (q, idx) => `
                                      <tr>
                                        <td>
                                          <strong>Phần III · C${idx + 1}</strong>
                                          ${q.group_tag ? `<br/><small style="color:var(--text-muted);"><code>${escapeHtml(q.group_tag)}</code></small>` : ""}
                                        </td>
                                        <td style="font-size:0.82rem;">${formatBioHtml((q.question || "").slice(0, 180))}</td>
                                        <td>
                                          ${
                                            (q.accepted_answers || []).length
                                              ? `<span class="pill pill-green">A. ${escapeHtml(q.accepted_answers[0])}</span>`
                                              : `<span class="pill pill-red">Chưa nhận diện</span>`
                                          }
                                        </td>
                                      </tr>
                                    `
                                    )
                                    .join("")}
                                </tbody>
                              </table>
                            </div>
                          `
                          : ""
                      }
                    </div>
                  `
                  : ""
              }
            </div>

            <!-- Bước 2: Tiêu đề đề kiểm tra + Số lượng đề + Mã đề 4 số -->
            <div class="card">
              <h3 class="card-title">Bước 2. Tiêu đề đề kiểm tra, Số lượng đề &amp; Mã đề (mặc định 4 số)</h3>
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;">
                <div class="form-group">
                  <label>Trường (tuỳ chọn — để trống sẽ ẩn):</label>
                  <input class="form-control" id="wx-school" value="${escapeHtml(examConfig.school_name)}" placeholder="VD: THPT ..., TT GDNN-GDTX ... (để trống sẽ ẩn)" />
                </div>
                <div class="form-group">
                  <label>Kỳ kiểm tra: *</label>
                  <input class="form-control" id="wx-period" value="${escapeHtml(examConfig.exam_period)}" placeholder="VD: KIỂM TRA GIỮA KÌ I" />
                </div>
                <div class="form-group">
                  <label>Năm học: *</label>
                  <input class="form-control" id="wx-year" value="${escapeHtml(examConfig.school_year)}" placeholder="VD: 2026 - 2027" />
                </div>
                <div class="form-group">
                  <label>Môn (tuỳ chọn — để trống sẽ ẩn):</label>
                  <input class="form-control" id="wx-subject" value="${escapeHtml(examConfig.subject)}" placeholder="VD: Sinh học 12, Hoá học 12, Toán 12..." />
                </div>
                <div class="form-group">
                  <label>Thời gian (phút): *</label>
                  <input type="number" min="5" max="180" class="form-control" id="wx-duration" value="${examConfig.duration_minutes}" />
                </div>
                <div class="form-group">
                  <label>Số lượng đề trộn: *</label>
                  <input type="number" min="1" max="30" class="form-control" id="wx-count" value="${examConfig.exam_count}" />
                </div>
              </div>

              <div class="form-group" style="margin-top:4px;">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
                  <label style="margin:0;">Mã đề (mặc định 4 chữ số, tự chọn/chỉnh sửa tương ứng với số lượng đề):</label>
                  <div style="display:flex;gap:6px;flex-wrap:wrap;">
                    <button type="button" class="btn btn-soft btn-sm" id="btn-wx-sync-codes">Đồng bộ mã 4 số (${examConfig.exam_count} mã)</button>
                    <button type="button" class="btn btn-secondary btn-sm" id="btn-wx-rand-codes">🎲 Tạo mã 4 số ngẫu nhiên</button>
                  </div>
                </div>
                <input class="form-control" id="wx-codes" value="${escapeHtml(examConfig.exam_codes)}" placeholder="VD: 1001, 1002, 1003, 1004" />
                <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;">
                  <span class="pill pill-muted">Đề gốc: 0000</span>
                  ${codePreviewList
                    .slice(0, examConfig.exam_count)
                    .map((c) => `<span class="pill pill-primary">Mã đề ${escapeHtml(c)}</span>`)
                    .join("")}
                </div>
              </div>

              <div style="margin-top:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                <button type="button" class="btn btn-primary btn-lg" id="btn-generate-word-exam" ${wordMixer.generating || !wp ? "disabled" : ""}>
                  ${wordMixer.generating ? "Đang tách từng mã đề & nén gói ZIP..." : "🔀 Trộn đề & Xuất gói nén (.zip)"}
                </button>
                ${!wp ? `<span style="font-size:0.82rem;color:var(--text-muted);">Hãy tải lên file Word (.docx) ở Bước 1 trước khi bấm trộn đề.</span>` : ""}
              </div>

              ${
                wordMixer.result
                  ? (() => {
                      const rs = wordMixer.result.summary || {};
                      const metaParts = [
                        rs.school_name || "",
                        rs.exam_period || "",
                        rs.school_year ? `Năm học ${rs.school_year}` : "",
                        rs.subject ? `Môn ${rs.subject}` : "",
                        `${rs.duration_minutes || 45} phút`,
                      ].filter(Boolean);
                      const filesInZip = Array.isArray(rs.files_in_zip) ? rs.files_in_zip : [];
                      return `
                        <div style="margin-top:16px;padding:16px;border-radius:10px;border:1px solid var(--primary-border);background:var(--surface-tint);">
                          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;">
                            <div>
                              <span class="pill pill-green">Đã trộn xong ${rs.exam_count} mã đề + Đề gốc ${escapeHtml(rs.original_code || "0000")}</span>
                              <div style="font-weight:700;margin-top:6px;">
                                Đề gốc: ${escapeHtml(rs.original_code || "0000")} · Mã đề trộn: ${escapeHtml((rs.exam_codes || []).join(", "))}
                              </div>
                              <div style="font-size:0.83rem;color:var(--text-secondary);margin-top:3px;">
                                ${escapeHtml(metaParts.join(" · "))}
                              </div>
                              <div style="font-size:0.82rem;color:var(--text-secondary);margin-top:2px;">
                                Phần I: ${rs.mcq_count} câu · Phần II: ${rs.true_false_count} câu · Phần III: ${rs.short_answer_count} câu · Tổng thang điểm: <strong>${rs.max_score} điểm</strong>
                              </div>
                            </div>
                            <div style="display:flex;gap:8px;flex-wrap:wrap;">
                              <a class="btn btn-primary" id="btn-dl-word-zip" href="${api.adminExamDownloadUrl(wordMixer.result.job_id, "zip")}" target="_blank">
                                📦 Tải trọn bộ file nén (.zip)
                              </a>
                              <a class="btn btn-soft" href="${api.adminExamDownloadUrl(wordMixer.result.job_id, "xlsx")}" target="_blank">
                                📊 Tải riêng Đáp án (.xlsx)
                              </a>
                              <a class="btn btn-secondary" href="${api.adminExamDownloadUrl(wordMixer.result.job_id, "docx")}" target="_blank">
                                📄 Tải bản gộp (.docx)
                              </a>
                            </div>
                          </div>
                          ${
                            filesInZip.length
                              ? `
                                <div style="margin-top:12px;padding-top:10px;border-top:1px dashed var(--primary-border);">
                                  <div style="font-size:0.8rem;font-weight:700;color:var(--text-secondary);margin-bottom:6px;">
                                    📂 Các tệp đã tách riêng trong gói nén (${filesInZip.length} tệp — bấm vào từng tệp để tải lẻ):
                                  </div>
                                  <div style="display:flex;gap:6px;flex-wrap:wrap;">
                                    ${filesInZip
                                      .map((fname) => {
                                        const isOrig = fname === "Ma_de_0000.docx";
                                        const isXlsx = fname.toLowerCase().endsWith(".xlsx");
                                        const icon = isXlsx ? "📊" : "📄";
                                        const tag = isOrig ? " (Đề gốc)" : "";
                                        return `<a class="btn btn-secondary btn-sm" style="padding:4px 9px;font-size:0.78rem;" href="${api.adminExamIndividualFileUrl(wordMixer.result.job_id, fname)}" target="_blank">${icon} ${escapeHtml(fname)}${tag}</a>`;
                                      })
                                      .join("")}
                                  </div>
                                </div>
                              `
                              : ""
                          }
                        </div>
                      `;
                    })()
                  : ""
              }
            </div>
          </div>
        </div>
      `;
    }

    if (!examPool) {
      return `
        <div>
          ${modeSwitcher}
          <div class="card" style="text-align:center;padding:36px;"><div class="spinner" style="margin:0 auto 10px;"></div>Đang tải ngân hàng câu hỏi các chủ đề...</div>
        </div>
      `;
    }

    const avail = computeAvailablePool();
    const sumCol = (k) => (matrix[k].nhan_biet || 0) + (matrix[k].thong_hieu || 0) + (matrix[k].van_dung || 0);
    const sumRow = (lv) => (matrix.mcq[lv] || 0) + (matrix.true_false[lv] || 0) + (matrix.short_answer[lv] || 0);
    const mcqTotal = sumCol("mcq");
    const tfTotal = sumCol("true_false");
    const saTotal = sumCol("short_answer");
    const grandQ = mcqTotal + tfTotal + saTotal;
    const mcqPts = Math.round(mcqTotal * 0.25 * 100) / 100;
    const tfPts = Math.round(tfTotal * 1.0 * 100) / 100;
    const saPts = Math.round(saTotal * 0.25 * 100) / 100;
    const grandPts = Math.round((mcqPts + tfPts + saPts) * 100) / 100;

    const levels = [
      { key: "nhan_biet", label: "Nhận biết" },
      { key: "thong_hieu", label: "Hiểu" },
      { key: "van_dung", label: "Vận dụng" },
    ];

    return `
      <div>
        ${modeSwitcher}
        <div style="display:flex;flex-direction:column;gap:18px;">
        <!-- Bước 1: Chọn nhiều bài học trong từng/nhiều chủ đề -->
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px;">
            <div>
              <h3 class="card-title" style="margin:0 0 2px;">Bước 1. Chọn Chủ đề &amp; Bài học cần trộn đề</h3>
              <p style="margin:0;font-size:0.83rem;color:var(--text-muted);">Có thể chọn cùng lúc nhiều bài trong một hoặc nhiều chủ đề (${selectedLessonIds.size} bài đang chọn).</p>
            </div>
            <div style="display:flex;gap:8px;">
              <button type="button" class="btn btn-soft btn-sm" id="ex-select-all">Chọn tất cả bài</button>
              <button type="button" class="btn btn-secondary btn-sm" id="ex-clear-all">Bỏ chọn hết</button>
            </div>
          </div>

          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px;">
            ${examPool
              .map((tp) => {
                const tpIds = (tp.lessons || []).map((l) => l.id);
                const allChecked = tpIds.length > 0 && tpIds.every((id) => selectedLessonIds.has(id));
                return `
                  <div style="border:1px solid var(--border);border-radius:10px;padding:12px;background:var(--surface);">
                    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid var(--border);">
                      <label style="display:flex;align-items:center;gap:8px;font-weight:700;font-size:0.88rem;cursor:pointer;">
                        <input type="checkbox" data-ex-topic="${tp.id}" ${allChecked ? "checked" : ""} />
                        <span>${escapeHtml(tp.title)}</span>
                      </label>
                    </div>
                    <div style="display:flex;flex-direction:column;gap:6px;">
                      ${(tp.lessons || [])
                        .map((ls) => {
                          const cMcq = (ls.counts?.mcq?.nhan_biet || 0) + (ls.counts?.mcq?.thong_hieu || 0) + (ls.counts?.mcq?.van_dung || 0);
                          const cTf = (ls.counts?.true_false?.nhan_biet || 0) + (ls.counts?.true_false?.thong_hieu || 0) + (ls.counts?.true_false?.van_dung || 0);
                          const cSa = (ls.counts?.short_answer?.nhan_biet || 0) + (ls.counts?.short_answer?.thong_hieu || 0) + (ls.counts?.short_answer?.van_dung || 0);
                          return `
                            <label style="display:flex;align-items:flex-start;gap:8px;font-size:0.83rem;cursor:pointer;line-height:1.35;">
                              <input type="checkbox" data-ex-lesson="${ls.id}" ${selectedLessonIds.has(ls.id) ? "checked" : ""} style="margin-top:3px;" />
                              <span>
                                <strong>${escapeHtml(ls.number)}:</strong> ${escapeHtml(ls.title)}
                                <br/><small style="color:var(--text-muted);">${cMcq} MCQ · ${cTf} Đ/S · ${cSa} TLN</small>
                              </span>
                            </label>
                          `;
                        })
                        .join("")}
                    </div>
                  </div>
                `;
              })
              .join("")}
          </div>
        </div>

        <!-- Bước 2: Ma trận 3 dạng x 3 mức độ -->
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px;">
            <div>
              <h3 class="card-title" style="margin:0 0 2px;">Bước 2. Nhập Ma trận đề (3 dạng câu hỏi × 3 mức độ)</h3>
              <p style="margin:0;font-size:0.83rem;color:var(--text-muted);">
                Phần I (4 đáp án): 0,25đ/câu · Phần II (Đúng/Sai): 1 ý 0,1đ / 2 ý 0,25đ / 3 ý 0,5đ / 4 ý 1,0đ · Phần III (Trả lời ngắn): 0,25đ/câu (số ≤ 4 ký tự).
              </p>
            </div>
            <button type="button" class="btn btn-soft btn-sm" id="ex-preset-10">Gợi ý ma trận 10 điểm chuẩn</button>
          </div>

          <div class="data-table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th style="min-width:130px;">Mức độ \ Dạng hỏi</th>
                  <th>Trắc nghiệm 4 đáp án<br/><small style="font-weight:500;">(0,25 điểm / câu)</small></th>
                  <th>Trắc nghiệm Đúng/Sai<br/><small style="font-weight:500;">(0,1 / 0,25 / 0,5 / 1,0đ)</small></th>
                  <th>Trắc nghiệm trả lời ngắn<br/><small style="font-weight:500;">(0,25đ · số ≤ 4 ký tự)</small></th>
                  <th>Tổng số câu</th>
                </tr>
              </thead>
              <tbody>
                ${levels
                  .map((lv) => {
                    const cells = ["mcq", "true_false", "short_answer"]
                      .map((kind) => {
                        const val = matrix[kind][lv.key] || 0;
                        const maxA = avail[kind][lv.key] || 0;
                        const over = val > maxA;
                        return `
                          <td>
                            <div style="display:flex;align-items:center;gap:6px;">
                              <input type="number" min="0" max="200"
                                     class="form-control form-control-sm"
                                     style="width:74px;font-weight:700;text-align:center;${over ? "border-color:#dc2626;color:#dc2626;" : ""}"
                                     data-mx-kind="${kind}" data-mx-lv="${lv.key}" value="${val}" />
                              <span style="font-size:0.78rem;color:${over ? "#dc2626" : "var(--text-muted)"};font-weight:${over ? "700" : "500"};">
                                / ${maxA} có sẵn
                              </span>
                            </div>
                          </td>
                        `;
                      })
                      .join("");
                    return `
                      <tr>
                        <td><strong>${lv.label}</strong></td>
                        ${cells}
                        <td><strong>${sumRow(lv.key)}</strong></td>
                      </tr>
                    `;
                  })
                  .join("")}
                <tr style="background:var(--surface-tint);">
                  <td><strong>Tổng số câu</strong></td>
                  <td><strong>${mcqTotal} câu</strong></td>
                  <td><strong>${tfTotal} câu</strong></td>
                  <td><strong>${saTotal} câu</strong></td>
                  <td><strong>${grandQ} câu</strong></td>
                </tr>
                <tr style="background:var(--surface-tint);">
                  <td><strong>Tổng điểm</strong></td>
                  <td><strong>${mcqPts} điểm</strong></td>
                  <td><strong>${tfPts} điểm</strong></td>
                  <td><strong>${saPts} điểm</strong></td>
                  <td><span class="pill ${grandPts === 10 ? "pill-green" : "pill-primary"}">${grandPts} điểm</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Bước 3: Số lượng đề, Mã đề 4 số & Xuất Word/Excel -->
        <div class="card">
          <h3 class="card-title">Bước 3. Tiêu đề, Số lượng đề &amp; Mã đề (mặc định 4 số) → Xuất Word + Excel</h3>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;">
            <div class="form-group">
              <label>Trường (để trống sẽ ẩn):</label>
              <input class="form-control" id="ex-school" value="${escapeHtml(examConfig.school_name)}" placeholder="VD: THPT ..., TT GDNN-GDTX ... (để trống sẽ ẩn)" />
            </div>
            <div class="form-group">
              <label>Kỳ kiểm tra:</label>
              <input class="form-control" id="ex-title" value="${escapeHtml(examConfig.exam_period || examConfig.title)}" />
            </div>
            <div class="form-group">
              <label>Năm học:</label>
              <input class="form-control" id="ex-year" value="${escapeHtml(examConfig.school_year)}" />
            </div>
            <div class="form-group">
              <label>Môn (để trống sẽ ẩn):</label>
              <input class="form-control" id="ex-subject" value="${escapeHtml(examConfig.subject)}" placeholder="VD: Sinh học 12..." />
            </div>
            <div class="form-group">
              <label>Thời gian (phút):</label>
              <input type="number" min="5" max="180" class="form-control" id="ex-duration" value="${examConfig.duration_minutes}" />
            </div>
            <div class="form-group">
              <label>Số lượng đề trộn *</label>
              <input type="number" min="1" max="30" class="form-control" id="ex-count" value="${examConfig.exam_count}" />
            </div>
          </div>
          <div class="form-group">
            <label>Mã đề (mặc định 4 số, ngăn cách bằng dấu phẩy; nếu nhập mã đầu hệ thống tự đánh tiếp)</label>
            <input class="form-control" id="ex-codes" value="${escapeHtml(examConfig.exam_codes)}" placeholder="VD: 1001, 1002, 1003, 1004" />
          </div>

          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:8px;">
            <button type="button" class="btn btn-primary btn-lg" id="btn-generate-exam" ${examGenerating ? "disabled" : ""}>
              ${examGenerating ? "Đang trộn đề & nén gói ZIP..." : "Tạo & Trộn đề thi (File nén .zip)"}
            </button>
          </div>

          ${
            examResult
              ? (() => {
                  const filesInZip = Array.isArray(examResult.summary?.files_in_zip) ? examResult.summary.files_in_zip : [];
                  return `
                    <div style="margin-top:16px;padding:16px;border-radius:10px;border:1px solid var(--primary-border);background:var(--surface-tint);">
                      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;">
                        <div>
                          <span class="pill pill-green">Đã trộn xong ${examResult.summary.exam_count} đề + Đề gốc ${escapeHtml(examResult.summary.original_code || "0000")}</span>
                          <div style="font-weight:700;margin-top:6px;">
                            Đề gốc: ${escapeHtml(examResult.summary.original_code || "0000")} · Mã đề: ${escapeHtml((examResult.summary.exam_codes || []).join(", "))}
                          </div>
                          <div style="font-size:0.84rem;color:var(--text-secondary);margin-top:2px;">
                            Phần I: ${examResult.summary.mcq_count} câu · Phần II: ${examResult.summary.true_false_count} câu · Phần III: ${examResult.summary.short_answer_count} câu · Tổng thang điểm: <strong>${examResult.summary.max_score} điểm</strong>
                          </div>
                        </div>
                        <div style="display:flex;gap:8px;flex-wrap:wrap;">
                          <a class="btn btn-primary" href="${api.adminExamDownloadUrl(examResult.job_id, "zip")}" target="_blank" id="btn-dl-exam-zip">
                            📦 Tải trọn bộ file nén (.zip)
                          </a>
                          <a class="btn btn-soft" href="${api.adminExamDownloadUrl(examResult.job_id, "xlsx")}" target="_blank" id="btn-dl-exam-xlsx">
                            📊 Tải riêng Đáp án (.xlsx)
                          </a>
                          <a class="btn btn-secondary" href="${api.adminExamDownloadUrl(examResult.job_id, "docx")}" target="_blank" id="btn-dl-exam-docx">
                            📄 Tải bản gộp (.docx)
                          </a>
                        </div>
                      </div>
                      ${
                        filesInZip.length
                          ? `
                            <div style="margin-top:12px;padding-top:10px;border-top:1px dashed var(--primary-border);display:flex;gap:6px;flex-wrap:wrap;">
                              ${filesInZip
                                .map((fname) => {
                                  const isOrig = fname === "Ma_de_0000.docx";
                                  const icon = fname.toLowerCase().endsWith(".xlsx") ? "📊" : "📄";
                                  return `<a class="btn btn-secondary btn-sm" style="padding:4px 9px;font-size:0.78rem;" href="${api.adminExamIndividualFileUrl(examResult.job_id, fname)}" target="_blank">${icon} ${escapeHtml(fname)}${isOrig ? " (Đề gốc)" : ""}</a>`;
                                })
                                .join("")}
                            </div>
                          `
                          : ""
                      }
                    </div>
                  `;
                })()
              : ""
          }
        </div>
      </div>
      </div>
    `;
  }

  // ================== 3. CHỈNH SỬA & THÊM NỘI DUNG MỚI ==================
  function renderContentStudio() {
    const t = activeTopic;
    const lessons = t?.lessons || [];
    const prev = importState.preview;
    const st = prev?.stats;

    const editingLesson = lessons.find((l) => l.id === editLessonId) || null;
    const lessonPlainText = editingLesson
      ? (editingLesson.sections || [])
          .map((sec) => {
            const body = (sec.blocks || [])
              .filter((b) => b.type === "paragraph" || b.text)
              .map((b) => b.text)
              .join("\n");
            return `## ${sec.heading}\n${body}`;
          })
          .join("\n\n")
      : "";

    return `
      <div style="display:flex;flex-direction:column;gap:16px;">
        <div class="segmented" style="flex-wrap:wrap;">
          <button class="seg-btn ${contentSubMode === "add_topic" ? "active" : ""}" data-csub="add_topic">Thêm Chủ đề mới (Word/PDF)</button>
          <button class="seg-btn ${contentSubMode === "add_question" ? "active" : ""}" data-csub="add_question">Thêm câu hỏi mới</button>
          <button class="seg-btn ${contentSubMode === "edit_lesson" ? "active" : ""}" data-csub="edit_lesson">Sửa / Thêm bài Lý thuyết</button>
          <button class="seg-btn ${contentSubMode === "youtube" ? "active" : ""}" data-csub="youtube">Video YouTube</button>
          <button class="seg-btn ${contentSubMode === "import" ? "active" : ""}" data-csub="import">Cập nhật Chủ đề hiện tại</button>
        </div>

        ${
          cacheInfo
            ? `
              <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 16px;border-radius:10px;border:1px solid var(--border);background:var(--surface);font-size:0.82rem;">
                <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                  <span class="pill ${cacheInfo.redis_connected ? "pill-green" : "pill-primary"}">Cache: ${escapeHtml(cacheInfo.backend)}</span>
                  <span style="color:var(--text-secondary);">
                    Tỉ lệ trúng cache: <strong>${cacheInfo.hit_rate_percent}%</strong> · Đang lưu: <strong>${cacheInfo.l1_entries}</strong> khoá (L1: ${cacheInfo.l1_hits} · Redis: ${cacheInfo.redis_hits})
                  </span>
                </div>
                <button type="button" class="btn btn-secondary btn-sm" id="btn-clear-cache" ${cacheClearing ? "disabled" : ""}>
                  ${cacheClearing ? "Đang làm mới..." : "Làm mới Cache"}
                </button>
              </div>
            `
            : ""
        }

        ${
          contentSubMode === "add_question"
            ? `
              <div class="card">
                <h3 class="card-title">Thêm câu hỏi ôn tập mới vào ${escapeHtml(t.title)}</h3>
                <form id="admin-add-question-form">
                  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;">
                    <div class="form-group">
                      <label>Thuộc bài học *</label>
                      <select class="form-control" name="lesson_id" required>
                        ${lessons.map((l) => `<option value="${l.id}">${escapeHtml(l.number)}: ${escapeHtml(l.title)}</option>`).join("")}
                      </select>
                    </div>
                    <div class="form-group">
                      <label>Dạng câu hỏi *</label>
                      <select class="form-control" name="q_type" id="admin-new-qtype">
                        <option value="mcq" ${newQuestionType === "mcq" ? "selected" : ""}>3.1 Trắc nghiệm 4 đáp án (0,25đ)</option>
                        <option value="true_false" ${newQuestionType === "true_false" ? "selected" : ""}>3.2 Trắc nghiệm Đúng/Sai (1,0đ)</option>
                        <option value="short_answer" ${newQuestionType === "short_answer" ? "selected" : ""}>3.3 Trả lời ngắn (0,25đ · số ≤ 4 ký tự)</option>
                      </select>
                    </div>
                    <div class="form-group">
                      <label>Mức độ nhận thức *</label>
                      <select class="form-control" name="cognitive_level">
                        <option value="nhan_biet">Nhận biết</option>
                        <option value="thong_hieu">Hiểu</option>
                        <option value="van_dung">Vận dụng</option>
                      </select>
                    </div>
                  </div>

                  <div class="form-group">
                    <label>Nội dung câu hỏi *</label>
                    <textarea class="form-control" name="question" rows="3" required placeholder="Nhập nội dung câu hỏi Sinh học 12..."></textarea>
                  </div>

                  ${
                    newQuestionType === "mcq"
                      ? `
                        <div class="form-row-2">
                          <div class="form-group"><label>Phương án A *</label><input class="form-control" name="opt_a" required /></div>
                          <div class="form-group"><label>Phương án B *</label><input class="form-control" name="opt_b" required /></div>
                          <div class="form-group"><label>Phương án C *</label><input class="form-control" name="opt_c" required /></div>
                          <div class="form-group"><label>Phương án D *</label><input class="form-control" name="opt_d" required /></div>
                        </div>
                        <div class="form-group" style="max-width:240px;">
                          <label>Đáp án đúng *</label>
                          <select class="form-control" name="correct_index">
                            <option value="0">A</option><option value="1">B</option><option value="2">C</option><option value="3">D</option>
                          </select>
                        </div>
                      `
                      : newQuestionType === "true_false"
                      ? `
                        ${["a", "b", "c", "d"]
                          .map(
                            (k) => `
                            <div style="display:grid;grid-template-columns:1fr 130px;gap:10px;align-items:end;margin-bottom:8px;">
                              <div class="form-group" style="margin:0;">
                                <label>Ý ${k}) *</label>
                                <input class="form-control" name="tf_${k}" required placeholder="Nội dung phát biểu ý ${k}..." />
                              </div>
                              <div class="form-group" style="margin:0;">
                                <label>Đáp án ý ${k}</label>
                                <select class="form-control" name="tf_${k}_ans">
                                  <option value="true">Đúng</option>
                                  <option value="false">Sai</option>
                                </select>
                              </div>
                            </div>
                          `
                          )
                          .join("")}
                      `
                      : `
                        <div class="form-group" style="max-width:300px;">
                          <label>Đáp án chuẩn (giá trị số tối đa 4 ký tự: số, -, ,) *</label>
                          <input class="form-control" name="sa_answer" maxlength="4" required placeholder="VD: 12,5 hoặc -2" />
                        </div>
                      `
                  }

                  <div class="form-group">
                    <label>Giải thích (tuỳ chọn)</label>
                    <input class="form-control" name="explanation" placeholder="Gợi ý lời giải sau khi học sinh nộp bài" />
                  </div>

                  <button type="submit" class="btn btn-primary">Lưu câu hỏi vào ngân hàng</button>
                </form>
              </div>
            `
            : contentSubMode === "edit_lesson"
            ? `
              <div class="card">
                <h3 class="card-title">Chỉnh sửa hoặc Thêm bài Lý thuyết — ${escapeHtml(t.title)}</h3>
                <div class="form-group" style="max-width:380px;">
                  <label>Chọn bài học để sửa hoặc tạo bài mới</label>
                  <select class="form-control" id="admin-edit-lesson-select">
                    <option value="__new__" ${editLessonId === "__new__" ? "selected" : ""}>+ Thêm bài học mới vào chủ đề này</option>
                    ${lessons
                      .map(
                        (l) => `<option value="${l.id}" ${editLessonId === l.id ? "selected" : ""}>${escapeHtml(l.number)}: ${escapeHtml(l.title)}</option>`
                      )
                      .join("")}
                  </select>
                </div>

                <form id="admin-lesson-form">
                  <div class="form-row-2">
                    <div class="form-group">
                      <label>Số hiệu bài *</label>
                      <input class="form-control" name="lesson_number" required value="${escapeHtml(editingLesson?.number || `Bài ${lessons.length + 1}`)}" />
                    </div>
                    <div class="form-group">
                      <label>Tiêu đề bài học *</label>
                      <input class="form-control" name="lesson_title" required value="${escapeHtml(editingLesson?.title || "")}" placeholder="Tên bài học mới..." />
                    </div>
                  </div>
                  <div class="form-group">
                    <label>Nội dung lý thuyết (dùng dòng bắt đầu bằng <code>## Tên mục</code> để tách các phần)</label>
                    <textarea class="form-control" name="lesson_body" rows="10" required placeholder="## I. Khái niệm&#10;Nội dung kiến thức...">${escapeHtml(lessonPlainText)}</textarea>
                  </div>
                  <button type="submit" class="btn btn-primary">${editingLesson ? "Lưu thay đổi bài học" : "Thêm bài học mới"}</button>
                </form>
              </div>
            `
            : contentSubMode === "add_topic"
            ? (() => {
                const dp = newTopicDraft.preview;
                const ds = dp?.stats;
                const ord = newTopicDraft.order_index || 5;
                return `
                  <div class="card">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:14px;">
                      <div>
                        <h3 class="card-title" style="margin:0 0 4px;">Thêm Chủ đề mới từ file Word (.docx) hoặc PDF (.pdf)</h3>
                        <p style="margin:0;font-size:0.84rem;color:var(--text-muted);">
                          Hệ thống tự động trích xuất Lý thuyết, Hình ảnh, Hệ thống kiến thức và Câu hỏi ôn tập 3 phần, tự đánh số (${ord}.1, ${ord}.2...) và tạo thẻ màu tương phản giống hệt các Chủ đề cũ.
                        </p>
                      </div>
                      <a class="btn btn-secondary btn-sm" href="${withBase("/api/import-template")}" target="_blank">Tải file Word mẫu</a>
                    </div>

                    <!-- Bước 1: Thông tin cơ bản & Chọn file Word/PDF -->
                    <div class="form-row-2">
                      <div class="form-group">
                        <label>Số thứ tự Chủ đề</label>
                        <input type="number" min="1" max="50" class="form-control" id="new-topic-order" value="${ord}" />
                      </div>
                      <div class="form-group">
                        <label>Tên Chủ đề (tự nhận diện từ file hoặc nhập thủ công)</label>
                        <input class="form-control" id="new-topic-title" value="${escapeHtml(newTopicDraft.title)}" placeholder="VD: Chủ đề ${ord}. Di truyền học quần thể và Di truyền học người" />
                      </div>
                    </div>

                    <div class="form-group">
                      <label>Mô tả ngắn (tuỳ chọn)</label>
                      <input class="form-control" id="new-topic-subtitle" value="${escapeHtml(newTopicDraft.subtitle)}" placeholder="Tự động tổng hợp từ danh sách bài học nếu để trống" />
                    </div>

                    <div class="mock-upload-guide" style="margin-top:0;margin-bottom:14px;">
                      <div class="mock-upload-guide-title">📌 Chuẩn đầu vào thông minh khi tải lên Chủ đề mới (tự đồng bộ giao diện &amp; kiểm tra chính tả theo SGK Sinh học 12):</div>
                      <div class="mock-upload-guide-grid">
                        <div><strong>• TN 4 đáp án &amp; Đúng/Sai:</strong> Đáp án <strong>Đúng</strong> được <u><strong>gạch chân</strong></u> (không gạch chân là Sai).</div>
                        <div><strong>• Trả lời ngắn:</strong> Ghi đáp án ngay sau từ <code><strong>A.</strong></code> (VD: <code>A. 12,5</code>).</div>
                        <div><strong>• Gợi ý đáp án:</strong> Tự trích nội dung sau cụm từ <code><strong>Giải chi tiết</strong></code> (nếu có).</div>
                        <div><strong>• Đối chiếu chuẩn:</strong> Tự động rà soát chính tả theo <code>SGK_SINH HỌC</code> và hỗ trợ tải kèm PDF <code>Đáp án</code> để khớp đáp án tự động.</div>
                      </div>
                    </div>

                    <div style="padding:16px;border:1.5px dashed var(--primary-border);border-radius:12px;background:var(--surface-tint);margin-bottom:16px;">
                      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                        <label class="btn btn-primary" style="cursor:pointer;">
                          ${newTopicDraft.loading ? "Đang đọc & thiết kế Chủ đề..." : "Chọn file Word (.docx) hoặc PDF (.pdf)"}
                          <input type="file" id="new-topic-file-input" accept=".docx,.pdf,.txt,.md" style="display:none;" ${newTopicDraft.loading ? "disabled" : ""} />
                        </label>
                        <span id="new-topic-upload-text" style="font-size:0.85rem;color:var(--text-secondary);">
                          ${
                            newTopicDraft.loading
                              ? "Đang chuẩn bị tải file lên..."
                              : newTopicDraft.file
                              ? `Đã đọc xong: <strong>${escapeHtml(newTopicDraft.file.name)}</strong>`
                              : "Hỗ trợ tệp Word (.docx) và PDF (.pdf) chuẩn cấu trúc giảng dạy"
                          }
                        </span>
                      </div>
                      ${
                        newTopicDraft.loading
                          ? `<div style="margin-top:10px;height:6px;border-radius:999px;background:rgba(15,118,110,0.14);overflow:hidden;">
                               <div id="new-topic-upload-bar" style="height:100%;width:8%;background:var(--primary);transition:width 0.15s ease;"></div>
                             </div>`
                          : ""
                      }
                    </div>

                    ${
                      dp && ds
                        ? `
                          <div style="padding:16px;border-radius:12px;border:1px solid var(--primary-border);background:#fff;margin-bottom:16px;">
                            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
                              <div>
                                <span class="pill pill-green">Đã trích xuất sẵn sàng xem trước</span>
                                <h4 style="margin:6px 0 2px;font-size:1rem;">${escapeHtml(newTopicDraft.title || dp.extracted?.title || dp.detected_title)}</h4>
                                <div style="font-size:0.83rem;color:var(--text-secondary);">
                                  <strong>${ds.lessons_count}</strong> bài học (${(dp.extracted?.lessons || []).map((l) => l.number).join(", ")}) ·
                                  <strong>${ds.images_count}</strong> hình ảnh ·
                                  <strong>${ds.tables_count}</strong> bảng ·
                                  <strong>${ds.htkt_units_count}</strong> phiếu HTKT
                                </div>
                                <div style="font-size:0.83rem;color:var(--text-secondary);margin-top:2px;">
                                  Ngân hàng ôn tập: <strong>${ds.mcq_count}</strong> câu 4 đáp án (${ds.mcq_keyed || 0} có ĐA) ·
                                  <strong>${ds.true_false_count}</strong> câu Đúng/Sai (${ds.true_false_keyed || 0} có ĐA) ·
                                  <strong>${ds.short_answer_count}</strong> câu Trả lời ngắn (${ds.short_answer_keyed || 0} có ĐA)
                                </div>
                                ${
                                  dp.spelling_report
                                    ? `
                                      <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:0.8rem;">
                                        <span class="pill ${dp.spelling_report.auto_fixed_count > 0 ? "pill-amber" : "pill-green"}">
                                          ✓ Kiểm tra chính tả: đã tự chuẩn hoá ${dp.spelling_report.auto_fixed_count || 0} mục (thuật ngữ/dấu/kiểu gene)
                                        </span>
                                        ${
                                          dp.spelling_report.sgk_reference?.available
                                            ? `<span class="pill pill-primary">📘 Đối chiếu SGK: ${escapeHtml(dp.spelling_report.sgk_reference.source_name)}</span>`
                                            : `<span class="pill pill-muted">📘 Chuẩn SGK Sinh học 12 GDPT 2018</span>`
                                        }
                                        ${
                                          (dp.spelling_report.suspect_words || []).length
                                            ? `<span class="pill pill-red">⚠️ Từ cần kiểm tra lại: ${escapeHtml(dp.spelling_report.suspect_words.slice(0, 6).join(", "))}</span>`
                                            : ""
                                        }
                                      </div>
                                    `
                                    : ""
                                }
                                ${
                                  answerPdfReport
                                    ? `<div style="margin-top:6px;font-size:0.8rem;color:var(--green);font-weight:600;">
                                         ✓ Đã đối chiếu PDF Đáp án (${escapeHtml(answerPdfReport.source_name || "")}): khớp thêm ${answerPdfReport.total_matched || 0} câu (TN: ${answerPdfReport.matched_mcq || 0}, Đ/S: ${answerPdfReport.matched_tf || 0}, TLN: ${answerPdfReport.matched_sa || 0}).
                                       </div>`
                                    : ""
                                }
                              </div>
                            </div>

                            <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                              <button type="button" class="btn btn-soft" id="btn-preview-new-topic">
                                Xem trước nội dung &amp; giao diện
                              </button>
                              <label class="btn btn-secondary btn-sm" style="cursor:pointer;">
                                ${answerPdfApplying ? "Đang đối chiếu PDF Đáp án..." : "📎 Đối chiếu thêm PDF Đáp án"}
                                <input type="file" id="new-topic-answer-pdf-input" accept=".pdf" style="display:none;" ${answerPdfApplying ? "disabled" : ""} />
                              </label>
                              <button type="button" class="btn btn-primary" id="btn-publish-new-topic" ${newTopicDraft.publishing ? "disabled" : ""}>
                                ${newTopicDraft.publishing ? "Đang cập nhật vào hệ thống..." : "Cập nhật & Đẩy lên dữ liệu"}
                              </button>
                              <button type="button" class="btn btn-ghost btn-sm" id="btn-reset-new-topic">Chọn lại file khác</button>
                            </div>
                          </div>
                        `
                        : `
                          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                            <button type="button" class="btn btn-secondary btn-sm" id="btn-create-empty-topic">
                              Hoặc tạo Chủ đề trống (nhập bài thủ công sau)
                            </button>
                          </div>
                        `
                    }
                  </div>

                  <div class="card">
                    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
                      <div>
                        <h3 class="card-title" style="margin:0 0 2px;">Danh sách Chủ đề hiện có (${topicsList.length})</h3>
                        <p style="margin:0;font-size:0.83rem;color:var(--text-muted);">
                          Mở xem nhanh hoặc xoá bớt Chủ đề không còn sử dụng (luôn giữ lại ít nhất 1 Chủ đề).
                        </p>
                      </div>
                    </div>
                    <div class="data-table-wrap">
                      <table class="data-table">
                        <thead>
                          <tr>
                            <th style="width:90px;">Thứ tự</th>
                            <th>Tên Chủ đề</th>
                            <th style="width:120px;">Trạng thái</th>
                            <th style="width:200px;">Thao tác</th>
                          </tr>
                        </thead>
                        <tbody>
                          ${
                            topicsList.length
                              ? topicsList
                                  .map((tp) => {
                                    const isCur = tp.id === activeTopic?.id;
                                    const isDel = deletingTopicId === tp.id;
                                    const isEditing = editingTopicId === tp.id;
                                    const isSavingMeta = savingTopicMetaId === tp.id;
                                    const disableDel = topicsList.length <= 1 || Boolean(deletingTopicId);
                                    return `
                                      <tr>
                                        <td><span class="pill pill-primary">Chủ đề ${escapeHtml(String(tp.order_index || ""))}</span></td>
                                        <td>
                                          ${
                                            isEditing
                                              ? `
                                                <div style="display:flex;flex-direction:column;gap:6px;">
                                                  <input type="text" class="form-control form-control-sm" id="edit-topic-title-input" value="${escapeHtml(editingTopicTitle)}" placeholder="Nhập tên Chủ đề mới..." />
                                                  <input type="text" class="form-control form-control-sm" id="edit-topic-subtitle-input" value="${escapeHtml(editingTopicSubtitle)}" placeholder="Mô tả ngắn (không bắt buộc)" />
                                                </div>
                                              `
                                              : `
                                                <strong>${escapeHtml(tp.title)}</strong>
                                                ${tp.subtitle ? `<div style="font-size:0.78rem;color:var(--text-muted);margin-top:2px;">${escapeHtml(tp.subtitle)}</div>` : ""}
                                              `
                                          }
                                        </td>
                                        <td>
                                          ${isCur ? `<span class="pill pill-green">Đang mở</span>` : `<span class="pill pill-muted">Đã xuất bản</span>`}
                                        </td>
                                        <td>
                                          <div style="display:flex;gap:8px;flex-wrap:wrap;">
                                            ${
                                              isEditing
                                                ? `
                                                  <button type="button" class="btn btn-primary btn-sm" data-save-topic-meta="${escapeHtml(tp.id)}" ${isSavingMeta ? "disabled" : ""}>
                                                    ${isSavingMeta ? "Đang lưu..." : "Lưu tên"}
                                                  </button>
                                                  <button type="button" class="btn btn-ghost btn-sm" data-cancel-topic-meta="1" ${isSavingMeta ? "disabled" : ""}>Huỷ</button>
                                                `
                                                : `
                                                  <button type="button" class="btn btn-secondary btn-sm" data-open-topic="${escapeHtml(tp.id)}">Mở xem</button>
                                                  <button type="button" class="btn btn-soft btn-sm" data-edit-topic-meta="${escapeHtml(tp.id)}" data-edit-topic-title="${escapeHtml(tp.title)}" data-edit-topic-subtitle="${escapeHtml(tp.subtitle || "")}">Sửa tên</button>
                                                  <button type="button" class="btn btn-danger btn-sm" data-delete-topic="${escapeHtml(tp.id)}" data-delete-topic-title="${escapeHtml(tp.title)}" ${disableDel ? "disabled" : ""}>
                                                    ${isDel ? "Đang xoá..." : "Xoá chủ đề"}
                                                  </button>
                                                `
                                            }
                                          </div>
                                        </td>
                                      </tr>
                                    `;
                                  })
                                  .join("")
                              : `<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:18px;">Chưa có Chủ đề nào.</td></tr>`
                          }
                        </tbody>
                      </table>
                    </div>
                  </div>
                `;
              })()
            : contentSubMode === "youtube"
            ? `
              <div class="card">
                <h3 class="card-title">Thư viện Video YouTube — ${escapeHtml(t.title)}</h3>
                <div id="teacher-yt-mount"></div>
              </div>
            `
            : `
              <div class="card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
                  <div>
                    <h3 class="card-title" style="margin:0 0 4px;">Cập nhật nội dung từ file Word (.docx) / PDF / TXT</h3>
                    <p style="margin:0;font-size:0.84rem;color:var(--text-muted);">
                      Chọn file tài liệu để cập nhật Lý thuyết, Phiếu hệ thống kiến thức hoặc Câu hỏi ôn tập cho chủ đề đang chọn.
                    </p>
                  </div>
                  <a class="btn btn-secondary btn-sm" href="${withBase("/api/import-template")}" target="_blank">Tải file Word mẫu</a>
                </div>

                <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px;">
                  <label class="btn btn-primary btn-sm" style="cursor:pointer;">
                    Chọn file tài liệu
                    <input type="file" id="doc-import-input" accept=".docx,.pdf,.txt,.md" style="display:none;" />
                  </label>
                  <span id="doc-import-upload-text" style="font-size:0.84rem;color:var(--text-secondary);">
                    ${
                      importState.loading
                        ? "Đang đọc tài liệu..."
                        : importState.file
                        ? `Đã chọn: <strong>${escapeHtml(importState.file.name)}</strong>`
                        : "Hỗ trợ .docx, .pdf, .txt"
                    }
                  </span>
                </div>
                ${
                  importState.loading
                    ? `<div style="margin-bottom:12px;height:6px;border-radius:999px;background:rgba(15,118,110,0.14);overflow:hidden;">
                         <div id="doc-import-upload-bar" style="height:100%;width:8%;background:var(--primary);transition:width 0.15s ease;"></div>
                       </div>`
                    : ""
                }

                <div style="display:flex;gap:14px;flex-wrap:wrap;font-size:0.84rem;color:var(--text-secondary);">
                  <label><input type="checkbox" data-imp-sec="theory" ${importState.sections.theory ? "checked" : ""}/> Lý thuyết &amp; Hình ảnh</label>
                  <label><input type="checkbox" data-imp-sec="knowledge" ${importState.sections.knowledge ? "checked" : ""}/> Hệ thống kiến thức</label>
                  <label><input type="checkbox" data-imp-sec="review" ${importState.sections.review ? "checked" : ""}/> Hệ thống ôn tập</label>
                  <label><input type="checkbox" id="imp-replace-review" ${importState.replaceReview ? "checked" : ""}/> Thay thế câu hỏi cũ</label>
                </div>

                ${
                  prev && st
                    ? `
                      <div style="margin-top:14px;padding:14px;border:1px solid var(--primary-border);background:var(--surface-tint);border-radius:10px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
                        <div style="font-size:0.85rem;">
                          <strong>${escapeHtml(prev.detected_title)}</strong><br/>
                          <span style="color:var(--text-secondary);">${st.lessons_count} bài · ${st.images_count} ảnh · ${st.mcq_count} MCQ · ${st.true_false_count} Đúng/Sai · ${st.short_answer_count} Trả lời ngắn</span>
                        </div>
                        <div style="display:flex;gap:8px;flex-wrap:wrap;">
                          <button type="button" class="btn btn-soft btn-sm" id="btn-preview-doc-import">Xem trước giao diện</button>
                          <button type="button" class="btn btn-primary btn-sm" id="btn-apply-doc-import" ${importState.loading ? "disabled" : ""}>Cập nhật &amp; Đẩy lên dữ liệu</button>
                        </div>
                      </div>
                    `
                    : ""
                }
              </div>
            `
        }
      </div>
    `;
  }

  // ================== 4. BÁO CÁO HỌC TẬP & KẾT QUẢ TỪNG ĐỢT ÔN TẬP ==================
  function accPillClass(pct) {
    if (pct === null || pct === undefined) return "pill-muted";
    if (pct >= 80) return "pill-green";
    if (pct >= 50) return "pill-amber";
    return "pill-red";
  }

  async function openStudentReportModal(studentId) {
    reportModal = { kind: "student", loading: true, error: "", data: null, tab: "theory", studentId };
    render();
    try {
      const data = await api.staffStudentLearningReport(studentId);
      reportModal = { kind: "student", loading: false, error: "", data, tab: "theory", studentId };
    } catch (err) {
      reportModal = { kind: "student", loading: false, error: err.message || "Không tải được báo cáo.", data: null, tab: "theory", studentId };
    }
    render();
  }

  async function openAttemptDetailModal(attemptId, prevStudentId = null) {
    reportModal = { kind: "attempt", loading: true, error: "", data: null, prevStudentId };
    render();
    try {
      const data = await api.staffQuizAttemptDetail(attemptId);
      reportModal = { kind: "attempt", loading: false, error: "", data, prevStudentId };
    } catch (err) {
      reportModal = { kind: "attempt", loading: false, error: err.message || "Không tải được chi tiết đợt làm bài.", data: null, prevStudentId };
    }
    render();
  }

  function renderScoresView(classes) {
    const q = reportStudentFilter.trim().toLowerCase();
    const curSum = overview.curriculum_summary || {
      total_topics: 0,
      total_lessons: 0,
      total_sections: 0,
      total_exercise_units: 0,
      topics: [],
    };
    const filteredStudents = (overview.students || []).filter((s) => {
      if (classFilter && s.class_name !== classFilter) return false;
      if (q && !`${s.full_name} ${s.username} ${s.class_name || ""}`.toLowerCase().includes(q)) return false;
      return true;
    });
    const filteredAttempts = (overview.attempts || []).filter((a) => {
      if (classFilter && a.class_name !== classFilter) return false;
      if (reportTopicFilter && a.topic_id !== reportTopicFilter) return false;
      if (q && !`${a.full_name} ${a.username} ${a.topic_title || ""} ${a.lesson_filter_label || ""}`.toLowerCase().includes(q)) return false;
      return true;
    });

    const avgTheory = filteredStudents.length
      ? Math.round((filteredStudents.reduce((acc, s) => acc + (s.theory_pct || 0), 0) / filteredStudents.length) * 10) / 10
      : 0;
    const avgExComp = filteredStudents.length
      ? Math.round((filteredStudents.reduce((acc, s) => acc + (s.exercise_completion_pct || 0), 0) / filteredStudents.length) * 10) / 10
      : 0;
    const exAccList = filteredStudents.map((s) => s.exercise_accuracy_pct).filter((v) => v !== null && v !== undefined);
    const avgExAcc = exAccList.length
      ? Math.round((exAccList.reduce((a, b) => a + b, 0) / exAccList.length) * 10) / 10
      : null;
    const revAccList = filteredAttempts.filter((a) => (a.total_questions || 0) > 0).map((a) => a.accuracy_pct || 0);
    const avgRevAcc = revAccList.length
      ? Math.round((revAccList.reduce((a, b) => a + b, 0) / revAccList.length) * 10) / 10
      : null;
    const activeLearners = filteredStudents.filter(
      (s) => (s.studied_sections || 0) > 0 || (s.exercises_done || 0) > 0 || (s.review_rounds_count || 0) > 0
    ).length;

    const typeLabel = {
      mcq: "3.1 Trắc nghiệm 4 đáp án",
      true_false: "3.2 Đúng / Sai",
      short_answer: "3.3 Trả lời ngắn",
      combined: "Đề tổng hợp 3 phần",
    };
    const shortTypeLabel = {
      mcq: "TN 4 ĐA",
      true_false: "Đúng / Sai",
      short_answer: "TL ngắn",
      combined: "Tổng hợp 3 phần",
    };

    return `
      <div style="display:flex;flex-direction:column;gap:18px;">
        <!-- Thanh lọc & Xuất báo cáo CSV -->
        <div class="card" style="padding:14px 16px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
              <select id="att-class-filter" class="form-control form-control-sm" style="width:auto;">
                <option value="">Tất cả các lớp</option>
                ${classes.map((c) => `<option value="${escapeHtml(c)}" ${classFilter === c ? "selected" : ""}>Lớp ${escapeHtml(c)}</option>`).join("")}
              </select>
              <select id="rep-topic-filter" class="form-control form-control-sm" style="width:auto;max-width:250px;">
                <option value="">Tất cả Chủ đề (${curSum.total_topics || 0})</option>
                ${(curSum.topics || [])
                  .map(
                    (tp) =>
                      `<option value="${escapeHtml(tp.id)}" ${reportTopicFilter === tp.id ? "selected" : ""}>${escapeHtml(tp.title)}</option>`
                  )
                  .join("")}
              </select>
              <input id="rep-student-search" class="form-control form-control-sm" style="width:210px;" placeholder="Tìm học sinh, @tài khoản..." value="${escapeHtml(reportStudentFilter)}" />
            </div>
            <a class="btn btn-primary btn-sm" href="${api.exportLearningReportUrl(classFilter)}" target="_blank">
              📥 Xuất báo cáo học tập (CSV)
            </a>
          </div>
        </div>

        <!-- 4 Thẻ KPI tổng hợp -->
        <div class="stats-grid" style="margin-bottom:0;">
          <div class="stat-card">
            <div class="stat-label">TB % Lý thuyết đã học</div>
            <div class="stat-value" style="color:var(--primary);">${avgTheory}%</div>
            <div class="progress-bar-track"><div class="progress-bar-fill" style="width:${Math.min(100, avgTheory)}%;"></div></div>
            <small style="color:var(--text-muted);">Chương trình: ${curSum.total_lessons} bài · ${curSum.total_sections} mục LT</small>
          </div>
          <div class="stat-card">
            <div class="stat-label">TB Bài tập LT &amp; HTKT</div>
            <div class="stat-value" style="color:#0369a1;">${avgExComp}%</div>
            <div class="progress-bar-track"><div class="progress-bar-fill fill-blue" style="width:${Math.min(100, avgExComp)}%;"></div></div>
            <small style="color:var(--text-muted);">Tỉ lệ đúng TB: <strong>${avgExAcc !== null ? `${avgExAcc}%` : "—"}</strong> (${curSum.total_exercise_units} bài tập)</small>
          </div>
          <div class="stat-card">
            <div class="stat-label">Tỉ lệ đúng Hệ thống ôn tập</div>
            <div class="stat-value" style="color:#15803d;">${avgRevAcc !== null ? `${avgRevAcc}%` : "—"}</div>
            <div class="progress-bar-track"><div class="progress-bar-fill fill-green" style="width:${Math.min(100, avgRevAcc || 0)}%;"></div></div>
            <small style="color:var(--text-muted);">${filteredAttempts.length} đợt làm bài đã nộp</small>
          </div>
          <div class="stat-card">
            <div class="stat-label">Học sinh đã tham gia học</div>
            <div class="stat-value">${activeLearners} / ${filteredStudents.length}</div>
            <small style="color:var(--text-muted);">Có ghi nhận học LT, bài tập hoặc ôn tập</small>
          </div>
        </div>

        <!-- Bảng 1: Tiến độ & Tỉ lệ % học được / làm được theo từng Học sinh -->
        <div class="card">
          <div class="rt-card-head">
            <div>
              <h3 class="card-title" style="margin:0 0 2px;">1. Thống kê tỉ lệ % học được &amp; làm được theo từng Học sinh (${filteredStudents.length})</h3>
              <p style="margin:0;font-size:0.82rem;color:var(--text-muted);">
                Nhấn vào tên học sinh hoặc nút <strong>⋯</strong> để mở hồ sơ học tập chi tiết từng mục.
              </p>
            </div>
          </div>

          <div class="rt-table-wrap">
            <table class="rt-table">
              <thead>
                <tr>
                  <th>Học sinh</th>
                  <th>Lớp</th>
                  <th>Phiên học</th>
                  <th>Lý thuyết</th>
                  <th>Bài tập LT &amp; HTKT</th>
                  <th>Hệ thống ôn tập</th>
                  <th class="rt-th-actions"></th>
                </tr>
              </thead>
              <tbody>
                ${
                  filteredStudents.length
                    ? filteredStudents
                        .map((s, idx) => {
                          const avColor = s.avatar_color || AVATAR_PALETTE[idx % AVATAR_PALETTE.length];
                          const exAccStr =
                            s.exercise_accuracy_pct !== null && s.exercise_accuracy_pct !== undefined
                              ? `Đúng ${s.exercise_accuracy_pct}%`
                              : "Chưa làm";
                          const revAccStr =
                            s.review_accuracy_pct !== null && s.review_accuracy_pct !== undefined
                              ? `${s.review_accuracy_pct}%`
                              : "Chưa nộp";
                          return `
                          <tr>
                            <td>
                              <div class="rt-user-cell">
                                <span class="rt-avatar" style="background:${escapeHtml(avColor)};">${escapeHtml(initialsOf(s.full_name || s.username))}</span>
                                <div class="rt-stack">
                                  <button type="button" class="rt-primary-link" data-open-student-report="${s.id}" title="${escapeHtml(s.full_name)}">${escapeHtml(s.full_name)}</button>
                                  <span class="rt-sub">@${escapeHtml(s.username)}</span>
                                </div>
                              </div>
                            </td>
                            <td class="rt-nowrap"><span class="rt-num-badge is-slate">${escapeHtml(s.class_name || "—")}</span></td>
                            <td class="rt-nowrap">
                              <div class="rt-stack">
                                <span class="rt-primary">${s.session_count || 0} phiên</span>
                                <span class="rt-sub">${formatDuration(s.total_seconds || 0)}</span>
                              </div>
                            </td>
                            <td>
                              <div class="rt-metric">
                                <div class="rt-metric-head">
                                  <span class="rt-metric-pct">${s.theory_pct || 0}%</span>
                                  <span class="rt-metric-meta">${s.studied_lessons || 0}/${s.total_lessons || curSum.total_lessons} bài</span>
                                </div>
                                <div class="rt-bar"><div class="rt-bar-fill" style="width:${Math.min(100, s.theory_pct || 0)}%;"></div></div>
                                <span class="rt-metric-meta">${s.studied_sections || 0}/${s.total_sections || curSum.total_sections} mục đã học</span>
                              </div>
                            </td>
                            <td>
                              <div class="rt-metric">
                                <div class="rt-metric-head">
                                  <span class="rt-metric-pct">${s.exercise_completion_pct || 0}%</span>
                                  <span class="rt-num-badge ${accBadgeClass(s.exercise_accuracy_pct)}">${exAccStr}</span>
                                </div>
                                <div class="rt-bar"><div class="rt-bar-fill is-blue" style="width:${Math.min(100, s.exercise_completion_pct || 0)}%;"></div></div>
                                <span class="rt-metric-meta">${s.exercises_done || 0}/${s.exercises_total || curSum.total_exercise_units} bài đã làm</span>
                              </div>
                            </td>
                            <td>
                              <div class="rt-metric">
                                <div class="rt-metric-head">
                                  <span class="rt-num-badge ${accBadgeClass(s.review_accuracy_pct)}">${revAccStr}</span>
                                  <span class="rt-metric-meta">${s.review_rounds_count || 0} đợt</span>
                                </div>
                                <span class="rt-metric-meta">${s.review_questions_total ? `Đúng ${s.review_correct_total}/${s.review_questions_total} câu/ý` : "Chưa có lượt"}</span>
                              </div>
                            </td>
                            <td class="rt-td-actions">
                              ${kebabButtonHtml(`data-score-student-menu="${s.id}"`)}
                            </td>
                          </tr>
                        `;
                        })
                        .join("")
                    : `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:24px;">Không có học sinh phù hợp bộ lọc.</td></tr>`
                }
              </tbody>
            </table>
          </div>
        </div>

        <!-- Bảng 2: Báo cáo chi tiết từng Đợt làm bài tại Hệ thống ôn tập -->
        <div class="card">
          <div class="rt-card-head">
            <div>
              <h3 class="card-title" style="margin:0 0 2px;">2. Báo cáo chi tiết từng Đợt làm bài tại Hệ thống ôn tập (${filteredAttempts.length} đợt)</h3>
              <p style="margin:0;font-size:0.82rem;color:var(--text-muted);">
                Ghi nhận từng đợt làm bài (Đợt #1, Đợt #2...) theo Chủ đề/Bài. Bấm nút <strong>⋯</strong> ở cuối dòng để xem đối chiếu từng câu.
              </p>
            </div>
          </div>
          <div class="rt-table-wrap">
            <table class="rt-table">
              <thead>
                <tr>
                  <th>Đợt</th>
                  <th>Học sinh</th>
                  <th>Chủ đề / Phạm vi</th>
                  <th>Dạng</th>
                  <th>Kết quả</th>
                  <th>Tỉ lệ</th>
                  <th>Thời gian</th>
                  <th class="rt-th-actions"></th>
                </tr>
              </thead>
              <tbody>
                ${
                  filteredAttempts.length
                    ? filteredAttempts
                        .map((a) => {
                          const acc = a.accuracy_pct ?? (a.total_questions > 0 ? Math.round((a.correct_count * 1000) / a.total_questions) / 10 : 0);
                          return `
                            <tr>
                              <td class="rt-nowrap"><span class="rt-num-badge is-teal">#${a.round_number || 1}</span></td>
                              <td>
                                <div class="rt-stack">
                                  <span class="rt-primary" title="${escapeHtml(a.full_name)}">${escapeHtml(a.full_name)}</span>
                                  <span class="rt-sub">${escapeHtml(a.class_name || "—")} · @${escapeHtml(a.username)}</span>
                                </div>
                              </td>
                              <td>
                                <div class="rt-stack">
                                  <span class="rt-truncate" style="font-weight:600;color:#0f172a;" title="${escapeHtml(a.topic_title || a.topic_id)}">${escapeHtml(a.topic_title || a.topic_id)}</span>
                                  <span class="rt-sub" style="color:var(--primary);" title="${escapeHtml(a.lesson_filter_label || "Toàn chủ đề")}">${escapeHtml(a.lesson_filter_label || "Toàn chủ đề")}</span>
                                </div>
                              </td>
                              <td class="rt-nowrap">
                                <span class="rt-num-badge is-slate" title="${escapeHtml(typeLabel[a.quiz_type] || a.quiz_type)}">${escapeHtml(shortTypeLabel[a.quiz_type] || a.quiz_type)}</span>
                              </td>
                              <td class="rt-nowrap">
                                <div class="rt-stack">
                                  <span class="rt-primary">${a.score} / ${a.max_score} đ</span>
                                  <span class="rt-sub">Đúng ${a.correct_count}/${a.total_questions}</span>
                                </div>
                              </td>
                              <td class="rt-nowrap"><span class="rt-num-badge ${accBadgeClass(acc)}">${acc}%</span></td>
                              <td class="rt-nowrap" title="${escapeHtml(formatDateTimeVN(a.submitted_at))}">
                                <div class="rt-stack">
                                  <span class="rt-primary">${formatDuration(a.duration_seconds)}</span>
                                  <span class="rt-sub">${compactDateVN(a.submitted_at)}</span>
                                </div>
                              </td>
                              <td class="rt-td-actions">
                                ${kebabButtonHtml(`data-attempt-menu="${a.id}" data-user-id="${a.user_id || ""}"`)}
                              </td>
                            </tr>
                          `;
                        })
                        .join("")
                    : `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:24px;">Chưa có đợt làm bài ôn tập nào phù hợp.</td></tr>`
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }

  function renderAnalyticsModal() {
    if (!reportModal) return "";

    if (reportModal.kind === "student") {
      const rep = reportModal.data;
      const st = rep?.student;
      const sm = rep?.summary;
      const activeTab = reportModal.tab || "theory";
      const typeLabel = {
        mcq: "3.1 Trắc nghiệm 4 đáp án",
        true_false: "3.2 Đúng / Sai",
        short_answer: "3.3 Trả lời ngắn",
        combined: "Đề tổng hợp 3 phần",
      };

      return `
        <div class="analytics-modal-backdrop" id="analytics-modal-backdrop">
          <div class="analytics-modal-box" role="dialog" aria-modal="true">
            <div class="analytics-modal-head">
              <div>
                <h3 style="margin:0 0 3px;font-size:1.1rem;">
                  📊 Hồ sơ học tập chi tiết${st ? ` — ${escapeHtml(st.full_name)}` : ""}
                </h3>
                ${
                  st
                    ? `<div style="font-size:0.82rem;color:var(--text-muted);">@${escapeHtml(st.username)} · Lớp ${escapeHtml(st.class_name || "—")} · ${escapeHtml(st.school_name || "Chưa cập nhật trường")}</div>`
                    : ""
                }
              </div>
              <button type="button" class="btn btn-secondary btn-sm" id="btn-close-analytics-modal">✕ Đóng</button>
            </div>

            <div class="analytics-modal-body">
              ${
                reportModal.loading
                  ? `<div style="text-align:center;padding:40px;"><div class="spinner" style="margin:0 auto 10px;"></div>Đang tổng hợp dữ liệu học tập chi tiết...</div>`
                  : reportModal.error
                  ? `<div class="card" style="border-color:#fecaca;color:var(--red);">${escapeHtml(reportModal.error)}</div>`
                  : `
                    <div class="stats-grid" style="margin-bottom:16px;">
                      <div class="stat-card">
                        <div class="stat-label">Lý thuyết đã học</div>
                        <div class="stat-value" style="color:var(--primary);">${sm.theory_pct}%</div>
                        <div class="progress-bar-track"><div class="progress-bar-fill" style="width:${Math.min(100, sm.theory_pct)}%;"></div></div>
                        <small style="color:var(--text-muted);">${sm.studied_lessons}/${sm.total_lessons} bài · ${sm.studied_sections}/${sm.total_sections} mục</small>
                      </div>
                      <div class="stat-card">
                        <div class="stat-label">Bài tập LT &amp; HTKT</div>
                        <div class="stat-value" style="color:#0369a1;">${sm.exercise_completion_pct}%</div>
                        <div class="progress-bar-track"><div class="progress-bar-fill fill-blue" style="width:${Math.min(100, sm.exercise_completion_pct)}%;"></div></div>
                        <small style="color:var(--text-muted);">${sm.exercises_done}/${sm.exercises_total} bài · Đúng: <strong>${sm.exercise_accuracy_pct !== null ? `${sm.exercise_accuracy_pct}%` : "—"}</strong></small>
                      </div>
                      <div class="stat-card">
                        <div class="stat-label">Hệ thống ôn tập</div>
                        <div class="stat-value" style="color:#15803d;">${sm.review_accuracy_pct !== null ? `${sm.review_accuracy_pct}%` : "—"}</div>
                        <div class="progress-bar-track"><div class="progress-bar-fill fill-green" style="width:${Math.min(100, sm.review_accuracy_pct || 0)}%;"></div></div>
                        <small style="color:var(--text-muted);">${sm.review_rounds_count} đợt · Đúng ${sm.review_correct_total}/${sm.review_questions_total}</small>
                      </div>
                      <div class="stat-card">
                        <div class="stat-label">Phiên học &amp; Thi thử</div>
                        <div class="stat-value">${sm.session_count} phiên</div>
                        <small style="color:var(--text-muted);">${formatDuration(sm.total_study_seconds)} · ${sm.mock_attempts_count} lượt thi thử</small>
                      </div>
                    </div>

                    <div class="segmented" style="margin-bottom:14px;flex-wrap:wrap;">
                      <button type="button" class="seg-btn ${activeTab === "theory" ? "active" : ""}" data-modal-tab="theory">
                        Mục Lý thuyết đã học (${sm.studied_sections}/${sm.total_sections})
                      </button>
                      <button type="button" class="seg-btn ${activeTab === "exercises" ? "active" : ""}" data-modal-tab="exercises">
                        Bài tập LT &amp; HTKT (${sm.exercises_done})
                      </button>
                      <button type="button" class="seg-btn ${activeTab === "reviews" ? "active" : ""}" data-modal-tab="reviews">
                        Các đợt Hệ thống ôn tập (${sm.review_rounds_count})
                      </button>
                      <button type="button" class="seg-btn ${activeTab === "mock" ? "active" : ""}" data-modal-tab="mock">
                        Thi thử THPT (${sm.mock_attempts_count})
                      </button>
                    </div>

                    ${
                      activeTab === "theory"
                        ? `
                          <div style="display:flex;flex-direction:column;gap:12px;">
                            ${(rep.topics || [])
                              .map(
                                (tp) => `
                                <div class="analytics-topic-box">
                                  <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px;">
                                    <div style="font-weight:700;font-size:0.92rem;">${escapeHtml(tp.title)}</div>
                                    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:0.78rem;">
                                      <span class="pill ${tp.theory_pct >= 80 ? "pill-green" : tp.theory_pct > 0 ? "pill-primary" : "pill-muted"}">
                                        Lý thuyết: ${tp.theory_pct}% (${tp.studied_sections}/${tp.total_sections} mục)
                                      </span>
                                      <span class="pill ${accPillClass(tp.exercise_accuracy_pct)}">
                                        Bài tập: ${tp.exercise_done}/${tp.exercise_total}${tp.exercise_accuracy_pct !== null ? ` (${tp.exercise_accuracy_pct}%)` : ""}
                                      </span>
                                      <span class="pill ${accPillClass(tp.review_accuracy_pct)}">
                                        Ôn tập: ${tp.review_rounds_count} đợt${tp.review_accuracy_pct !== null ? ` (${tp.review_accuracy_pct}%)` : ""}
                                      </span>
                                    </div>
                                  </div>
                                  <div class="progress-bar-track" style="margin-bottom:10px;"><div class="progress-bar-fill" style="width:${Math.min(100, tp.theory_pct)}%;"></div></div>
                                  <div style="display:flex;flex-direction:column;gap:8px;">
                                    ${(tp.lessons || [])
                                      .map(
                                        (ls) => `
                                        <div class="analytics-lesson-row">
                                          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
                                            <div style="font-size:0.84rem;">
                                              <strong>${escapeHtml(ls.number)}:</strong> ${escapeHtml(ls.title)}
                                            </div>
                                            <span class="pill ${ls.progress_pct === 100 ? "pill-green" : ls.progress_pct > 0 ? "pill-amber" : "pill-muted"}" style="font-size:0.72rem;">
                                              ${ls.studied_sections}/${ls.total_sections} mục (${ls.progress_pct}%)
                                            </span>
                                          </div>
                                          <div class="analytics-sec-chips">
                                            ${(ls.sections || [])
                                              .map(
                                                (sc) => `
                                                <span class="sec-status-chip ${sc.studied ? "is-studied" : ""}" title="${sc.last_viewed_at ? `Học lúc: ${formatDateTimeVN(sc.last_viewed_at)}` : "Chưa học mục này"}">
                                                  <span>${sc.studied ? "✓" : "○"}</span>
                                                  <span>${escapeHtml(sc.heading)}</span>
                                                </span>
                                              `
                                              )
                                              .join("")}
                                          </div>
                                        </div>
                                      `
                                      )
                                      .join("")}
                                  </div>
                                </div>
                              `
                              )
                              .join("")}
                          </div>
                        `
                        : activeTab === "exercises"
                        ? `
                          <div class="data-table-wrap">
                            <table class="data-table">
                              <thead>
                                <tr>
                                  <th>Nguồn</th>
                                  <th>Bài học / Phiếu</th>
                                  <th>Nội dung bài tập</th>
                                  <th>Đúng / Tổng</th>
                                  <th>Tỉ lệ đúng</th>
                                  <th>Cao nhất</th>
                                  <th>Số lần</th>
                                  <th>Cập nhật</th>
                                </tr>
                              </thead>
                              <tbody>
                                ${
                                  (rep.exercises || []).length
                                    ? rep.exercises
                                        .map(
                                          (ex) => `
                                          <tr>
                                            <td><span class="pill ${ex.source_tab === "theory" ? "pill-primary" : "pill-amber"}">${ex.source_tab === "theory" ? "Lý thuyết" : "HTKT"}</span></td>
                                            <td style="font-size:0.82rem;"><strong>${escapeHtml(ex.lesson_label || ex.topic_id)}</strong></td>
                                            <td style="font-size:0.82rem;">${escapeHtml(ex.unit_title)}</td>
                                            <td><strong>${ex.correct_count} / ${ex.total_items}</strong></td>
                                            <td><span class="pill ${accPillClass(ex.accuracy_pct)}">${ex.accuracy_pct}%</span></td>
                                            <td>${ex.best_accuracy_pct}%</td>
                                            <td>${ex.attempt_count}</td>
                                            <td style="font-size:0.78rem;">${formatDateTimeVN(ex.updated_at)}</td>
                                          </tr>
                                        `
                                        )
                                        .join("")
                                    : `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:20px;">Học sinh chưa kiểm tra bài tập vận dụng nào trong mục Lý thuyết / Hệ thống kiến thức.</td></tr>`
                                }
                              </tbody>
                            </table>
                          </div>
                        `
                        : activeTab === "reviews"
                        ? `
                          <div class="data-table-wrap">
                            <table class="data-table">
                              <thead>
                                <tr>
                                  <th>Đợt</th>
                                  <th>Chủ đề &amp; Phạm vi</th>
                                  <th>Dạng ôn tập</th>
                                  <th>Đúng / Tổng</th>
                                  <th>Tỉ lệ đúng</th>
                                  <th>Điểm</th>
                                  <th>Theo từng bài</th>
                                  <th>Nộp lúc</th>
                                  <th></th>
                                </tr>
                              </thead>
                              <tbody>
                                ${
                                  (rep.review_rounds || []).length
                                    ? rep.review_rounds
                                        .map(
                                          (rd) => `
                                          <tr>
                                            <td><span class="pill pill-primary">Đợt #${rd.round_number}</span></td>
                                            <td>
                                              <div style="font-weight:600;font-size:0.82rem;">${escapeHtml(rd.topic_title)}</div>
                                              <small style="color:var(--primary);">${escapeHtml(rd.lesson_filter_label)}</small>
                                            </td>
                                            <td style="font-size:0.8rem;">${typeLabel[rd.quiz_type] || escapeHtml(rd.quiz_type)}</td>
                                            <td><strong>${rd.correct_count} / ${rd.total_questions}</strong></td>
                                            <td><span class="pill ${accPillClass(rd.accuracy_pct)}">${rd.accuracy_pct}%</span></td>
                                            <td><strong>${rd.score} / ${rd.max_score}</strong></td>
                                            <td style="font-size:0.76rem;">
                                              ${
                                                (rd.by_lesson || []).length
                                                  ? rd.by_lesson
                                                      .map(
                                                        (bl) =>
                                                          `<span class="pill pill-muted" style="margin:2px;font-size:0.72rem;">${escapeHtml(bl.lesson)}: ${bl.correct}/${bl.total} (${bl.accuracy_pct}%)</span>`
                                                      )
                                                      .join("")
                                                  : "—"
                                              }
                                            </td>
                                            <td style="font-size:0.78rem;">${formatDateTimeVN(rd.submitted_at)}</td>
                                            <td>
                                              <button type="button" class="btn btn-secondary btn-sm" data-open-attempt-detail="${rd.id}" data-from-student="${st.id}">🔍 Xem câu</button>
                                            </td>
                                          </tr>
                                        `
                                        )
                                        .join("")
                                    : `<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:20px;">Học sinh chưa có đợt làm bài nào tại Hệ thống ôn tập.</td></tr>`
                                }
                              </tbody>
                            </table>
                          </div>
                        `
                        : `
                          <div class="data-table-wrap">
                            <table class="data-table">
                              <thead>
                                <tr><th>Đề thi</th><th>Điểm tổng</th><th>Phần I / II / III</th><th>Đúng / Tổng</th><th>Thời gian</th><th>Nộp lúc</th></tr>
                              </thead>
                              <tbody>
                                ${
                                  (rep.mock_attempts || []).length
                                    ? rep.mock_attempts
                                        .map(
                                          (ma) => `
                                          <tr>
                                            <td><strong>Đề ${ma.order_number}: ${escapeHtml(ma.exam_title)}</strong></td>
                                            <td><span class="pill pill-primary">${ma.score} / ${ma.max_score}</span></td>
                                            <td>${ma.part1_score} · ${ma.part2_score} · ${ma.part3_score}</td>
                                            <td>${ma.correct_count} / ${ma.total_questions}</td>
                                            <td>${formatDuration(ma.duration_seconds)}</td>
                                            <td>${formatDateTimeVN(ma.submitted_at)}</td>
                                          </tr>
                                        `
                                        )
                                        .join("")
                                    : `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:20px;">Học sinh chưa có lượt thi thử THPT nào.</td></tr>`
                                }
                              </tbody>
                            </table>
                          </div>
                        `
                    }
                  `
              }
            </div>
          </div>
        </div>
      `;
    }

    // Modal 2: Chi tiết từng câu của 1 Đợt làm bài Hệ thống ôn tập
    const payload = reportModal.data;
    const att = payload?.attempt;
    const items = payload?.items || [];
    const partNames = {
      mcq: "3.1 Trắc nghiệm 4 đáp án",
      true_false: "3.2 Đúng / Sai",
      short_answer: "3.3 Trả lời ngắn",
      combined: "Đề tổng hợp 3 phần",
    };

    return `
      <div class="analytics-modal-backdrop" id="analytics-modal-backdrop">
        <div class="analytics-modal-box" role="dialog" aria-modal="true">
          <div class="analytics-modal-head">
            <div>
              <h3 style="margin:0 0 3px;font-size:1.08rem;">
                🔍 Chi tiết bài làm${att ? ` — Đợt #${att.round_number} · ${escapeHtml(att.full_name)}` : ""}
              </h3>
              ${
                att
                  ? `<div style="font-size:0.82rem;color:var(--text-muted);">
                       ${escapeHtml(att.topic_title)} · ${escapeHtml(att.lesson_filter_label)} · ${partNames[att.quiz_type] || escapeHtml(att.quiz_type)} · Nộp lúc ${formatDateTimeVN(att.submitted_at)}
                     </div>`
                  : ""
              }
            </div>
            <div style="display:flex;gap:8px;">
              ${
                reportModal.prevStudentId
                  ? `<button type="button" class="btn btn-soft btn-sm" id="btn-back-to-student-modal" data-student-id="${reportModal.prevStudentId}">← Về hồ sơ HS</button>`
                  : ""
              }
              <button type="button" class="btn btn-secondary btn-sm" id="btn-close-analytics-modal">✕ Đóng</button>
            </div>
          </div>

          <div class="analytics-modal-body">
            ${
              reportModal.loading
                ? `<div style="text-align:center;padding:40px;"><div class="spinner" style="margin:0 auto 10px;"></div>Đang tải chi tiết từng câu hỏi...</div>`
                : reportModal.error
                ? `<div class="card" style="border-color:#fecaca;color:var(--red);">${escapeHtml(reportModal.error)}</div>`
                : `
                  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:12px 14px;border-radius:10px;background:var(--surface-tint);border:1px solid var(--primary-border);margin-bottom:14px;">
                    <span class="pill pill-primary">Điểm: ${att.score} / ${att.max_score}</span>
                    <span class="pill ${accPillClass(att.accuracy_pct)}">Tỉ lệ đúng: ${att.accuracy_pct}% (${att.correct_count}/${att.total_questions} câu/ý)</span>
                    <span class="pill pill-muted">Thời gian: ${formatDuration(att.duration_seconds)}</span>
                    <span class="pill pill-muted">Lớp: ${escapeHtml(att.class_name || "—")}</span>
                  </div>

                  ${
                    (att.by_lesson || []).length
                      ? `
                        <div style="margin-bottom:14px;">
                          <div style="font-size:0.82rem;font-weight:700;margin-bottom:6px;color:var(--text-secondary);">Kết quả chính xác theo từng bài trong đợt này:</div>
                          <div style="display:flex;gap:6px;flex-wrap:wrap;">
                            ${att.by_lesson
                              .map(
                                (bl) =>
                                  `<span class="pill ${accPillClass(bl.accuracy_pct)}">${escapeHtml(bl.lesson)}: đúng ${bl.correct}/${bl.total} (${bl.accuracy_pct}%)</span>`
                              )
                              .join("")}
                          </div>
                        </div>
                      `
                      : ""
                  }

                  ${
                    items.length
                      ? `
                        <div class="data-table-wrap">
                          <table class="data-table">
                            <thead>
                              <tr>
                                <th style="width:76px;">Câu</th>
                                <th>Nội dung câu hỏi</th>
                                <th>Học sinh trả lời</th>
                                <th>Đáp án chuẩn</th>
                                <th style="width:105px;">Kết quả</th>
                              </tr>
                            </thead>
                            <tbody>
                              ${items
                                .map((it) => {
                                  const partTag = it.part === "mcq" ? "TN" : it.part === "true_false" ? "Đ/S" : "TLN";
                                  return `
                                    <tr style="background:${it.is_correct ? "rgba(22,163,74,0.04)" : "rgba(220,38,38,0.04)"};">
                                      <td>
                                        <strong>${partTag} ${it.num}</strong><br/>
                                        <small style="color:var(--text-muted);">${escapeHtml(it.lesson || "")}</small>
                                      </td>
                                      <td style="font-size:0.82rem;line-height:1.45;">
                                        ${formatBioHtml(it.question || "")}
                                        ${
                                          Array.isArray(it.statements) && it.statements.length
                                            ? `<div style="margin-top:6px;display:flex;flex-direction:column;gap:3px;">
                                                ${it.statements
                                                  .map(
                                                    (st) =>
                                                      `<div style="font-size:0.78rem;color:${st.is_correct ? "#15803d" : "#b91c1c"};">
                                                         <strong>${escapeHtml(st.key)})</strong> ${formatBioHtml(st.text)} — HS: <strong>${escapeHtml(st.user)}</strong> · ĐA: <strong>${escapeHtml(st.correct)}</strong>
                                                       </div>`
                                                  )
                                                  .join("")}
                                               </div>`
                                            : ""
                                        }
                                      </td>
                                      <td style="font-size:0.82rem;font-weight:600;color:${it.is_correct ? "#15803d" : "#b91c1c"};">${formatBioHtml(it.user_answer || "Bỏ trống")}</td>
                                      <td style="font-size:0.82rem;color:#0f766e;font-weight:600;">${formatBioHtml(it.correct_answer || "")}</td>
                                      <td>
                                        <span class="pill ${it.is_correct ? "pill-green" : "pill-red"}">
                                          ${it.is_correct ? "✓ Đúng" : it.part === "true_false" ? `${it.right_statements}/${it.total_statements} ý` : "✕ Sai"}
                                        </span>
                                        <div style="font-size:0.75rem;color:var(--text-muted);margin-top:3px;">+${it.points} / ${it.max_points}đ</div>
                                      </td>
                                    </tr>
                                  `;
                                })
                                .join("")}
                            </tbody>
                          </table>
                        </div>
                      `
                      : `<div class="card" style="background:var(--surface-tint);font-size:0.85rem;color:var(--text-secondary);">Đợt làm bài này được nộp trước đợt nâng cấp ghi chi tiết từng câu, nên chỉ có thống kê tổng hợp điểm và tỉ lệ đúng (${att.correct_count}/${att.total_questions} — ${att.accuracy_pct}%). Các đợt mới nộp từ bây giờ sẽ hiển thị đầy đủ đối chiếu từng câu.</div>`
                  }
                `
            }
          </div>
        </div>
      </div>
    `;
  }

  // ================== 5. QUẢN LÝ THÀNH VIÊN (GV + HS) & THỐNG KÊ TRUY CẬP ==================
  function renderMembersView() {
    const students = overview.students || [];
    const teachers = overview.teachers || [];
    const memberClasses = getUniqueClasses();
    const mq = memberSearchFilter.trim().toLowerCase();
    const filteredStudents = students.filter((s) => {
      if (memberClassFilter && s.class_name !== memberClassFilter) return false;
      if (
        mq &&
        !`${s.full_name} ${s.username} ${s.class_name || ""} ${s.school_name || ""}`
          .toLowerCase()
          .includes(mq)
      ) {
        return false;
      }
      return true;
    });

    return `
      <div style="display:flex;flex-direction:column;gap:18px;">
        ${
          isAdmin
            ? `
              <!-- CHỈ QUẢN TRỊ VIÊN: RESET MẬT KHẨU NHANH VỀ MẶC ĐỊNH 123456@ -->
              <div class="card" style="border:1.5px solid #fcd34d;background:linear-gradient(135deg,#fffbeb 0%,#ffffff 100%);">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:10px;">
                  <div>
                    <h3 class="card-title" style="margin:0 0 2px;color:#92400e;">🔑 Reset mật khẩu thành viên về mặc định (123456@)</h3>
                    <p style="margin:0;font-size:0.83rem;color:var(--text-secondary);">
                      Dành riêng cho Quản trị viên: chọn thành viên bên dưới hoặc bấm nút <strong>⋯</strong> ở từng dòng trong bảng để reset mật khẩu về <code>123456@</code>.
                    </p>
                  </div>
                </div>
                <form id="admin-quick-reset-form" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;">
                  <div class="form-group" style="margin:0;min-width:240px;flex:1;">
                    <label>Chọn nhanh thành viên hoặc gõ tên đăng nhập</label>
                    <input class="form-control form-control-sm" name="username" list="all-members-datalist" required placeholder="Chọn từ danh sách hoặc nhập @username (VD: gv_an, hs_binh)..." />
                    <datalist id="all-members-datalist">
                      ${[...teachers, ...students]
                        .map(
                          (m) =>
                            `<option value="${escapeHtml(m.username)}">${escapeHtml(m.full_name)} (${m.role === "teacher" ? "Giáo viên" : `HS ${m.class_name || ""}`})</option>`
                        )
                        .join("")}
                    </datalist>
                  </div>
                  <div class="form-group" style="margin:0;width:155px;">
                    <label>Mật khẩu sau reset</label>
                    <input class="form-control form-control-sm" value="123456@" readonly style="font-weight:700;background:#fff;text-align:center;" />
                  </div>
                  <button type="submit" class="btn btn-primary btn-sm" id="btn-quick-reset-mk">🔑 Reset MK về mặc định</button>
                </form>
              </div>

              <!-- CHỈ QUẢN TRỊ VIÊN: THÊM, RESET MK & XOÁ GIÁO VIÊN -->
              <div class="card">
                <div class="rt-card-head">
                  <div>
                    <h3 class="card-title" style="margin:0 0 2px;">Quản lý Giáo viên sử dụng (${teachers.length})</h3>
                    <p style="margin:0;font-size:0.82rem;color:var(--text-muted);">
                      Chỉ Quản trị viên có quyền thêm giáo viên hoặc thao tác qua nút <strong>⋯</strong> (Reset mật khẩu <code>123456@</code>, Xoá tài khoản).
                    </p>
                  </div>
                </div>

                <form id="admin-add-teacher-form" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;padding:12px;border-radius:10px;background:var(--surface-tint);border:1px solid var(--border);margin-bottom:14px;">
                  <div class="form-group" style="margin:0;min-width:220px;flex:1;">
                    <label>Tên đăng nhập Giáo viên (viết liền không dấu) *</label>
                    <input class="form-control form-control-sm" name="username" required placeholder="VD: gv_nguyenvana" />
                  </div>
                  <div class="form-group" style="margin:0;width:180px;">
                    <label>Mật khẩu mặc định</label>
                    <input class="form-control form-control-sm" name="password" value="123456@" readonly style="font-weight:700;background:#fff;" />
                  </div>
                  <button type="submit" class="btn btn-primary btn-sm">Thêm Giáo viên</button>
                </form>

                <div class="rt-table-wrap">
                  <table class="rt-table">
                    <thead>
                      <tr>
                        <th>Giáo viên</th>
                        <th>Trường</th>
                        <th>SĐT</th>
                        <th>Trạng thái</th>
                        <th class="rt-th-actions"></th>
                      </tr>
                    </thead>
                    <tbody>
                      ${
                        teachers.length
                          ? teachers
                              .map((t, idx) => {
                                const avColor = t.avatar_color || AVATAR_PALETTE[(idx + 1) % AVATAR_PALETTE.length];
                                return `
                                <tr>
                                  <td>
                                    <div class="rt-user-cell">
                                      <span class="rt-avatar" style="background:${escapeHtml(avColor)};">${escapeHtml(initialsOf(t.full_name || t.username))}</span>
                                      <div class="rt-stack">
                                        <span class="rt-primary" title="${escapeHtml(t.full_name)}">${escapeHtml(t.full_name)}</span>
                                        <span class="rt-sub">@${escapeHtml(t.username)}</span>
                                      </div>
                                    </div>
                                  </td>
                                  <td><span class="rt-truncate" title="${escapeHtml(t.school_name || "Chưa cập nhật")}">${escapeHtml(t.school_name || "—")}</span></td>
                                  <td class="rt-nowrap">${escapeHtml(t.phone || "—")}</td>
                                  <td class="rt-nowrap">
                                    ${
                                      t.must_change_password
                                        ? `<span class="rt-status is-pending"><span class="rt-status-dot"></span>Chờ đổi MK</span>`
                                        : `<span class="rt-status is-online"><span class="rt-status-dot"></span>Đã kích hoạt</span>`
                                    }
                                  </td>
                                  <td class="rt-td-actions">
                                    ${kebabButtonHtml(`data-teacher-menu="${t.id}"`)}
                                  </td>
                                </tr>
                              `;
                              })
                              .join("")
                          : `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:20px;">Chưa có Giáo viên nào được thêm.</td></tr>`
                      }
                    </tbody>
                  </table>
                </div>
              </div>
            `
            : ""
        }

        <!-- QUẢN TRỊ VIÊN & GIÁO VIÊN: THÊM HỌC SINH (THỦ CÔNG HOẶC FILE EXCEL) -->
        <div class="card">
          <div style="margin-bottom:14px;">
            <h3 class="card-title" style="margin:0 0 2px;">Thêm tài khoản Học sinh (Nhập thủ công hoặc File Excel)</h3>
            <p style="margin:0;font-size:0.83rem;color:var(--text-muted);">
              Tài khoản học sinh gồm <strong>Tên đăng nhập (viết liền không dấu)</strong> và mật khẩu mặc định <code>123456@</code>. Sau khi đăng nhập lần đầu, học sinh sẽ bắt buộc cập nhật Họ tên, Lớp, Trường, SĐT và đổi mật khẩu mới.
            </p>
          </div>

          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;">
            <!-- Nhập thủ công -->
            <form id="staff-add-student-form" style="padding:14px;border-radius:10px;border:1px solid var(--border);background:var(--surface);">
              <div style="font-weight:700;font-size:0.9rem;margin-bottom:10px;">Cách 1. Nhập thủ công</div>
              <div class="form-group">
                <label>Tên đăng nhập viết liền không dấu (có thể nhập nhiều dòng, mỗi dòng 1 HS) *</label>
                <textarea class="form-control" name="usernames" rows="3" required placeholder="nguyenvanan&#10;tranthibinh"></textarea>
              </div>
              <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;">
                <div class="form-group" style="margin:0;width:160px;">
                  <label>Mật khẩu mặc định</label>
                  <input class="form-control form-control-sm" name="password" value="123456@" readonly style="font-weight:700;" />
                </div>
                <button type="submit" class="btn btn-primary btn-sm">Tạo tài khoản HS</button>
              </div>
            </form>

            <!-- Nhập từ file Excel -->
            <div style="padding:14px;border-radius:10px;border:1px solid var(--border);background:var(--surface-tint);">
              <div style="font-weight:700;font-size:0.9rem;margin-bottom:8px;">Cách 2. Nhập hàng loạt từ File Excel (.xlsx)</div>
              <p style="font-size:0.82rem;color:var(--text-secondary);margin:0 0 12px;line-height:1.45;">
                Tải file Excel mẫu gồm 2 cột (<code>Ten dang nhap</code>, <code>Mat khau mac dinh</code>), điền danh sách học sinh rồi tải lên hệ thống.
              </p>
              <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                <a class="btn btn-secondary btn-sm" href="${api.studentImportTemplateUrl()}" target="_blank" id="btn-dl-student-template">
                  Tải file Excel mẫu (.xlsx)
                </a>
                <label class="btn btn-primary btn-sm" style="cursor:pointer;">
                  ${studentExcelLoading ? "Đang nhập Excel..." : "Tải lên file Excel (.xlsx/.csv)"}
                  <input type="file" id="student-excel-input" accept=".xlsx,.csv" style="display:none;" ${studentExcelLoading ? "disabled" : ""} />
                </label>
              </div>
              ${
                studentExcelResult
                  ? `
                    <div style="margin-top:12px;padding:10px 12px;border-radius:8px;background:#fff;border:1px solid var(--primary-border);font-size:0.82rem;">
                      <strong style="color:var(--green);">${escapeHtml(studentExcelResult.message || "")}</strong>
                      ${
                        (studentExcelResult.skipped || []).length
                          ? `<div style="color:var(--amber);margin-top:4px;">Đã tồn tại (bỏ qua): ${escapeHtml(studentExcelResult.skipped.join(", "))}</div>`
                          : ""
                      }
                      ${
                        (studentExcelResult.errors || []).length
                          ? `<div style="color:var(--red);margin-top:4px;">Lỗi: ${escapeHtml(studentExcelResult.errors.slice(0, 5).join(" | "))}</div>`
                          : ""
                      }
                    </div>
                  `
                  : ""
              }
            </div>
          </div>
        </div>

        <!-- DANH SÁCH HỌC SINH & SỐ LẦN TRUY CẬP -->
        <div class="card">
          <div class="rt-card-head">
            <div>
              <h3 class="card-title" style="margin:0 0 2px;">Danh sách Học sinh (${filteredStudents.length}${filteredStudents.length !== students.length ? ` / ${students.length}` : ""})</h3>
              <p style="margin:0;font-size:0.82rem;color:var(--text-muted);">
                Nhấn tên học sinh để xem báo cáo học tập hoặc bấm <strong>⋯</strong> ở cuối dòng để thao tác.
              </p>
            </div>
            <div class="rt-toolbar">
              <select id="members-class-filter" class="form-control form-control-sm" style="width:auto;">
                <option value="">Tất cả lớp</option>
                ${memberClasses.map((c) => `<option value="${escapeHtml(c)}" ${memberClassFilter === c ? "selected" : ""}>Lớp ${escapeHtml(c)}</option>`).join("")}
              </select>
              <input id="members-search" class="form-control form-control-sm" style="width:190px;" placeholder="Tìm tên, @username..." value="${escapeHtml(memberSearchFilter)}" />
            </div>
          </div>
          <div class="rt-table-wrap">
            <table class="rt-table">
              <thead>
                <tr>
                  <th>Học sinh</th>
                  <th>Lớp / Trường</th>
                  <th>SĐT</th>
                  <th>Truy cập</th>
                  <th>Học tập</th>
                  <th>Trạng thái</th>
                  <th class="rt-th-actions"></th>
                </tr>
              </thead>
              <tbody>
                ${
                  filteredStudents.length
                    ? filteredStudents
                        .map((s, idx) => {
                          const avColor = s.avatar_color || AVATAR_PALETTE[idx % AVATAR_PALETTE.length];
                          const lastLoginFull = formatDateTimeVN(s.last_login);
                          return `
                          <tr>
                            <td>
                              <div class="rt-user-cell">
                                <span class="rt-avatar" style="background:${escapeHtml(avColor)};">${escapeHtml(initialsOf(s.full_name || s.username))}</span>
                                <div class="rt-stack">
                                  <button type="button" class="rt-primary-link" data-open-student-report="${s.id}" title="${escapeHtml(s.full_name)}">${escapeHtml(s.full_name)}</button>
                                  <span class="rt-sub">@${escapeHtml(s.username)}</span>
                                </div>
                              </div>
                            </td>
                            <td>
                              <div class="rt-stack">
                                <span class="rt-primary">${s.class_name ? `Lớp ${escapeHtml(s.class_name)}` : "Chưa nhập lớp"}</span>
                                <span class="rt-sub" title="${escapeHtml(s.school_name || "Chưa cập nhật")}">${escapeHtml(s.school_name || "—")}</span>
                              </div>
                            </td>
                            <td class="rt-nowrap">${escapeHtml(s.phone || "—")}</td>
                            <td class="rt-nowrap" title="${escapeHtml(lastLoginFull)}">
                              <div class="rt-stack">
                                <span class="rt-num-badge is-teal" style="width:fit-content;">${s.login_count || 0} lần</span>
                                <span class="rt-sub">${compactDateVN(s.last_login)}</span>
                              </div>
                            </td>
                            <td class="rt-nowrap">
                              <div class="rt-stack">
                                <span class="rt-primary">${formatDuration(s.total_seconds)}</span>
                                <span class="rt-sub">${s.session_count || 0} phiên · LT ${s.theory_pct || 0}%</span>
                              </div>
                            </td>
                            <td class="rt-nowrap">
                              ${
                                s.must_change_password
                                  ? `<span class="rt-status is-pending"><span class="rt-status-dot"></span>Chờ đổi MK</span>`
                                  : s.is_online
                                  ? `<span class="rt-status is-online"><span class="rt-status-dot"></span>Đang học</span>`
                                  : `<span class="rt-status is-offline"><span class="rt-status-dot"></span>Ngoại tuyến</span>`
                              }
                            </td>
                            <td class="rt-td-actions">
                              ${kebabButtonHtml(`data-student-menu="${s.id}"`)}
                            </td>
                          </tr>
                        `;
                        })
                        .join("")
                    : `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:22px;">${students.length ? "Không có học sinh phù hợp bộ lọc." : "Chưa có tài khoản Học sinh nào. Hãy thêm bằng thủ công hoặc file Excel ở trên."}</td></tr>`
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }

  // ================== 6. CHỈ QUẢN TRỊ VIÊN: BÁO CÁO ĐỔI MẬT KHẨU CỦA GV & HS ==================
  function renderPasswordAlertsView() {
    const logs = overview.password_change_logs || [];
    const unreadCount = overview.stats?.unread_password_changes || 0;
    const reasonText = {
      first_login_setup: "Kích hoạt & đổi mật khẩu lần đầu",
      profile_change: "Đổi mật khẩu trong Hồ sơ",
      admin_reset: "Admin reset về mặc định (123456@)",
    };

    return `
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px;">
          <div>
            <h3 class="card-title" style="margin:0 0 2px;">Báo cáo đổi mật khẩu từ Giáo viên &amp; Học sinh (${logs.length})</h3>
            <p style="margin:0;font-size:0.83rem;color:var(--text-muted);">
              Mọi lượt cập nhật mật khẩu mới của Giáo viên và Học sinh đều được tự động ghi nhận và gửi về Quản trị viên.
            </p>
          </div>
          ${
            unreadCount > 0
              ? `<button type="button" class="btn btn-primary btn-sm" id="btn-mark-pw-read">Đánh dấu đã xem tất cả (${unreadCount})</button>`
              : ""
          }
        </div>

        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Trạng thái</th>
                <th>Vai trò</th>
                <th>Họ và tên / Tài khoản</th>
                <th>Trường / Lớp</th>
                <th>Số điện thoại</th>
                <th>Loại cập nhật</th>
                <th>Thời điểm đổi</th>
              </tr>
            </thead>
            <tbody>
              ${
                logs.length
                  ? logs
                      .map(
                        (l) => `
                        <tr style="${!l.is_read ? "background:var(--surface-tint);" : ""}">
                          <td>${!l.is_read ? `<span class="pill pill-red">Mới</span>` : `<span class="pill pill-muted">Đã xem</span>`}</td>
                          <td><span class="pill ${l.role === "teacher" ? "pill-primary" : "pill-green"}">${l.role === "teacher" ? "Giáo viên" : "Học sinh"}</span></td>
                          <td><strong>${escapeHtml(l.full_name)}</strong><br/><small style="color:var(--text-muted)">@${escapeHtml(l.username)}</small></td>
                          <td>${escapeHtml(l.school_name || "—")}${l.class_name ? `<br/><small style="color:var(--text-muted)">${escapeHtml(l.class_name)}</small>` : ""}</td>
                          <td>${escapeHtml(l.phone || "—")}</td>
                          <td>${escapeHtml(reasonText[l.reason] || l.reason)}</td>
                          <td><strong>${formatDateTimeVN(l.changed_at)}</strong></td>
                        </tr>
                      `
                      )
                      .join("")
                  : `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:22px;">Chưa có dữ liệu đổi mật khẩu nào.</td></tr>`
              }
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // ================== EVENT BINDINGS ==================
  async function resetUserById(userId, displayName, uname) {
    if (
      !window.confirm(
        `Xác nhận đặt lại mật khẩu của "${displayName}" (@${uname}) về mật khẩu mặc định 123456@?\nThành viên này sẽ cần đăng nhập lại bằng mật khẩu 123456@ và đổi mật khẩu mới.`
      )
    ) {
      return;
    }
    try {
      const res = await api.adminResetUserPassword(userId);
      showToast(res.message || "Đã đặt lại mật khẩu về 123456@.", "success");
      await loadOverview(true);
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function deleteUserById(userId, uname) {
    if (!window.confirm(`Xác nhận xoá tài khoản "${uname}" khỏi hệ thống?`)) return;
    try {
      const res = await api.adminDeleteUser(userId);
      showToast(res.message || "Đã xoá tài khoản.", "success");
      await loadOverview(true);
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function bindSubviewEvents() {
    // ---- MEMBERS & PASSWORD ALERTS EVENTS ----
    if (subtab === "members") {
      container.querySelector("#admin-quick-reset-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const uname = String(fd.get("username") || "").trim().replace(/^@/, "");
        if (!uname) {
          showToast("Vui lòng nhập hoặc chọn tên đăng nhập thành viên cần reset mật khẩu.", "error");
          return;
        }
        if (
          !window.confirm(
            `Xác nhận đặt lại mật khẩu của tài khoản "@${uname}" về mật khẩu mặc định 123456@?`
          )
        ) {
          return;
        }
        try {
          const res = await api.adminResetPasswordByUsername(uname);
          showToast(res.message || "Đã đặt lại mật khẩu về 123456@.", "success");
          e.target.reset();
          await loadOverview(true);
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      container.querySelector("#admin-add-teacher-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
          const res = await api.adminAddTeacher(String(fd.get("username") || "").trim(), String(fd.get("password") || "123456@"));
          showToast(res.message || "Đã thêm Giáo viên mới!", "success");
          e.target.reset();
          await loadOverview(true);
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      container.querySelector("#members-class-filter")?.addEventListener("change", (e) => {
        memberClassFilter = e.target.value;
        render();
      });

      container.querySelector("#members-search")?.addEventListener("input", (e) => {
        memberSearchFilter = e.target.value;
        render();
        const el = container.querySelector("#members-search");
        if (el) {
          el.focus();
          el.setSelectionRange(el.value.length, el.value.length);
        }
      });

      container.querySelectorAll("[data-teacher-menu]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          const tid = btn.dataset.teacherMenu;
          const t = (overview.teachers || []).find((x) => String(x.id) === String(tid));
          if (!t) return;
          openRowActionMenu(btn, [
            {
              label: "🔑 Reset mật khẩu (123456@)",
              onClick: () => resetUserById(t.id, t.full_name || t.username, t.username),
            },
            { divider: true },
            {
              label: "🗑 Xoá giáo viên",
              danger: true,
              onClick: () => deleteUserById(t.id, t.username),
            },
          ]);
        });
      });

      container.querySelectorAll("[data-student-menu]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          const sid = btn.dataset.studentMenu;
          const s = (overview.students || []).find((x) => String(x.id) === String(sid));
          if (!s) return;
          const items = [
            {
              label: "📊 Xem báo cáo học tập",
              onClick: () => openStudentReportModal(s.id),
            },
          ];
          if (isAdmin) {
            items.push(
              {
                label: "🔑 Reset mật khẩu (123456@)",
                onClick: () => resetUserById(s.id, s.full_name || s.username, s.username),
              },
              { divider: true },
              {
                label: "🗑 Xoá học sinh",
                danger: true,
                onClick: () => deleteUserById(s.id, s.username),
              }
            );
          }
          openRowActionMenu(btn, items);
        });
      });

      container.querySelector("#staff-add-student-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const rawText = String(fd.get("usernames") || "");
        const pwd = String(fd.get("password") || "123456@");
        const lines = rawText
          .split(/[\r\n,;]+/)
          .map((s) => s.trim())
          .filter(Boolean);
        if (!lines.length) {
          showToast("Vui lòng nhập ít nhất 1 tên đăng nhập viết liền không dấu.", "error");
          return;
        }
        try {
          const res = await api.staffAddStudents({
            students: lines.map((u) => ({ username: u, password: pwd })),
          });
          showToast(res.message || "Đã tạo tài khoản học sinh!", "success");
          e.target.reset();
          await loadOverview(true);
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      container.querySelector("#student-excel-input")?.addEventListener("change", async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        studentExcelLoading = true;
        studentExcelResult = null;
        render();
        try {
          const b64 = await fileToBase64(file);
          const res = await api.staffImportStudentsExcel(file.name, b64);
          studentExcelResult = res;
          showToast(res.message || "Đã nhập danh sách học sinh từ Excel!", "success");
          await loadOverview(true);
        } catch (err) {
          showToast(err.message, "error");
        } finally {
          studentExcelLoading = false;
          render();
        }
      });
    }

    if (subtab === "pw_alerts") {
      container.querySelector("#btn-mark-pw-read")?.addEventListener("click", async () => {
        try {
          await api.adminMarkPasswordAlertsRead();
          showToast("Đã đánh dấu tất cả báo cáo là đã xem.", "success");
          await loadOverview(true);
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    }

    container.querySelector("#att-class-filter")?.addEventListener("change", (e) => {
      classFilter = e.target.value;
      render();
    });
    container.querySelector("#rep-topic-filter")?.addEventListener("change", (e) => {
      reportTopicFilter = e.target.value;
      render();
    });
    container.querySelector("#rep-student-search")?.addEventListener("input", (e) => {
      reportStudentFilter = e.target.value;
      render();
      const el = container.querySelector("#rep-student-search");
      if (el) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    });
    container.querySelector("#att-search")?.addEventListener("input", (e) => {
      searchFilter = e.target.value;
      render();
      const el = container.querySelector("#att-search");
      if (el) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    });

    // ---- ANALYTICS REPORT MODAL EVENTS ----
    container.querySelectorAll("[data-score-student-menu]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const sid = btn.dataset.scoreStudentMenu;
        const s = (overview.students || []).find((x) => String(x.id) === String(sid));
        if (!s) return;
        const items = [
          {
            label: "📊 Xem hồ sơ học tập chi tiết",
            onClick: () => openStudentReportModal(s.id),
          },
        ];
        if (isAdmin) {
          items.push({
            label: "🔑 Reset mật khẩu (123456@)",
            onClick: () => resetUserById(s.id, s.full_name || s.username, s.username),
          });
        }
        openRowActionMenu(btn, items);
      });
    });

    container.querySelectorAll("[data-attempt-menu]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const aid = btn.dataset.attemptMenu;
        const uid = btn.dataset.userId;
        const items = [
          {
            label: "🔍 Xem chi tiết từng câu",
            onClick: () => openAttemptDetailModal(aid, null),
          },
        ];
        if (uid) {
          items.push({
            label: "📊 Xem hồ sơ học sinh",
            onClick: () => openStudentReportModal(uid),
          });
        }
        openRowActionMenu(btn, items);
      });
    });

    container.querySelectorAll("[data-open-student-report]").forEach((btn) => {
      btn.addEventListener("click", () => {
        openStudentReportModal(btn.dataset.openStudentReport);
      });
    });
    container.querySelectorAll("[data-open-attempt-detail]").forEach((btn) => {
      btn.addEventListener("click", () => {
        openAttemptDetailModal(btn.dataset.openAttemptDetail, btn.dataset.fromStudent || null);
      });
    });
    container.querySelector("#btn-close-analytics-modal")?.addEventListener("click", () => {
      reportModal = null;
      render();
    });
    container.querySelector("#analytics-modal-backdrop")?.addEventListener("click", (e) => {
      if (e.target.id === "analytics-modal-backdrop") {
        reportModal = null;
        render();
      }
    });
    container.querySelector("#btn-back-to-student-modal")?.addEventListener("click", (e) => {
      const sid = e.currentTarget.dataset.studentId;
      if (sid) openStudentReportModal(sid);
    });
    container.querySelectorAll("[data-modal-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (reportModal) {
          reportModal.tab = btn.dataset.modalTab;
          render();
        }
      });
    });

    // ---- EXAM MIXER EVENTS (WORD .DOCX & MATRIX 3x3) ----
    if (subtab === "exam_mixer") {
      container.querySelectorAll("[data-em-mode]").forEach((btn) => {
        btn.addEventListener("click", () => {
          examMixerMode = btn.dataset.emMode || "word";
          onSubRouteChange?.({ subtab, contentSubMode, examMixerMode });
          if (examMixerMode === "matrix" && !examPool) {
            render();
            ensureExamPoolLoaded();
          } else {
            render();
          }
        });
      });

      if (examMixerMode === "word") {
        const syncWordConfig = () => {
          const s = container.querySelector("#wx-school");
          const p = container.querySelector("#wx-period");
          const y = container.querySelector("#wx-year");
          const sub = container.querySelector("#wx-subject");
          const dur = container.querySelector("#wx-duration");
          const cnt = container.querySelector("#wx-count");
          const cds = container.querySelector("#wx-codes");
          if (s) examConfig.school_name = s.value.trim();
          if (p) examConfig.exam_period = p.value.trim() || examConfig.exam_period;
          if (y) examConfig.school_year = y.value.trim() || examConfig.school_year;
          if (sub) examConfig.subject = sub.value.trim();
          if (dur) examConfig.duration_minutes = Math.max(5, Math.min(180, parseInt(dur.value || "45", 10) || 45));
          if (cnt) examConfig.exam_count = Math.max(1, Math.min(30, parseInt(cnt.value || "4", 10) || 4));
          if (cds) examConfig.exam_codes = cds.value.trim();
        };

        container.querySelector("#wx-count")?.addEventListener("change", (e) => {
          syncWordConfig();
          const newCount = Math.max(1, Math.min(30, parseInt(e.target.value || "4", 10) || 4));
          examConfig.exam_count = newCount;
          examConfig.exam_codes = buildDefault4DigitCodes(newCount, 1001);
          render();
        });

        container.querySelector("#btn-wx-sync-codes")?.addEventListener("click", () => {
          syncWordConfig();
          examConfig.exam_codes = buildDefault4DigitCodes(examConfig.exam_count, 1001);
          render();
        });

        container.querySelector("#btn-wx-rand-codes")?.addEventListener("click", () => {
          syncWordConfig();
          examConfig.exam_codes = buildRandom4DigitCodes(examConfig.exam_count);
          render();
        });

        container.querySelector("#btn-toggle-word-preview")?.addEventListener("click", () => {
          syncWordConfig();
          wordMixer.showPreview = !wordMixer.showPreview;
          render();
        });

        container.querySelector("#word-mixer-file-input")?.addEventListener("change", async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          syncWordConfig();
          wordMixer.file = file;
          wordMixer.loading = true;
          wordMixer.loadingSampleName = "";
          wordMixer.parsed = null;
          wordMixer.result = null;
          render();
          try {
            const res = await api.parseWordExamForMixer(file);
            wordMixer.parsed = res;
            showToast(
              `Đã phân tích xong "${file.name}": ${res.stats?.total_questions || 0} câu (${res.stats?.exam_format_label || ""}).`,
              "success"
            );
          } catch (err) {
            wordMixer.file = null;
            showToast(err.message, "error");
          } finally {
            e.target.value = "";
            wordMixer.loading = false;
            render();
          }
        });

        container.querySelectorAll("[data-load-sample-exam]").forEach((btn) => {
          btn.addEventListener("click", async () => {
            const fname = btn.dataset.loadSampleExam;
            if (!fname) return;
            syncWordConfig();
            wordMixer.loading = true;
            wordMixer.loadingSampleName = fname;
            wordMixer.parsed = null;
            wordMixer.result = null;
            render();
            try {
              const res = await api.loadExamMixerSample(fname);
              wordMixer.parsed = res;
              showToast(
                `Đã nạp đề mẫu "${fname}": ${res.stats?.total_questions || 0} câu (${res.stats?.exam_format_label || ""}).`,
                "success"
              );
            } catch (err) {
              showToast(err.message, "error");
            } finally {
              wordMixer.loading = false;
              wordMixer.loadingSampleName = "";
              render();
            }
          });
        });

        container.querySelector("#btn-generate-word-exam")?.addEventListener("click", async () => {
          syncWordConfig();
          if (!wordMixer.parsed?.content) {
            showToast("Vui lòng tải lên file Word (.docx) đề kiểm tra gốc trước.", "error");
            return;
          }
          wordMixer.generating = true;
          wordMixer.result = null;
          render();
          try {
            const res = await api.generateShuffledFromWord({
              content: wordMixer.parsed.content,
              exam_count: examConfig.exam_count,
              exam_codes: examConfig.exam_codes,
              school_name: examConfig.school_name,
              exam_period: examConfig.exam_period,
              school_year: examConfig.school_year,
              subject: examConfig.subject,
              duration_minutes: examConfig.duration_minutes,
            });
            wordMixer.result = { job_id: res.job_id, summary: res.summary };
            showToast(`Đã trộn thành công ${res.summary.exam_count} mã đề 4 số!`, "success");
          } catch (err) {
            showToast(err.message, "error");
          } finally {
            wordMixer.generating = false;
            render();
          }
        });
      }
    }

    if (subtab === "exam_mixer" && examMixerMode === "matrix" && examPool) {
      container.querySelector("#ex-select-all")?.addEventListener("click", () => {
        examPool.forEach((tp) => (tp.lessons || []).forEach((ls) => selectedLessonIds.add(ls.id)));
        render();
      });
      container.querySelector("#ex-clear-all")?.addEventListener("click", () => {
        selectedLessonIds.clear();
        render();
      });
      container.querySelectorAll("[data-ex-topic]").forEach((cb) => {
        cb.addEventListener("change", () => {
          const tp = examPool.find((x) => x.id === cb.dataset.exTopic);
          if (!tp) return;
          (tp.lessons || []).forEach((ls) => {
            if (cb.checked) selectedLessonIds.add(ls.id);
            else selectedLessonIds.delete(ls.id);
          });
          render();
        });
      });
      container.querySelectorAll("[data-ex-lesson]").forEach((cb) => {
        cb.addEventListener("change", () => {
          if (cb.checked) selectedLessonIds.add(cb.dataset.exLesson);
          else selectedLessonIds.delete(cb.dataset.exLesson);
          render();
        });
      });

      container.querySelectorAll("[data-mx-kind]").forEach((inp) => {
        inp.addEventListener("change", () => {
          const val = Math.max(0, parseInt(inp.value || "0", 10) || 0);
          matrix[inp.dataset.mxKind][inp.dataset.mxLv] = val;
          render();
        });
      });

      container.querySelector("#ex-preset-10")?.addEventListener("click", () => {
        const av = computeAvailablePool();
        const distribute = (kind, targets) => {
          // Phân bổ theo tỉ lệ đích nhưng không vượt quá số câu có sẵn
          const out = { nhan_biet: 0, thong_hieu: 0, van_dung: 0 };
          let rem = targets.nhan_biet + targets.thong_hieu + targets.van_dung;
          ["nhan_biet", "thong_hieu", "van_dung"].forEach((lv) => {
            const take = Math.min(targets[lv], av[kind][lv]);
            out[lv] = take;
            rem -= take;
          });
          // Bù vào các mức còn dư nếu thiếu ở một mức
          ["thong_hieu", "nhan_biet", "van_dung"].forEach((lv) => {
            if (rem <= 0) return;
            const room = Math.max(0, av[kind][lv] - out[lv]);
            const add = Math.min(rem, room);
            out[lv] += add;
            rem -= add;
          });
          return out;
        };
        matrix = {
          mcq: distribute("mcq", { nhan_biet: 8, thong_hieu: 6, van_dung: 4 }),
          true_false: distribute("true_false", { nhan_biet: 1, thong_hieu: 2, van_dung: 1 }),
          short_answer: distribute("short_answer", { nhan_biet: 1, thong_hieu: 2, van_dung: 3 }),
        };
        render();
        showToast("Đã điền gợi ý ma trận chuẩn 10 điểm theo nguồn câu hỏi đã chọn.", "success");
      });

      const syncConfig = () => {
        examConfig.exam_period = container.querySelector("#ex-title")?.value.trim() || examConfig.exam_period;
        examConfig.title = examConfig.exam_period;
        const sEl = container.querySelector("#ex-school");
        if (sEl) examConfig.school_name = sEl.value.trim();
        examConfig.school_year = container.querySelector("#ex-year")?.value.trim() || examConfig.school_year;
        const subEl = container.querySelector("#ex-subject");
        if (subEl) examConfig.subject = subEl.value.trim();
        examConfig.duration_minutes = Math.max(5, parseInt(container.querySelector("#ex-duration")?.value || "45", 10) || 45);
        examConfig.exam_count = Math.max(1, Math.min(30, parseInt(container.querySelector("#ex-count")?.value || "4", 10) || 4));
        examConfig.exam_codes = container.querySelector("#ex-codes")?.value || "";
      };

      container.querySelector("#btn-generate-exam")?.addEventListener("click", async () => {
        syncConfig();
        if (selectedLessonIds.size === 0) {
          showToast("Vui lòng chọn ít nhất 1 bài học ở Bước 1.", "error");
          return;
        }
        examGenerating = true;
        examResult = null;
        render();
        try {
          const res = await api.adminGenerateExam({
            selected_lesson_ids: Array.from(selectedLessonIds),
            matrix,
            exam_count: examConfig.exam_count,
            exam_codes: examConfig.exam_codes,
            title: examConfig.exam_period,
            exam_period: examConfig.exam_period,
            school_name: examConfig.school_name,
            school_year: examConfig.school_year,
            subject: examConfig.subject,
            duration_minutes: examConfig.duration_minutes,
          });
          examResult = { job_id: res.job_id, summary: res.summary };
          showToast(`Đã trộn thành công ${res.summary.exam_count} mã đề!`, "success");
        } catch (err) {
          showToast(err.message, "error");
        } finally {
          examGenerating = false;
          render();
        }
      });
    }

    // ---- CONTENT STUDIO EVENTS ----
    if (subtab === "content") {
      container.querySelectorAll("[data-csub]").forEach((btn) => {
        btn.addEventListener("click", () => {
          contentSubMode = btn.dataset.csub;
          clientCache.setTeacherData({ contentSubMode });
          onSubRouteChange?.({ subtab, contentSubMode, examMixerMode });
          render();
        });
      });

      container.querySelector("#admin-new-qtype")?.addEventListener("change", (e) => {
        newQuestionType = e.target.value;
        render();
      });

      container.querySelector("#admin-add-question-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const lessonId = fd.get("lesson_id");
        const lsObj = (activeTopic.lessons || []).find((l) => l.id === lessonId);
        const qType = fd.get("q_type");
        const level = fd.get("cognitive_level") || "thong_hieu";
        const qText = String(fd.get("question") || "").trim();
        const explanation = String(fd.get("explanation") || "").trim();
        const uid = `${activeTopic.id}-${qType}-${Date.now()}`;

        activeTopic.review = activeTopic.review || { mcq: [], true_false: [], short_answer: [] };
        if (qType === "mcq") {
          activeTopic.review.mcq.unshift({
            id: uid,
            lesson_id: lessonId,
            lesson: lsObj ? lsObj.number : "",
            cognitive_level: level,
            question: qText,
            options: [fd.get("opt_a"), fd.get("opt_b"), fd.get("opt_c"), fd.get("opt_d")].map((x) => String(x || "").trim()),
            correct_index: Number(fd.get("correct_index") || 0),
            answer_key_ready: true,
            explanation,
          });
        } else if (qType === "true_false") {
          activeTopic.review.true_false.unshift({
            id: uid,
            lesson_id: lessonId,
            lesson: lsObj ? lsObj.number : "",
            cognitive_level: level,
            stem: qText,
            statements: ["a", "b", "c", "d"].map((k) => ({
              key: k,
              text: String(fd.get(`tf_${k}`) || "").trim(),
              answer: fd.get(`tf_${k}_ans`) === "true",
              explanation: "",
            })),
            answer_key_ready: true,
            explanation,
          });
        } else {
          const saAns = String(fd.get("sa_answer") || "").trim().replace(/\./g, ",").slice(0, 4);
          activeTopic.review.short_answer.unshift({
            id: uid,
            lesson_id: lessonId,
            lesson: lsObj ? lsObj.number : "",
            cognitive_level: level,
            question: qText,
            accepted_answers: [saAns],
            answer_key_ready: Boolean(saAns),
            explanation,
          });
        }

        try {
          const res = await api.updateTopic(activeTopic.id, activeTopic);
          activeTopic = res.topic;
          onTopicUpdated(res.topic);
          examPool = null; // Force refresh pool next time
          clientCache.setTeacherData({ examPool: null });
          e.target.reset();
          showToast("Đã thêm câu hỏi mới vào ngân hàng!", "success");
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      container.querySelector("#admin-edit-lesson-select")?.addEventListener("change", (e) => {
        editLessonId = e.target.value;
        render();
      });

      container.querySelector("#admin-lesson-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const number = String(fd.get("lesson_number") || "").trim();
        const title = String(fd.get("lesson_title") || "").trim();
        const rawBody = String(fd.get("lesson_body") || "").trim();

        // Chuyển văn bản thành các sections với blocks chuẩn
        const sections = [];
        let curSec = { heading: "Nội dung trọng tâm", blocks: [] };
        rawBody.split(/\r?\n/).forEach((line) => {
          const t = line.trim();
          if (!t) return;
          if (t.startsWith("## ")) {
            if (curSec.blocks.length) sections.push(curSec);
            curSec = { heading: t.slice(3).trim(), blocks: [] };
          } else {
            curSec.blocks.push({ type: "paragraph", text: t, is_bold: false });
          }
        });
        if (curSec.blocks.length || !sections.length) sections.push(curSec);

        activeTopic.lessons = activeTopic.lessons || [];
        const existingIdx = activeTopic.lessons.findIndex((l) => l.id === editLessonId);
        if (existingIdx >= 0) {
          activeTopic.lessons[existingIdx] = {
            ...activeTopic.lessons[existingIdx],
            number,
            title,
            sections,
          };
        } else {
          const newId = `${activeTopic.id}-bai-${activeTopic.lessons.length + 1}-${Date.now().toString().slice(-3)}`;
          activeTopic.lessons.push({
            id: newId,
            number,
            title,
            sections,
          });
          editLessonId = newId;
        }

        try {
          const res = await api.updateTopic(activeTopic.id, activeTopic);
          activeTopic = res.topic;
          onTopicUpdated(res.topic);
          examPool = null;
          clientCache.setTeacherData({ examPool: null });
          showToast("Đã lưu nội dung bài học Lý thuyết!", "success");
          render();
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      container.querySelector("#btn-clear-cache")?.addEventListener("click", async () => {
        cacheClearing = true;
        render();
        try {
          const res = await api.cacheClear();
          cacheInfo = res.cache || cacheInfo;
          examPool = null;
          clientCache.invalidateTopic("");
          clientCache.setTeacherData({ cacheInfo, examPool: null });
          showToast(res.message || "Đã làm mới toàn bộ Cache!", "success");
        } catch (err) {
          showToast(err.message, "error");
        } finally {
          cacheClearing = false;
          render();
        }
      });

      const syncNewTopicMeta = () => {
        const ordVal = parseInt(container.querySelector("#new-topic-order")?.value || "", 10);
        if (!Number.isNaN(ordVal) && ordVal > 0) newTopicDraft.order_index = ordVal;
        const titleEl = container.querySelector("#new-topic-title");
        if (titleEl) newTopicDraft.title = titleEl.value.trim();
        const subEl = container.querySelector("#new-topic-subtitle");
        if (subEl) newTopicDraft.subtitle = subEl.value.trim();
      };

      const buildFinalDraftTopic = () => {
        syncNewTopicMeta();
        if (!newTopicDraft.preview?.extracted) return null;
        const cloned = JSON.parse(JSON.stringify(newTopicDraft.preview.extracted));
        cloned.order_index = newTopicDraft.order_index || cloned.order_index || 5;
        if (newTopicDraft.title) cloned.title = newTopicDraft.title;
        if (newTopicDraft.subtitle) cloned.subtitle = newTopicDraft.subtitle;
        return cloned;
      };

      const doPublishNewTopic = async (topicPayload) => {
        newTopicDraft.publishing = true;
        render();
        try {
          const res = await api.publishNewTopic({ topic: topicPayload });
          examPool = null;
          newTopicDraft.file = null;
          newTopicDraft.preview = null;
          newTopicDraft.title = "";
          newTopicDraft.subtitle = "";
          answerPdfReport = null;
          showToast(res.message || `Đã xuất bản "${res.topic.title}"!`, "success");
          await onTopicsReload(res.topic.id, { changedTopicId: res.topic.id });
        } catch (err) {
          showToast(err.message, "error");
          throw err;
        } finally {
          newTopicDraft.publishing = false;
          render();
        }
      };

      container.querySelector("#new-topic-file-input")?.addEventListener("change", async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const prevDraftId = newTopicDraft.preview?.extracted?.id;
        if (prevDraftId) {
          api.cleanupDraftTopic(prevDraftId).catch(() => {});
        }
        syncNewTopicMeta();
        newTopicDraft.file = file;
        newTopicDraft.loading = true;
        newTopicDraft.preview = null;
        render();
        try {
          const txtEl = container.querySelector("#new-topic-upload-text");
          const barEl = container.querySelector("#new-topic-upload-bar");
          const slimRes = await slimDocxFile(file, (msg) => {
            if (txtEl) txtEl.textContent = msg;
            if (barEl) barEl.style.width = "10%";
          });
          const uploadFile = slimRes.file || file;
          const updateProgressUi = (p) => {
            if (p.phase === "uploading") {
              const mbDone = (p.loaded / (1024 * 1024)).toFixed(1);
              const mbTotal = (p.total / (1024 * 1024)).toFixed(1);
              if (txtEl) txtEl.textContent = `Đang tải file lên: ${p.percent}% (${mbDone} / ${mbTotal} MB)...`;
              if (barEl) barEl.style.width = `${Math.max(10, p.percent)}%`;
            } else {
              if (txtEl) txtEl.textContent = "Đã tải lên 100% — Máy chủ đang trích xuất bài học, hình ảnh & câu hỏi...";
              if (barEl) barEl.style.width = "100%";
            }
          };
          const res = await api.previewNewTopicFile(uploadFile, {
            order_index: newTopicDraft.order_index,
            title: newTopicDraft.title,
            subtitle: newTopicDraft.subtitle,
            onProgress: updateProgressUi,
          });
          newTopicDraft.preview = res.preview;
          answerPdfReport = res.preview?.answer_pdf_report || null;
          newTopicDraft.order_index = res.order_index || newTopicDraft.order_index;
          if (!newTopicDraft.title && res.preview?.extracted?.title) {
            newTopicDraft.title = res.preview.extracted.title;
          }
          if (!newTopicDraft.subtitle && res.preview?.extracted?.subtitle) {
            newTopicDraft.subtitle = res.preview.extracted.subtitle;
          }
          showToast(`Đã trích xuất xong "${file.name}". Bấm "Xem trước" hoặc "Cập nhật & Đẩy lên dữ liệu"!`, "success");
        } catch (err) {
          newTopicDraft.file = null;
          showToast(err.message, "error");
        } finally {
          e.target.value = "";
          newTopicDraft.loading = false;
          render();
        }
      });

      container.querySelector("#btn-preview-new-topic")?.addEventListener("click", () => {
        const topicPayload = buildFinalDraftTopic();
        if (!topicPayload) return;
        openTopicPreviewModal(topicPayload, {
          publishLabel: "Cập nhật & Đẩy lên dữ liệu",
          onPublish: doPublishNewTopic,
        });
      });

      container.querySelector("#new-topic-answer-pdf-input")?.addEventListener("change", async (e) => {
        const pdfFile = e.target.files?.[0];
        if (!pdfFile || !newTopicDraft.preview?.extracted) return;
        answerPdfApplying = true;
        render();
        try {
          const b64 = await fileToBase64(pdfFile);
          const res = await api.applyAnswerPdfToDraftTopic({
            topic: newTopicDraft.preview.extracted,
            pdf_filename: pdfFile.name,
            pdf_base64: b64,
          });
          if (res.topic) {
            newTopicDraft.preview.extracted = res.topic;
          }
          if (res.keyed_counts && newTopicDraft.preview.stats) {
            newTopicDraft.preview.stats.mcq_keyed = res.keyed_counts.mcq_keyed;
            newTopicDraft.preview.stats.true_false_keyed = res.keyed_counts.true_false_keyed;
            newTopicDraft.preview.stats.short_answer_keyed = res.keyed_counts.short_answer_keyed;
          }
          answerPdfReport = res.report || null;
          showToast(res.message || "Đã đối chiếu đáp án từ file PDF!", "success");
        } catch (err) {
          showToast(err.message, "error");
        } finally {
          e.target.value = "";
          answerPdfApplying = false;
          render();
        }
      });

      container.querySelector("#btn-publish-new-topic")?.addEventListener("click", async () => {
        const topicPayload = buildFinalDraftTopic();
        if (!topicPayload) return;
        await doPublishNewTopic(topicPayload);
      });

      container.querySelector("#btn-reset-new-topic")?.addEventListener("click", () => {
        const draftId = newTopicDraft.preview?.extracted?.id;
        if (draftId) {
          api.cleanupDraftTopic(draftId).catch(() => {});
        }
        newTopicDraft.file = null;
        newTopicDraft.preview = null;
        newTopicDraft.title = "";
        newTopicDraft.subtitle = "";
        answerPdfReport = null;
        render();
      });

      container.querySelectorAll("[data-open-topic]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const tid = btn.dataset.openTopic;
          if (!tid) return;
          if (onSelectTopic) {
            await onSelectTopic(tid);
          }
        });
      });

      container.querySelectorAll("[data-edit-topic-meta]").forEach((btn) => {
        btn.addEventListener("click", () => {
          editingTopicId = btn.dataset.editTopicMeta || "";
          editingTopicTitle = btn.dataset.editTopicTitle || "";
          editingTopicSubtitle = btn.dataset.editTopicSubtitle || "";
          render();
          const inp = container.querySelector("#edit-topic-title-input");
          if (inp) {
            inp.focus();
            inp.setSelectionRange(inp.value.length, inp.value.length);
          }
        });
      });

      container.querySelector("[data-cancel-topic-meta]")?.addEventListener("click", () => {
        editingTopicId = "";
        editingTopicTitle = "";
        editingTopicSubtitle = "";
        render();
      });

      container.querySelectorAll("[data-save-topic-meta]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const tid = btn.dataset.saveTopicMeta;
          const newTitle = (container.querySelector("#edit-topic-title-input")?.value || "").trim();
          const newSubtitle = (container.querySelector("#edit-topic-subtitle-input")?.value || "").trim();
          if (!newTitle) {
            showToast("Vui lòng nhập tên Chủ đề.", "error");
            return;
          }
          savingTopicMetaId = tid;
          render();
          try {
            const res = await api.updateTopicMeta(tid, { title: newTitle, subtitle: newSubtitle });
            clientCache.invalidateTopic(tid);
            clientCache.invalidateTeacherData();
            editingTopicId = "";
            editingTopicTitle = "";
            editingTopicSubtitle = "";
            showToast(res.message || `Đã đổi tên Chủ đề thành "${newTitle}".`, "success");
            await onTopicsReload(activeTopic?.id || tid);
          } catch (err) {
            showToast(err.message, "error");
          } finally {
            savingTopicMetaId = "";
            render();
          }
        });
      });

      container.querySelectorAll("[data-delete-topic]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const tid = btn.dataset.deleteTopic;
          const title = btn.dataset.deleteTopicTitle || tid;
          if (!tid || deletingTopicId) return;
          if (topicsList.length <= 1) {
            showToast("Không thể xoá Chủ đề cuối cùng của hệ thống.", "error");
            return;
          }
          if (!window.confirm(`Xác nhận xoá "${title}"?\nToàn bộ bài học và câu hỏi thuộc chủ đề này sẽ bị xoá khỏi hệ thống.`)) {
            return;
          }
          deletingTopicId = tid;
          render();
          try {
            const res = await api.deleteTopic(tid);
            examPool = null;
            clientCache.invalidateTopic(tid);
            clientCache.invalidateTeacherData();
            const remaining = topicsList.filter((x) => x.id !== tid);
            const nextTopicId = tid === activeTopic?.id ? remaining[0]?.id || "" : activeTopic?.id || remaining[0]?.id || "";
            showToast(res.message || `Đã xoá "${title}".`, "success");
            await onTopicsReload(nextTopicId, { deletedTopicId: tid });
          } catch (err) {
            showToast(err.message, "error");
          } finally {
            deletingTopicId = "";
            render();
          }
        });
      });

      container.querySelector("#btn-create-empty-topic")?.addEventListener("click", async () => {
        syncNewTopicMeta();
        if (!newTopicDraft.title) {
          showToast("Vui lòng nhập Tên Chủ đề trước khi tạo Chủ đề trống.", "error");
          return;
        }
        try {
          const res = await api.createTopic({
            title: newTopicDraft.title,
            subtitle: newTopicDraft.subtitle,
            order_index: newTopicDraft.order_index || 5,
          });
          examPool = null;
          newTopicDraft.title = "";
          newTopicDraft.subtitle = "";
          showToast(`Đã tạo chủ đề "${res.topic.title}"!`, "success");
          await onTopicsReload(res.topic.id, { changedTopicId: res.topic.id });
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      if (contentSubMode === "youtube") {
        mountYoutubeLibrary(container.querySelector("#teacher-yt-mount"), activeTopic, {
          canManage: true,
          onTopicUpdated,
          showToast,
        });
      }

      if (contentSubMode === "import") {
        const applyDocImport = async () => {
          if (!importState.file) return;
          importState.loading = true;
          render();
          try {
            const res = await api.importTopicFile(activeTopic.id, importState.file, {
              preview_only: false,
              sections: importState.sections,
              replace_review: importState.replaceReview,
            });
            activeTopic = res.topic;
            onTopicUpdated(res.topic);
            examPool = null;
            clientCache.invalidateTeacherData();
            showToast(res.message || "Đã cập nhật nội dung chủ đề.", "success");
          } catch (err) {
            showToast(err.message, "error");
          } finally {
            importState.loading = false;
            render();
          }
        };

        container.querySelectorAll("[data-imp-sec]").forEach((cb) => {
          cb.addEventListener("change", () => {
            importState.sections[cb.dataset.impSec] = cb.checked;
          });
        });
        container.querySelector("#imp-replace-review")?.addEventListener("change", (e) => {
          importState.replaceReview = e.target.checked;
        });
        container.querySelector("#doc-import-input")?.addEventListener("change", async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          importState.file = file;
          importState.loading = true;
          importState.preview = null;
          render();
          try {
            const txtEl = container.querySelector("#doc-import-upload-text");
            const barEl = container.querySelector("#doc-import-upload-bar");
            const slimRes = await slimDocxFile(file, (msg) => {
              if (txtEl) txtEl.textContent = msg;
              if (barEl) barEl.style.width = "10%";
            });
            const uploadFile = slimRes.file || file;
            importState.file = uploadFile;
            const updateDocProgressUi = (p) => {
              if (p.phase === "uploading") {
                const mbDone = (p.loaded / (1024 * 1024)).toFixed(1);
                const mbTotal = (p.total / (1024 * 1024)).toFixed(1);
                if (txtEl) txtEl.textContent = `Đang tải file lên: ${p.percent}% (${mbDone} / ${mbTotal} MB)...`;
                if (barEl) barEl.style.width = `${Math.max(10, p.percent)}%`;
              } else {
                if (txtEl) txtEl.textContent = "Đã tải lên 100% — Máy chủ đang phân tích tài liệu...";
                if (barEl) barEl.style.width = "100%";
              }
            };
            const res = await api.importTopicFile(activeTopic.id, uploadFile, {
              preview_only: true,
              onProgress: updateDocProgressUi,
            });
            importState.preview = res.preview;
            showToast(`Đã đọc xong "${file.name}".`, "success");
          } catch (err) {
            importState.file = null;
            showToast(err.message, "error");
          } finally {
            e.target.value = "";
            importState.loading = false;
            render();
          }
        });
        container.querySelector("#btn-preview-doc-import")?.addEventListener("click", () => {
          if (!importState.preview?.extracted) return;
          openTopicPreviewModal(importState.preview.extracted, {
            publishLabel: "Cập nhật vào Chủ đề hiện tại",
            onPublish: applyDocImport,
          });
        });
        container.querySelector("#btn-apply-doc-import")?.addEventListener("click", applyDocImport);
      }
    }
  }

  render();
  loadOverview();
  if (subtab === "exam_mixer" && examMixerMode === "word") {
    ensureSampleExamsLoaded();
  }
}
