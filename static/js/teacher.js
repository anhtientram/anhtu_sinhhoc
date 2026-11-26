// Bảng điều khiển Quản trị viên (Giáo viên):
// - Nhật ký Vào/Rời lớp & Lịch sử đăng nhập (đếm số lần truy cập từng học sinh)
// - Trộn đề trắc nghiệm theo Ma trận 3x3 (chọn nhiều bài trong nhiều chủ đề, xuất Word .docx & Excel .xlsx)
// - Chỉnh sửa & Thêm nội dung mới (Chủ đề, Bài học Lý thuyết, Câu hỏi mới, Video YouTube, Nhập file Word)
// - Kết quả Ôn tập & Danh sách Thành viên

import { api, clientCache, formatDateTimeVN, formatDuration, withBase } from "./api.js";
import { slimDocxFile } from "./docx_slim.js";
import { escapeHtml } from "./format.js";
import { openTopicPreviewModal } from "./topic_preview.js";
import { mountYoutubeLibrary } from "./youtube_videos.js";

export function mountTeacherDashboard(container, activeTopic, onTopicUpdated, showToast, opts = {}) {
  const onTopicsReload = opts.onTopicsReload || (async () => {});
  const onSelectTopic = opts.onSelectTopic || null;
  const topicsList = Array.isArray(opts.topicsList) ? opts.topicsList : [];
  const currentUser = opts.currentUser || { role: "teacher" };
  const isAdmin = currentUser.role === "admin";
  const cachedTeacher = clientCache.getTeacherData();

  let subtab = cachedTeacher.subtab || "members"; // 'members' | 'attendance' | 'exam_mixer' | 'content' | 'scores' | 'pw_alerts'
  if (!isAdmin && (subtab === "content" || subtab === "pw_alerts")) {
    subtab = "members";
  }
  let overview = cachedTeacher.overview || null;
  let classFilter = "";
  let searchFilter = "";
  let studentExcelResult = null;
  let studentExcelLoading = false;

  // Trạng thái Trộn đề Ma trận 3x3
  let examPool = cachedTeacher.examPool || null; // [{id, title, lessons: [{id, number, title, counts}]}]
  let selectedLessonIds = new Set();
  let matrix = {
    mcq: { nhan_biet: 8, thong_hieu: 6, van_dung: 4 },
    true_false: { nhan_biet: 1, thong_hieu: 2, van_dung: 1 },
    short_answer: { nhan_biet: 1, thong_hieu: 2, van_dung: 3 },
  };
  let examConfig = {
    title: "ĐỀ KIỂM TRA ĐỊNH KÌ MÔN SINH HỌC 12",
    school_name: "TRƯỜNG THPT",
    duration_minutes: 50,
    exam_count: 4,
    exam_codes: "101, 102, 103, 104",
  };
  let examGenerating = false;
  let examResult = null; // { job_id, summary }

  // Trạng thái Chỉnh sửa / Thêm nội dung
  let contentSubMode = cachedTeacher.contentSubMode || "add_topic"; // 'add_topic' | 'add_question' | 'edit_lesson' | 'youtube' | 'import'
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
          <button class="seg-btn ${subtab === "exam_mixer" ? "active" : ""}" data-tsub="exam_mixer">Trộn đề (Ma trận)</button>
          ${
            isAdmin
              ? `<button class="seg-btn ${subtab === "content" ? "active" : ""}" data-tsub="content">Chỉnh sửa &amp; Thêm nội dung</button>`
              : ""
          }
          <button class="seg-btn ${subtab === "scores" ? "active" : ""}" data-tsub="scores">Kết quả Ôn tập</button>
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
    `;

    container.querySelectorAll("[data-tsub]").forEach((btn) => {
      btn.addEventListener("click", () => {
        subtab = btn.dataset.tsub;
        clientCache.setTeacherData({ subtab });
        if (subtab === "exam_mixer" && !examPool) {
          render();
          ensureExamPoolLoaded();
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

  // ================== 2. TRỘN ĐỀ TRẮC NGHIỆM THEO MA TRẬN 3x3 ==================
  function renderExamMixerView() {
    if (!examPool) {
      return `<div class="card" style="text-align:center;padding:36px;"><div class="spinner" style="margin:0 auto 10px;"></div>Đang tải ngân hàng câu hỏi các chủ đề...</div>`;
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

        <!-- Bước 3: Số lượng đề, Mã đề & Xuất Word/Excel -->
        <div class="card">
          <h3 class="card-title">Bước 3. Cấu hình Đề trộn &amp; Xuất file Word (.docx) + Đáp án Excel (.xlsx)</h3>
          <div class="form-row-2">
            <div class="form-group">
              <label>Tiêu đề đề kiểm tra</label>
              <input class="form-control" id="ex-title" value="${escapeHtml(examConfig.title)}" />
            </div>
            <div class="form-group">
              <label>Tên trường hiển thị trên đề</label>
              <input class="form-control" id="ex-school" value="${escapeHtml(examConfig.school_name)}" />
            </div>
          </div>

          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;">
            <div class="form-group">
              <label>Thời gian làm bài (phút)</label>
              <input type="number" min="5" max="180" class="form-control" id="ex-duration" value="${examConfig.duration_minutes}" />
            </div>
            <div class="form-group">
              <label>Số lượng đề trộn *</label>
              <input type="number" min="1" max="30" class="form-control" id="ex-count" value="${examConfig.exam_count}" />
            </div>
            <div class="form-group" style="grid-column:span 2;">
              <label>Mã đề (tự nhập, ngăn cách bằng dấu phẩy; nếu nhập mã đầu hệ thống tự đánh tiếp)</label>
              <input class="form-control" id="ex-codes" value="${escapeHtml(examConfig.exam_codes)}" placeholder="VD: 101, 102, 103, 104" />
            </div>
          </div>

          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:8px;">
            <button type="button" class="btn btn-primary btn-lg" id="btn-generate-exam" ${examGenerating ? "disabled" : ""}>
              ${examGenerating ? "Đang trộn đề & tạo file..." : "Tạo & Trộn đề thi ngay"}
            </button>
          </div>

          ${
            examResult
              ? `
                <div style="margin-top:16px;padding:16px;border-radius:10px;border:1px solid var(--primary-border);background:var(--surface-tint);">
                  <div style="display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;">
                    <div>
                      <span class="pill pill-green">Đã trộn xong ${examResult.summary.exam_count} đề</span>
                      <div style="font-weight:700;margin-top:6px;">
                        Mã đề: ${escapeHtml((examResult.summary.exam_codes || []).join(", "))}
                      </div>
                      <div style="font-size:0.84rem;color:var(--text-secondary);margin-top:2px;">
                        Phần I: ${examResult.summary.mcq_count} câu · Phần II: ${examResult.summary.true_false_count} câu · Phần III: ${examResult.summary.short_answer_count} câu · Tổng thang điểm: <strong>${examResult.summary.max_score} điểm</strong>
                      </div>
                    </div>
                    <div style="display:flex;gap:10px;flex-wrap:wrap;">
                      <a class="btn btn-primary" href="${api.adminExamDownloadUrl(examResult.job_id, "docx")}" target="_blank" id="btn-dl-exam-docx">
                        Tải Đề trộn (Word .docx)
                      </a>
                      <a class="btn btn-soft" href="${api.adminExamDownloadUrl(examResult.job_id, "xlsx")}" target="_blank" id="btn-dl-exam-xlsx">
                        Tải Đáp án (Excel .xlsx)
                      </a>
                    </div>
                  </div>
                </div>
              `
              : ""
          }
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
                                  Ngân hàng ôn tập: <strong>${ds.mcq_count}</strong> câu 4 đáp án · <strong>${ds.true_false_count}</strong> câu Đúng/Sai · <strong>${ds.short_answer_count}</strong> câu Trả lời ngắn
                                </div>
                              </div>
                            </div>

                            <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                              <button type="button" class="btn btn-soft" id="btn-preview-new-topic">
                                Xem trước nội dung &amp; giao diện
                              </button>
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

  // ================== 4. KẾT QUẢ ÔN TẬP ==================
  function renderScoresView(classes) {
    const attempts = (overview.attempts || []).filter((a) => !classFilter || a.class_name === classFilter);
    const typeLabel = { mcq: "3.1 Trắc nghiệm 4 đáp án", true_false: "3.2 Đúng / Sai", short_answer: "3.3 Trả lời ngắn", combined: "Đề tổng hợp" };

    return `
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px;">
          <h3 class="card-title" style="margin:0;">Bảng điểm Hệ thống Ôn tập</h3>
          <select id="att-class-filter" class="form-control form-control-sm" style="width:auto;">
            <option value="">Tất cả các lớp</option>
            ${classes.map((c) => `<option value="${c}" ${classFilter === c ? "selected" : ""}>Lớp ${escapeHtml(c)}</option>`).join("")}
          </select>
        </div>
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>Học sinh</th><th>Lớp</th><th>Phần ôn tập</th><th>Điểm</th><th>Đúng / Tổng</th><th>Thời gian</th><th>Nộp lúc</th></tr>
            </thead>
            <tbody>
              ${
                attempts.length
                  ? attempts
                      .map((a) => {
                        const pct = a.max_score > 0 ? Math.round((a.score / a.max_score) * 100) : 0;
                        const pcls = pct >= 80 ? "pill-green" : pct >= 50 ? "pill-amber" : "pill-red";
                        return `
                          <tr>
                            <td><strong>${escapeHtml(a.full_name)}</strong></td>
                            <td>${escapeHtml(a.class_name || "—")}</td>
                            <td>${typeLabel[a.quiz_type] || a.quiz_type}</td>
                            <td><span class="pill ${pcls}">${a.score} / ${a.max_score} (${pct}%)</span></td>
                            <td>${a.correct_count} / ${a.total_questions}</td>
                            <td>${formatDuration(a.duration_seconds)}</td>
                            <td>${formatDateTimeVN(a.submitted_at)}</td>
                          </tr>
                        `;
                      })
                      .join("")
                  : `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:22px;">Chưa có bài nộp.</td></tr>`
              }
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // ================== 5. QUẢN LÝ THÀNH VIÊN (GV + HS) & THỐNG KÊ TRUY CẬP ==================
  function renderMembersView() {
    const students = overview.students || [];
    const teachers = overview.teachers || [];
    return `
      <div style="display:flex;flex-direction:column;gap:18px;">
        ${
          isAdmin
            ? `
              <!-- CHỈ QUẢN TRỊ VIÊN: THÊM & XOÁ GIÁO VIÊN -->
              <div class="card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
                  <div>
                    <h3 class="card-title" style="margin:0 0 2px;">Quản lý Giáo viên sử dụng (${teachers.length})</h3>
                    <p style="margin:0;font-size:0.83rem;color:var(--text-muted);">
                      Chỉ Quản trị viên có quyền thêm hoặc xoá Giáo viên. Giáo viên được cấp tài khoản sẽ bắt buộc cập nhật Họ tên, Trường, SĐT và đổi mật khẩu mới ngay khi đăng nhập lần đầu.
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

                <div class="data-table-wrap">
                  <table class="data-table">
                    <thead>
                      <tr>
                        <th>Họ và tên GV</th>
                        <th>Tên đăng nhập</th>
                        <th>Trường</th>
                        <th>Số điện thoại</th>
                        <th>Trạng thái kích hoạt</th>
                        <th>Thao tác</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${
                        teachers.length
                          ? teachers
                              .map(
                                (t) => `
                                <tr>
                                  <td><strong>${escapeHtml(t.full_name)}</strong></td>
                                  <td>@${escapeHtml(t.username)}</td>
                                  <td>${escapeHtml(t.school_name || "Chưa cập nhật")}</td>
                                  <td>${escapeHtml(t.phone || "Chưa cập nhật")}</td>
                                  <td>
                                    ${
                                      t.must_change_password
                                        ? `<span class="pill pill-amber">Chờ đổi MK lần đầu</span>`
                                        : `<span class="pill pill-green">Đã kích hoạt</span>`
                                    }
                                  </td>
                                  <td>
                                    <button type="button" class="btn btn-danger btn-sm" data-delete-user="${t.id}" data-delete-name="${escapeHtml(t.username)}">Xoá GV</button>
                                  </td>
                                </tr>
                              `
                              )
                              .join("")
                          : `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:18px;">Chưa có Giáo viên nào được thêm.</td></tr>`
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
          <h3 class="card-title">Danh sách Học sinh &amp; Thống kê số lần truy cập (${students.length})</h3>
          <div class="data-table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Họ và tên / Đăng nhập</th>
                  <th>Trường / Lớp</th>
                  <th>Số điện thoại</th>
                  <th>Số lần truy cập</th>
                  <th>Đăng nhập gần nhất</th>
                  <th>Thời lượng học</th>
                  <th>Trạng thái</th>
                  ${isAdmin ? `<th>Thao tác</th>` : ""}
                </tr>
              </thead>
              <tbody>
                ${
                  students.length
                    ? students
                        .map(
                          (s) => `
                          <tr>
                            <td><strong>${escapeHtml(s.full_name)}</strong><br/><small style="color:var(--text-muted)">@${escapeHtml(s.username)}</small></td>
                            <td>${escapeHtml(s.school_name || "Chưa cập nhật")}<br/><small style="color:var(--text-muted)">${s.class_name ? `Lớp ${escapeHtml(s.class_name)}` : "Chưa nhập lớp"}</small></td>
                            <td>${escapeHtml(s.phone || "—")}</td>
                            <td><span class="pill pill-primary">${s.login_count || 0} lần</span></td>
                            <td>${formatDateTimeVN(s.last_login)}</td>
                            <td><strong>${formatDuration(s.total_seconds)}</strong><br/><small style="color:var(--text-muted)">${s.session_count} phiên</small></td>
                            <td>
                              ${
                                s.must_change_password
                                  ? `<span class="pill pill-amber">Chờ đổi MK lần đầu</span>`
                                  : s.is_online
                                  ? `<span class="pill pill-green">Đang học</span>`
                                  : `<span class="pill pill-muted">Ngoại tuyến</span>`
                              }
                            </td>
                            ${
                              isAdmin
                                ? `<td><button type="button" class="btn btn-ghost btn-sm" style="color:var(--red);" data-delete-user="${s.id}" data-delete-name="${escapeHtml(s.username)}">Xoá</button></td>`
                                : ""
                            }
                          </tr>
                        `
                        )
                        .join("")
                    : `<tr><td colspan="${isAdmin ? 8 : 7}" style="text-align:center;color:var(--text-muted);padding:20px;">Chưa có tài khoản Học sinh nào. Hãy thêm bằng thủ công hoặc file Excel ở trên.</td></tr>`
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
  function bindSubviewEvents() {
    // ---- MEMBERS & PASSWORD ALERTS EVENTS ----
    if (subtab === "members") {
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

      container.querySelectorAll("[data-delete-user]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const uname = btn.dataset.deleteName;
          if (!window.confirm(`Xác nhận xoá tài khoản "${uname}" khỏi hệ thống?`)) return;
          try {
            const res = await api.adminDeleteUser(btn.dataset.deleteUser);
            showToast(res.message || "Đã xoá tài khoản.", "success");
            await loadOverview(true);
          } catch (err) {
            showToast(err.message, "error");
          }
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
    container.querySelector("#att-search")?.addEventListener("input", (e) => {
      searchFilter = e.target.value;
      render();
      const el = container.querySelector("#att-search");
      if (el) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    });

    // ---- EXAM MIXER EVENTS ----
    if (subtab === "exam_mixer" && examPool) {
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
        examConfig.title = container.querySelector("#ex-title")?.value || examConfig.title;
        examConfig.school_name = container.querySelector("#ex-school")?.value || examConfig.school_name;
        examConfig.duration_minutes = Math.max(5, parseInt(container.querySelector("#ex-duration")?.value || "50", 10) || 50);
        examConfig.exam_count = Math.max(1, Math.min(30, parseInt(container.querySelector("#ex-count")?.value || "1", 10) || 1));
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
            title: examConfig.title,
            school_name: examConfig.school_name,
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
}
