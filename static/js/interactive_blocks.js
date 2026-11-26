// Render & xử lý tương tác cho toàn bộ bài tập vận dụng & phiếu bảng
// trong mục "1. Lý thuyết" và "2. Hệ thống kiến thức":
// - Ô nhập đáp án (input / textarea / Đúng-Sai / Đánh dấu chéo / Chọn cột phân loại)
// - Nút "Kiểm tra đáp án" & "Làm lại" cho từng bài tập / từng bảng và toàn bài
// - Hiển thị kết quả đúng KẾ BÊN ô bài làm của học sinh với định dạng chuẩn Sinh học 12

import { escapeHtml, formatBioHtml } from "./format.js";
import { withBase } from "./api.js";

// Lưu trữ tạm bài làm và trạng thái đã kiểm tra trong phiên học (không mất khi chuyển tab/bài)
const answerStore = new Map(); // fieldKey -> string | boolean | number
const checkedUnits = new Set(); // groupId or tableId

function stripDiacritics(str) {
  return String(str || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D");
}

function normalizeForExact(val) {
  return stripDiacritics(String(val || ""))
    .toLowerCase()
    .replace(/[’‘`´]/g, "'")
    .replace(/[–—−]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeCompact(val) {
  return normalizeForExact(val).replace(/\s+/g, "");
}

function evaluateAnswer(studentVal, meta) {
  const raw = String(studentVal || "").trim();
  if (!raw) {
    return { status: "empty", label: "Chưa trả lời" };
  }
  if (meta.mode === "true_false") {
    const normS = normalizeForExact(raw);
    const normA = normalizeForExact(meta.answer);
    return normS === normA
      ? { status: "correct", label: "Chính xác" }
      : { status: "wrong", label: "Chưa đúng" };
  }
  if (meta.grade_type === "exact" && Array.isArray(meta.exact) && meta.exact.length) {
    const ns = normalizeForExact(raw);
    const nsc = normalizeCompact(raw);
    const ok = meta.exact.some((cand) => {
      const nc = normalizeForExact(cand);
      const ncc = normalizeCompact(cand);
      return ns === nc || nsc === ncc;
    });
    return ok
      ? { status: "correct", label: "Chính xác" }
      : { status: "wrong", label: "Chưa đúng" };
  }
  // Câu tự luận / khái niệm / sơ đồ lai: đối chiếu trực tiếp kế bên
  // Nếu khớp sát với đáp án chuẩn thì báo Chính xác, ngược lại hiện Đáp án chuẩn để tự đối chiếu
  const ns = normalizeCompact(raw);
  const na = normalizeCompact(meta.answer || "");
  if (ns && na && ns === na) {
    return { status: "correct", label: "Chính xác" };
  }
  return { status: "compare", label: "Đối chiếu đáp án" };
}

function renderSideAnswerBox(evalRes, officialAnswer) {
  const cls =
    evalRes.status === "correct"
      ? "ex-ans-correct"
      : evalRes.status === "wrong"
      ? "ex-ans-wrong"
      : evalRes.status === "empty"
      ? "ex-ans-empty"
      : "ex-ans-compare";
  const badgeIcon =
    evalRes.status === "correct"
      ? "✓"
      : evalRes.status === "wrong"
      ? "✕"
      : evalRes.status === "empty"
      ? "•"
      : "★";
  return `
    <div class="ex-answer-side ${cls}">
      <div class="ex-answer-badge"><span>${badgeIcon}</span> ${escapeHtml(evalRes.label)}</div>
      <div class="ex-answer-text"><strong>Đáp án đúng:</strong> ${formatBioHtml(officialAnswer)}</div>
    </div>
  `;
}

function renderFieldControl(fieldKey, meta, isChecked) {
  const val = answerStore.has(fieldKey) ? String(answerStore.get(fieldKey)) : "";
  const evalRes = isChecked ? evaluateAnswer(val, meta) : null;
  const stateCls = isChecked
    ? evalRes.status === "correct"
      ? "ex-input-correct"
      : evalRes.status === "wrong"
      ? "ex-input-wrong"
      : evalRes.status === "empty"
      ? "ex-input-empty"
      : "ex-input-compare"
    : "";

  if (meta.mode === "true_false") {
    const isT = val === "Đúng";
    const isF = val === "Sai";
    return `
      <div class="ex-pair ${isChecked ? "is-checked" : ""}" data-field-wrap="${escapeHtml(fieldKey)}">
        <div class="ex-student-col">
          <div class="ex-tf-group" data-tf-key="${escapeHtml(fieldKey)}">
            <button type="button" class="ex-tf-btn ${isT ? "selected-true" : ""}" data-tf-val="Đúng">Đúng</button>
            <button type="button" class="ex-tf-btn ${isF ? "selected-false" : ""}" data-tf-val="Sai">Sai</button>
          </div>
        </div>
        ${isChecked ? renderSideAnswerBox(evalRes, meta.answer) : ""}
      </div>
    `;
  }

  const placeholder = meta.placeholder || (meta.mode === "textarea" ? "Nhập lời giải / sơ đồ lai của em..." : "Nhập đáp án của em...");
  const controlHtml =
    meta.mode === "textarea"
      ? `<textarea class="form-control ex-input ${stateCls}" rows="3" data-ex-key="${escapeHtml(fieldKey)}" placeholder="${escapeHtml(placeholder)}">${escapeHtml(val)}</textarea>`
      : `<input type="text" class="form-control ex-input ${stateCls}" data-ex-key="${escapeHtml(fieldKey)}" value="${escapeHtml(val)}" placeholder="${escapeHtml(placeholder)}" />`;

  return `
    <div class="ex-pair ${isChecked ? "is-checked" : ""}" data-field-wrap="${escapeHtml(fieldKey)}">
      <div class="ex-student-col">${controlHtml}</div>
      ${isChecked ? renderSideAnswerBox(evalRes, meta.answer) : ""}
    </div>
  `;
}

function renderActionBar(unitId, isChecked, summaryText = "") {
  return `
    <div class="ex-action-bar" data-ex-bar="${escapeHtml(unitId)}">
      <button type="button" class="btn btn-sm btn-primary" data-ex-check="${escapeHtml(unitId)}">
        ${isChecked ? "Cập nhật kết quả kiểm tra" : "Kiểm tra đáp án"}
      </button>
      ${
        isChecked
          ? `<button type="button" class="btn btn-sm btn-secondary" data-ex-hide="${escapeHtml(unitId)}">Ẩn đáp án</button>`
          : ""
      }
      <button type="button" class="btn btn-sm btn-ghost" data-ex-reset="${escapeHtml(unitId)}">Làm lại</button>
      ${summaryText ? `<span class="ex-score-pill">${escapeHtml(summaryText)}</span>` : ""}
    </div>
  `;
}

function computeGroupSummary(unitId, itemsMeta) {
  if (!checkedUnits.has(unitId)) return "";
  let exactTotal = 0;
  let exactRight = 0;
  let answered = 0;
  for (const { key, meta } of itemsMeta) {
    const val = answerStore.has(key) ? String(answerStore.get(key)).trim() : "";
    if (val) answered++;
    if (meta.grade_type === "exact" || meta.mode === "true_false") {
      exactTotal++;
      if (evaluateAnswer(val, meta).status === "correct") exactRight++;
    }
  }
  if (exactTotal > 0) {
    return `Đúng ${exactRight}/${exactTotal} câu chấm tự động · Đã điền ${answered}/${itemsMeta.length}`;
  }
  return `Đã mở đáp án đối chiếu · Đã điền ${answered}/${itemsMeta.length} mục`;
}

// ================== INTERACTIVE TABLE RENDERER ==================
function renderInteractiveTable(block) {
  const rows = block.rows || [];
  const inter = block.interactive;
  if (!rows.length || !inter) return "";

  const tid = inter.id;
  const isChecked = checkedUnits.has(tid);
  const mode = inter.mode;

  // --- Mode 1: tf_rows (VD: 1.1 Ví dụ 2 — 4 nhận định Đúng/Sai) ---
  if (mode === "tf_rows") {
    const tfAnswers = inter.tf_answers || {};
    let rightCount = 0;
    const totalCount = Object.keys(tfAnswers).length;
    const bodyHtml = rows
      .map((r, ri) => {
        const key = `${tid}::tf::${ri}`;
        const ans = tfAnswers[String(ri)] || "";
        const val = answerStore.has(key) ? String(answerStore.get(key)) : "";
        const evalRes = isChecked ? evaluateAnswer(val, { mode: "true_false", answer: ans }) : null;
        if (isChecked && evalRes.status === "correct") rightCount++;
        return `
          <tr>
            <td style="width:46px;"><strong>${formatBioHtml(r[0] || "")}</strong></td>
            <td style="white-space:pre-line;">${formatBioHtml(r[1] || "")}</td>
            <td class="ex-table-interactive-cell">
              <div class="ex-cell-pair ${isChecked ? "is-checked" : ""}">
                <div class="ex-tf-group" data-tf-key="${escapeHtml(key)}">
                  <button type="button" class="ex-tf-btn ${val === "Đúng" ? "selected-true" : ""}" data-tf-val="Đúng">Đúng</button>
                  <button type="button" class="ex-tf-btn ${val === "Sai" ? "selected-false" : ""}" data-tf-val="Sai">Sai</button>
                </div>
                ${isChecked ? renderSideAnswerBox(evalRes, ans) : ""}
              </div>
            </td>
          </tr>
        `;
      })
      .join("");

    const summary = isChecked ? `Đúng ${rightCount}/${totalCount} nhận định` : "";
    return `
      <div class="ex-block-card" data-ex-unit="${escapeHtml(tid)}">
        <div class="data-table-wrap" style="margin:0;">
          <table class="data-table ex-interactive-table">
            <thead>
              <tr>
                <th>Ý</th>
                <th>Nhận định</th>
                <th>Trả lời của học sinh${isChecked ? " &amp; Đáp án đúng kế bên" : ""}</th>
              </tr>
            </thead>
            <tbody>${bodyHtml}</tbody>
          </table>
        </div>
        ${renderActionBar(tid, isChecked, summary)}
      </div>
    `;
  }

  // --- Mode 2: check_single (VD: 1.4 Câu 2 — đánh dấu chéo vào ví dụ là đột biến) ---
  if (mode === "check_single") {
    const [header, ...body] = rows;
    const checkCol = inter.check_col ?? 2;
    const checkSet = new Set((inter.check_rows || []).map(Number));
    let rightCount = 0;
    const totalCount = body.length;

    const bodyHtml = body
      .map((r, bi) => {
        const rowIndex = bi + 1; // 1-based row index in block.rows
        const key = `${tid}::chk::${rowIndex}`;
        const studentChecked = Boolean(answerStore.get(key));
        const shouldCheck = checkSet.has(rowIndex);
        const isCorrect = studentChecked === shouldCheck;
        if (isChecked && isCorrect) rightCount++;

        const rowCells = r
          .map((c, ci) => {
            if (ci === checkCol) {
              const sideCls = isCorrect ? "ex-ans-correct" : "ex-ans-wrong";
              const officialText = shouldCheck
                ? inter.checked_label || "× Đột biến"
                : inter.unchecked_label || "Không đánh dấu";
              return `
                <td class="ex-table-interactive-cell">
                  <div class="ex-cell-pair ${isChecked ? "is-checked" : ""}">
                    <button type="button" class="ex-check-box ${studentChecked ? "is-marked" : ""} ${
                isChecked ? (isCorrect ? "ex-input-correct" : "ex-input-wrong") : ""
              }" data-chk-key="${escapeHtml(key)}" aria-pressed="${studentChecked ? "true" : "false"}">
                      ${studentChecked ? "✕" : ""}
                    </button>
                    ${
                      isChecked
                        ? `<div class="ex-answer-side ${sideCls}"><div class="ex-answer-badge"><span>${
                            isCorrect ? "✓" : "✕"
                          }</span> ${isCorrect ? "Đúng" : "Chưa đúng"}</div><div class="ex-answer-text"><strong>Đáp án:</strong> ${escapeHtml(
                            officialText
                          )}</div></div>`
                        : ""
                    }
                  </div>
                </td>
              `;
            }
            return ci === 0
              ? `<td><strong>${formatBioHtml(c)}</strong></td>`
              : `<td style="white-space:pre-line;">${formatBioHtml(c)}</td>`;
          })
          .join("");
        return `<tr>${rowCells}</tr>`;
      })
      .join("");

    const summary = isChecked ? `Đúng ${rightCount}/${totalCount} ví dụ` : "";
    return `
      <div class="ex-block-card" data-ex-unit="${escapeHtml(tid)}">
        <div class="data-table-wrap" style="margin:0;">
          <table class="data-table ex-interactive-table">
            <thead><tr>${header.map((c) => `<th>${formatBioHtml(c)}</th>`).join("")}</tr></thead>
            <tbody>${bodyHtml}</tbody>
          </table>
        </div>
        ${renderActionBar(tid, isChecked, summary)}
      </div>
    `;
  }

  // --- Mode 3: check_radio (VD: 4.4 Câu 2 — đánh dấu chéo chọn 1 trong 3 cột Đột biến / Thường biến / Mức phản ứng) ---
  if (mode === "check_radio") {
    const headerCount = inter.header_rows || 2;
    const headerRow = rows[headerCount - 1] || rows[0];
    const body = rows.slice(headerCount);
    const radioCols = inter.radio_cols || [2, 3, 4];
    const radioAnswers = inter.radio_answers || {};
    const colLabels = inter.col_labels || {};
    let rightCount = 0;
    const totalCount = Object.keys(radioAnswers).length;

    const bodyHtml = body
      .map((r, bi) => {
        const rowIndex = bi + headerCount;
        const key = `${tid}::rad::${rowIndex}`;
        const chosenCol = answerStore.has(key) ? Number(answerStore.get(key)) : -1;
        const correctCol = Number(radioAnswers[String(rowIndex)]);
        const isCorrect = chosenCol === correctCol;
        if (isChecked && isCorrect) rightCount++;

        const cellsHtml = r
          .map((c, ci) => {
            if (radioCols.includes(ci)) {
              const selected = chosenCol === ci;
              let extraCls = "";
              if (isChecked) {
                if (selected && isCorrect) extraCls = "ex-input-correct";
                else if (selected && !isCorrect) extraCls = "ex-input-wrong";
                else if (ci === correctCol) extraCls = "ex-radio-reveal";
              }
              return `
                <td style="text-align:center;">
                  <button type="button" class="ex-check-box ${selected ? "is-marked" : ""} ${extraCls}" data-rad-key="${escapeHtml(
                key
              )}" data-rad-col="${ci}" aria-pressed="${selected ? "true" : "false"}">
                    ${selected ? "✕" : ""}
                  </button>
                </td>
              `;
            }
            return ci === 0
              ? `<td><strong>${formatBioHtml(c)}</strong></td>`
              : `<td style="white-space:pre-line;">${formatBioHtml(c)}</td>`;
          })
          .join("");

        const sideCell = isChecked
          ? `<td class="ex-table-interactive-cell ex-radio-answer-col">
               <div class="ex-answer-side ${chosenCol === -1 ? "ex-ans-empty" : isCorrect ? "ex-ans-correct" : "ex-ans-wrong"}">
                 <div class="ex-answer-badge"><span>${chosenCol === -1 ? "•" : isCorrect ? "✓" : "✕"}</span> ${
              chosenCol === -1 ? "Chưa chọn" : isCorrect ? "Chính xác" : "Chưa đúng"
            }</div>
                 <div class="ex-answer-text"><strong>Đáp án:</strong> ${escapeHtml(colLabels[String(correctCol)] || "")}</div>
               </div>
             </td>`
          : "";

        return `<tr>${cellsHtml}${sideCell}</tr>`;
      })
      .join("");

    const summary = isChecked ? `Đúng ${rightCount}/${totalCount} ví dụ` : "";
    return `
      <div class="ex-block-card" data-ex-unit="${escapeHtml(tid)}">
        <div class="data-table-wrap" style="margin:0;">
          <table class="data-table ex-interactive-table">
            <thead>
              <tr>
                ${headerRow.map((c) => `<th>${formatBioHtml(c)}</th>`).join("")}
                ${isChecked ? `<th>Đáp án đúng</th>` : ""}
              </tr>
            </thead>
            <tbody>${bodyHtml}</tbody>
          </table>
        </div>
        ${renderActionBar(tid, isChecked, summary)}
      </div>
    `;
  }

  // --- Mode 3b: check_multi_and_fill (VD: 5.4 Câu 1 — chọn nhiều cột nguyên nhân + nhập Phương pháp nghiên cứu) ---
  if (mode === "check_multi_and_fill") {
    const headerCount = inter.header_rows || 2;
    const headerRow = rows[headerCount - 1] || rows[0];
    const body = rows.slice(headerCount);
    const checkCols = inter.check_cols || [2, 3, 4, 5];
    const textCol = inter.text_col ?? 6;
    const colLabels = inter.col_labels || {};
    const rowAnswers = inter.row_answers || {};
    let rightRows = 0;
    const totalRows = Object.keys(rowAnswers).length;

    const bodyHtml = body
      .map((r, bi) => {
        const rowIndex = bi + headerCount;
        const rowMeta = rowAnswers[String(rowIndex)] || { checks: [], text: "", exact: [] };
        const expectedSet = new Set((rowMeta.checks || []).map(Number));
        const textKey = `${tid}::mtxt::${rowIndex}`;
        const studentText = answerStore.has(textKey) ? String(answerStore.get(textKey)) : "";

        let checksAllMatch = true;
        for (const ci of checkCols) {
          const cKey = `${tid}::mchk::${rowIndex}:${ci}`;
          const isMarked = Boolean(answerStore.get(cKey));
          if (isMarked !== expectedSet.has(ci)) checksAllMatch = false;
        }
        const textEval = isChecked
          ? evaluateAnswer(studentText, {
              mode: "input",
              answer: rowMeta.text || "",
              exact: rowMeta.exact,
              grade_type: rowMeta.exact?.length ? "exact" : "compare",
            })
          : null;
        const rowAllRight = checksAllMatch && textEval?.status === "correct";
        if (isChecked && rowAllRight) rightRows++;

        const cellsHtml = r
          .map((c, ci) => {
            if (checkCols.includes(ci)) {
              const cKey = `${tid}::mchk::${rowIndex}:${ci}`;
              const selected = Boolean(answerStore.get(cKey));
              const shouldMark = expectedSet.has(ci);
              let extraCls = "";
              if (isChecked) {
                if (selected && shouldMark) extraCls = "ex-input-correct";
                else if (selected && !shouldMark) extraCls = "ex-input-wrong";
                else if (!selected && shouldMark) extraCls = "ex-radio-reveal";
              }
              return `
                <td style="text-align:center;">
                  <button type="button" class="ex-check-box ${selected ? "is-marked" : ""} ${extraCls}" data-chk-key="${escapeHtml(
                cKey
              )}" aria-pressed="${selected ? "true" : "false"}">
                    ${selected ? "✕" : ""}
                  </button>
                </td>
              `;
            }
            if (ci === textCol) {
              const tCls = isChecked
                ? textEval.status === "correct"
                  ? "ex-input-correct"
                  : textEval.status === "wrong"
                  ? "ex-input-wrong"
                  : textEval.status === "empty"
                  ? "ex-input-empty"
                  : "ex-input-compare"
                : "";
              const causeNames = (rowMeta.checks || []).map((col) => colLabels[String(col)] || "").filter(Boolean).join(" + ");
              const fullOfficial = `Nguyên nhân: ${causeNames}\nPhương pháp: ${rowMeta.text || ""}`;
              const combinedEval = isChecked
                ? rowAllRight
                  ? { status: "correct", label: "Chính xác" }
                  : { status: checksAllMatch ? textEval.status : "wrong", label: checksAllMatch ? textEval.label : "Đối chiếu đáp án" }
                : null;
              return `
                <td class="ex-table-interactive-cell">
                  <div class="ex-cell-pair ${isChecked ? "is-checked" : ""}">
                    <div class="ex-student-col">
                      <input type="text" class="form-control ex-input ex-table-input ${tCls}" data-ex-key="${escapeHtml(
                textKey
              )}" value="${escapeHtml(studentText)}" placeholder="Nhập phương pháp..." />
                    </div>
                    ${isChecked ? renderSideAnswerBox(combinedEval, fullOfficial) : ""}
                  </div>
                </td>
              `;
            }
            return ci === 0
              ? `<td><strong>${formatBioHtml(c)}</strong></td>`
              : `<td style="white-space:pre-line;">${formatBioHtml(c)}</td>`;
          })
          .join("");
        return `<tr>${cellsHtml}</tr>`;
      })
      .join("");

    const summary = isChecked ? `Đúng trọn vẹn ${rightRows}/${totalRows} bệnh` : "";
    return `
      <div class="ex-block-card" data-ex-unit="${escapeHtml(tid)}">
        <div class="data-table-wrap" style="margin:0;">
          <table class="data-table ex-interactive-table">
            <thead><tr>${headerRow.map((c) => `<th>${formatBioHtml(c)}</th>`).join("")}</tr></thead>
            <tbody>${bodyHtml}</tbody>
          </table>
        </div>
        ${renderActionBar(tid, isChecked, summary)}
      </div>
    `;
  }

  // --- Mode 4: fill (Bảng điền khuyết / khái niệm / sơ đồ lai / tính toán) ---
  const headerCount = inter.header_rows || 1;
  const headerRow = rows[headerCount - 1] || rows[0];
  const body = rows.slice(headerCount);
  const answersMap = inter.answers || {};
  const trackedItems = [];

  const bodyHtml = body
    .map((r, bi) => {
      const rowIndex = bi + headerCount;
      // Hàng tiêu đề nhóm (chỉ có 1 cột span toàn bảng, VD: "Kiểu gene đồng hợp")
      if (r.length === 1 && headerRow.length > 1) {
        return `<tr class="ex-subhead-row"><td colspan="${headerRow.length}"><strong>${formatBioHtml(r[0])}</strong></td></tr>`;
      }
      const cellsHtml = r
        .map((c, ci) => {
          const coord = `${rowIndex}:${ci}`;
          const cellMeta = answersMap[coord];
          if (cellMeta) {
            const fieldKey = `${tid}::cell::${coord}`;
            const meta = {
              mode: cellMeta.multiline ? "textarea" : "input",
              answer: cellMeta.answer,
              exact: cellMeta.exact,
              grade_type: cellMeta.grade_type || "compare",
            };
            trackedItems.push({ key: fieldKey, meta });
            const val = answerStore.has(fieldKey) ? String(answerStore.get(fieldKey)) : "";
            const evalRes = isChecked ? evaluateAnswer(val, meta) : null;
            const stateCls = isChecked
              ? evalRes.status === "correct"
                ? "ex-input-correct"
                : evalRes.status === "wrong"
                ? "ex-input-wrong"
                : evalRes.status === "empty"
                ? "ex-input-empty"
                : "ex-input-compare"
              : "";
            const trimmed = String(c || "").trim();
            const hasHintPrefix = trimmed && !/^[\.\…\_\-]+$/.test(trimmed) && !/^\/[\.\s\/]+\/$/.test(trimmed);
            const placeholder = hasHintPrefix ? trimmed : "Nhập đáp án...";
            const inputEl = cellMeta.multiline
              ? `<textarea class="form-control ex-input ex-table-input ${stateCls}" rows="2" data-ex-key="${escapeHtml(
                  fieldKey
                )}" placeholder="${escapeHtml(placeholder)}">${escapeHtml(val)}</textarea>`
              : `<input type="text" class="form-control ex-input ex-table-input ${stateCls}" data-ex-key="${escapeHtml(
                  fieldKey
                )}" value="${escapeHtml(val)}" placeholder="${escapeHtml(placeholder)}" />`;

            return `
              <td class="ex-table-interactive-cell">
                <div class="ex-cell-pair ${isChecked ? "is-checked" : ""}">
                  <div class="ex-student-col">${inputEl}</div>
                  ${isChecked ? renderSideAnswerBox(evalRes, cellMeta.answer) : ""}
                </div>
              </td>
            `;
          }
          return ci === 0
            ? `<td><strong>${formatBioHtml(c)}</strong></td>`
            : `<td style="white-space:pre-line;">${formatBioHtml(c)}</td>`;
        })
        .join("");
      return `<tr>${cellsHtml}</tr>`;
    })
    .join("");

  const summary = computeGroupSummary(tid, trackedItems);
  return `
    <div class="ex-block-card" data-ex-unit="${escapeHtml(tid)}">
      <div class="data-table-wrap" style="margin:0;">
        <table class="data-table ex-interactive-table">
          <thead><tr>${headerRow.map((c) => `<th>${formatBioHtml(c)}</th>`).join("")}</tr></thead>
          <tbody>${bodyHtml}</tbody>
        </table>
      </div>
      ${renderActionBar(tid, isChecked, summary)}
    </div>
  `;
}

