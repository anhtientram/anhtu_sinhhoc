// Cửa sổ Xem trước trực quan Chủ đề mới (mô phỏng y nguyên giao diện thật của Web App)

import { withBase } from "./api.js";
import { escapeHtml, formatBioHtml } from "./format.js";

function renderPreviewTable(rows) {
  if (!rows || !rows.length) return "";
  const [hdr, ...body] = rows;
  return `
    <div class="data-table-wrap" style="margin:10px 0;">
      <table class="data-table">
        <thead><tr>${hdr.map((c) => `<th>${formatBioHtml(c)}</th>`).join("")}</tr></thead>
        <tbody>
          ${body.map((r) => `<tr>${r.map((c) => `<td>${formatBioHtml(c)}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPreviewBlocks(blocks) {
  if (!blocks || !blocks.length) return "";
  return blocks
    .map((b) => {
      if (b.type === "image") {
        return `
          <figure class="lesson-hero-figure" style="margin:10px 0;">
            <img src="${withBase(b.src)}" alt="Hình minh họa" loading="lazy" />
            ${b.caption ? `<figcaption>${formatBioHtml(b.caption)}</figcaption>` : ""}
          </figure>
        `;
      }
      if (b.type === "table") {
        return renderPreviewTable(b.rows);
      }
      const html = formatBioHtml(b.text || "");
      if (b.is_bold) return `<p class="prose-p-bold">${html}</p>`;
      if (/^[-–+•]\s*/.test(b.text || "")) return `<p class="prose-bullet">${html}</p>`;
      return `<p class="prose-p">${html}</p>`;
    })
    .join("");
}

export function openTopicPreviewModal(topicObj, opts = {}) {
  const onPublish = opts.onPublish || null;
  const publishLabel = opts.publishLabel || "Cập nhật & Đẩy lên dữ liệu";

  const backdrop = document.createElement("div");
  backdrop.className = "preview-modal-backdrop";
  backdrop.id = "topic-preview-modal";

  let activeTab = "theory"; // 'theory' | 'knowledge' | 'review'
  let activeLessonIdx = 0;
  let activeUnitIdx = 0;
  let activeQuizPart = "mcq";
  let publishing = false;

  const num = Number(topicObj.order_index || 5);
  const themeCls = `topic-theme-${((num - 1) % 8) + 1}`;
  const shortTitle = (topicObj.title || "").replace(/^Chủ đề\s*\d+[\.\:]?\s*/i, "");
  const lessons = topicObj.lessons || [];
  const ks = topicObj.knowledge_system || {};
  const units = ks.units || [];
  const rev = topicObj.review || { mcq: [], true_false: [], short_answer: [] };
  const lvLabels = { nhan_biet: "Nhận biết", thong_hieu: "Hiểu", van_dung: "Vận dụng" };

  function closeModal() {
    backdrop.remove();
    document.removeEventListener("keydown", onEsc);
  }

  function onEsc(e) {
    if (e.key === "Escape") closeModal();
  }
  document.addEventListener("keydown", onEsc);

  function renderTheory() {
    if (!lessons.length) {
      return `<div class="empty-state"><div class="empty-state-title">Chưa có bài học lý thuyết trong bản xem trước</div></div>`;
    }
    const ls = lessons[activeLessonIdx] || lessons[0];
    return `
      <div class="lesson-tabs-bar">
        ${lessons
          .map(
            (l, i) => `
            <button type="button" class="lesson-pill-tab ${i === activeLessonIdx ? "active" : ""}" data-prev-ls="${i}">
              ${escapeHtml(l.number)}: ${escapeHtml(l.title)}
            </button>
          `
          )
          .join("")}
      </div>
      <article class="card prose-article">
        <div style="margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--border);">
          <span class="pill pill-primary">${escapeHtml(ls.number)}</span>
          <h2 style="margin:6px 0 0;font-size:1.18rem;">${formatBioHtml(ls.title)}</h2>
        </div>
        ${(ls.sections || [])
          .map((sec) => {
            const isYccd = /yêu cầu cần đạt/i.test(sec.heading || "");
            return `
              <section class="theory-section ${isYccd ? "yccd-box" : ""}">
                <h3>${formatBioHtml(sec.heading)}</h3>
                ${
                  (sec.blocks || []).length
                    ? renderPreviewBlocks(sec.blocks)
                    : `<ul style="margin:0;padding-left:20px;">${(sec.points || []).map((p) => `<li>${formatBioHtml(p)}</li>`).join("")}</ul>`
                }
              </section>
            `;
          })
          .join("")}
      </article>
    `;
  }

  function renderKnowledge() {
    const branches = ks.mindmap?.branches || [];
    const flashcards = ks.flashcards || [];
    return `
      <div style="display:flex;flex-direction:column;gap:16px;">
        ${
          units.length
            ? `
              <div class="lesson-tabs-bar">
                ${units
                  .map(
                    (u, i) => `
                    <button type="button" class="lesson-pill-tab ${i === activeUnitIdx ? "active" : ""}" data-prev-unit="${i}">
                      ${escapeHtml(u.lesson_number)}: ${escapeHtml(u.lesson_title)}
                    </button>
                  `
                  )
                  .join("")}
              </div>
              <article class="card prose-article">
                <h3 class="card-title">${escapeHtml(units[activeUnitIdx]?.lesson_number || "")}: ${formatBioHtml(units[activeUnitIdx]?.lesson_title || "")}</h3>
                ${renderPreviewBlocks(units[activeUnitIdx]?.blocks || [])}
              </article>
            `
            : ""
        }
        ${
          branches.length
            ? `
              <div class="card">
                <h3 class="card-title">Sơ đồ hệ thống hóa (${branches.length} nhánh)</h3>
                <div class="mindmap-grid">
                  ${branches
                    .map(
                      (br) => `
                      <div class="mindmap-branch">
                        <div class="mindmap-branch-head"><span>${formatBioHtml(br.title)}</span></div>
                        <div class="mindmap-branch-body">
                          <ul>${(br.nodes || []).slice(0, 5).map((n) => `<li>${formatBioHtml(n)}</li>`).join("")}</ul>
                        </div>
                      </div>
                    `
                    )
                    .join("")}
                </div>
              </div>
            `
            : `<div class="empty-state"><div class="empty-state-title">Chưa có dữ liệu Hệ thống kiến thức</div></div>`
        }
        ${
          flashcards.length
            ? `
              <div class="card">
                <h3 class="card-title">Thẻ ghi nhớ tự tạo (${flashcards.length} thẻ)</h3>
                <div class="flashcard-grid">
                  ${flashcards
                    .slice(0, 6)
                    .map(
                      (fc) => `
                      <div class="flashcard" style="cursor:default;">
                        <div style="font-weight:700;font-size:0.86rem;">${formatBioHtml(fc.front)}</div>
                        <div style="font-size:0.8rem;color:var(--text-secondary);margin-top:8px;">${formatBioHtml(fc.back)}</div>
                      </div>
                    `
                    )
                    .join("")}
                </div>
              </div>
            `
            : ""
        }
      </div>
    `;
  }

  function renderReview() {
    const mcq = rev.mcq || [];
    const tf = rev.true_false || [];
    const sa = rev.short_answer || [];
    const total = mcq.length + tf.length + sa.length;
    if (!total) {
      return `<div class="empty-state"><div class="empty-state-title">File chưa có câu hỏi ôn tập (có thể thêm sau ở mục Thêm câu hỏi mới)</div></div>`;
    }
    return `
      <div class="segmented" style="margin-bottom:14px;">
        <button type="button" class="seg-btn ${activeQuizPart === "mcq" ? "active" : ""}" data-prev-q="mcq">3.1 Trắc nghiệm 4 đáp án (${mcq.length})</button>
        <button type="button" class="seg-btn ${activeQuizPart === "true_false" ? "active" : ""}" data-prev-q="true_false">3.2 Đúng / Sai (${tf.length})</button>
        <button type="button" class="seg-btn ${activeQuizPart === "short_answer" ? "active" : ""}" data-prev-q="short_answer">3.3 Trả lời ngắn (${sa.length})</button>
      </div>
      ${
        activeQuizPart === "mcq"
          ? mcq
              .slice(0, 8)
              .map(
                (q, i) => `
                <div class="question-card">
                  <div class="q-header">
                    <span class="q-num">Câu ${i + 1} · ${escapeHtml(q.lesson || "")}</span>
                    <span class="pill pill-muted">${lvLabels[q.cognitive_level] || "Hiểu"}</span>
                  </div>
                  <div class="q-stem">${formatBioHtml(q.question)}</div>
                  <div class="option-list">
                    ${(q.options || [])
                      .map(
                        (o, oi) =>
                          `<div class="option-btn" style="cursor:default;"><strong>${"ABCD"[oi]}.</strong><span>${formatBioHtml(o)}</span></div>`
                      )
                      .join("")}
                  </div>
                </div>
              `
              )
              .join("") + (mcq.length > 8 ? `<p style="text-align:center;color:var(--text-muted);font-size:0.84rem;">... và ${mcq.length - 8} câu hỏi khác đã sẵn sàng.</p>` : "")
          : activeQuizPart === "true_false"
          ? tf
              .slice(0, 6)
              .map(
                (q, i) => `
                <div class="question-card">
                  <div class="q-header">
                    <span class="q-num">Câu ${i + 1} · ${escapeHtml(q.lesson || "")}</span>
                    <span class="pill pill-muted">${lvLabels[q.cognitive_level] || "Hiểu"}</span>
                  </div>
                  <div class="q-stem">${formatBioHtml(q.stem)}</div>
                  ${(q.statements || [])
                    .map((st) => `<div class="tf-row"><div><strong>${escapeHtml(st.key)})</strong> ${formatBioHtml(st.text)}</div><span class="pill pill-muted">Đúng / Sai</span></div>`)
                    .join("")}
                </div>
              `
              )
              .join("")
          : sa
              .slice(0, 8)
              .map(
                (q, i) => `
                <div class="question-card">
                  <div class="q-header">
                    <span class="q-num">Câu ${i + 1} · ${escapeHtml(q.lesson || "")}</span>
                    <span class="pill pill-muted">${lvLabels[q.cognitive_level] || "Hiểu"}</span>
                  </div>
                  <div class="q-stem">${formatBioHtml(q.question)}</div>
                </div>
              `
              )
              .join("")
      }
    `;
  }

  function draw() {
    backdrop.innerHTML = `
      <div class="preview-modal" role="dialog" aria-modal="true" aria-label="Xem trước giao diện Chủ đề mới">
        <div class="preview-modal-header">
          <div>
            <span class="pill pill-primary">Xem trước trực tiếp giao diện Chủ đề mới (chưa lưu vào CSDL)</span>
            <h2 style="margin:4px 0 0;font-size:1.1rem;">${escapeHtml(topicObj.title)}</h2>
          </div>
          <button type="button" class="btn btn-ghost btn-sm" id="prev-close-top">Đóng ✕</button>
        </div>

        <div class="preview-modal-body">
          <div style="display:grid;grid-template-columns:230px minmax(0,1fr);gap:18px;align-items:start;">
            <div>
              <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px;">
                Thẻ hiển thị cột trái
              </div>
              <div class="topic-color-card ${themeCls} active" style="cursor:default;">
                <span class="topic-color-badge">Chủ đề ${num}</span>
                <span class="topic-color-title">${escapeHtml(shortTitle || topicObj.title)}</span>
              </div>
              <div class="card" style="margin-top:12px;padding:12px 14px;font-size:0.82rem;color:var(--text-secondary);">
                <div><strong>${lessons.length}</strong> bài lý thuyết</div>
                <div><strong>${units.length}</strong> phiếu hệ thống kiến thức</div>
                <div><strong>${(rev.mcq || []).length}</strong> câu 4 đáp án</div>
                <div><strong>${(rev.true_false || []).length}</strong> câu Đúng/Sai</div>
                <div><strong>${(rev.short_answer || []).length}</strong> câu Trả lời ngắn</div>
              </div>
            </div>

            <div style="min-width:0;">
              <nav class="center-tabs-bar" style="justify-content:flex-start;margin-bottom:16px;">
                <button type="button" class="center-tab-card ctab-theory ${activeTab === "theory" ? "active" : ""}" data-prev-tab="theory">1. Lý thuyết</button>
                <button type="button" class="center-tab-card ctab-knowledge ${activeTab === "knowledge" ? "active" : ""}" data-prev-tab="knowledge">2. Hệ thống kiến thức</button>
                <button type="button" class="center-tab-card ctab-review ${activeTab === "review" ? "active" : ""}" data-prev-tab="review">3. Hệ thống ôn tập</button>
              </nav>
              ${activeTab === "theory" ? renderTheory() : activeTab === "knowledge" ? renderKnowledge() : renderReview()}
            </div>
          </div>
        </div>

        <div class="preview-modal-footer">
          <span style="font-size:0.83rem;color:var(--text-muted);">
            Giao diện, đánh số đề mục (${num}.1, ${num}.2...) và thẻ màu tương phản khớp 100% với các Chủ đề hiện có.
          </span>
          <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <button type="button" class="btn btn-secondary" id="prev-close-btn">Đóng xem trước</button>
            ${
              onPublish
                ? `<button type="button" class="btn btn-primary" id="prev-publish-btn" ${publishing ? "disabled" : ""}>
                     ${publishing ? "Đang lưu & đẩy lên hệ thống..." : publishLabel}
                   </button>`
                : ""
            }
          </div>
        </div>
      </div>
    `;

    backdrop.querySelector("#prev-close-top")?.addEventListener("click", closeModal);
    backdrop.querySelector("#prev-close-btn")?.addEventListener("click", closeModal);
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeModal();
    });

    backdrop.querySelectorAll("[data-prev-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTab = btn.dataset.prevTab;
        draw();
      });
    });
    backdrop.querySelectorAll("[data-prev-ls]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeLessonIdx = Number(btn.dataset.prevLs);
        draw();
      });
    });
    backdrop.querySelectorAll("[data-prev-unit]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeUnitIdx = Number(btn.dataset.prevUnit);
        draw();
      });
    });
    backdrop.querySelectorAll("[data-prev-q]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeQuizPart = btn.dataset.prevQ;
        draw();
      });
    });

    backdrop.querySelector("#prev-publish-btn")?.addEventListener("click", async () => {
      if (!onPublish || publishing) return;
      publishing = true;
      draw();
      try {
        await onPublish(topicObj);
        closeModal();
      } catch {
        publishing = false;
        draw();
      }
    });
  }

  document.body.appendChild(backdrop);
  draw();
}
