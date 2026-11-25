// Mô phỏng sinh học tương tác trực quan (Interactive Biology Labs) cho Chủ đề 1

const CODON_TABLE = {
  AUG: "Met (Mở đầu)",
  UUU: "Phe", UUC: "Phe",
  UUA: "Leu", UUG: "Leu", CUU: "Leu", CUC: "Leu", CUA: "Leu", CUG: "Leu",
  AUU: "Ile", AUC: "Ile", AUA: "Ile",
  GUU: "Val", GUC: "Val", GUA: "Val", GUG: "Val",
  UCU: "Ser", UCC: "Ser", UCA: "Ser", UCG: "Ser", AGU: "Ser", AGC: "Ser",
  CCU: "Pro", CCC: "Pro", CCA: "Pro", CCG: "Pro",
  ACU: "Thr", ACC: "Thr", ACA: "Thr", ACG: "Thr",
  GCU: "Ala", GCC: "Ala", GCA: "Ala", GCG: "Ala",
  UAU: "Tyr", UAC: "Tyr",
  UAA: "KẾT THÚC", UAG: "KẾT THÚC", UGA: "KẾT THÚC",
  CAU: "His", CAC: "His", CAA: "Gln", CAG: "Gln",
  AAU: "Asn", AAC: "Asn", AAA: "Lys", AAG: "Lys",
  GAU: "Asp", GAC: "Asp", GAA: "Glu", GAG: "Glu",
  UGU: "Cys", UGC: "Cys", UGG: "Trp",
  CGU: "Arg", CGC: "Arg", CGA: "Arg", CGG: "Arg", AGA: "Arg", AGG: "Arg",
  GGU: "Gly", GGC: "Gly", GGA: "Gly", GGG: "Gly",
};

const COMP_DNA = { A: "T", T: "A", G: "C", C: "G" };
const COMP_RNA = { A: "U", T: "A", G: "C", C: "G" };

export function mountInteractiveDiagram(container, diagramType) {
  if (!container) return;
  if (diagramType === "dna-replication") return renderDnaReplicationSim(container);
  if (diagramType === "codon-translator") return renderCodonTranslatorSim(container);
  if (diagramType === "operon-lac") return renderOperonLacSim(container);
  if (diagramType === "mutation-lab") return renderMutationLabSim(container);
}

