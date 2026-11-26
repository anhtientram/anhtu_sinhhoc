// Hệ thống Ôn tập Sinh học 12 (3.1 Trắc nghiệm 4 đáp án · 3.2 Đúng/Sai · 3.3 Trả lời ngắn)
// Thang điểm chuẩn:
// - 3.1 Trắc nghiệm 4 đáp án: 0,25 điểm / câu đúng
// - 3.2 Trắc nghiệm Đúng/Sai: 1 ý = 0,1đ · 2 ý = 0,25đ · 3 ý = 0,5đ · 4 ý = 1,0đ
// - 3.3 Trắc nghiệm trả lời ngắn: 0,25 điểm / câu đúng (giá trị số tối đa 4 ký tự: số, dấu âm -, dấu phẩy ,)

import { api, clientCache, formatDateTimeVN, formatDuration, withBase } from "./api.js";
import { escapeHtml, formatBioHtml } from "./format.js";

const LEVEL_MAP = {
  nhan_biet: { label: "Nhận biết", cls: "pill-muted" },
  thong_hieu: { label: "Hiểu", cls: "pill-primary" },
  van_dung: { label: "Vận dụng", cls: "pill-amber" },
};

function sanitizeShortAnswerInput(raw) {
  let s = String(raw || "").replace(/\./g, ",").replace(/[^0-9,\-]/g, "");
  // Dấu âm chỉ được đứng ở đầu
  if (s.includes("-")) {
    const neg = s.startsWith("-");
    s = (neg ? "-" : "") + s.replace(/-/g, "");
  }
  // Chỉ giữ tối đa 1 dấu phẩy
  const firstComma = s.indexOf(",");
  if (firstComma >= 0) {
    s = s.slice(0, firstComma + 1) + s.slice(firstComma + 1).replace(/,/g, "");
  }
  return s.slice(0, 4);
}

function normalizeShortAnswer(str) {
  const s = String(str || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/,/g, ".")
    .replace(/%$/g, "");
  if (!s) return "";
  // Chuẩn hóa số thập phân (vd: 0.50 -> 0.5, -2.0 -> -2)
  if (/^-?\d+(\.\d+)?$/.test(s)) {
    const n = Number(s);
    if (!Number.isNaN(n)) return String(n);
  }
  return s;
}

function gradeTrueFalseProgressive(correctStatementsCount) {
  const map = { 0: 0, 1: 0.1, 2: 0.25, 3: 0.5, 4: 1.0 };
  return map[correctStatementsCount] ?? 0;
}

