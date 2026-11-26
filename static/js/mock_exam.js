// PHÒNG LUYỆN TẬP — THI THỬ TỐT NGHIỆP THPT (SINH HỌC 12 - GDPT 2018)
// Hỗ trợ:
//  - Upload file Word (.docx) / PDF (.pdf), tự phân tích câu hỏi, hình ảnh, đáp án
//  - Xem trước & chỉnh sửa trực tiếp từng câu hỏi + Studio làm đẹp/chau chuốt ảnh bằng HTML5 Canvas
//  - Tiêu đề mặc định: PHÒNG LUYỆN TẬP · Đề số {STT} · Thời gian: 45 phút
//  - Đồng hồ hiển thị thời gian bắt đầu, thời gian đã làm và đếm ngược 45 phút
//  - Bắt buộc hoàn thành 100% câu hỏi mới được bấm "Nộp bài"
//  - Chấm điểm tự động theo thang điểm Bộ GD&ĐT + hiển thị đáp án gợi ý chi tiết
//  - Phân quyền chặt chẽ: Quản trị viên (toàn quyền) | Giáo viên (chỉ thêm, không xoá) | Học sinh (chỉ làm bài)

import { api, formatDateTimeVN, formatDuration } from "./api.js";
import { escapeHtml, formatBioHtml } from "./format.js";

const LETTERS = ["A", "B", "C", "D"];

// ================== CANVAS IMAGE POLISHING ENGINE ==================
function loadImageFromUrl(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Không thể đọc dữ liệu ảnh."));
    img.src = src;
  });
}

function applyUnsharpMask(ctx, width, height, amount = 0.45) {
  if (amount <= 0.01) return;
  const srcData = ctx.getImageData(0, 0, width, height);
  const src = srcData.data;
  const out = new Uint8ClampedArray(src);
  const w4 = width * 4;
  // 3x3 sharpening kernel: center = 1 + 4*k, neighbors = -k
  const k = Math.min(1.0, amount * 0.65);
  for (let y = 1; y < height - 1; y++) {
    const row = y * w4;
    for (let x = 1; x < width - 1; x++) {
      const i = row + x * 4;
      for (let c = 0; c < 3; c++) {
        const center = src[i + c];
        const avg = (src[i - 4 + c] + src[i + 4 + c] + src[i - w4 + c] + src[i + w4 + c]) * 0.25;
        const val = center + (center - avg) * (k * 2.2);
        out[i + c] = val < 0 ? 0 : val > 255 ? 255 : val;
      }
    }
  }
  srcData.data.set(out);
  ctx.putImageData(srcData, 0, 0);
}

/**
 * Làm đẹp & chau chuốt hình ảnh đề thi bằng HTML5 Canvas:
 *  - Cắt viền trắng dư tự động (autoTrim) + chừa lề trắng cân đối
 *  - Khử nền xám scan / làm trong nền trắng (cleanPaper)
 *  - Cân chỉnh sáng / tương phản / độ nét (unsharp mask)
 *  - Tùy chọn xoay 90° và đóng khung học thuật gọn đẹp
 */
export async function polishImageDataUrl(srcUrl, opts = {}) {
  const {
    brightness = 1.04,
    contrast = 1.14,
    sharpness = 0.55,
    cleanPaper = true,
    grayscale = false,
    autoTrim = true,
    addFrame = true,
    rotateDeg = 0,
    maxWidth = 1100,
  } = opts;

  const img = await loadImageFromUrl(srcUrl);
  const rot = ((rotateDeg % 360) + 360) % 360;
  const swap = rot === 90 || rot === 270;
  const rawW = img.naturalWidth || img.width || 600;
  const rawH = img.naturalHeight || img.height || 400;
  const scale = rawW > maxWidth ? maxWidth / rawW : 1;
  const drawW = Math.max(20, Math.round(rawW * scale));
  const drawH = Math.max(20, Math.round(rawH * scale));
  const workW = swap ? drawH : drawW;
  const workH = swap ? drawW : drawH;

  const work = document.createElement("canvas");
  work.width = workW;
  work.height = workH;
  const wctx = work.getContext("2d", { willReadFrequently: true });
  wctx.fillStyle = "#ffffff";
  wctx.fillRect(0, 0, workW, workH);

  wctx.save();
  wctx.translate(workW / 2, workH / 2);
  wctx.rotate((rot * Math.PI) / 180);
  wctx.drawImage(img, -drawW / 2, -drawH / 2, drawW, drawH);
  wctx.restore();

  // Chỉnh màu, độ sáng, độ tương phản và làm trắng nền giấy scan
  const imgData = wctx.getImageData(0, 0, workW, workH);
  const d = imgData.data;
  const cFactor = contrast;
  const bShift = (brightness - 1) * 255;

  for (let i = 0; i < d.length; i += 4) {
    let r = (d[i] - 128) * cFactor + 128 + bShift;
    let g = (d[i + 1] - 128) * cFactor + 128 + bShift;
    let b = (d[i + 2] - 128) * cFactor + 128 + bShift;
    if (grayscale) {
      const lum = 0.299 * r + 0.587 * g + 0.114 * b;
      r = g = b = lum;
    }
    if (cleanPaper) {
      // Kéo vùng nền gần trắng/xám nhạt (scan cũ) về trắng tinh #FFFFFF
      if (r > 224 && g > 224 && b > 224) {
        r = g = b = 255;
      } else if (r < 55 && g < 55 && b < 55) {
        // Làm sâu nét chữ & đường vẽ đậm hơn một chút
        r *= 0.85;
        g *= 0.85;
        b *= 0.85;
      }
    }
    d[i] = r < 0 ? 0 : r > 255 ? 255 : r;
    d[i + 1] = g < 0 ? 0 : g > 255 ? 255 : g;
    d[i + 2] = b < 0 ? 0 : b > 255 ? 255 : b;
    d[i + 3] = 255;
  }
  wctx.putImageData(imgData, 0, 0);

  if (sharpness > 0.05) {
    applyUnsharpMask(wctx, workW, workH, sharpness);
  }

  // Tự động cắt viền trắng dư thừa
  let minX = 0, minY = 0, maxX = workW - 1, maxY = workH - 1;
  if (autoTrim) {
    const scan = wctx.getImageData(0, 0, workW, workH).data;
    let fx1 = workW, fy1 = workH, fx2 = 0, fy2 = 0;
    for (let y = 0; y < workH; y++) {
      const row = y * workW * 4;
      for (let x = 0; x < workW; x++) {
        const idx = row + x * 4;
        if (scan[idx] < 245 || scan[idx + 1] < 245 || scan[idx + 2] < 245) {
          if (x < fx1) fx1 = x;
          if (x > fx2) fx2 = x;
          if (y < fy1) fy1 = y;
          if (y > fy2) fy2 = y;
        }
      }
    }
    if (fx2 > fx1 + 12 && fy2 > fy1 + 12) {
      minX = fx1;
      minY = fy1;
      maxX = fx2;
      maxY = fy2;
    }
  }

  const cropW = maxX - minX + 1;
  const cropH = maxY - minY + 1;
  const pad = addFrame ? 16 : 8;
  const out = document.createElement("canvas");
  out.width = cropW + pad * 2;
  out.height = cropH + pad * 2;
  const octx = out.getContext("2d");
  octx.fillStyle = "#ffffff";
  octx.fillRect(0, 0, out.width, out.height);
  octx.drawImage(work, minX, minY, cropW, cropH, pad, pad, cropW, cropH);

  if (addFrame) {
    octx.strokeStyle = "#d9e2ec";
    octx.lineWidth = 2;
    octx.strokeRect(1, 1, out.width - 2, out.height - 2);
  }

  // Ưu tiên WebP hoặc JPEG chất lượng cao cho dung lượng gọn nhẹ trong DB
  let dataUrl = out.toDataURL("image/webp", 0.88);
  if (!dataUrl.startsWith("data:image/webp")) {
    dataUrl = out.toDataURL("image/jpeg", 0.9);
  }
  return dataUrl;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Không thể đọc tệp hình ảnh."));
    reader.readAsDataURL(file);
  });
}

// ================== MODULE STATE (PRESERVED ACROSS RE-RENDERS) ==================
let activeTimerInterval = null;

export function stopMockExamTimers() {
  if (activeTimerInterval) {
    clearInterval(activeTimerInterval);
    activeTimerInterval = null;
  }
}