// 1. Mô phỏng cấu trúc & tái bản DNA tương tác
function renderDnaReplicationSim(container) {
  let step = 0; // 0: Xoắn kép gốc, 1: Helicase tháo xoắn, 2: DNA pol tổng hợp bán bảo toàn
  const templateTop = ["A", "T", "G", "C", "C", "A", "T", "G", "A", "C"];
  const templateBot = templateTop.map((b) => COMP_DNA[b]);

  const draw = () => {
    const stepTitles = [
      "Bước 0: Phân tử DNA mạch kép ban đầu (2 mạch ngược chiều, liên kết Hydrogen A=T, G≡C)",
      "Bước 1: Enzyme Helicase tháo xoắn, cắt đứt liên kết Hydrogen tách rời 2 mạch khuôn",
      "Bước 2: DNA polymerase tổng hợp 2 mạch mới theo chiều 5'→3' → tạo 2 DNA con (Bán bảo toàn)",
    ];

    const renderRow = (bases, label, isNew = false) => `
      <div style="display:flex;align-items:center;gap:6px;margin:5px 0;flex-wrap:wrap;">
        <span style="min-width:118px;font-size:0.78rem;font-weight:700;color:${isNew ? "#0369a1" : "#0f172a"}">${label}</span>
        ${bases
          .map(
            (b) =>
              `<span class="nucleotide-pill base-${b}" style="${isNew ? "outline:2px dashed #0284c7;outline-offset:1px;" : ""}">${b}</span>`
          )
          .join("")}
      </div>
    `;

    const hBonds = templateTop
      .map((b) => `<span style="display:inline-flex;width:28px;justify-content:center;font-weight:800;color:#64748b;font-size:0.85rem;">${b === "A" || b === "T" ? "‖" : "≡"}</span>`)
      .join("");

    const totalA = templateTop.filter((b) => b === "A" || b === "T").length;
    const totalG = templateTop.filter((b) => b === "G" || b === "C").length;
    const hCount = 2 * totalA + 3 * totalG;

    container.innerHTML = `
      <div class="sim-box">
        <div class="sim-header">
          <div>
            <span class="badge badge-teal">Mô phỏng tương tác • Bài 1</span>
            <h4 style="margin:6px 0 2px;">Phòng thí nghiệm Tái bản DNA (Bán bảo toàn)</h4>
            <small style="color:var(--text-muted)">${stepTitles[step]}</small>
          </div>
          <div class="sim-controls">
            <button class="btn btn-sm ${step === 0 ? "btn-primary" : "btn-secondary"}" data-step="0">1. DNA gốc</button>
            <button class="btn btn-sm ${step === 1 ? "btn-primary" : "btn-secondary"}" data-step="1">2. Tháo xoắn</button>
            <button class="btn btn-sm ${step === 2 ? "btn-primary" : "btn-secondary"}" data-step="2">3. Tái bản xong</button>
          </div>
        </div>
        <div class="sim-canvas">
          ${
            step === 0
              ? `
                ${renderRow(templateTop, "Mạch 1 (5' → 3')")}
                <div style="display:flex;align-items:center;gap:6px;margin:2px 0;">
                  <span style="min-width:118px;font-size:0.75rem;color:#64748b;">Liên kết H (${hCount})</span>
                  ${hBonds}
                </div>
                ${renderRow(templateBot, "Mạch 2 (3' → 5')")}
              `
              : step === 1
              ? `
                ${renderRow(templateTop, "Khuôn 1 (5' → 3')")}
                <div style="margin:14px 0;padding:8px 12px;border-radius:8px;background:#fef3c7;color:#92400e;font-size:0.84rem;font-weight:600;">
                  ✂️ Enzyme Helicase đã cắt đứt ${hCount} liên kết Hydrogen, tách 2 mạch làm khuôn tổng hợp.
                </div>
                ${renderRow(templateBot, "Khuôn 2 (3' → 5')")}
              `
              : `
                <div style="padding:10px 12px;border-radius:10px;border:1px solid #bae6fd;background:#f0f9ff;margin-bottom:10px;">
                  <div style="font-size:0.78rem;font-weight:700;color:#0369a1;margin-bottom:4px;">DNA con 1 (1 mạch cũ + 1 mạch mới gián đoạn Okazaki 5'→3')</div>
                  ${renderRow(templateTop, "Mạch cũ (5'→3')")}
                  ${renderRow(templateBot, "Mạch mới (3'←5')", true)}
                </div>
                <div style="padding:10px 12px;border-radius:10px;border:1px solid #a7f3d0;background:#ecfdf5;">
                  <div style="font-size:0.78rem;font-weight:700;color:#047857;margin-bottom:4px;">DNA con 2 (1 mạch cũ + 1 mạch mới liên tục 5'→3')</div>
                  ${renderRow(templateTop, "Mạch mới (5'→3')", true)}
                  ${renderRow(templateBot, "Mạch cũ (3'→5')")}
                </div>
              `
          }
          <div style="margin-top:12px;font-size:0.82rem;color:var(--text-muted);display:flex;gap:16px;flex-wrap:wrap;">
            <span><strong>Tổng N:</strong> ${templateTop.length * 2} nu</span>
            <span><strong>A = T:</strong> ${totalA}</span>
            <span><strong>G = C:</strong> ${totalG}</span>
            <span><strong>Số liên kết H:</strong> 2×${totalA} + 3×${totalG} = <strong>${hCount}</strong></span>
          </div>
        </div>
      </div>
    `;

    container.querySelectorAll("[data-step]").forEach((btn) => {
      btn.addEventListener("click", () => {
        step = Number(btn.dataset.step);
        draw();
      });
    });
  };

  draw();
}

// 2. Mô phỏng Phiên mã & Dịch mã (Nhập mạch khuôn DNA -> mRNA -> Polypeptide)
function renderCodonTranslatorSim(container) {
  let dnaInput = "TACTTCAACCCGATT";

  const draw = () => {
    const clean = dnaInput.toUpperCase().replace(/[^ATGC]/g, "").slice(0, 24);
    const mrna = clean.split("").map((b) => COMP_RNA[b] || "?").join("");
    const codons = [];
    for (let i = 0; i + 2 < mrna.length; i += 3) {
      codons.push(mrna.slice(i, i + 3));
    }

    const aaList = [];
    let stopped = false;
    for (const c of codons) {
      if (stopped) {
        aaList.push({ codon: c, aa: "(Sau mã dừng)", stop: true });
        continue;
      }
      const aa = CODON_TABLE[c] || "?";
      if (aa === "KẾT THÚC") {
        stopped = true;
        aaList.push({ codon: c, aa: "⛔ KẾT THÚC", stop: true });
      } else {
        aaList.push({ codon: c, aa, stop: false });
      }
    }

    container.innerHTML = `
      <div class="sim-box">
        <div class="sim-header">
          <div>
            <span class="badge badge-blue">Mô phỏng tương tác • Bài 2</span>
            <h4 style="margin:6px 0 2px;">Bộ giải mã Phiên mã & Dịch mã trực tuyến</h4>
            <small style="color:var(--text-muted)">Nhập mạch khuôn DNA (3' → 5', chỉ gồm A, T, G, C) để xem mRNA và chuỗi amino acid tương ứng.</small>
          </div>
        </div>
        <div class="sim-canvas">
          <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;align-items:center;">
            <label style="font-size:0.84rem;font-weight:700;">Mạch khuôn DNA (3'→5'):</label>
            <input id="sim-dna-input" class="form-control" style="max-width:280px;font-family:monospace;font-weight:700;letter-spacing:1px;" value="${clean}" maxlength="24" />
            <button class="btn btn-sm btn-soft" id="sim-dna-sample">Mẫu chuẩn (có mở đầu & kết thúc)</button>
          </div>

          <div style="display:flex;flex-direction:column;gap:10px;">
            <div>
              <div style="font-size:0.8rem;font-weight:700;color:var(--text-muted);margin-bottom:4px;">1. Mạch khuôn DNA (3' → 5'):</div>
              <div style="display:flex;gap:4px;flex-wrap:wrap;">
                ${clean.split("").map((b, i) => `<span class="nucleotide-pill base-${b}" style="${i % 3 === 0 && i > 0 ? "margin-left:8px;" : ""}">${b}</span>`).join("")}
              </div>
            </div>

            <div>
              <div style="font-size:0.8rem;font-weight:700;color:#0369a1;margin-bottom:4px;">2. Phân tử mRNA sau phiên mã (5' → 3'):</div>
              <div style="display:flex;gap:4px;flex-wrap:wrap;">
                ${mrna.split("").map((b, i) => `<span class="nucleotide-pill base-${b}" style="${i % 3 === 0 && i > 0 ? "margin-left:8px;" : ""}">${b}</span>`).join("")}
              </div>
            </div>

            <div>
              <div style="font-size:0.8rem;font-weight:700;color:#0f766e;margin-bottom:6px;">3. Chuỗi Polypeptide sau dịch mã (tại Ribosome):</div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                ${
                  aaList.length
                    ? aaList
                        .map(
                          (item, idx) => `
                          <div style="padding:7px 12px;border-radius:10px;border:1px solid ${item.stop ? "#fda4af" : "#99f6e4"};background:${item.stop ? "#fff1f2" : "#f0fdfa"};text-align:center;">
                            <div style="font-size:0.72rem;font-family:monospace;color:var(--text-muted)">${item.codon}</div>
                            <div style="font-size:0.86rem;font-weight:700;color:${item.stop ? "#be123c" : "#0f766e"}">${item.aa}</div>
                          </div>
                          ${idx < aaList.length - 1 && !item.stop ? `<span style="color:#94a3b8;font-weight:800;">→</span>` : ""}
                        `
                        )
                        .join("")
                    : `<span style="color:var(--text-muted);font-size:0.85rem;">Nhập ít nhất 3 nucleotide để dịch mã.</span>`
                }
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    const inputEl = container.querySelector("#sim-dna-input");
    inputEl?.addEventListener("input", (e) => {
      dnaInput = e.target.value;
      draw();
      const restored = container.querySelector("#sim-dna-input");
      if (restored) {
        restored.focus();
        restored.setSelectionRange(restored.value.length, restored.value.length);
      }
    });

    container.querySelector("#sim-dna-sample")?.addEventListener("click", () => {
      dnaInput = "TACTTCAACCCGATT";
      draw();
    });
  };

  draw();
}