function fisherYatesShuffle(arr) {
  const copy = [...arr];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function prepareMcqForDisplay(q, shuffleOptions = false) {
  const opts = [...(q.options || [])];
  if (!shuffleOptions || opts.length < 2) {
    return { ...q, _displayOptions: opts, _displayCorrectIdx: q.correct_index };
  }
  // Không trộn nếu đáp án chứa "Cả A và B" / "Tất cả đều đúng"
  const hasRef = opts.some((o) => /(cả\s*[a-d]|tất\s*cả\s*(?:các|đều))/i.test(o));
  if (hasRef) {
    return { ...q, _displayOptions: opts, _displayCorrectIdx: q.correct_index };
  }
  const indexed = fisherYatesShuffle(opts.map((text, oldIdx) => ({ text, oldIdx })));
  let newCorrect = q.correct_index;
  if (q.correct_index !== null && q.correct_index !== undefined) {
    newCorrect = indexed.findIndex((x) => x.oldIdx === q.correct_index);
  }
  return {
    ...q,
    _displayOptions: indexed.map((x) => x.text),
    _displayCorrectIdx: newCorrect,
  };
}

function renderQuestionMedia(q) {
  let html = "";
  if (q.images && q.images.length) {
    html += `
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin:10px 0;">
        ${q.images
          .map(
            (src) => `
            <figure class="lesson-hero-figure" style="margin:0;max-width:440px;">
              <img src="${withBase(src)}" alt="Hình minh họa câu hỏi" loading="lazy" style="max-height:280px;" />
            </figure>
          `
          )
          .join("")}
      </div>
    `;
  }
  if (q.tables && q.tables.length) {
    html += q.tables
      .map((rows) => {
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
      })
      .join("");
  }
  return html;
}

export function mountQuizSection(container, topic, user, showToast, opts = {}) {
  const canEditKeys = Boolean(opts.canEditKeys);
  const onTopicUpdated = opts.onTopicUpdated || (() => {});
  const review = topic.review || { mcq: [], true_false: [], short_answer: [] };
  const lessons = topic.lessons || [];

  let activeMode = "mcq";
  let lessonFilter = "all";
  let batchLimit = 20;
  let answers = { mcq: {}, true_false: {}, short_answer: {} };
  let submitted = false;
  let resultSummary = null;
  let startTime = Date.now();
  let recentAttempts = [];
  let keyEditMode = false;
  let shuffleCount = 0;

  // Bộ câu hỏi đang hiển thị (được giữ cố định trong phiên làm bài và trộn mới hoàn toàn khi bấm "Làm mới câu hỏi")
  let activeLists = { mcq: [], true_false: [], short_answer: [] };

  function filterByLesson(list) {
    return lessonFilter === "all"
      ? list || []
      : (list || []).filter((q) => q.lesson_id === lessonFilter || q.lesson === lessonFilter);
  }

  function buildActiveLists(shouldShuffle = false) {
    let mcqPool = filterByLesson(review.mcq);
    let tfPool = filterByLesson(review.true_false);
    let saPool = filterByLesson(review.short_answer);

    if (shouldShuffle) {
      mcqPool = fisherYatesShuffle(mcqPool);
      tfPool = fisherYatesShuffle(tfPool);
      saPool = fisherYatesShuffle(saPool);
    }

    if (activeMode === "combined") {
      const mcqPick = batchLimit > 0 ? mcqPool.slice(0, Math.min(18, batchLimit)) : mcqPool;
      const tfPick = batchLimit > 0 ? tfPool.slice(0, 4) : tfPool;
      const saPick = batchLimit > 0 ? saPool.slice(0, 6) : saPool;
      activeLists = {
        mcq: mcqPick.map((q) => prepareMcqForDisplay(q, shouldShuffle && !keyEditMode)),
        true_false: tfPick,
        short_answer: saPick,
      };
    } else {
      const lim = (arr) => (batchLimit > 0 ? arr.slice(0, batchLimit) : arr);
      activeLists = {
        mcq: activeMode === "mcq" ? lim(mcqPool).map((q) => prepareMcqForDisplay(q, shouldShuffle && !keyEditMode)) : [],
        true_false: activeMode === "true_false" ? lim(tfPool) : [],
        short_answer: activeMode === "short_answer" ? lim(saPool) : [],
      };
    }
  }

  async function loadAttempts(force = false) {
    if (!force) {
      const cached = clientCache.getAttempts(topic.id);
      if (cached) {
        recentAttempts = cached;
        renderHistoryBlock();
        return;
      }
    }
    try {
      const res = await api.myQuizAttempts(topic.id);
      recentAttempts = res.attempts || [];
      clientCache.setAttempts(topic.id, recentAttempts);
      renderHistoryBlock();
    } catch {}
  }

  function resetAttempt(newMode = activeMode, shouldShuffle = false) {
    activeMode = newMode;
    answers = { mcq: {}, true_false: {}, short_answer: {} };
    submitted = false;
    resultSummary = null;
    startTime = Date.now();
    if (shouldShuffle) shuffleCount += 1;
    buildActiveLists(shouldShuffle);
    render();
    if (shouldShuffle) {
      const count = activeLists.mcq.length + activeLists.true_false.length + activeLists.short_answer.length;
      showToast(`Đã làm mới và trộn ngẫu nhiên ${count} câu hỏi!`, "success");
    }
  }

  async function saveTopicKeysToServer(msg) {
    try {
      const res = await api.updateTopic(topic.id, topic);
      onTopicUpdated(res.topic);
      showToast(msg || "Đã lưu chỉnh sửa câu hỏi.", "success");
      // Đồng bộ lại hiển thị sau khi lưu đáp án/mức độ
      buildActiveLists(false);
      render();
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function handleSubmit() {
    const durationSeconds = Math.max(1, Math.round((Date.now() - startTime) / 1000));
    const lists = activeLists;

    let score = 0;
    let maxScore = 0;
    let correctCount = 0;
    let totalGradable = 0;
    let answeredPendingCount = 0;

    // Phần 1: Trắc nghiệm 4 đáp án — 0,25 điểm / câu
    lists.mcq.forEach((q) => {
      const corrIdx = q._displayCorrectIdx !== undefined ? q._displayCorrectIdx : q.correct_index;
      const hasKey = q.answer_key_ready !== false && corrIdx !== null && corrIdx !== undefined && corrIdx >= 0;
      if (hasKey) {
        maxScore += 0.25;
        totalGradable += 1;
        if (answers.mcq[q.id] === corrIdx) {
          score += 0.25;
          correctCount += 1;
        }
      } else if (answers.mcq[q.id] !== undefined) {
        answeredPendingCount += 1;
      }
    });

    // Phần 2: Trắc nghiệm Đúng/Sai — 1 ý: 0,1đ; 2 ý: 0,25đ; 3 ý: 0,5đ; 4 ý: 1,0đ
    lists.true_false.forEach((q) => {
      const stmts = q.statements || [];
      const hasKey =
        q.answer_key_ready !== false &&
        stmts.length > 0 &&
        stmts.every((s) => s.answer !== null && s.answer !== undefined);
      if (hasKey) {
        maxScore += 1.0;
        let rightInStem = 0;
        stmts.forEach((st) => {
          totalGradable += 1;
          if (answers.true_false[`${q.id}:${st.key}`] === st.answer) {
            rightInStem += 1;
            correctCount += 1;
          }
        });
        score += gradeTrueFalseProgressive(rightInStem);
      } else {
        const anyFilled = stmts.some((st) => answers.true_false[`${q.id}:${st.key}`] !== undefined);
        if (anyFilled) answeredPendingCount += 1;
      }
    });

    // Phần 3: Trắc nghiệm trả lời ngắn — 0,25 điểm / câu
    lists.short_answer.forEach((q) => {
      const accepted = (q.accepted_answers || []).map(normalizeShortAnswer).filter(Boolean);
      const hasKey = q.answer_key_ready !== false && accepted.length > 0;
      const userNorm = normalizeShortAnswer(answers.short_answer[q.id]);
      if (hasKey) {
        maxScore += 0.25;
        totalGradable += 1;
        if (userNorm && accepted.includes(userNorm)) {
          score += 0.25;
          correctCount += 1;
        }
      } else if (userNorm) {
        answeredPendingCount += 1;
      }
    });

    score = Math.round(score * 100) / 100;
    maxScore = Math.round(maxScore * 100) / 100;
    submitted = true;
    resultSummary = { score, maxScore, correctCount, totalGradable, answeredPendingCount, durationSeconds };

    try {
      await api.submitQuiz({
        topic_id: topic.id,
        quiz_type: activeMode,
        score,
        max_score: maxScore || Math.max(1, answeredPendingCount),
        correct_count: correctCount,
        total_questions: totalGradable || answeredPendingCount,
        duration_seconds: durationSeconds,
        answers,
      });
      showToast(
        maxScore > 0 ? `Đã nộp bài: ${score}/${maxScore} điểm` : `Đã lưu bài làm (${answeredPendingCount} câu)`,
        "success"
      );
      clientCache.invalidateAttempts(topic.id);
      loadAttempts(true);
    } catch (err) {
      showToast(err.message, "error");
    }

    render();
    container.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderLevelBadge(q) {
    const lv = LEVEL_MAP[q.cognitive_level] || LEVEL_MAP.thong_hieu;
    return `<span class="pill ${lv.cls}">${lv.label}</span>`;
  }

  function renderLevelEditor(kind, q) {
    const cur = q.cognitive_level || "thong_hieu";
    return `
      <span style="margin-left:auto;display:inline-flex;align-items:center;gap:6px;">
        <small style="color:var(--amber);font-weight:600;">Mức độ:</small>
        <select class="form-control form-control-sm" style="width:auto;" data-set-level-kind="${kind}" data-set-level-id="${q.id}">
          <option value="nhan_biet" ${cur === "nhan_biet" ? "selected" : ""}>Nhận biết</option>
          <option value="thong_hieu" ${cur === "thong_hieu" ? "selected" : ""}>Hiểu</option>
          <option value="van_dung" ${cur === "van_dung" ? "selected" : ""}>Vận dụng</option>
        </select>
      </span>
    `;
  }

  function renderMcqList(list) {
    if (!list.length) return `<div class="empty-state"><div class="empty-state-title">Không có câu hỏi ở bộ lọc này</div></div>`;
    return `
      <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;font-size:1rem;">3.1. Trắc nghiệm 4 đáp án (${list.length} câu)</h3>
        <span class="pill pill-muted">0,25 điểm / câu đúng</span>
      </div>
      ${list
        .map((q, idx) => {
          const picked = answers.mcq[q.id];
          const opts = q._displayOptions || q.options || [];
          const corrIdx = q._displayCorrectIdx !== undefined ? q._displayCorrectIdx : q.correct_index;
          const hasKey = q.answer_key_ready !== false && corrIdx !== null && corrIdx !== undefined && corrIdx >= 0;
          return `
            <div class="question-card">
              <div class="q-header">
                <span class="q-num">Câu ${idx + 1} · ${escapeHtml(q.lesson || "")}</span>
                <div style="display:flex;gap:6px;align-items:center;">
                  ${renderLevelBadge(q)}
                  ${!hasKey ? `<span class="pill pill-muted">Chưa có đáp án</span>` : ""}
                </div>
              </div>
              <div class="q-stem">${formatBioHtml(q.question)}</div>
              ${renderQuestionMedia(q)}
              <div class="option-list">
                ${opts
                  .map((opt, optIdx) => {
                    let cls = "option-btn";
                    if (submitted && hasKey) {
                      if (optIdx === corrIdx) cls += " correct";
                      else if (optIdx === picked) cls += " wrong";
                    } else if (optIdx === picked) {
                      cls += " selected";
                    }
                    return `
                      <button class="${cls}" data-mcq="${q.id}" data-opt="${optIdx}" ${submitted ? "disabled" : ""}>
                        <strong>${String.fromCharCode(65 + optIdx)}.</strong>
                        <span>${formatBioHtml(opt)}</span>
                      </button>
                    `;
                  })
                  .join("")}
              </div>

              ${
                canEditKeys && keyEditMode
                  ? `
                    <div style="margin-top:10px;padding:8px 12px;border-radius:6px;background:var(--amber-soft);border:1px solid var(--amber-border);display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                      <span style="font-size:0.8rem;font-weight:600;color:var(--amber);">Đáp án chuẩn (gốc):</span>
                      ${(q.options || [])
                        .map(
                          (_, optIdx) => `
                          <button type="button" class="btn btn-sm ${q.correct_index === optIdx ? "btn-primary" : "btn-secondary"}"
                                  data-set-mcq-key="${q.id}" data-key-idx="${optIdx}">
                            ${String.fromCharCode(65 + optIdx)}
                          </button>
                        `
                        )
                        .join("")}
                      ${renderLevelEditor("mcq", q)}
                    </div>
                  `
                  : ""
              }

              ${
                submitted && hasKey
                  ? `<div class="explanation-box"><strong>Đáp án đúng: ${String.fromCharCode(65 + corrIdx)} (+${picked === corrIdx ? "0,25" : "0"}đ).</strong> ${formatBioHtml(q.explanation || "")}</div>`
                  : ""
              }
            </div>
          `;
        })
        .join("")}
    `;
  }

  function renderTrueFalseList(list) {
    if (!list.length) return `<div class="empty-state"><div class="empty-state-title">Không có câu hỏi Đúng/Sai ở bộ lọc này</div></div>`;
    return `
      <div style="margin:18px 0 12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;font-size:1rem;">3.2. Trắc nghiệm Đúng / Sai (${list.length} câu)</h3>
        <span class="pill pill-muted">1 ý: 0,1đ · 2 ý: 0,25đ · 3 ý: 0,5đ · 4 ý: 1,0đ</span>
      </div>
      ${list
        .map((q, idx) => {
          const stmts = q.statements || [];
          const hasKey =
            q.answer_key_ready !== false &&
            stmts.length > 0 &&
            stmts.every((s) => s.answer !== null && s.answer !== undefined);
          let rightCount = 0;
          if (submitted && hasKey) {
            stmts.forEach((st) => {
              if (answers.true_false[`${q.id}:${st.key}`] === st.answer) rightCount += 1;
            });
          }
          return `
            <div class="question-card">
              <div class="q-header">
                <span class="q-num">Câu ${idx + 1} · ${escapeHtml(q.lesson || "")}</span>
                <div style="display:flex;gap:6px;align-items:center;">
                  ${renderLevelBadge(q)}
                  ${
                    submitted && hasKey
                      ? `<span class="pill ${rightCount === stmts.length ? "pill-green" : "pill-amber"}">Đúng ${rightCount}/${stmts.length} ý (+${gradeTrueFalseProgressive(rightCount)}đ)</span>`
                      : !hasKey
                      ? `<span class="pill pill-muted">Chưa có đáp án</span>`
                      : ""
                  }
                </div>
              </div>
              <div class="q-stem">${formatBioHtml(q.stem)}</div>
              ${renderQuestionMedia(q)}
              ${stmts
                .map((st) => {
                  const key = `${q.id}:${st.key}`;
                  const val = answers.true_false[key];
                  const isCorrect = submitted && hasKey && val === st.answer;
                  return `
                    <div class="tf-row" style="${submitted && hasKey ? `border-color:${isCorrect ? "#16a34a" : "#dc2626"};background:${isCorrect ? "var(--green-soft)" : "var(--red-soft)"};` : ""}">
                      <div>
                        <strong>${escapeHtml(st.key)})</strong> ${formatBioHtml(st.text)}
                        ${
                          submitted && hasKey
                            ? `<div style="margin-top:4px;font-size:0.82rem;color:var(--text-secondary);"><strong>Đáp án: ${st.answer ? "Đúng" : "Sai"}</strong>${st.explanation ? ` — ${formatBioHtml(st.explanation)}` : ""}</div>`
                            : ""
                        }
                        ${
                          canEditKeys && keyEditMode
                            ? `
                              <div style="margin-top:6px;display:flex;gap:6px;align-items:center;">
                                <small style="color:var(--amber);font-weight:600;">Đáp án chuẩn:</small>
                                <button type="button" class="btn btn-sm ${st.answer === true ? "btn-primary" : "btn-secondary"}" data-set-tf-key="${q.id}" data-stmt-key="${st.key}" data-tf-val="true">Đúng</button>
                                <button type="button" class="btn btn-sm ${st.answer === false ? "btn-danger" : "btn-secondary"}" data-set-tf-key="${q.id}" data-stmt-key="${st.key}" data-tf-val="false">Sai</button>
                              </div>
                            `
                            : ""
                        }
                      </div>
                      <div class="tf-toggle-group">
                        <button class="tf-choice ${val === true ? "selected-true" : ""}" data-tf="${key}" data-val="true" ${submitted ? "disabled" : ""}>Đúng</button>
                        <button class="tf-choice ${val === false ? "selected-false" : ""}" data-tf="${key}" data-val="false" ${submitted ? "disabled" : ""}>Sai</button>
                      </div>
                    </div>
                  `;
                })
                .join("")}
              ${
                canEditKeys && keyEditMode
                  ? `
                    <div style="margin-top:10px;padding:8px 12px;border-radius:6px;background:var(--amber-soft);border:1px solid var(--amber-border);display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                      ${renderLevelEditor("true_false", q)}
                    </div>
                  `
                  : ""
              }
            </div>
          `;
        })
        .join("")}
    `;
  }

  function renderShortAnswerList(list) {
    if (!list.length) return `<div class="empty-state"><div class="empty-state-title">Không có câu hỏi Trả lời ngắn ở bộ lọc này</div></div>`;
    return `
      <div style="margin:18px 0 12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;font-size:1rem;">3.3. Trắc nghiệm trả lời ngắn (${list.length} câu)</h3>
        <span class="pill pill-muted">0,25 điểm / câu · Giá trị số tối đa 4 ký tự (số, -, ,)</span>
      </div>
      ${list
        .map((q, idx) => {
          const val = answers.short_answer[q.id] || "";
          const accepted = (q.accepted_answers || []).map(normalizeShortAnswer).filter(Boolean);
          const hasKey = q.answer_key_ready !== false && accepted.length > 0;
          const isCorrect = submitted && hasKey && accepted.includes(normalizeShortAnswer(val));
          return `
            <div class="question-card" style="${submitted && hasKey ? `border-color:${isCorrect ? "#16a34a" : "#dc2626"};` : ""}">
              <div class="q-header">
                <span class="q-num">Câu ${idx + 1} · ${escapeHtml(q.lesson || "")}</span>
                <div style="display:flex;gap:6px;align-items:center;">
                  ${renderLevelBadge(q)}
                  ${
                    submitted && hasKey
                      ? `<span class="pill ${isCorrect ? "pill-green" : "pill-red"}">${isCorrect ? "Đúng (+0,25đ)" : "Chưa đúng"}</span>`
                      : !hasKey
                      ? `<span class="pill pill-muted">Chưa có đáp án</span>`
                      : ""
                  }
                </div>
              </div>
              <div class="q-stem">${formatBioHtml(q.question)}</div>
              ${renderQuestionMedia(q)}
              <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:10px;">
                <input type="text" class="form-control" style="max-width:190px;font-weight:700;letter-spacing:0.12em;text-align:center;"
                       maxlength="4" inputmode="decimal"
                       placeholder="VD: 12,5"
                       value="${escapeHtml(val)}"
                       data-sa="${q.id}" ${submitted ? "disabled" : ""} />
                <span style="font-size:0.78rem;color:var(--text-muted);">Tối đa 4 ký tự gồm chữ số, dấu âm (-) và dấu phẩy (,)</span>
              </div>

              ${
                canEditKeys && keyEditMode
                  ? `
                    <div style="margin-top:10px;padding:8px 12px;border-radius:6px;background:var(--amber-soft);border:1px solid var(--amber-border);display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                      <span style="font-size:0.8rem;font-weight:600;color:var(--amber);">Đáp án chuẩn (tối đa 4 ký tự):</span>
                      <input type="text" class="form-control form-control-sm" style="max-width:140px;"
                             data-sa-key-input="${q.id}" value="${escapeHtml((q.accepted_answers || []).join("; "))}" />
                      <button type="button" class="btn btn-sm btn-primary" data-save-sa-key="${q.id}">Lưu</button>
                      ${renderLevelEditor("short_answer", q)}
                    </div>
                  `
                  : ""
              }

              ${
                submitted && hasKey
                  ? `<div class="explanation-box"><strong>Đáp án chuẩn: ${formatBioHtml((q.accepted_answers || [])[0] || "")}</strong>${q.explanation ? `<br/>${formatBioHtml(q.explanation)}` : ""}</div>`
                  : ""
              }
            </div>
          `;
        })
        .join("")}
    `;
  }

  function renderHistoryBlock() {
    const el = container.querySelector("#quiz-history-box");
    if (!el) return;
    if (!recentAttempts.length) {
      el.innerHTML = `<p style="color:var(--text-muted);margin:0;font-size:0.86rem;">Chưa có lượt nộp bài nào cho chủ đề này.</p>`;
      return;
    }
    const typeLabel = {
      mcq: "3.1 Trắc nghiệm 4 đáp án",
      true_false: "3.2 Đúng / Sai",
      short_answer: "3.3 Trả lời ngắn",
      combined: "Đề tổng hợp 3 phần",
    };
    el.innerHTML = `
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr><th>Phần ôn tập</th><th>Điểm số</th><th>Số câu/ý đúng</th><th>Thời gian làm</th><th>Thời điểm nộp</th></tr>
          </thead>
          <tbody>
            ${recentAttempts
              .slice(0, 8)
              .map(
                (a) => `
                <tr>
                  <td><strong>${typeLabel[a.quiz_type] || a.quiz_type}</strong></td>
                  <td><span class="pill pill-primary">${a.score} / ${a.max_score}</span></td>
                  <td>${a.correct_count} / ${a.total_questions}</td>
                  <td>${formatDuration(a.duration_seconds)}</td>
                  <td>${formatDateTimeVN(a.submitted_at)}</td>
                </tr>
              `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function render() {
    const mcqTotal = (review.mcq || []).length;
    const tfTotal = (review.true_false || []).length;
    const saTotal = (review.short_answer || []).length;
    const mcqKeyed = (review.mcq || []).filter((q) => q.answer_key_ready).length;
    const tfKeyed = (review.true_false || []).filter((q) => q.answer_key_ready).length;
    const saKeyed = (review.short_answer || []).filter((q) => q.answer_key_ready).length;
    const lists = activeLists;

    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Hệ thống ôn tập — ${formatBioHtml(topic.title)}</h1>
          <p>${mcqTotal + tfTotal + saTotal} câu hỏi · ${mcqKeyed + tfKeyed + saKeyed} câu có sẵn đáp án chấm tự động${shuffleCount > 0 ? ` · Đã trộn bộ đề #${shuffleCount}` : ""}</p>
        </div>
        ${
          canEditKeys
            ? `
              <button class="btn btn-sm ${keyEditMode ? "btn-primary" : "btn-secondary"}" id="toggle-key-edit">
                ${keyEditMode ? "Hoàn tất chỉnh sửa đáp án" : "Chỉnh sửa đáp án & mức độ"}
              </button>
            `
            : ""
        }
      </div>

      <div class="quiz-mode-strip">
        <button class="quiz-mode-tab ${activeMode === "mcq" ? "active" : ""}" data-qmode="mcq">
          <div class="pill pill-primary">3.1</div>
          <div class="quiz-mode-tab-title">Trắc nghiệm 4 đáp án</div>
          <div class="quiz-mode-tab-meta">${mcqTotal} câu · 0,25đ/câu</div>
        </button>

        <button class="quiz-mode-tab ${activeMode === "true_false" ? "active" : ""}" data-qmode="true_false">
          <div class="pill pill-muted">3.2</div>
          <div class="quiz-mode-tab-title">Trắc nghiệm Đúng / Sai</div>
          <div class="quiz-mode-tab-meta">${tfTotal} câu · tối đa 1,0đ/câu</div>
        </button>

        <button class="quiz-mode-tab ${activeMode === "short_answer" ? "active" : ""}" data-qmode="short_answer">
          <div class="pill pill-muted">3.3</div>
          <div class="quiz-mode-tab-title">Trả lời ngắn</div>
          <div class="quiz-mode-tab-meta">${saTotal} câu · 0,25đ/câu</div>
        </button>

        <button class="quiz-mode-tab ${activeMode === "combined" ? "active" : ""}" data-qmode="combined">
          <div class="pill pill-muted">Tổng hợp</div>
          <div class="quiz-mode-tab-title">Đề thi đủ 3 phần</div>
          <div class="quiz-mode-tab-meta">18 MCQ + 4 Đ/S + 6 TLN (10đ)</div>
        </button>
      </div>

      <div class="filter-bar">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <label style="font-size:0.82rem;font-weight:600;color:var(--text-muted);">Bài học:</label>
          <select id="quiz-lesson-filter" class="form-control form-control-sm" style="width:auto;min-width:210px;">
            <option value="all" ${lessonFilter === "all" ? "selected" : ""}>Tất cả các bài</option>
            ${lessons
              .map(
                (ls) =>
                  `<option value="${ls.id}" ${lessonFilter === ls.id ? "selected" : ""}>${escapeHtml(ls.number)}: ${escapeHtml(ls.title)}</option>`
              )
              .join("")}
          </select>

          <label style="font-size:0.82rem;font-weight:600;color:var(--text-muted);">Hiển thị:</label>
          <select id="quiz-batch-limit" class="form-control form-control-sm" style="width:auto;">
            <option value="10" ${batchLimit === 10 ? "selected" : ""}>10 câu</option>
            <option value="20" ${batchLimit === 20 ? "selected" : ""}>20 câu</option>
            <option value="50" ${batchLimit === 50 ? "selected" : ""}>50 câu</option>
            <option value="0" ${batchLimit === 0 ? "selected" : ""}>Tất cả</option>
          </select>
        </div>
        <button type="button" class="btn btn-soft btn-sm" id="quiz-reset-btn">Làm mới câu hỏi</button>
      </div>

      ${
        submitted && resultSummary
          ? `
            <div class="card" style="margin-bottom:18px;border-color:var(--primary-border);background:var(--surface-tint);">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;">
                <div>
                  <span class="pill pill-green">Đã lưu kết quả</span>
                  <h2 style="margin:6px 0 4px;font-size:1.18rem;">
                    ${
                      resultSummary.maxScore > 0
                        ? `Điểm số: ${resultSummary.score} / ${resultSummary.maxScore} điểm`
                        : `Đã ghi nhận ${resultSummary.answeredPendingCount} câu trả lời`
                    }
                  </h2>
                  <p style="margin:0;color:var(--text-secondary);font-size:0.86rem;">
                    ${resultSummary.maxScore > 0 ? `Đúng ${resultSummary.correctCount}/${resultSummary.totalGradable} câu/ý · ` : ""}
                    Thời gian làm bài: ${formatDuration(resultSummary.durationSeconds)}
                  </p>
                </div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                  <button type="button" class="btn btn-secondary btn-sm" id="quiz-retry-same-btn">Làm lại đề này</button>
                  <button type="button" class="btn btn-primary btn-sm" id="quiz-retry-btn">Làm mới câu hỏi</button>
                </div>
              </div>
            </div>
          `
          : ""
      }

      <div>
        ${activeMode === "mcq" || activeMode === "combined" ? renderMcqList(lists.mcq) : ""}
        ${activeMode === "true_false" || activeMode === "combined" ? renderTrueFalseList(lists.true_false) : ""}
        ${activeMode === "short_answer" || activeMode === "combined" ? renderShortAnswerList(lists.short_answer) : ""}
      </div>

      ${
        !submitted
          ? `
            <div style="display:flex;justify-content:flex-end;gap:10px;margin:20px 0 28px;">
              <button type="button" class="btn btn-primary btn-lg" id="quiz-submit-btn">Nộp bài &amp; Chấm điểm</button>
            </div>
          `
          : ""
      }

      <div class="card" style="margin-top:20px;">
        <h3 class="card-title">Lịch sử làm bài</h3>
        <div id="quiz-history-box">Đang tải...</div>
      </div>
    `;

    container.querySelectorAll("[data-qmode]").forEach((card) => {
      card.addEventListener("click", () => resetAttempt(card.dataset.qmode, false));
    });
    container.querySelector("#quiz-lesson-filter")?.addEventListener("change", (e) => {
      lessonFilter = e.target.value;
      resetAttempt(activeMode, false);
    });
    container.querySelector("#quiz-batch-limit")?.addEventListener("change", (e) => {
      batchLimit = Number(e.target.value);
      resetAttempt(activeMode, false);
    });
    container.querySelector("#toggle-key-edit")?.addEventListener("click", () => {
      keyEditMode = !keyEditMode;
      buildActiveLists(false);
      render();
    });

    container.querySelectorAll("[data-mcq]").forEach((btn) => {
      btn.addEventListener("click", () => {
        answers.mcq[btn.dataset.mcq] = Number(btn.dataset.opt);
        render();
      });
    });

    container.querySelectorAll("[data-tf]").forEach((btn) => {
      btn.addEventListener("click", () => {
        answers.true_false[btn.dataset.tf] = btn.dataset.val === "true";
        render();
      });
    });

    container.querySelectorAll("[data-sa]").forEach((inp) => {
      inp.addEventListener("input", () => {
        const clean = sanitizeShortAnswerInput(inp.value);
        if (inp.value !== clean) inp.value = clean;
        answers.short_answer[inp.dataset.sa] = clean;
      });
    });

    container.querySelectorAll("[data-set-mcq-key]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = (review.mcq || []).find((x) => x.id === btn.dataset.setMcqKey);
        if (!q) return;
        q.correct_index = Number(btn.dataset.keyIdx);
        q.answer_key_ready = true;
        saveTopicKeysToServer(`Đã lưu đáp án ${String.fromCharCode(65 + q.correct_index)}`);
      });
    });

    container.querySelectorAll("[data-set-tf-key]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = (review.true_false || []).find((x) => x.id === btn.dataset.setTfKey);
        if (!q) return;
        const st = (q.statements || []).find((s) => s.key === btn.dataset.stmtKey);
        if (!st) return;
        st.answer = btn.dataset.tfVal === "true";
        q.answer_key_ready = (q.statements || []).every((s) => s.answer !== null && s.answer !== undefined);
        saveTopicKeysToServer(`Đã lưu đáp án ý ${st.key})`);
      });
    });

    container.querySelectorAll("[data-save-sa-key]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = (review.short_answer || []).find((x) => x.id === btn.dataset.saveSaKey);
        const inp = container.querySelector(`[data-sa-key-input="${btn.dataset.saveSaKey}"]`);
        if (!q || !inp) return;
        const parts = inp.value
          .split(/[;|]/)
          .map((s) => sanitizeShortAnswerInput(s.trim()))
          .filter(Boolean);
        q.accepted_answers = parts;
        q.answer_key_ready = parts.length > 0;
        saveTopicKeysToServer("Đã lưu đáp án trả lời ngắn");
      });
    });

    container.querySelectorAll("[data-set-level-id]").forEach((sel) => {
      sel.addEventListener("change", () => {
        const kind = sel.dataset.setLevelKind;
        const q = (review[kind] || []).find((x) => x.id === sel.dataset.setLevelId);
        if (!q) return;
        q.cognitive_level = sel.value;
        saveTopicKeysToServer(`Đã cập nhật mức độ: ${(LEVEL_MAP[sel.value] || {}).label || sel.value}`);
      });
    });

    container.querySelector("#quiz-submit-btn")?.addEventListener("click", handleSubmit);
    // Nút Làm mới câu hỏi: trộn bộ câu hỏi mới hoàn toàn!
    container.querySelector("#quiz-reset-btn")?.addEventListener("click", () => resetAttempt(activeMode, true));
    container.querySelector("#quiz-retry-btn")?.addEventListener("click", () => resetAttempt(activeMode, true));
    container.querySelector("#quiz-retry-same-btn")?.addEventListener("click", () => resetAttempt(activeMode, false));

    renderHistoryBlock();
  }

  buildActiveLists(false);
  render();
  loadAttempts();
}