function formatClockHMS(dateObj) {
  return dateObj.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDateDMY(dateObj) {
  return dateObj.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatScoreVN(n) {
  const num = Number(n || 0);
  return num.toFixed(2).replace(".", ",");
}

// ================== MAIN MOUNT FUNCTION ==================
export function mountMockExamSection(container, { currentUser, effectiveStudentView, showToast }) {
  stopMockExamTimers();

  const role = effectiveStudentView ? "student" : currentUser?.role || "student";
  const isAdmin = role === "admin";
  const isTeacher = role === "teacher";
  const canAdd = isAdmin || isTeacher;
  const canEditPublished = isAdmin;
  const canDelete = isAdmin;

  const st = {
    view: "lobby", // 'lobby' | 'editor' | 'taking' | 'result' | 'attempts'
    loading: true,
    exams: [],

    // Upload / Editor state
    uploading: false,
    uploadPercent: 0,
    uploadPhase: "",
    editingExamId: null, // null = creating new; number = admin editing existing
    draft: null,
    draftWarnings: [],
    editorFilter: "all", // 'all' | 'mcq' | 'true_false' | 'short_answer'
    polishingAll: false,
    savingDraft: false,

    // Taking exam state
    activeExam: null,
    startedAtIso: "",
    startedAtDate: null,
    durationSecondsLimit: 45 * 60,
    elapsedSeconds: 0,
    answers: { mcq: {}, true_false: {}, short_answer: {} },
    submitting: false,

    // Result / Review state
    resultData: null,

    // Attempts list state
    attemptsExam: null,
    attemptsList: [],
  };

  function calcDraftStats(draft) {
    const c = draft?.content || { mcq: [], true_false: [], short_answer: [] };
    const mcq = c.mcq || [];
    const tf = c.true_false || [];
    const sa = c.short_answer || [];
    const total = mcq.length + tf.length + sa.length;
    const mcqKeyed = mcq.filter((q) => q.correct_index !== null && q.correct_index !== undefined).length;
    const tfKeyed = tf.filter((q) => (q.statements || []).length > 0 && q.statements.every((s) => s.answer !== null && s.answer !== undefined)).length;
    const saKeyed = sa.filter((q) => (q.accepted_answers || []).filter(Boolean).length > 0).length;
    const imgs = [...mcq, ...tf, ...sa].reduce((acc, q) => acc + (q.images || []).length, 0);
    const maxScore = Math.round((mcq.length * 0.25 + tf.length * 1.0 + sa.length * 0.25) * 100) / 100;
    return {
      total,
      mcq: mcq.length,
      tf: tf.length,
      sa: sa.length,
      keyed: mcqKeyed + tfKeyed + saKeyed,
      imgs,
      maxScore,
    };
  }

  function calcCompletion(exam, answers) {
    const c = exam?.content || { mcq: [], true_false: [], short_answer: [] };
    const mcq = c.mcq || [];
    const tf = c.true_false || [];
    const sa = c.short_answer || [];
    let done = 0;
    const missingIds = [];

    mcq.forEach((q) => {
      const v = answers.mcq[q.id];
      if (v !== undefined && v !== null && v !== "") done += 1;
      else missingIds.push(q.id);
    });
    tf.forEach((q) => {
      const stmts = q.statements || [];
      const filled = stmts.filter((s) => answers.true_false[`${q.id}:${s.key}`] !== undefined).length;
      if (stmts.length > 0 && filled === stmts.length) done += 1;
      else missingIds.push(q.id);
    });
    sa.forEach((q) => {
      if (String(answers.short_answer[q.id] || "").trim().length > 0) done += 1;
      else missingIds.push(q.id);
    });

    const total = mcq.length + tf.length + sa.length;
    return { done, total, missingIds, isComplete: total > 0 && done === total };
  }

  async function loadExamsList() {
    st.loading = true;
    render();
    try {
      const res = await api.getMockExams();
      st.exams = res.exams || [];
    } catch (err) {
      showToast(err.message || "Không thể tải danh sách đề thi thử.", "error");
    } finally {
      st.loading = false;
      render();
    }
  }

  // ================== IMAGE STUDIO MODAL ==================
  function openImageStudioModal(qListKey, qIdx, imgIdx) {
    const q = st.draft?.content?.[qListKey]?.[qIdx];
    if (!q || !q.images?.[imgIdx]) return;
    const originalUrl = q.images[imgIdx];

    const opts = {
      brightness: 1.04,
      contrast: 1.15,
      sharpness: 0.55,
      cleanPaper: true,
      grayscale: false,
      autoTrim: true,
      addFrame: true,
      rotateDeg: 0,
    };

    const modalRoot = document.getElementById("modal-root");
    if (!modalRoot) return;

    let currentPreviewUrl = originalUrl;

    modalRoot.innerHTML = `
      <div class="modal-backdrop open" id="img-studio-backdrop" style="z-index:2000;">
        <div class="modal-dialog" style="max-width:860px;width:95vw;max-height:92vh;overflow-y:auto;">
          <div class="modal-header">
            <div>
              <h3 style="margin:0;font-size:1.08rem;">Studio làm đẹp &amp; chau chuốt hình ảnh</h3>
              <div style="font-size:0.78rem;color:var(--text-muted);margin-top:2px;">
                Tự động làm sạch nền xám scan, cắt viền thừa, tăng độ nét chuẩn sơ đồ SGK trước khi xuất bản đề thi
              </div>
            </div>
            <button type="button" class="btn btn-ghost btn-sm" id="btn-studio-close">Đóng ✕</button>
          </div>
          <div class="modal-body" style="display:flex;flex-direction:column;gap:14px;">
            <div style="display:flex;flex-wrap:wrap;gap:8px;">
              <button type="button" class="btn btn-sm btn-primary" data-preset="textbook">✨ Chuẩn SGK (Nền trắng + Nét)</button>
              <button type="button" class="btn btn-sm btn-secondary" data-preset="vivid">🎨 Sơ đồ màu sống động</button>
              <button type="button" class="btn btn-sm btn-secondary" data-preset="bw">📄 Scan đen trắng rõ nét</button>
              <button type="button" class="btn btn-sm btn-secondary" data-preset="original">↩ Ảnh gốc ban đầu</button>
              <button type="button" class="btn btn-sm btn-secondary" id="btn-studio-rotate">↻ Xoay 90°</button>
            </div>

            <div class="mock-studio-grid">
              <div class="mock-studio-preview-col">
                <div style="font-size:0.78rem;font-weight:700;color:var(--text-muted);margin-bottom:6px;">ẢNH SAU KHI CHAU CHUỐT</div>
                <div class="mock-studio-canvas-box">
                  <img id="studio-preview-img" src="${originalUrl}" alt="Xem trước ảnh" style="max-width:100%;max-height:360px;object-fit:contain;" />
                </div>
              </div>
              <div class="mock-studio-controls-col">
                <div class="form-group">
                  <label>Độ sáng: <strong id="lbl-bright">104%</strong></label>
                  <input type="range" id="rng-bright" min="80" max="135" value="104" style="width:100%;" />
                </div>
                <div class="form-group">
                  <label>Độ tương phản: <strong id="lbl-contrast">115%</strong></label>
                  <input type="range" id="rng-contrast" min="85" max="165" value="115" style="width:100%;" />
                </div>
                <div class="form-group">
                  <label>Độ sắc nét (Unsharp): <strong id="lbl-sharp">55%</strong></label>
                  <input type="range" id="rng-sharp" min="0" max="100" value="55" style="width:100%;" />
                </div>
                <label class="mock-check-row"><input type="checkbox" id="chk-clean-paper" checked /> <span>Khử nền xám / Làm trắng nền giấy scan</span></label>
                <label class="mock-check-row"><input type="checkbox" id="chk-auto-trim" checked /> <span>Tự động cắt viền trắng thừa</span></label>
                <label class="mock-check-row"><input type="checkbox" id="chk-add-frame" checked /> <span>Đóng khung học thuật sạch đẹp</span></label>
                <label class="mock-check-row"><input type="checkbox" id="chk-grayscale" /> <span>Chuyển đen trắng tương phản cao</span></label>
              </div>
            </div>
          </div>
          <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:10px;padding-top:12px;border-top:1px solid var(--border);">
            <button type="button" class="btn btn-secondary" id="btn-studio-cancel">Huỷ</button>
            <button type="button" class="btn btn-primary" id="btn-studio-apply">Áp dụng ảnh đã chau chuốt</button>
          </div>
        </div>
      </div>
    `;

    const closeModal = () => {
      modalRoot.innerHTML = "";
    };

    const syncControlsFromOpts = () => {
      document.getElementById("rng-bright").value = String(Math.round(opts.brightness * 100));
      document.getElementById("lbl-bright").textContent = `${Math.round(opts.brightness * 100)}%`;
      document.getElementById("rng-contrast").value = String(Math.round(opts.contrast * 100));
      document.getElementById("lbl-contrast").textContent = `${Math.round(opts.contrast * 100)}%`;
      document.getElementById("rng-sharp").value = String(Math.round(opts.sharpness * 100));
      document.getElementById("lbl-sharp").textContent = `${Math.round(opts.sharpness * 100)}%`;
      document.getElementById("chk-clean-paper").checked = opts.cleanPaper;
      document.getElementById("chk-auto-trim").checked = opts.autoTrim;
      document.getElementById("chk-add-frame").checked = opts.addFrame;
      document.getElementById("chk-grayscale").checked = opts.grayscale;
    };

    let renderSeq = 0;
    const updatePreview = async () => {
      const seq = ++renderSeq;
      try {
        const polished = await polishImageDataUrl(originalUrl, opts);
        if (seq !== renderSeq) return;
        currentPreviewUrl = polished;
        const imgEl = document.getElementById("studio-preview-img");
        if (imgEl) imgEl.src = polished;
      } catch (err) {
        showToast(err.message, "error");
      }
    };

    document.getElementById("btn-studio-close")?.addEventListener("click", closeModal);
    document.getElementById("btn-studio-cancel")?.addEventListener("click", closeModal);
    document.getElementById("img-studio-backdrop")?.addEventListener("click", (e) => {
      if (e.target.id === "img-studio-backdrop") closeModal();
    });

    document.querySelectorAll("[data-preset]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = btn.dataset.preset;
        if (p === "textbook") {
          Object.assign(opts, { brightness: 1.04, contrast: 1.15, sharpness: 0.55, cleanPaper: true, grayscale: false, autoTrim: true, addFrame: true });
        } else if (p === "vivid") {
          Object.assign(opts, { brightness: 1.02, contrast: 1.22, sharpness: 0.45, cleanPaper: false, grayscale: false, autoTrim: true, addFrame: true });
        } else if (p === "bw") {
          Object.assign(opts, { brightness: 1.08, contrast: 1.38, sharpness: 0.7, cleanPaper: true, grayscale: true, autoTrim: true, addFrame: true });
        } else {
          Object.assign(opts, { brightness: 1.0, contrast: 1.0, sharpness: 0, cleanPaper: false, grayscale: false, autoTrim: false, addFrame: false, rotateDeg: 0 });
        }
        syncControlsFromOpts();
        updatePreview();
      });
    });

    document.getElementById("btn-studio-rotate")?.addEventListener("click", () => {
      opts.rotateDeg = (opts.rotateDeg + 90) % 360;
      updatePreview();
    });

    const bindRange = (id, lblId, key) => {
      document.getElementById(id)?.addEventListener("input", (e) => {
        const v = Number(e.target.value);
        document.getElementById(lblId).textContent = `${v}%`;
        opts[key] = v / 100;
        updatePreview();
      });
    };
    bindRange("rng-bright", "lbl-bright", "brightness");
    bindRange("rng-contrast", "lbl-contrast", "contrast");
    bindRange("rng-sharp", "lbl-sharp", "sharpness");

    const bindCheck = (id, key) => {
      document.getElementById(id)?.addEventListener("change", (e) => {
        opts[key] = e.target.checked;
        updatePreview();
      });
    };
    bindCheck("chk-clean-paper", "cleanPaper");
    bindCheck("chk-auto-trim", "autoTrim");
    bindCheck("chk-add-frame", "addFrame");
    bindCheck("chk-grayscale", "grayscale");

    document.getElementById("btn-studio-apply")?.addEventListener("click", () => {
      q.images[imgIdx] = currentPreviewUrl;
      closeModal();
      showToast("Đã chau chuốt và cập nhật hình ảnh!", "success");
      render();
    });

    updatePreview();
  }

  // ================== VIEW 1: LOBBY (PHÒNG LUYỆN TẬP) ==================
  function renderLobby() {
    const roleBanner = isAdmin
      ? `<span class="pill pill-primary">Quản trị viên · Toàn quyền thêm, sửa, xoá đề &amp; xem điểm</span>`
      : isTeacher
        ? `<span class="pill pill-amber">Giáo viên · Quyền tải lên &amp; thêm đề mới (không xoá đề đã tạo)</span>`
        : `<span class="pill pill-emerald">Học sinh · Chọn đề thi &amp; làm bài 45 phút</span>`;

    container.innerHTML = `
      <div class="mock-hero-card">
        <div class="mock-hero-top">
          <div>
            <div class="mock-hero-kicker">PHÒNG LUYỆN TẬP · SINH HỌC 12 (CT GDPT 2018)</div>
            <h1 class="mock-hero-title">Thi thử Tốt nghiệp THPT</h1>
            <p class="mock-hero-sub">
              Mô phỏng chuẩn cấu trúc đề thi Tốt nghiệp THPT mới (3 phần: Trắc nghiệm 4 phương án, Đúng/Sai 4 ý lũy tiến, Trả lời ngắn) · Thời gian làm bài <strong>45 phút</strong> · Chấm điểm &amp; hiển thị đáp án gợi ý ngay sau khi hoàn tất.
            </p>
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:8px;">
            ${roleBanner}
            <div style="font-size:0.8rem;color:var(--text-muted);">
              Tổng số đề hiện có: <strong>${st.exams.length}</strong> đề
            </div>
          </div>
        </div>

        ${
          canAdd
            ? `
              <div class="mock-upload-bar">
                <div class="mock-upload-info">
                  <div style="font-weight:700;font-size:0.95rem;color:var(--text);">
                    Tải lên đề thi mới (Word .docx hoặc PDF .pdf)
                  </div>
                  <div style="font-size:0.82rem;color:var(--text-secondary);margin-top:2px;">
                    Hệ thống tự động tách 3 phần câu hỏi, trích xuất hình ảnh &amp; đáp án, cho phép xem trước, chỉnh sửa từng câu và chau chuốt hình ảnh trước khi tạo đề.
                  </div>
                </div>
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                  <input type="file" id="mock-file-input" accept=".docx,.pdf" style="display:none;" />
                  <button type="button" class="btn btn-primary" id="btn-upload-mock-file" ${st.uploading ? "disabled" : ""}>
                    ${st.uploading ? `Đang phân tích (${st.uploadPercent}%)...` : "📄 Tải file Word / PDF lên"}
                  </button>
                  <button type="button" class="btn btn-secondary" id="btn-create-blank-mock" ${st.uploading ? "disabled" : ""}>
                    + Tạo đề thủ công
                  </button>
                </div>
              </div>
              ${
                st.uploading
                  ? `
                    <div class="mock-upload-progress">
                      <div class="mock-upload-progress-bar" style="width:${st.uploadPercent}%;"></div>
                    </div>
                    <div style="font-size:0.78rem;color:var(--primary);margin-top:4px;font-weight:600;">
                      ${st.uploadPhase === "processing" ? "Đang trích xuất câu hỏi, hình ảnh và đáp án từ tệp..." : `Đang tải tệp lên máy chủ (${st.uploadPercent}%)...`}
                    </div>
                  `
                  : ""
              }
            `
            : ""
        }
      </div>

      ${
        st.loading
          ? `
            <div class="card" style="padding:36px;text-align:center;">
              <div class="spinner" style="margin:0 auto 12px;"></div>
              <div style="color:var(--text-secondary);">Đang tải danh sách đề thi thử...</div>
            </div>
          `
          : st.exams.length === 0
            ? `
              <div class="card" style="padding:40px 24px;text-align:center;">
                <div style="font-size:2rem;margin-bottom:8px;">📝</div>
                <h3 style="margin:0 0 6px;">Chưa có đề thi thử nào trong Phòng luyện tập</h3>
                <p style="margin:0;color:var(--text-secondary);font-size:0.88rem;">
                  ${canAdd ? "Thầy/Cô hãy bấm nút <strong>Tải file Word / PDF lên</strong> ở trên để tạo Đề số 1 ngay." : "Giáo viên đang chuẩn bị đề thi thử. Em vui lòng quay lại sau nhé!"}
                </p>
              </div>
            `
            : `
              <div class="mock-exams-grid">
                ${st.exams
                  .map(
                    (ex) => `
                    <article class="mock-exam-card">
                      <div class="mock-exam-card-head">
                        <div class="mock-exam-kicker">${escapeHtml(ex.header_label || "PHÒNG LUYỆN TẬP")}</div>
                        <div class="mock-exam-stt-row">
                          <h3 class="mock-exam-title">${escapeHtml(ex.title || `Đề số ${ex.order_number}`)}</h3>
                          <span class="mock-exam-time-badge">⏱ Thời gian: ${ex.duration_minutes || 45} phút</span>
                        </div>
                        ${
                          ex.subtitle
                            ? `<div class="mock-exam-subtitle">${escapeHtml(ex.subtitle)}</div>`
                            : ""
                        }
                      </div>

                      <div class="mock-exam-meta-grid">
                        <div class="mock-meta-chip"><strong>${ex.mcq_count}</strong><span>Phần I (TN)</span></div>
                        <div class="mock-meta-chip"><strong>${ex.tf_count}</strong><span>Phần II (Đ/S)</span></div>
                        <div class="mock-meta-chip"><strong>${ex.sa_count}</strong><span>Phần III (TLN)</span></div>
                        <div class="mock-meta-chip accent"><strong>${formatScoreVN(ex.max_score)}</strong><span>Thang điểm</span></div>
                      </div>

                      <div class="mock-exam-status-row">
                        <span>Tổng <strong>${ex.question_count}</strong> câu hỏi</span>
                        ${
                          ex.my_attempt_count > 0
                            ? `<span class="pill pill-emerald">Điểm cao nhất: <strong>${formatScoreVN(ex.my_best_score)}/${formatScoreVN(ex.max_score)}</strong> (${ex.my_attempt_count} lượt)</span>`
                            : `<span style="color:var(--text-muted);font-size:0.78rem;">Chưa làm bài</span>`
                        }
                      </div>

                      ${
                        canAdd
                          ? `
                            <div style="font-size:0.76rem;color:var(--text-muted);padding:0 16px 8px;display:flex;justify-content:space-between;gap:8px;">
                              <span>Người tạo: ${escapeHtml(ex.created_by_name || "Hệ thống")}</span>
                              <span>Tổng lượt làm: <strong>${ex.total_attempts || 0}</strong></span>
                            </div>
                          `
                          : ""
                      }

                      <div class="mock-exam-actions">
                        <button type="button" class="btn btn-primary btn-sm" data-start-exam="${ex.id}" style="flex:1;">
                          ▶ Bắt đầu làm bài
                        </button>
                        ${
                          ex.my_last_attempt_id
                            ? `<button type="button" class="btn btn-secondary btn-sm" data-review-attempt="${ex.my_last_attempt_id}">Xem lại</button>`
                            : ""
                        }
                        ${
                          canAdd
                            ? `<button type="button" class="btn btn-secondary btn-sm" data-view-attempts="${ex.id}">Bảng điểm</button>`
                            : ""
                        }
                        ${
                          canEditPublished
                            ? `<button type="button" class="btn btn-secondary btn-sm" data-edit-exam="${ex.id}">Sửa đề</button>`
                            : ""
                        }
                        ${
                          canDelete
                            ? `<button type="button" class="btn btn-danger btn-sm" data-delete-exam="${ex.id}" data-exam-stt="${ex.order_number}">Xoá</button>`
                            : ""
                        }
                      </div>
                    </article>
                  `
                  )
                  .join("")}
              </div>
            `
      }
    `;

    // Bind upload events
    const fileInput = document.getElementById("mock-file-input");
    document.getElementById("btn-upload-mock-file")?.addEventListener("click", () => fileInput?.click());
    fileInput?.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const lower = (file.name || "").toLowerCase();
      if (!lower.endsWith(".docx") && !lower.endsWith(".pdf")) {
        showToast("Vui lòng chọn file Word (.docx) hoặc file PDF (.pdf).", "error");
        e.target.value = "";
        return;
      }
      st.uploading = true;
      st.uploadPercent = 5;
      st.uploadPhase = "uploading";
      render();
      try {
        const res = await api.parseMockExamBinary(file, (p) => {
          st.uploadPercent = p.percent || 0;
          st.uploadPhase = p.phase || "uploading";
          const bar = document.querySelector(".mock-upload-progress-bar");
          if (bar) bar.style.width = `${st.uploadPercent}%`;
        });
        st.editingExamId = null;
        st.draft = res.draft;
        st.draftWarnings = res.warnings || [];
        st.editorFilter = "all";
        st.view = "editor";
        showToast(
          `Đã phân tích xong ${res.stats?.total_questions || 0} câu hỏi và ${res.stats?.images_count || 0} hình ảnh! Hãy kiểm tra & chau chuốt trước khi lưu.`,
          "success"
        );
      } catch (err) {
        showToast(err.message || "Lỗi khi phân tích file đề thi.", "error");
      } finally {
        st.uploading = false;
        e.target.value = "";
        render();
      }
    });

    document.getElementById("btn-create-blank-mock")?.addEventListener("click", () => {
      const nextStt = (st.exams.reduce((m, e) => Math.max(m, Number(e.order_number || 0)), 0) || 0) + 1;
      st.editingExamId = null;
      st.draft = {
        order_number: nextStt,
        header_label: "PHÒNG LUYỆN TẬP",
        title: `Đề số ${nextStt}`,
        subtitle: "",
        duration_minutes: 45,
        source_filename: "",
        content: {
          mcq: [
            {
              id: "mcq-1",
              orig_num: 1,
              question: "",
              images: [],
              tables: [],
              options: ["", "", "", ""],
              correct_index: 0,
              explanation: "",
            },
          ],
          true_false: [],
          short_answer: [],
        },
      };
      st.draftWarnings = [];
      st.editorFilter = "all";
      st.view = "editor";
      render();
    });

    // Bind exam actions
    container.querySelectorAll("[data-start-exam]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const examId = Number(btn.dataset.startExam);
        try {
          const res = await api.getMockExam(examId, false);
          startExamSession(res.exam);
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    container.querySelectorAll("[data-review-attempt]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const attId = Number(btn.dataset.reviewAttempt);
        try {
          const res = await api.getMockExamAttemptDetail(attId);
          st.resultData = {
            exam: res.exam,
            result: res.result,
            started_at: res.attempt.started_at,
            submitted_at: res.attempt.submitted_at,
            duration_seconds: res.attempt.duration_seconds,
            reviewerName: res.attempt.full_name,
          };
          st.view = "result";
          render();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    container.querySelectorAll("[data-view-attempts]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const examId = Number(btn.dataset.viewAttempts);
        const ex = st.exams.find((x) => x.id === examId);
        try {
          const res = await api.getMockExamAttempts(examId);
          st.attemptsExam = ex;
          st.attemptsList = res.attempts || [];
          st.view = "attempts";
          render();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    container.querySelectorAll("[data-edit-exam]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const examId = Number(btn.dataset.editExam);
        try {
          const res = await api.getMockExam(examId, true);
          st.editingExamId = examId;
          st.draft = res.exam;
          st.draftWarnings = [];
          st.editorFilter = "all";
          st.view = "editor";
          render();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    container.querySelectorAll("[data-delete-exam]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const examId = Number(btn.dataset.deleteExam);
        const stt = btn.dataset.examStt;
        if (!window.confirm(`Xác nhận xoá Đề số ${stt} và toàn bộ lịch sử bài làm của đề này?`)) return;
        try {
          const res = await api.deleteMockExam(examId);
          showToast(res.message || "Đã xoá đề thi.", "success");
          await loadExamsList();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });
  }

  // ================== VIEW 2: PREVIEW & PER-QUESTION EDITOR + IMAGE POLISHING ==================
  function renderEditor() {
    const d = st.draft;
    if (!d) {
      st.view = "lobby";
      return render();
    }
    const stats = calcDraftStats(d);
    const c = d.content || { mcq: [], true_false: [], short_answer: [] };

    const renderImagesBar = (partKey, qIdx, imgs) => `
      <div class="mock-ed-imgs-wrap">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;">
          <span style="font-size:0.78rem;font-weight:700;color:var(--text-secondary);">Hình ảnh minh hoạ (${imgs.length})</span>
          <label class="btn btn-secondary btn-sm" style="cursor:pointer;margin:0;">
            + Thêm ảnh
            <input type="file" accept="image/*" style="display:none;" data-add-img="${partKey}:${qIdx}" />
          </label>
        </div>
        ${
          imgs.length
            ? `
              <div class="mock-ed-img-list">
                ${imgs
                  .map(
                    (src, imIdx) => `
                    <div class="mock-ed-img-card">
                      <img src="${src}" alt="Ảnh câu hỏi" class="mock-ed-img-thumb" />
                      <div class="mock-ed-img-actions">
                        <button type="button" class="btn btn-sm btn-primary" data-quick-polish="${partKey}:${qIdx}:${imIdx}">✨ Làm đẹp nhanh</button>
                        <button type="button" class="btn btn-sm btn-secondary" data-open-studio="${partKey}:${qIdx}:${imIdx}">🎨 Studio chỉnh ảnh</button>
                        <label class="btn btn-sm btn-secondary" style="cursor:pointer;margin:0;">
                          Thay ảnh
                          <input type="file" accept="image/*" style="display:none;" data-replace-img="${partKey}:${qIdx}:${imIdx}" />
                        </label>
                        <button type="button" class="btn btn-sm btn-danger" data-remove-img="${partKey}:${qIdx}:${imIdx}">Xoá</button>
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
    `;

    const showMcq = st.editorFilter === "all" || st.editorFilter === "mcq";
    const showTf = st.editorFilter === "all" || st.editorFilter === "true_false";
    const showSa = st.editorFilter === "all" || st.editorFilter === "short_answer";

    container.innerHTML = `
      <div class="card mock-editor-topbar">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;">
          <div>
            <div class="mock-hero-kicker">XEM TRƯỚC &amp; CHỈNH SỬA ĐỀ THI TRƯỚC KHI XUẤT BẢN</div>
            <h2 style="margin:4px 0 4px;font-size:1.2rem;">
              ${escapeHtml(d.header_label || "PHÒNG LUYỆN TẬP")} — ${escapeHtml(d.title || `Đề số ${d.order_number}`)}
            </h2>
            <div style="font-size:0.82rem;color:var(--text-secondary);">
              Thời gian: <strong>${d.duration_minutes || 45} phút</strong>
              ${d.source_filename ? ` · Nguồn: <code>${escapeHtml(d.source_filename)}</code>` : ""}
            </div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button type="button" class="btn btn-secondary" id="btn-ed-cancel">← Quay lại</button>
            ${
              stats.imgs > 0
                ? `<button type="button" class="btn btn-secondary" id="btn-ed-polish-all" ${st.polishingAll ? "disabled" : ""}>
                    ${st.polishingAll ? "Đang chau chuốt ảnh..." : `✨ Chau chuốt tất cả ${stats.imgs} ảnh (1 chạm)`}
                  </button>`
                : ""
            }
            <button type="button" class="btn btn-primary" id="btn-ed-save" ${st.savingDraft ? "disabled" : ""}>
              ${st.savingDraft ? "Đang lưu..." : st.editingExamId ? "💾 Lưu thay đổi đề thi" : "✅ Lưu & Tạo đề thi"}
            </button>
          </div>
        </div>

        <div class="mock-ed-meta-inputs">
          <div class="form-group" style="margin:0;">
            <label>Tiêu đề số đề (mặc định theo STT upload)</label>
            <input type="text" class="form-control" id="ed-title" value="${escapeHtml(d.title || `Đề số ${d.order_number}`)}" />
          </div>
          <div class="form-group" style="margin:0;">
            <label>Ghi chú phụ (không bắt buộc)</label>
            <input type="text" class="form-control" id="ed-subtitle" placeholder="VD: Đề minh hoạ THPT 2026 - Sở GD..." value="${escapeHtml(d.subtitle || "")}" />
          </div>
          <div class="form-group" style="margin:0;max-width:150px;">
            <label>Thời gian (phút)</label>
            <input type="number" class="form-control" id="ed-duration" min="5" max="180" value="${Number(d.duration_minutes || 45)}" />
          </div>
        </div>

        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;align-items:center;">
          <span class="pill pill-primary">Tổng: ${stats.total} câu</span>
          <span class="pill ${stats.keyed === stats.total && stats.total > 0 ? "pill-emerald" : "pill-amber"}">Đã có đáp án: ${stats.keyed}/${stats.total}</span>
          <span class="pill">Hình ảnh: ${stats.imgs}</span>
          <span class="pill">Thang điểm: ${formatScoreVN(stats.maxScore)}đ</span>
        </div>

        ${
          st.draftWarnings.length
            ? `
              <div class="mock-warning-box">
                ${st.draftWarnings.map((w) => `<div>⚠️ ${escapeHtml(w)}</div>`).join("")}
              </div>
            `
            : ""
        }

        <div class="mock-ed-filter-bar">
          <button type="button" class="btn btn-sm ${st.editorFilter === "all" ? "btn-primary" : "btn-secondary"}" data-ed-filter="all">Tất cả (${stats.total})</button>
          <button type="button" class="btn btn-sm ${st.editorFilter === "mcq" ? "btn-primary" : "btn-secondary"}" data-ed-filter="mcq">Phần I · TN 4 chọn (${stats.mcq})</button>
          <button type="button" class="btn btn-sm ${st.editorFilter === "true_false" ? "btn-primary" : "btn-secondary"}" data-ed-filter="true_false">Phần II · Đúng/Sai (${stats.tf})</button>
          <button type="button" class="btn btn-sm ${st.editorFilter === "short_answer" ? "btn-primary" : "btn-secondary"}" data-ed-filter="short_answer">Phần III · Trả lời ngắn (${stats.sa})</button>
        </div>
      </div>

      ${
        showMcq
          ? `
            <div class="mock-part-heading-bar">
              <h3>PHẦN I. Trắc nghiệm nhiều phương án lựa chọn (${c.mcq.length} câu · 0,25đ/câu)</h3>
              <button type="button" class="btn btn-sm btn-secondary" data-add-q="mcq">+ Thêm câu Phần I</button>
            </div>
            ${c.mcq
              .map(
                (q, idx) => `
                <div class="card mock-ed-qcard">
                  <div class="mock-ed-qhead">
                    <span class="pill pill-primary">Phần I · Câu ${idx + 1}</span>
                    <div style="display:flex;align-items:center;gap:8px;">
                      <span class="pill ${q.correct_index !== null && q.correct_index !== undefined ? "pill-emerald" : "pill-amber"}">
                        ${q.correct_index !== null && q.correct_index !== undefined ? `Đáp án: ${LETTERS[q.correct_index]}` : "Chưa chọn đáp án"}
                      </span>
                      <button type="button" class="btn btn-sm btn-danger" data-del-q="mcq:${idx}">Xoá câu</button>
                    </div>
                  </div>

                  <div class="mock-ed-preview-box">
                    <div class="mock-ed-preview-label">Xem trước hiển thị công thức &amp; kiểu gene</div>
                    <div style="white-space:pre-line;line-height:1.6;">${formatBioHtml(q.question || "(Chưa nhập nội dung câu hỏi)")}</div>
                  </div>

                  <div class="form-group">
                    <label>Nội dung câu hỏi</label>
                    <textarea class="form-control" rows="3" data-q-field="mcq:${idx}:question">${escapeHtml(q.question || "")}</textarea>
                  </div>

                  ${renderImagesBar("mcq", idx, q.images || [])}

                  <div class="mock-ed-opts-grid">
                    ${[0, 1, 2, 3]
                      .map(
                        (oi) => `
                        <div class="mock-ed-opt-row ${q.correct_index === oi ? "is-correct" : ""}">
                          <label class="mock-ed-opt-radio" title="Chọn làm đáp án đúng">
                            <input type="radio" name="mcq-ans-${idx}" value="${oi}" ${q.correct_index === oi ? "checked" : ""} data-mcq-ans="${idx}:${oi}" />
                            <strong>${LETTERS[oi]}</strong>
                          </label>
                          <input type="text" class="form-control" value="${escapeHtml((q.options || [])[oi] || "")}" data-mcq-opt="${idx}:${oi}" placeholder="Phương án ${LETTERS[oi]}" />
                        </div>
                      `
                      )
                      .join("")}
                  </div>

                  <div class="form-group" style="margin-top:10px;margin-bottom:0;">
                    <label>Đáp án gợi ý / Hướng dẫn giải (hiển thị sau khi học sinh nộp bài)</label>
                    <textarea class="form-control" rows="2" placeholder="Nhập lời giải hoặc gợi ý cho câu hỏi này..." data-q-field="mcq:${idx}:explanation">${escapeHtml(q.explanation || "")}</textarea>
                  </div>
                </div>
              `
              )
              .join("")}
          `
          : ""
      }

      ${
        showTf
          ? `
            <div class="mock-part-heading-bar">
              <h3>PHẦN II. Trắc nghiệm Đúng / Sai (${c.true_false.length} câu · tối đa 1,0đ/câu)</h3>
              <button type="button" class="btn btn-sm btn-secondary" data-add-q="true_false">+ Thêm câu Phần II</button>
            </div>
            ${c.true_false
              .map(
                (q, idx) => `
                <div class="card mock-ed-qcard">
                  <div class="mock-ed-qhead">
                    <span class="pill pill-primary">Phần II · Câu ${idx + 1}</span>
                    <button type="button" class="btn btn-sm btn-danger" data-del-q="true_false:${idx}">Xoá câu</button>
                  </div>

                  <div class="mock-ed-preview-box">
                    <div class="mock-ed-preview-label">Xem trước đề dẫn</div>
                    <div style="white-space:pre-line;line-height:1.6;">${formatBioHtml(q.question || "(Chưa nhập đề dẫn)")}</div>
                  </div>

                  <div class="form-group">
                    <label>Đề dẫn câu hỏi Đúng/Sai</label>
                    <textarea class="form-control" rows="3" data-q-field="true_false:${idx}:question">${escapeHtml(q.question || "")}</textarea>
                  </div>

                  ${renderImagesBar("true_false", idx, q.images || [])}

                  <div style="display:flex;flex-direction:column;gap:8px;margin-top:8px;">
                    ${(q.statements || [])
                      .map(
                        (stItem, si) => `
                        <div class="mock-ed-tf-row">
                          <span class="mock-tf-key">${escapeHtml(stItem.key)})</span>
                          <input type="text" class="form-control" value="${escapeHtml(stItem.text || "")}" data-tf-text="${idx}:${si}" placeholder="Nội dung ý ${stItem.key}" />
                          <div class="mock-tf-toggle">
                            <button type="button" class="btn btn-sm ${stItem.answer === true ? "btn-primary" : "btn-secondary"}" data-tf-ans="${idx}:${si}:true">Đúng</button>
                            <button type="button" class="btn btn-sm ${stItem.answer === false ? "btn-danger" : "btn-secondary"}" data-tf-ans="${idx}:${si}:false">Sai</button>
                          </div>
                        </div>
                      `
                      )
                      .join("")}
                  </div>

                  <div class="form-group" style="margin-top:10px;margin-bottom:0;">
                    <label>Đáp án gợi ý / Hướng dẫn giải</label>
                    <textarea class="form-control" rows="2" placeholder="Nhập lời giải chi tiết từng ý a, b, c, d..." data-q-field="true_false:${idx}:explanation">${escapeHtml(q.explanation || "")}</textarea>
                  </div>
                </div>
              `
              )
              .join("")}
          `
          : ""
      }

      ${
        showSa
          ? `
            <div class="mock-part-heading-bar">
              <h3>PHẦN III. Trắc nghiệm trả lời ngắn (${c.short_answer.length} câu · 0,25đ/câu)</h3>
              <button type="button" class="btn btn-sm btn-secondary" data-add-q="short_answer">+ Thêm câu Phần III</button>
            </div>
            ${c.short_answer
              .map(
                (q, idx) => `
                <div class="card mock-ed-qcard">
                  <div class="mock-ed-qhead">
                    <span class="pill pill-primary">Phần III · Câu ${idx + 1}</span>
                    <button type="button" class="btn btn-sm btn-danger" data-del-q="short_answer:${idx}">Xoá câu</button>
                  </div>

                  <div class="mock-ed-preview-box">
                    <div class="mock-ed-preview-label">Xem trước câu hỏi</div>
                    <div style="white-space:pre-line;line-height:1.6;">${formatBioHtml(q.question || "(Chưa nhập câu hỏi)")}</div>
                  </div>

                  <div class="form-group">
                    <label>Nội dung câu hỏi</label>
                    <textarea class="form-control" rows="3" data-q-field="short_answer:${idx}:question">${escapeHtml(q.question || "")}</textarea>
                  </div>

                  ${renderImagesBar("short_answer", idx, q.images || [])}

                  <div class="form-group" style="margin-top:8px;">
                    <label>Đáp án chấp nhận (ngăn cách nhiều dạng bằng dấu chấm phẩy <code>;</code> — VD: <code>0,25; 0.25</code>)</label>
                    <input type="text" class="form-control" value="${escapeHtml((q.accepted_answers || []).join("; "))}" data-sa-ans="${idx}" placeholder="VD: 4 hoặc 0,25; 0.25" />
                  </div>

                  <div class="form-group" style="margin-bottom:0;">
                    <label>Đáp án gợi ý / Hướng dẫn giải</label>
                    <textarea class="form-control" rows="2" placeholder="Nhập cách tính hoặc giải thích..." data-q-field="short_answer:${idx}:explanation">${escapeHtml(q.explanation || "")}</textarea>
                  </div>
                </div>
              `
              )
              .join("")}
          `
          : ""
      }
    `;

    // Metadata bindings
    document.getElementById("ed-title")?.addEventListener("input", (e) => {
      d.title = e.target.value;
    });
    document.getElementById("ed-subtitle")?.addEventListener("input", (e) => {
      d.subtitle = e.target.value;
    });
    document.getElementById("ed-duration")?.addEventListener("input", (e) => {
      d.duration_minutes = Math.max(5, Math.min(180, Number(e.target.value) || 45));
    });

    document.getElementById("btn-ed-cancel")?.addEventListener("click", () => {
      st.view = "lobby";
      st.draft = null;
      st.editingExamId = null;
      render();
    });

    document.querySelectorAll("[data-ed-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        st.editorFilter = btn.dataset.edFilter;
        render();
      });
    });

    // Chau chuốt tất cả ảnh 1 chạm
    document.getElementById("btn-ed-polish-all")?.addEventListener("click", async () => {
      st.polishingAll = true;
      render();
      let count = 0;
      try {
        for (const pk of ["mcq", "true_false", "short_answer"]) {
          for (const q of d.content[pk] || []) {
            if (!q.images || !q.images.length) continue;
            for (let i = 0; i < q.images.length; i++) {
              q.images[i] = await polishImageDataUrl(q.images[i]);
              count += 1;
            }
          }
        }
        showToast(`Đã tự động chau chuốt & làm nét ${count} hình ảnh chuẩn SGK!`, "success");
      } catch (err) {
        showToast(err.message || "Có lỗi khi chau chuốt ảnh.", "error");
      } finally {
        st.polishingAll = false;
        render();
      }
    });

    // Lưu đề thi
    document.getElementById("btn-ed-save")?.addEventListener("click", async () => {
      const curStats = calcDraftStats(d);
      if (curStats.total === 0) {
        showToast("Đề thi cần ít nhất 1 câu hỏi.", "error");
        return;
      }
      // Chuẩn hóa lại ID từng câu trước khi lưu
      (d.content.mcq || []).forEach((q, i) => {
        q.id = `mcq-${i + 1}`;
        q.orig_num = i + 1;
      });
      (d.content.true_false || []).forEach((q, i) => {
        q.id = `tf-${i + 1}`;
        q.orig_num = i + 1;
      });
      (d.content.short_answer || []).forEach((q, i) => {
        q.id = `sa-${i + 1}`;
        q.orig_num = i + 1;
      });

      st.savingDraft = true;
      render();
      try {
        const payload = {
          title: (d.title || "").trim() || `Đề số ${d.order_number || 1}`,
          subtitle: (d.subtitle || "").trim(),
          duration_minutes: Number(d.duration_minutes || 45),
          source_filename: d.source_filename || "",
          content: d.content,
        };
        const res = st.editingExamId
          ? await api.updateMockExam(st.editingExamId, payload)
          : await api.createMockExam(payload);
        showToast(res.message || "Đã lưu đề thi thành công!", "success");
        st.draft = null;
        st.editingExamId = null;
        st.view = "lobby";
        await loadExamsList();
      } catch (err) {
        showToast(err.message || "Không thể lưu đề thi.", "error");
        st.savingDraft = false;
        render();
      }
    });

    // Add/delete question
    container.querySelectorAll("[data-add-q]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const pk = btn.dataset.addQ;
        const arr = d.content[pk];
        const nextNum = arr.length + 1;
        if (pk === "mcq") {
          arr.push({
            id: `mcq-${nextNum}`,
            orig_num: nextNum,
            question: "",
            images: [],
            tables: [],
            options: ["", "", "", ""],
            correct_index: null,
            explanation: "",
          });
        } else if (pk === "true_false") {
          arr.push({
            id: `tf-${nextNum}`,
            orig_num: nextNum,
            question: "",
            images: [],
            tables: [],
            statements: [
              { key: "a", text: "", answer: null },
              { key: "b", text: "", answer: null },
              { key: "c", text: "", answer: null },
              { key: "d", text: "", answer: null },
            ],
            explanation: "",
          });
        } else {
          arr.push({
            id: `sa-${nextNum}`,
            orig_num: nextNum,
            question: "",
            images: [],
            tables: [],
            accepted_answers: [],
            explanation: "",
          });
        }
        render();
      });
    });

    container.querySelectorAll("[data-del-q]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [pk, idxS] = btn.dataset.delQ.split(":");
        d.content[pk].splice(Number(idxS), 1);
        render();
      });
    });

    // Text field live updates
    container.querySelectorAll("[data-q-field]").forEach((el) => {
      el.addEventListener("input", () => {
        const [pk, idxS, field] = el.dataset.qField.split(":");
        d.content[pk][Number(idxS)][field] = el.value;
        if (field === "question") {
          const card = el.closest(".mock-ed-qcard");
          const prev = card?.querySelector(".mock-ed-preview-box > div:last-child");
          if (prev) prev.innerHTML = formatBioHtml(el.value || "(Chưa nhập nội dung)");
        }
      });
    });

    container.querySelectorAll("[data-mcq-opt]").forEach((el) => {
      el.addEventListener("input", () => {
        const [idxS, oiS] = el.dataset.mcqOpt.split(":");
        d.content.mcq[Number(idxS)].options[Number(oiS)] = el.value;
      });
    });

    container.querySelectorAll("[data-mcq-ans]").forEach((el) => {
      el.addEventListener("change", () => {
        const [idxS, oiS] = el.dataset.mcqAns.split(":");
        d.content.mcq[Number(idxS)].correct_index = Number(oiS);
        render();
      });
    });

    container.querySelectorAll("[data-tf-text]").forEach((el) => {
      el.addEventListener("input", () => {
        const [idxS, siS] = el.dataset.tfText.split(":");
        d.content.true_false[Number(idxS)].statements[Number(siS)].text = el.value;
      });
    });

    container.querySelectorAll("[data-tf-ans]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [idxS, siS, valS] = btn.dataset.tfAns.split(":");
        d.content.true_false[Number(idxS)].statements[Number(siS)].answer = valS === "true";
        render();
      });
    });

    container.querySelectorAll("[data-sa-ans]").forEach((el) => {
      el.addEventListener("input", () => {
        const idx = Number(el.dataset.saAns);
        d.content.short_answer[idx].accepted_answers = el.value
          .split(";")
          .map((x) => x.trim())
          .filter(Boolean);
      });
    });

    // Image actions per question
    container.querySelectorAll("[data-quick-polish]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const [pk, qi, imi] = btn.dataset.quickPolish.split(":");
        const q = d.content[pk][Number(qi)];
        btn.disabled = true;
        btn.textContent = "Đang xử lý...";
        try {
          q.images[Number(imi)] = await polishImageDataUrl(q.images[Number(imi)]);
          showToast("Đã làm đẹp ảnh tự động!", "success");
          render();
        } catch (err) {
          showToast(err.message, "error");
          render();
        }
      });
    });

    container.querySelectorAll("[data-open-studio]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [pk, qi, imi] = btn.dataset.openStudio.split(":");
        openImageStudioModal(pk, Number(qi), Number(imi));
      });
    });

    container.querySelectorAll("[data-remove-img]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [pk, qi, imi] = btn.dataset.removeImg.split(":");
        d.content[pk][Number(qi)].images.splice(Number(imi), 1);
        render();
      });
    });

    container.querySelectorAll("[data-add-img]").forEach((inp) => {
      inp.addEventListener("change", async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const [pk, qi] = inp.dataset.addImg.split(":");
        try {
          const rawUrl = await readFileAsDataUrl(file);
          const polished = await polishImageDataUrl(rawUrl);
          d.content[pk][Number(qi)].images.push(polished);
          showToast("Đã thêm & tự động làm đẹp hình ảnh!", "success");
          render();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    container.querySelectorAll("[data-replace-img]").forEach((inp) => {
      inp.addEventListener("change", async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const [pk, qi, imi] = inp.dataset.replaceImg.split(":");
        try {
          const rawUrl = await readFileAsDataUrl(file);
          const polished = await polishImageDataUrl(rawUrl);
          d.content[pk][Number(qi)].images[Number(imi)] = polished;
          showToast("Đã thay thế & làm đẹp hình ảnh!", "success");
          render();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });
  }

  // ================== VIEW 3: TAKING EXAM (45-MIN CLOCK + STRICT 100% SUBMIT) ==================
  function startExamSession(exam) {
    stopMockExamTimers();
    const now = new Date();
    st.activeExam = exam;
    st.startedAtDate = now;
    st.startedAtIso = now.toISOString();
    st.durationSecondsLimit = (Number(exam.duration_minutes) || 45) * 60;
    st.elapsedSeconds = 0;
    st.answers = { mcq: {}, true_false: {}, short_answer: {} };
    st.submitting = false;
    st.view = "taking";

    activeTimerInterval = setInterval(() => {
      st.elapsedSeconds = Math.max(0, Math.floor((Date.now() - st.startedAtDate.getTime()) / 1000));
      const remaining = Math.max(0, st.durationSecondsLimit - st.elapsedSeconds);
      const elapsedEl = document.getElementById("mock-clock-elapsed");
      const remainEl = document.getElementById("mock-clock-remaining");
      if (elapsedEl) elapsedEl.textContent = formatDuration(st.elapsedSeconds);
      if (remainEl) {
        remainEl.textContent = formatDuration(remaining);
        remainEl.classList.toggle("warn", remaining <= 300 && remaining > 60);
        remainEl.classList.toggle("danger", remaining <= 60);
      }
      if (remaining === 0 && !st.submitting) {
        stopMockExamTimers();
        showToast("Hết thời gian 45 phút! Hệ thống đang tự động nộp bài và chấm điểm...", "info");
        submitActiveExam(true);
      }
    }, 1000);

    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submitActiveExam(autoTimeout = false) {
    if (!st.activeExam || st.submitting) return;
    const comp = calcCompletion(st.activeExam, st.answers);
    if (!autoTimeout && !comp.isComplete) {
      showToast(`Em còn thiếu ${comp.total - comp.done} câu chưa hoàn thành. Phải làm hết tất cả câu mới được bấm Nộp bài!`, "error");
      return;
    }

    st.submitting = true;
    stopMockExamTimers();
    const btn = document.getElementById("btn-submit-mock-exam");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Đang chấm điểm...";
    }
    try {
      const res = await api.submitMockExam(st.activeExam.id, {
        answers: st.answers,
        started_at: st.startedAtIso,
        duration_seconds: st.elapsedSeconds,
        auto_submitted_timeout: autoTimeout,
      });
      st.resultData = {
        exam: res.exam,
        result: res.result,
        started_at: res.started_at,
        submitted_at: res.submitted_at,
        duration_seconds: res.duration_seconds,
        reviewerName: currentUser?.full_name || "",
      };
      st.activeExam = null;
      st.view = "result";
      showToast(`Đã nộp bài! Tổng điểm: ${formatScoreVN(res.result.score)} / ${formatScoreVN(res.result.max_score)} điểm`, "success");
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      showToast(err.message || "Không thể nộp bài.", "error");
      st.submitting = false;
      render();
    }
  }

  function updateTakingProgressUI() {
    if (!st.activeExam) return;
    const comp = calcCompletion(st.activeExam, st.answers);
    const pct = comp.total > 0 ? Math.round((comp.done / comp.total) * 100) : 0;

    const progText = document.getElementById("mock-prog-text");
    if (progText) progText.textContent = `${comp.done} / ${comp.total} câu (${pct}%)`;
    const progFill = document.getElementById("mock-prog-fill");
    if (progFill) progFill.style.width = `${pct}%`;

    const submitBtn = document.getElementById("btn-submit-mock-exam");
    const hintEl = document.getElementById("mock-submit-hint");
    const jumpBtn = document.getElementById("btn-jump-missing");

    if (submitBtn) {
      submitBtn.disabled = !comp.isComplete || st.submitting;
      submitBtn.className = comp.isComplete ? "btn btn-primary" : "btn btn-secondary";
      submitBtn.textContent = comp.isComplete
        ? "✅ Nộp bài & Chấm điểm"
        : `🔒 Nộp bài (còn thiếu ${comp.total - comp.done} câu)`;
    }
    if (hintEl) {
      hintEl.textContent = comp.isComplete
        ? "Đã hoàn thành 100% câu hỏi — Em có thể bấm Nộp bài ngay!"
        : `Cần hoàn thành đủ ${comp.total}/${comp.total} câu mới mở khóa nút Nộp bài.`;
    }
    if (jumpBtn) {
      jumpBtn.style.display = comp.isComplete ? "none" : "inline-flex";
    }

    // Cập nhật màu chip điều hướng
    const c = st.activeExam.content;
    (c.mcq || []).forEach((q) => {
      const chip = document.querySelector(`[data-nav-q="${q.id}"]`);
      if (!chip) return;
      const done = st.answers.mcq[q.id] !== undefined && st.answers.mcq[q.id] !== "";
      chip.classList.toggle("done", done);
      chip.classList.remove("partial");
    });
    (c.true_false || []).forEach((q) => {
      const chip = document.querySelector(`[data-nav-q="${q.id}"]`);
      if (!chip) return;
      const stmts = q.statements || [];
      const filled = stmts.filter((s) => st.answers.true_false[`${q.id}:${s.key}`] !== undefined).length;
      chip.classList.toggle("done", stmts.length > 0 && filled === stmts.length);
      chip.classList.toggle("partial", filled > 0 && filled < stmts.length);
    });
    (c.short_answer || []).forEach((q) => {
      const chip = document.querySelector(`[data-nav-q="${q.id}"]`);
      if (!chip) return;
      const done = String(st.answers.short_answer[q.id] || "").trim().length > 0;
      chip.classList.toggle("done", done);
      chip.classList.remove("partial");
    });
  }

  function renderTablesHtml(tables) {
    if (!tables || !tables.length) return "";
    return tables
      .map(
        (rows) => `
        <div class="data-table-wrap" style="margin:10px 0;">
          <table class="data-table">
            <tbody>
              ${rows
                .map(
                  (r, ri) => `
                  <tr>
                    ${r
                      .map((cell) =>
                        ri === 0
                          ? `<th>${formatBioHtml(cell)}</th>`
                          : `<td>${formatBioHtml(cell)}</td>`
                      )
                      .join("")}
                  </tr>
                `
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `
      )
      .join("");
  }

  function renderTaking() {
    const ex = st.activeExam;
    if (!ex) {
      st.view = "lobby";
      return render();
    }
    const c = ex.content || { mcq: [], true_false: [], short_answer: [] };
    const comp = calcCompletion(ex, st.answers);
    const remaining = Math.max(0, st.durationSecondsLimit - st.elapsedSeconds);
    const startClock = st.startedAtDate ? formatClockHMS(st.startedAtDate) : "--:--:--";
    const startDay = st.startedAtDate ? formatDateDMY(st.startedAtDate) : "";

    container.innerHTML = `
      <!-- Official Exam Header -->
      <div class="mock-exam-paper-header">
        <div class="mock-paper-kicker">${escapeHtml(ex.header_label || "PHÒNG LUYỆN TẬP")}</div>
        <h1 class="mock-paper-title">${escapeHtml(ex.title || `Đề số ${ex.order_number}`)}</h1>
        <div class="mock-paper-time">Thời gian: ${ex.duration_minutes || 45} phút</div>
        ${ex.subtitle ? `<div class="mock-paper-sub">${escapeHtml(ex.subtitle)}</div>` : ""}
      </div>

      <!-- Sticky Live Clock & Strict Submit Bar -->
      <div class="mock-sticky-clock-bar">
        <div class="mock-clock-metrics">
          <div class="mock-clock-item">
            <span class="mock-clock-lbl">Bắt đầu lúc</span>
            <strong class="mock-clock-val">${startClock}</strong>
            <span class="mock-clock-sub">${startDay}</span>
          </div>
          <div class="mock-clock-item">
            <span class="mock-clock-lbl">Đã làm bài</span>
            <strong class="mock-clock-val" id="mock-clock-elapsed">${formatDuration(st.elapsedSeconds)}</strong>
            <span class="mock-clock-sub">Tính giờ trực tiếp</span>
          </div>
          <div class="mock-clock-item highlight">
            <span class="mock-clock-lbl">Thời gian còn lại</span>
            <strong class="mock-clock-val countdown" id="mock-clock-remaining">${formatDuration(remaining)}</strong>
            <span class="mock-clock-sub">Đếm ngược ${ex.duration_minutes || 45} phút</span>
          </div>
        </div>

        <div class="mock-clock-submit-zone">
          <div style="flex:1;min-width:180px;">
            <div style="display:flex;justify-content:space-between;font-size:0.78rem;font-weight:700;margin-bottom:4px;">
              <span>Tiến độ hoàn thành</span>
              <span id="mock-prog-text">${comp.done} / ${comp.total} câu</span>
            </div>
            <div class="mock-prog-track"><div class="mock-prog-fill" id="mock-prog-fill" style="width:${comp.total ? Math.round((comp.done / comp.total) * 100) : 0}%;"></div></div>
            <div id="mock-submit-hint" style="font-size:0.73rem;color:var(--text-muted);margin-top:4px;">
              ${comp.isComplete ? "Đã hoàn thành 100% câu hỏi — Em có thể bấm Nộp bài ngay!" : `Cần hoàn thành đủ ${comp.total}/${comp.total} câu mới mở khóa nút Nộp bài.`}
            </div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <button type="button" class="btn btn-sm btn-secondary" id="btn-jump-missing" style="${comp.isComplete ? "display:none;" : ""}">
              Tới câu chưa làm
            </button>
            <button type="button" class="${comp.isComplete ? "btn btn-primary" : "btn btn-secondary"}" id="btn-submit-mock-exam" ${comp.isComplete ? "" : "disabled"}>
              ${comp.isComplete ? "✅ Nộp bài & Chấm điểm" : `🔒 Nộp bài (còn thiếu ${comp.total - comp.done} câu)`}
            </button>
            <button type="button" class="btn btn-sm btn-ghost" id="btn-exit-exam">Thoát</button>
          </div>
        </div>
      </div>

      <div class="mock-exam-layout">
        <!-- Main Questions Column -->
        <div class="mock-exam-questions">
          ${
            (c.mcq || []).length
              ? `
                <div class="mock-section-banner">
                  <strong>PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn</strong>
                  <span>Thí sinh trả lời từ câu 1 đến câu ${c.mcq.length}. Mỗi câu hỏi thí sinh chỉ chọn một phương án (0,25 điểm/câu).</span>
                </div>
                ${c.mcq
                  .map(
                    (q, idx) => `
                    <div class="card mock-q-card" id="mock-q-${q.id}">
                      <div class="mock-q-stem">
                        <span class="mock-q-num">Câu ${idx + 1}.</span>
                        <span style="white-space:pre-line;">${formatBioHtml(q.question)}</span>
                      </div>
                      ${(q.images || [])
                        .map((im) => `<div class="mock-q-img-wrap"><img src="${im}" alt="Hình câu ${idx + 1}" /></div>`)
                        .join("")}
                      ${renderTablesHtml(q.tables)}
                      <div class="mock-mcq-options">
                        ${(q.options || [])
                          .map(
                            (opt, oi) => `
                            <label class="mock-mcq-opt ${st.answers.mcq[q.id] === oi ? "selected" : ""}">
                              <input type="radio" name="take-${q.id}" value="${oi}" ${st.answers.mcq[q.id] === oi ? "checked" : ""} data-take-mcq="${q.id}:${oi}" />
                              <span class="mock-opt-letter">${LETTERS[oi]}</span>
                              <span class="mock-opt-text">${formatBioHtml(opt)}</span>
                            </label>
                          `
                          )
                          .join("")}
                      </div>
                    </div>
                  `
                  )
                  .join("")}
              `
              : ""
          }

          ${
            (c.true_false || []).length
              ? `
                <div class="mock-section-banner">
                  <strong>PHẦN II. Câu trắc nghiệm đúng sai</strong>
                  <span>Thí sinh trả lời từ câu 1 đến câu ${c.true_false.length}. Trong mỗi ý a), b), c), d) ở mỗi câu, thí sinh chọn Đúng hoặc Sai (1 ý: 0,1đ · 2 ý: 0,25đ · 3 ý: 0,5đ · 4 ý: 1,0đ).</span>
                </div>
                ${c.true_false
                  .map(
                    (q, idx) => `
                    <div class="card mock-q-card" id="mock-q-${q.id}">
                      <div class="mock-q-stem">
                        <span class="mock-q-num">Câu ${idx + 1}.</span>
                        <span style="white-space:pre-line;">${formatBioHtml(q.question)}</span>
                      </div>
                      ${(q.images || [])
                        .map((im) => `<div class="mock-q-img-wrap"><img src="${im}" alt="Hình câu Đ/S ${idx + 1}" /></div>`)
                        .join("")}
                      ${renderTablesHtml(q.tables)}
                      <div class="mock-tf-list">
                        ${(q.statements || [])
                          .map((stItem) => {
                            const curVal = st.answers.true_false[`${q.id}:${stItem.key}`];
                            return `
                              <div class="mock-tf-item">
                                <div class="mock-tf-text"><strong>${escapeHtml(stItem.key)})</strong> ${formatBioHtml(stItem.text)}</div>
                                <div class="mock-tf-btns">
                                  <button type="button" class="mock-tf-btn ${curVal === true ? "selected-true" : ""}" data-take-tf="${q.id}:${stItem.key}:true">Đúng</button>
                                  <button type="button" class="mock-tf-btn ${curVal === false ? "selected-false" : ""}" data-take-tf="${q.id}:${stItem.key}:false">Sai</button>
                                </div>
                              </div>
                            `;
                          })
                          .join("")}
                      </div>
                    </div>
                  `
                  )
                  .join("")}
              `
              : ""
          }

          ${
            (c.short_answer || []).length
              ? `
                <div class="mock-section-banner">
                  <strong>PHẦN III. Câu trắc nghiệm trả lời ngắn</strong>
                  <span>Thí sinh trả lời từ câu 1 đến câu ${c.short_answer.length}. Nhập kết quả số vào ô đáp án (0,25 điểm/câu).</span>
                </div>
                ${c.short_answer
                  .map(
                    (q, idx) => `
                    <div class="card mock-q-card" id="mock-q-${q.id}">
                      <div class="mock-q-stem">
                        <span class="mock-q-num">Câu ${idx + 1}.</span>
                        <span style="white-space:pre-line;">${formatBioHtml(q.question)}</span>
                      </div>
                      ${(q.images || [])
                        .map((im) => `<div class="mock-q-img-wrap"><img src="${im}" alt="Hình câu TLN ${idx + 1}" /></div>`)
                        .join("")}
                      ${renderTablesHtml(q.tables)}
                      <div class="mock-sa-box">
                        <label>Nhập đáp án của em:</label>
                        <input type="text" class="form-control" style="max-width:260px;" placeholder="VD: 4 hoặc 0,25" value="${escapeHtml(st.answers.short_answer[q.id] || "")}" data-take-sa="${q.id}" />
                      </div>
                    </div>
                  `
                  )
                  .join("")}
              `
              : ""
          }
        </div>

        <!-- Question Navigator Palette -->
        <aside class="card mock-nav-palette">
          <div style="font-weight:700;font-size:0.88rem;margin-bottom:8px;">Bảng điều hướng câu hỏi</div>
          ${
            (c.mcq || []).length
              ? `
                <div class="mock-nav-group-title">Phần I (${c.mcq.length} câu)</div>
                <div class="mock-nav-chips">
                  ${c.mcq.map((q, i) => `<button type="button" class="mock-nav-chip" data-nav-q="${q.id}">${i + 1}</button>`).join("")}
                </div>
              `
              : ""
          }
          ${
            (c.true_false || []).length
              ? `
                <div class="mock-nav-group-title">Phần II (${c.true_false.length} câu)</div>
                <div class="mock-nav-chips">
                  ${c.true_false.map((q, i) => `<button type="button" class="mock-nav-chip" data-nav-q="${q.id}">ĐS${i + 1}</button>`).join("")}
                </div>
              `
              : ""
          }
          ${
            (c.short_answer || []).length
              ? `
                <div class="mock-nav-group-title">Phần III (${c.short_answer.length} câu)</div>
                <div class="mock-nav-chips">
                  ${c.short_answer.map((q, i) => `<button type="button" class="mock-nav-chip" data-nav-q="${q.id}">N${i + 1}</button>`).join("")}
                </div>
              `
              : ""
          }
          <div style="margin-top:12px;font-size:0.74rem;color:var(--text-muted);line-height:1.5;">
            <span class="mock-legend-dot done"></span> Đã xong &nbsp;
            <span class="mock-legend-dot partial"></span> Làm dở &nbsp;
            <span class="mock-legend-dot"></span> Chưa làm
          </div>
        </aside>
      </div>
    `;

    // Bind taking interactions (NO full re-render on click so scroll & input focus stay silky smooth!)
    container.querySelectorAll("[data-take-mcq]").forEach((inp) => {
      inp.addEventListener("change", () => {
        const [qid, oiS] = inp.dataset.takeMcq.split(":");
        st.answers.mcq[qid] = Number(oiS);
        const card = document.getElementById(`mock-q-${qid}`);
        card?.querySelectorAll(".mock-mcq-opt").forEach((lbl) => lbl.classList.remove("selected"));
        inp.closest(".mock-mcq-opt")?.classList.add("selected");
        updateTakingProgressUI();
      });
    });

    container.querySelectorAll("[data-take-tf]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [qid, sk, valS] = btn.dataset.takeTf.split(":");
        const isTrue = valS === "true";
        st.answers.true_false[`${qid}:${sk}`] = isTrue;
        const row = btn.closest(".mock-tf-btns");
        row?.querySelectorAll(".mock-tf-btn").forEach((b) => {
          b.classList.remove("selected-true", "selected-false");
        });
        btn.classList.add(isTrue ? "selected-true" : "selected-false");
        updateTakingProgressUI();
      });
    });

    container.querySelectorAll("[data-take-sa]").forEach((inp) => {
      inp.addEventListener("input", () => {
        st.answers.short_answer[inp.dataset.takeSa] = inp.value;
        updateTakingProgressUI();
      });
    });

    container.querySelectorAll("[data-nav-q]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const target = document.getElementById(`mock-q-${chip.dataset.navQ}`);
        target?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });

    document.getElementById("btn-jump-missing")?.addEventListener("click", () => {
      const latest = calcCompletion(st.activeExam, st.answers);
      if (latest.missingIds.length) {
        const target = document.getElementById(`mock-q-${latest.missingIds[0]}`);
        target?.scrollIntoView({ behavior: "smooth", block: "center" });
        target?.classList.add("mock-q-pulse");
        setTimeout(() => target?.classList.remove("mock-q-pulse"), 1400);
      }
    });

    document.getElementById("btn-submit-mock-exam")?.addEventListener("click", () => {
      submitActiveExam(false);
    });

    document.getElementById("btn-exit-exam")?.addEventListener("click", () => {
      if (!window.confirm("Thoát phòng thi sẽ không lưu bài làm hiện tại. Bạn chắc chắn muốn thoát?")) return;
      stopMockExamTimers();
      st.activeExam = null;
      st.view = "lobby";
      render();
    });

    updateTakingProgressUI();
  }

  // ================== VIEW 4: RESULT & SUGGESTED ANSWERS ==================
  function renderResult() {
    const rd = st.resultData;
    if (!rd) {
      st.view = "lobby";
      return render();
    }
    const ex = rd.exam;
    const res = rd.result;
    const c = ex.content || { mcq: [], true_false: [], short_answer: [] };
    const mcqMap = Object.fromEntries((res.details?.mcq || []).map((x) => [x.id, x]));
    const tfMap = Object.fromEntries((res.details?.true_false || []).map((x) => [x.id, x]));
    const saMap = Object.fromEntries((res.details?.short_answer || []).map((x) => [x.id, x]));

    container.innerHTML = `
      <div class="card mock-result-hero">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;">
          <div>
            <div class="mock-hero-kicker">${escapeHtml(ex.header_label || "PHÒNG LUYỆN TẬP")} · KẾT QUẢ CHẤM ĐIỂM CHÍNH THỨC</div>
            <h2 style="margin:4px 0 6px;font-size:1.3rem;">${escapeHtml(ex.title || `Đề số ${ex.order_number}`)}</h2>
            <div style="font-size:0.84rem;color:var(--text-secondary);display:flex;flex-wrap:wrap;gap:12px;">
              ${rd.reviewerName ? `<span>Thí sinh: <strong>${escapeHtml(rd.reviewerName)}</strong></span>` : ""}
              <span>Bắt đầu: <strong>${formatDateTimeVN(rd.started_at)}</strong></span>
              <span>Nộp bài: <strong>${formatDateTimeVN(rd.submitted_at)}</strong></span>
              <span>Thời gian làm: <strong>${formatDuration(rd.duration_seconds)}</strong></span>
            </div>
          </div>
          <div class="mock-score-circle">
            <div class="mock-score-big">${formatScoreVN(res.score)}</div>
            <div class="mock-score-denom">/ ${formatScoreVN(res.max_score)} điểm</div>
          </div>
        </div>

        <div class="mock-rubric-grid">
          <div class="mock-rubric-card">
            <div class="mock-rubric-title">Phần I · Trắc nghiệm 4 lựa chọn</div>
            <div class="mock-rubric-score">${formatScoreVN(res.part1_score)} / ${formatScoreVN(res.part1_max)} điểm</div>
            <div class="mock-rubric-sub">Đúng ${res.part1_correct} / ${c.mcq.length} câu (0,25đ / câu)</div>
          </div>
          <div class="mock-rubric-card">
            <div class="mock-rubric-title">Phần II · Trắc nghiệm Đúng / Sai</div>
            <div class="mock-rubric-score">${formatScoreVN(res.part2_score)} / ${formatScoreVN(res.part2_max)} điểm</div>
            <div class="mock-rubric-sub">Đúng trọn 4 ý: ${res.part2_correct_full} / ${c.true_false.length} câu (0,1 / 0,25 / 0,5 / 1,0đ)</div>
          </div>
          <div class="mock-rubric-card">
            <div class="mock-rubric-title">Phần III · Trả lời ngắn</div>
            <div class="mock-rubric-score">${formatScoreVN(res.part3_score)} / ${formatScoreVN(res.part3_max)} điểm</div>
            <div class="mock-rubric-sub">Đúng ${res.part3_correct} / ${c.short_answer.length} câu (0,25đ / câu)</div>
          </div>
        </div>

        <div class="mock-rubric-note">
          <strong>Thang điểm công bố (Bộ GD&amp;ĐT — CT GDPT 2018):</strong>
          Phần I tính <strong>0,25 điểm/câu</strong>; Phần II tính lũy tiến theo số ý đúng trong mỗi câu (1 ý = <strong>0,1đ</strong>, 2 ý = <strong>0,25đ</strong>, 3 ý = <strong>0,5đ</strong>, 4 ý = <strong>1,0đ</strong>); Phần III tính <strong>0,25 điểm/câu</strong>.
        </div>

        <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap;">
          <button type="button" class="btn btn-primary" id="btn-retake-mock">↻ Làm lại đề này</button>
          <button type="button" class="btn btn-secondary" id="btn-back-lobby">← Về danh sách Phòng luyện tập</button>
        </div>
      </div>

      <!-- Detailed Answer Review -->
      <div class="mock-review-list">
        ${
          c.mcq.length
            ? `
              <div class="mock-section-banner"><strong>PHẦN I · Chi tiết chấm bài &amp; Đáp án gợi ý</strong></div>
              ${c.mcq
                .map((q, idx) => {
                  const r = mcqMap[q.id] || {};
                  const uIdx = r.user_answer;
                  const cIdx = r.correct_index;
                  const ok = r.is_correct;
                  return `
                    <div class="card mock-q-card ${ok ? "res-correct" : "res-wrong"}">
                      <div class="mock-ed-qhead">
                        <span class="mock-q-num">Câu ${idx + 1}.</span>
                        <span class="pill ${ok ? "pill-emerald" : "pill-danger"}">
                          ${ok ? `✓ Đúng (+0,25đ)` : `✕ Sai (0đ) · Đáp án đúng: ${cIdx !== null && cIdx !== undefined ? LETTERS[cIdx] : "Chưa có"}`}
                        </span>
                      </div>
                      <div style="white-space:pre-line;margin-bottom:8px;">${formatBioHtml(q.question)}</div>
                      ${(q.images || []).map((im) => `<div class="mock-q-img-wrap"><img src="${im}" alt="" /></div>`).join("")}
                      ${renderTablesHtml(q.tables)}
                      <div class="mock-mcq-options">
                        ${(q.options || [])
                          .map((opt, oi) => {
                            let cls = "";
                            if (oi === cIdx) cls = "opt-correct";
                            else if (oi === uIdx && oi !== cIdx) cls = "opt-wrong";
                            return `
                              <div class="mock-mcq-opt readonly ${cls}">
                                <span class="mock-opt-letter">${LETTERS[oi]}</span>
                                <span class="mock-opt-text">${formatBioHtml(opt)}</span>
                                ${oi === uIdx ? `<span class="mock-pick-tag">Em chọn</span>` : ""}
                                ${oi === cIdx ? `<span class="mock-key-tag">Đáp án đúng</span>` : ""}
                              </div>
                            `;
                          })
                          .join("")}
                      </div>
                      <div class="mock-suggestion-box">
                        <strong>💡 Đáp án gợi ý:</strong>
                        ${
                          cIdx !== null && cIdx !== undefined
                            ? `Chọn phương án <strong>${LETTERS[cIdx]}</strong>.`
                            : ""
                        }
                        ${q.explanation ? `<div style="margin-top:4px;white-space:pre-line;">${formatBioHtml(q.explanation)}</div>` : ""}
                      </div>
                    </div>
                  `;
                })
                .join("")}
            `
            : ""
        }

        ${
          c.true_false.length
            ? `
              <div class="mock-section-banner"><strong>PHẦN II · Chi tiết chấm bài Đúng / Sai &amp; Đáp án gợi ý</strong></div>
              ${c.true_false
                .map((q, idx) => {
                  const r = tfMap[q.id] || {};
                  const stResMap = Object.fromEntries((r.statements || []).map((s) => [s.key, s]));
                  return `
                    <div class="card mock-q-card ${r.right_statements === r.total_statements ? "res-correct" : ""}">
                      <div class="mock-ed-qhead">
                        <span class="mock-q-num">Câu ${idx + 1}.</span>
                        <span class="pill ${r.points >= 0.5 ? "pill-emerald" : "pill-amber"}">
                          Đúng ${r.right_statements || 0}/${r.total_statements || 4} ý (+${formatScoreVN(r.points)}đ)
                        </span>
                      </div>
                      <div style="white-space:pre-line;margin-bottom:8px;">${formatBioHtml(q.question)}</div>
                      ${(q.images || []).map((im) => `<div class="mock-q-img-wrap"><img src="${im}" alt="" /></div>`).join("")}
                      ${renderTablesHtml(q.tables)}
                      <div class="mock-tf-list">
                        ${(q.statements || [])
                          .map((stItem) => {
                            const sr = stResMap[stItem.key] || {};
                            const uTxt = sr.user_answer === true ? "Đúng" : sr.user_answer === false ? "Sai" : "Bỏ trống";
                            const cTxt = sr.correct_answer === true ? "Đúng" : sr.correct_answer === false ? "Sai" : "Chưa có";
                            return `
                              <div class="mock-tf-item ${sr.is_correct ? "tf-ok" : "tf-bad"}">
                                <div class="mock-tf-text"><strong>${escapeHtml(stItem.key)})</strong> ${formatBioHtml(stItem.text)}</div>
                                <div style="display:flex;gap:8px;align-items:center;flex-shrink:0;font-size:0.8rem;">
                                  <span>Em chọn: <strong>${uTxt}</strong></span>
                                  <span class="pill ${sr.is_correct ? "pill-emerald" : "pill-danger"}">Đáp án: ${cTxt}</span>
                                </div>
                              </div>
                            `;
                          })
                          .join("")}
                      </div>
                      ${
                        q.explanation
                          ? `<div class="mock-suggestion-box"><strong>💡 Đáp án gợi ý:</strong><div style="margin-top:4px;white-space:pre-line;">${formatBioHtml(q.explanation)}</div></div>`
                          : ""
                      }
                    </div>
                  `;
                })
                .join("")}
            `
            : ""
        }

        ${
          c.short_answer.length
            ? `
              <div class="mock-section-banner"><strong>PHẦN III · Chi tiết chấm bài Trả lời ngắn &amp; Đáp án gợi ý</strong></div>
              ${c.short_answer
                .map((q, idx) => {
                  const r = saMap[q.id] || {};
                  const ok = r.is_correct;
                  const acc = (r.accepted_answers || q.accepted_answers || []).join(" / ");
                  return `
                    <div class="card mock-q-card ${ok ? "res-correct" : "res-wrong"}">
                      <div class="mock-ed-qhead">
                        <span class="mock-q-num">Câu ${idx + 1}.</span>
                        <span class="pill ${ok ? "pill-emerald" : "pill-danger"}">${ok ? "✓ Đúng (+0,25đ)" : "✕ Chưa đúng (0đ)"}</span>
                      </div>
                      <div style="white-space:pre-line;margin-bottom:8px;">${formatBioHtml(q.question)}</div>
                      ${(q.images || []).map((im) => `<div class="mock-q-img-wrap"><img src="${im}" alt="" /></div>`).join("")}
                      ${renderTablesHtml(q.tables)}
                      <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;font-size:0.88rem;">
                        <div>Bài làm của em: <strong style="color:${ok ? "#047857" : "#dc2626"};">${escapeHtml(r.user_answer || "(Bỏ trống)")}</strong></div>
                        <div>Đáp án chuẩn: <strong style="color:#047857;">${escapeHtml(acc || "Chưa cập nhật")}</strong></div>
                      </div>
                      <div class="mock-suggestion-box">
                        <strong>💡 Đáp án gợi ý:</strong> <strong>${escapeHtml(acc || "—")}</strong>
                        ${q.explanation ? `<div style="margin-top:4px;white-space:pre-line;">${formatBioHtml(q.explanation)}</div>` : ""}
                      </div>
                    </div>
                  `;
                })
                .join("")}
            `
            : ""
        }
      </div>
    `;

    document.getElementById("btn-retake-mock")?.addEventListener("click", async () => {
      try {
        const res = await api.getMockExam(ex.id, false);
        startExamSession(res.exam);
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    document.getElementById("btn-back-lobby")?.addEventListener("click", async () => {
      st.resultData = null;
      st.view = "lobby";
      await loadExamsList();
    });
  }

  // ================== VIEW 5: ATTEMPTS SCOREBOARD (ADMIN / TEACHER) ==================
  function renderAttempts() {
    const ex = st.attemptsExam;
    container.innerHTML = `
      <div class="card" style="padding:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;">
          <div>
            <div class="mock-hero-kicker">BẢNG ĐIỂM &amp; LỊCH SỬ LÀM BÀI</div>
            <h2 style="margin:2px 0 0;font-size:1.18rem;">
              ${escapeHtml(ex?.header_label || "PHÒNG LUYỆN TẬP")} — ${escapeHtml(ex?.title || `Đề số ${ex?.order_number || ""}`)}
            </h2>
          </div>
          <button type="button" class="btn btn-secondary btn-sm" id="btn-att-back">← Quay lại danh sách đề</button>
        </div>

        ${
          st.attemptsList.length === 0
            ? `<p style="color:var(--text-secondary);">Chưa có học sinh nào nộp bài cho đề này.</p>`
            : `
              <div class="data-table-wrap">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>STT</th>
                      <th>Học sinh / Tài khoản</th>
                      <th>Lớp</th>
                      <th>Bắt đầu</th>
                      <th>Thời gian làm</th>
                      <th>Phần I / II / III</th>
                      <th>Tổng điểm</th>
                      <th>Chi tiết</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${st.attemptsList
                      .map(
                        (a, i) => `
                        <tr>
                          <td>${i + 1}</td>
                          <td><strong>${escapeHtml(a.full_name)}</strong> <span style="color:var(--text-muted);font-size:0.78rem;">(@${escapeHtml(a.username)})</span></td>
                          <td>${escapeHtml(a.class_name || "—")}</td>
                          <td style="font-size:0.8rem;">${formatDateTimeVN(a.started_at)}</td>
                          <td>${formatDuration(a.duration_seconds)}</td>
                          <td style="font-size:0.8rem;">${formatScoreVN(a.part1_score)} / ${formatScoreVN(a.part2_score)} / ${formatScoreVN(a.part3_score)}</td>
                          <td><strong style="color:var(--primary);font-size:0.95rem;">${formatScoreVN(a.score)} / ${formatScoreVN(a.max_score)}</strong></td>
                          <td><button type="button" class="btn btn-secondary btn-sm" data-open-att="${a.id}">Xem bài</button></td>
                        </tr>
                      `
                      )
                      .join("")}
                  </tbody>
                </table>
              </div>
            `
        }
      </div>
    `;

    document.getElementById("btn-att-back")?.addEventListener("click", () => {
      st.view = "lobby";
      render();
    });

    container.querySelectorAll("[data-open-att]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const res = await api.getMockExamAttemptDetail(Number(btn.dataset.openAtt));
          st.resultData = {
            exam: res.exam,
            result: res.result,
            started_at: res.attempt.started_at,
            submitted_at: res.attempt.submitted_at,
            duration_seconds: res.attempt.duration_seconds,
            reviewerName: res.attempt.full_name,
          };
          st.view = "result";
          render();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });
  }

  function render() {
    if (st.view === "lobby") renderLobby();
    else if (st.view === "editor") renderEditor();
    else if (st.view === "taking") renderTaking();
    else if (st.view === "result") renderResult();
    else if (st.view === "attempts") renderAttempts();
  }

  loadExamsList();
}