// 3. Mô phỏng công tắc điều hòa Operon Lac (Bật/Tắt Lactose & Đột biến)
function renderOperonLacSim(container) {
  let hasLactose = false;
  let mutatedOperator = false;

  const draw = () => {
    const isTranscribing = hasLactose || mutatedOperator;
    const statusText = isTranscribing
      ? "OPERON ĐANG BẬT — Các gene lacZ, lacY, lacA đang phiên mã tạo enzyme phân giải lactose!"
      : "OPERON ĐANG TẮT — Protein ức chế bám chặt vào vùng vận hành O, chặn RNA polymerase.";

    container.innerHTML = `
      <div class="sim-box">
        <div class="sim-header">
          <div>
            <span class="badge badge-amber">Mô phỏng tương tác • Bài 3</span>
            <h4 style="margin:6px 0 2px;">Mô hình Công tắc Operon Lac (E. coli)</h4>
            <small style="color:var(--text-muted)">Thử bật/tắt đường Lactose hoặc gây đột biến vùng O để quan sát phản ứng của Operon.</small>
          </div>
          <div class="sim-controls">
            <button class="btn btn-sm ${hasLactose ? "btn-primary" : "btn-secondary"}" id="toggle-lactose">
              ${hasLactose ? "✓ Môi trường CÓ Lactose" : "Môi trường KHÔNG Lactose"}
            </button>
            <button class="btn btn-sm ${mutatedOperator ? "btn-danger" : "btn-secondary"}" id="toggle-mut-o">
              ${mutatedOperator ? "⚠ Đột biến vùng O (Hỏng)" : "Vùng O bình thường"}
            </button>
          </div>
        </div>

        <div class="sim-canvas">
          <svg viewBox="0 0 820 215" style="width:100%;max-height:230px;display:block;">
            <!-- DNA backbone -->
            <line x1="20" y1="115" x2="800" y2="115" stroke="#334155" stroke-width="5" stroke-linecap="round"/>

            <!-- Gene blocks -->
            <rect x="35" y="95" width="95" height="40" rx="8" fill="#6d28d9"/>
            <text x="82" y="120" fill="#fff" font-size="13" font-weight="700" text-anchor="middle">lacI (Điều hòa)</text>

            <rect x="175" y="95" width="75" height="40" rx="8" fill="#0284c7"/>
            <text x="212" y="120" fill="#fff" font-size="13" font-weight="700" text-anchor="middle">P (Khởi động)</text>

            <rect x="258" y="95" width="85" height="40" rx="8" fill="${mutatedOperator ? "#e11d48" : "#d97706"}"/>
            <text x="300" y="120" fill="#fff" font-size="13" font-weight="700" text-anchor="middle">${mutatedOperator ? "O* (Đột biến)" : "O (Vận hành)"}</text>

            <rect x="355" y="95" width="130" height="40" rx="8" fill="${isTranscribing ? "#0f766e" : "#94a3b8"}"/>
            <text x="420" y="120" fill="#fff" font-size="13" font-weight="700" text-anchor="middle">lacZ</text>

            <rect x="493" y="95" width="130" height="40" rx="8" fill="${isTranscribing ? "#0d9488" : "#94a3b8"}"/>
            <text x="558" y="120" fill="#fff" font-size="13" font-weight="700" text-anchor="middle">lacY</text>

            <rect x="631" y="95" width="130" height="40" rx="8" fill="${isTranscribing ? "#14b8a6" : "#94a3b8"}"/>
            <text x="696" y="120" fill="#fff" font-size="13" font-weight="700" text-anchor="middle">lacA</text>

            <!-- Operon bracket -->
            <path d="M 175 150 L 175 162 L 761 162 L 761 150" fill="none" stroke="#0f766e" stroke-width="2"/>
            <text x="468" y="182" fill="#0f766e" font-size="13" font-weight="700" text-anchor="middle">Cấu trúc Operon Lac (P + O + lacZ, lacY, lacA)</text>
            <text x="82" y="158" fill="#6d28d9" font-size="11" font-weight="600" text-anchor="middle">Ngoài Operon</text>

            <!-- RNA Polymerase -->
            <ellipse cx="${isTranscribing ? 450 : 212}" cy="66" rx="44" ry="22" fill="#38bdf8" fill-opacity="0.88" stroke="#0369a1" stroke-width="2"/>
            <text x="${isTranscribing ? 450 : 212}" y="70" fill="#0c4a6e" font-size="11" font-weight="800" text-anchor="middle">RNA Pol</text>

            <!-- Repressor protein -->
            ${
              !isTranscribing
                ? `
                  <rect x="275" y="55" width="52" height="42" rx="10" fill="#e11d48"/>
                  <text x="301" y="79" fill="#fff" font-size="10" font-weight="700" text-anchor="middle">Ức chế</text>
                  <text x="301" y="46" fill="#be123c" font-size="11" font-weight="700" text-anchor="middle">Chặn đường!</text>
                `
                : `
                  <rect x="70" y="24" width="60" height="36" rx="10" fill="#fb7185" stroke="#be123c" stroke-dasharray="4 2"/>
                  <text x="100" y="46" fill="#fff" font-size="10" font-weight="700" text-anchor="middle">${hasLactose ? "Bất hoạt" : "Tự do"}</text>
                  ${
                    hasLactose
                      ? `<circle cx="136" cy="40" r="12" fill="#f59e0b"/><text x="136" y="44" fill="#fff" font-size="9" font-weight="800" text-anchor="middle">Lac</text>`
                      : ""
                  }
                  <!-- mRNA wave -->
                  <path d="M 355 44 Q 400 26 445 44 T 535 44 T 625 44 T 720 44" fill="none" stroke="#10b981" stroke-width="4" stroke-linecap="round"/>
                  <text x="645" y="25" fill="#047857" font-size="12" font-weight="800">→ Phiên mã tạo mRNA (lacZ, lacY, lacA)</text>
                `
            }
          </svg>

          <div style="margin-top:10px;padding:10px 14px;border-radius:8px;background:${isTranscribing ? "#dcfce7" : "#ffe4e6"};color:${isTranscribing ? "#14532d" : "#881337"};font-size:0.86rem;font-weight:600;">
            ${statusText}
          </div>
        </div>
      </div>
    `;

    container.querySelector("#toggle-lactose")?.addEventListener("click", () => {
      hasLactose = !hasLactose;
      draw();
    });
    container.querySelector("#toggle-mut-o")?.addEventListener("click", () => {
      mutatedOperator = !mutatedOperator;
      draw();
    });
  };

  draw();
}