// ================== PLAIN TABLE RENDERER (không có interactive metadata) ==================
function renderPlainTable(rows, editableEmptyCells = false) {
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

// ================== MAIN BLOCKS RENDERER ==================
export function collectInteractiveUnitIds(blocks) {
  const ids = new Set();
  for (const b of blocks || []) {
    if (b.interactive?.id) ids.add(b.interactive.id);
    if (b.exercise?.group) ids.add(b.exercise.group);
    if (b.exercise_group?.id) ids.add(b.exercise_group.id);
  }
  return Array.from(ids);
}

export function renderInteractiveToolbar(allUnitIds, label = "bài học này") {
  if (!allUnitIds.length) return "";
  const allChecked = allUnitIds.every((id) => checkedUnits.has(id));
  return `
    <div class="ex-master-toolbar">
      <div class="ex-master-info">
        <strong>Bài tập tương tác trong ${escapeHtml(label)}:</strong>
        <span>${allUnitIds.length} phần bài tập có ô nhập &amp; đối chiếu đáp án chuẩn kế bên.</span>
      </div>
      <div class="ex-master-actions">
        <button type="button" class="btn btn-sm btn-primary" data-ex-check-all="1">
          ${allChecked ? "Cập nhật kiểm tra tất cả" : "Kiểm tra tất cả đáp án"}
        </button>
        ${
          allChecked
            ? `<button type="button" class="btn btn-sm btn-secondary" data-ex-hide-all="1">Ẩn tất cả đáp án</button>`
            : ""
        }
        <button type="button" class="btn btn-sm btn-ghost" data-ex-reset-all="1">Làm lại tất cả</button>
      </div>
    </div>
  `;
}

export function renderDocumentBlocksInteractive(blocks, editableEmptyCells = false) {
  if (!blocks || !blocks.length) return "";

  // Xác định block cuối cùng của mỗi group exercise để đặt thanh nút "Kiểm tra đáp án" ngay sau nhóm đó
  const lastIndexByGroup = new Map();
  const itemsByGroup = new Map();
  blocks.forEach((b, idx) => {
    if (b.exercise?.group) {
      const g = b.exercise.group;
      lastIndexByGroup.set(g, idx);
      if (!itemsByGroup.has(g)) itemsByGroup.set(g, []);
      itemsByGroup.get(g).push({ key: b.exercise.id, meta: b.exercise });
    }
  });

  return blocks
    .map((b, idx) => {
      if (b.hidden_by_group) return "";

      let html = "";
      if (b.type === "image") {
        html = `
          <figure class="lesson-hero-figure">
            <img src="${withBase(b.src)}" alt="${escapeHtml(b.caption || "Hình minh họa Sinh học 12")}" loading="lazy" />
            ${b.caption ? `<figcaption>${formatBioHtml(b.caption)}</figcaption>` : ""}
          </figure>
        `;
      } else if (b.type === "table") {
        const extraImgs = (b.images || [])
          .map(
            (src) => `
            <figure class="lesson-hero-figure" style="margin:10px 0;">
              <img src="${withBase(src)}" alt="Hình minh họa" loading="lazy" />
            </figure>
          `
          )
          .join("");
        html = (b.interactive ? renderInteractiveTable(b) : renderPlainTable(b.rows, editableEmptyCells)) + extraImgs;
      } else {
        const textHtml = formatBioHtml(b.text || "");
        const isBullet = /^[-–+•]\s*/.test(b.text || "");
        if (b.is_bold) html = `<p class="prose-p-bold">${textHtml}</p>`;
        else if (isBullet) html = `<p class="prose-bullet">${textHtml}</p>`;
        else html = `<p class="prose-p">${textHtml}</p>`;
      }

      // Gắn ô nhập đơn lẻ cho câu hỏi dạng paragraph
      if (b.exercise) {
        const ex = b.exercise;
        const isChecked = checkedUnits.has(ex.group);
        const isLastInGroup = lastIndexByGroup.get(ex.group) === idx;
        const summary = isLastInGroup ? computeGroupSummary(ex.group, itemsByGroup.get(ex.group) || []) : "";
        html = `
          <div class="ex-prompt-item ${isChecked ? "is-checked" : ""}" data-ex-unit="${escapeHtml(ex.group)}">
            ${html}
            ${renderFieldControl(ex.id, ex, isChecked)}
          </div>
          ${isLastInGroup ? renderActionBar(ex.group, isChecked, summary) : ""}
        `;
      }

      // Gắn nhóm nhiều ô nhập (VD: chú thích số 1..17 trên hình, danh sách 12 câu viết giao tử...)
      if (b.exercise_group) {
        const eg = b.exercise_group;
        const isChecked = checkedUnits.has(eg.id);
        const cols = eg.columns || 1;
        const tracked = (eg.items || []).map((it) => ({ key: it.id, meta: it }));
        const summary = computeGroupSummary(eg.id, tracked);
        const gridCls = !isChecked && cols === 3 ? "ex-grid-3" : !isChecked && cols === 2 ? "ex-grid-2" : "ex-grid-1";
        html += `
          <div class="ex-block-card ex-group-card" data-ex-unit="${escapeHtml(eg.id)}">
            ${eg.title ? `<div class="ex-group-title">${formatBioHtml(eg.title)}</div>` : ""}
            <div class="ex-items-grid ${gridCls}">
              ${(eg.items || [])
                .map(
                  (it) => `
                  <div class="ex-subitem">
                    <label class="ex-subitem-label">${formatBioHtml(it.label)}</label>
                    ${renderFieldControl(it.id, it, isChecked)}
                  </div>
                `
                )
                .join("")}
            </div>
            ${renderActionBar(eg.id, isChecked, summary)}
          </div>
        `;
      }

      return html;
    })
    .join("");
}

// ================== EVENT BINDING (delegated on container) ==================
export function bindInteractiveExerciseEvents(container, allUnitIds, rerender) {
  if (!container) return;

  // Lưu giá trị input/textarea ngay khi học sinh gõ (không rerender để không mất focus)
  container.querySelectorAll("[data-ex-key]").forEach((el) => {
    el.addEventListener("input", () => {
      answerStore.set(el.dataset.exKey, el.value);
    });
  });

  // Nút Đúng / Sai
  container.querySelectorAll("[data-tf-key]").forEach((grp) => {
    const key = grp.dataset.tfKey;
    grp.querySelectorAll("[data-tf-val]").forEach((btn) => {
      btn.addEventListener("click", () => {
        answerStore.set(key, btn.dataset.tfVal);
        grp.querySelectorAll("[data-tf-val]").forEach((b) => {
          b.classList.remove("selected-true", "selected-false");
        });
        btn.classList.add(btn.dataset.tfVal === "Đúng" ? "selected-true" : "selected-false");
      });
    });
  });

  // Ô đánh dấu chéo (single checkbox — VD 1.4 Câu 2)
  container.querySelectorAll("[data-chk-key]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.chkKey;
      const next = !Boolean(answerStore.get(key));
      answerStore.set(key, next);
      btn.classList.toggle("is-marked", next);
      btn.setAttribute("aria-pressed", next ? "true" : "false");
      btn.textContent = next ? "✕" : "";
    });
  });

  // Ô đánh dấu chéo chọn 1 trong nhiều cột (radio — VD 4.4 Câu 2)
  container.querySelectorAll("[data-rad-key]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.radKey;
      const col = Number(btn.dataset.radCol);
      answerStore.set(key, col);
      container.querySelectorAll(`[data-rad-key="${CSS.escape(key)}"]`).forEach((sib) => {
        const isMe = Number(sib.dataset.radCol) === col;
        sib.classList.toggle("is-marked", isMe);
        sib.setAttribute("aria-pressed", isMe ? "true" : "false");
        sib.textContent = isMe ? "✕" : "";
      });
    });
  });

  const keepScrollRerender = () => {
    const y = window.scrollY;
    rerender();
    requestAnimationFrame(() => window.scrollTo(0, y));
  };

  // Kiểm tra đáp án từng nhóm / bảng
  container.querySelectorAll("[data-ex-check]").forEach((btn) => {
    btn.addEventListener("click", () => {
      checkedUnits.add(btn.dataset.exCheck);
      keepScrollRerender();
    });
  });

  // Ẩn đáp án từng nhóm / bảng
  container.querySelectorAll("[data-ex-hide]").forEach((btn) => {
    btn.addEventListener("click", () => {
      checkedUnits.delete(btn.dataset.exHide);
      keepScrollRerender();
    });
  });

  // Làm lại từng nhóm / bảng
  container.querySelectorAll("[data-ex-reset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const uid = btn.dataset.exReset;
      checkedUnits.delete(uid);
      for (const k of Array.from(answerStore.keys())) {
        if (k === uid || k.startsWith(`${uid}-`) || k.startsWith(`${uid}::`)) {
          answerStore.delete(k);
        }
      }
      keepScrollRerender();
    });
  });

  // Thanh điều khiển tổng của cả bài học / phiếu
  container.querySelector("[data-ex-check-all]")?.addEventListener("click", () => {
    allUnitIds.forEach((id) => checkedUnits.add(id));
    keepScrollRerender();
  });

  container.querySelector("[data-ex-hide-all]")?.addEventListener("click", () => {
    allUnitIds.forEach((id) => checkedUnits.delete(id));
    keepScrollRerender();
  });

  container.querySelector("[data-ex-reset-all]")?.addEventListener("click", () => {
    allUnitIds.forEach((uid) => {
      checkedUnits.delete(uid);
      for (const k of Array.from(answerStore.keys())) {
        if (k === uid || k.startsWith(`${uid}-`) || k.startsWith(`${uid}::`)) {
          answerStore.delete(k);
        }
      }
    });
    keepScrollRerender();
  });
}