// 4. Mô phỏng Đột biến điểm & Dịch khung đọc
function renderMutationLabSim(container) {
  const original = "TACGAAACCGGG"; // mRNA: AUG CUU UGG CCC -> Met - Leu - Trp - Pro
  let mode = "normal"; // normal | silent | missense | nonsense | frameshift

  const variants = {
    normal: {
      label: "Gene bình thường",
      seq: "TACGAAACCGGG",
      desc: "Mạch khuôn gốc 3'-TAC GAA ACC GGG-5' → dịch mã bình thường tạo 4 amino acid.",
      badge: "badge-teal",
    },
    silent: {
      label: "Thay thế (Đồng nghĩa)",
      seq: "TACGAGACCGGG",
      desc: "Thay A → G ở vị trí 6: codon CUU đổi thành CUC nhưng vẫn mã hóa Leucine (tính thoái hóa của mã di truyền).",
      badge: "badge-blue",
    },
    missense: {
      label: "Thay thế (Sai nghĩa)",
      seq: "TACAAAACCGGG",
      desc: "Thay G → A ở vị trí 4: codon CUU đổi thành UUU → thay Leucine thành Phenylalanine.",
      badge: "badge-amber",
    },
    nonsense: {
      label: "Thay thế (Vô nghĩa)",
      seq: "TACGAAATCGGG",
      desc: "Thay C → T ở vị trí 8: codon UGG đổi thành UAG (mã kết thúc sớm!) → chuỗi polypeptide bị ngắn lại.",
      badge: "badge-rose",
    },
    frameshift: {
      label: "Mất 1 cặp nu (Dịch khung)",
      seq: "TACGAACCGGG",
      desc: "Mất 1 nucleotide A ở vị trí 5: toàn bộ khung đọc từ bộ ba thứ 2 trở về sau bị lệch, làm biến đổi hàng loạt amino acid!",
      badge: "badge-rose",
    },
  };

  const draw = () => {
    const v = variants[mode];
    const mrna = v.seq.split("").map((b) => COMP_RNA[b]).join("");
    const codons = [];
    for (let i = 0; i + 2 < mrna.length; i += 3) {
      codons.push(mrna.slice(i, i + 3));
    }
    const origMrna = original.split("").map((b) => COMP_RNA[b]).join("");
    const origCodons = [0, 3, 6, 9].map((i) => origMrna.slice(i, i + 3));

    container.innerHTML = `
      <div class="sim-box">
        <div class="sim-header">
          <div>
            <span class="badge ${v.badge}">Mô phỏng tương tác • Bài 4</span>
            <h4 style="margin:6px 0 2px;">Phòng thí nghiệm Đột biến điểm</h4>
            <small style="color:var(--text-muted)">Chọn các dạng đột biến để so sánh ảnh hưởng lên mRNA và chuỗi polypeptide.</small>
          </div>
          <div class="sim-controls">
            ${Object.entries(variants)
              .map(
                ([k, info]) =>
                  `<button class="btn btn-sm ${mode === k ? "btn-primary" : "btn-secondary"}" data-mut="${k}">${info.label}</button>`
              )
              .join("")}
          </div>
        </div>
        <div class="sim-canvas">
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:12px;">
            ${codons
              .map((c, idx) => {
                const aa = CODON_TABLE[c] || "?";
                const origAa = CODON_TABLE[origCodons[idx]] || "?";
                const changed = aa !== origAa;
                return `
                  <div style="padding:10px;border-radius:10px;border:2px solid ${changed ? "#e11d48" : "#cbd5e1"};background:${changed ? "#fff1f2" : "#f8fafc"};text-align:center;">
                    <div style="font-size:0.74rem;color:var(--text-muted);">Codon ${idx + 1}</div>
                    <div style="font-family:monospace;font-size:1rem;font-weight:800;margin:4px 0;">5'-${c}-3'</div>
                    <div style="font-size:0.86rem;font-weight:700;color:${changed ? "#be123c" : "#0f766e"};">${aa}</div>
                    ${changed ? `<div style="font-size:0.72rem;color:#9f1239;margin-top:2px;">(Gốc: ${origAa})</div>` : ""}
                  </div>
                `;
              })
              .join("")}
          </div>
          <div style="padding:10px 14px;border-radius:8px;background:#f1f5f9;font-size:0.86rem;color:var(--text-secondary);">
            <strong>Phân tích:</strong> ${v.desc}
          </div>
        </div>
      </div>
    `;

    container.querySelectorAll("[data-mut]").forEach((btn) => {
      btn.addEventListener("click", () => {
        mode = btn.dataset.mut;
        draw();
      });
    });
  };

  draw();
}
