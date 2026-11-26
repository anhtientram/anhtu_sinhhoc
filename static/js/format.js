// Chuẩn hóa hiển thị công thức phân tử hóa học, đồng vị phóng xạ và ký hiệu Sinh học 12
// (An toàn HTML: luôn escape trước, sau đó mới gắn thẻ <sub>/<sup> và phân số kiểu gene chuẩn SGK)

export function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function isLinkedGenotypePair(top, bot) {
  if (top.length !== bot.length || top.length < 2 || top.length > 4) return false;
  // Loại trừ các viết tắt sinh học phổ biến không phải kiểu gene liên kết
  const bad = /^(DNA|RNA|ATP|ADP|NAD|FAD|PCR|EMS|NST|UV|OK|PH|MG|KG|CM|MM|NM|ML)$/i;
  if (bad.test(top) || bad.test(bot)) return false;
  // Chỉ chứa các chữ cái ký hiệu allele quen thuộc (A-Z, a-z)
  if (!/^[A-Za-z]+$/.test(top) || !/^[A-Za-z]+$/.test(bot)) return false;
  // Phải có ít nhất 1 ký tự thường hoặc cả hai viết cùng tập chữ cái (VD: AB/AB, BV/bv, Ab/aB, ABD/abd, BB/dd)
  const hasLower = /[a-z]/.test(top + bot);
  const sameLetters = top.toLowerCase() === bot.toLowerCase();
  return hasLower || sameLetters;
}

/**
 * Chuyển đổi văn bản Sinh học / Hóa sinh thành HTML chuẩn SGK GDPT 2018:
 * - Kiểu gene liên kết dạng phân số 2 gạch ngang: AB/ab, BV/bv, ABD/abd, De/dE
 * - Kiểu gene liên kết NST giới tính: X^{DE}X^{de}, X^A X^a, X^A Y, XAXa, XAY, DdXHY
 * - Nhóm máu ABO: I^A, I^B, I^O, I^A I^B
 * - Công thức phân tử, đồng vị phóng xạ (15N, 14N, 32P...), thế hệ lai (F1, F2...)
 */
export function formatBioHtml(raw) {
  let s = escapeHtml(raw);
  if (!s) return "";

  // 1. Ký hiệu lũy thừa có ngoặc nhọn: X^{DE}, Y^{Hd}, 10^{-6}
  s = s.replace(/([A-Za-z0-9\)])\^\{([A-Za-z0-9\+\-]+)\}/g, "$1<sup>$2</sup>");
  // Ký hiệu lũy thừa/chỉ số tường minh từ OMML: X^A, X^a, 2^n, 2^k, 10^-6, PO4^3-
  s = s.replace(/([A-Za-z0-9\)])\^([A-Za-z0-9\+\-]+)/g, "$1<sup>$2</sup>");
  s = s.replace(/([A-Za-z])_([A-Za-z0-9]+)/g, "$1<sub>$2</sub>");

  // 2. Công thức phân tử đa nguyên tử cụ thể (tránh nhầm chữ thường)
  const exactFormulas = [
    [/\bC5H10O4\b/g, "C<sub>5</sub>H<sub>10</sub>O<sub>4</sub>"],
    [/\bC5H10O5\b/g, "C<sub>5</sub>H<sub>10</sub>O<sub>5</sub>"],
    [/\bC6H12O6\b/g, "C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>"],
    [/\bC12H22O11\b/g, "C<sub>12</sub>H<sub>22</sub>O<sub>11</sub>"],
    [/\bH3PO4\b/g, "H<sub>3</sub>PO<sub>4</sub>"],
    [/\bH2SO4\b/g, "H<sub>2</sub>SO<sub>4</sub>"],
    [/\bH2CO3\b/g, "H<sub>2</sub>CO<sub>3</sub>"],
    [/\bHNO3\b/g, "HNO<sub>3</sub>"],
    [/\bNaHCO3\b/g, "NaHCO<sub>3</sub>"],
    [/\bCaCO3\b/g, "CaCO<sub>3</sub>"],
    [/\bMgCl2\b/g, "MgCl<sub>2</sub>"],
    [/\bCaCl2\b/g, "CaCl<sub>2</sub>"],
    [/\bNH4\+/g, "NH<sub>4</sub><sup>+</sup>"],
    [/\bNH3\b/g, "NH<sub>3</sub>"],
    [/\bNH2\b/g, "NH<sub>2</sub>"],
    [/\bCH4\b/g, "CH<sub>4</sub>"],
    [/\bCH3\b/g, "CH<sub>3</sub>"],
    [/\bCH2\b/g, "CH<sub>2</sub>"],
    [/\bH2O2\b/g, "H<sub>2</sub>O<sub>2</sub>"],
    [/\bH2O\b/g, "H<sub>2</sub>O"],
    [/\bCO2\b/g, "CO<sub>2</sub>"],
    [/\bSO2\b/g, "SO<sub>2</sub>"],
    [/\bNO2\b/g, "NO<sub>2</sub>"],
    [/\bNO3-/g, "NO<sub>3</sub><sup>−</sup>"],
    [/\bSO42-/g, "SO<sub>4</sub><sup>2−</sup>"],
    [/\bPO43-/g, "PO<sub>4</sub><sup>3−</sup>"],
    [/(-?)PO4\b/g, "$1PO<sub>4</sub>"],
    [/\bO2\b/g, "O<sub>2</sub>"],
    [/\bH2\b/g, "H<sub>2</sub>"],
    [/\bN2\b/g, "N<sub>2</sub>"],
    [/\bCl2\b/g, "Cl<sub>2</sub>"],
    [/\bCa2\+/g, "Ca<sup>2+</sup>"],
    [/\bMg2\+/g, "Mg<sup>2+</sup>"],
    [/\bFe2\+/g, "Fe<sup>2+</sup>"],
    [/\bFe3\+/g, "Fe<sup>3+</sup>"],
    [/\bCu2\+/g, "Cu<sup>2+</sup>"],
    [/\bZn2\+/g, "Zn<sup>2+</sup>"],
    [/\bK\+(?=\s|,|\.|;|\)|$)/g, "K<sup>+</sup>"],
    [/\bNa\+(?=\s|,|\.|;|\)|$)/g, "Na<sup>+</sup>"],
    [/\bH\+(?=\s|,|\.|;|\)|$)/g, "H<sup>+</sup>"],
    [/\bOH-(?=\s|,|\.|;|\)|$)/g, "OH<sup>−</sup>"],
    [/\bCl-(?=\s|,|\.|;|\)|$)/g, "Cl<sup>−</sup>"],
  ];
  for (const [re, rep] of exactFormulas) {
    s = s.replace(re, rep);
  }

  // 3. Đồng vị phóng xạ phổ biến trong Sinh học 12
  s = s.replace(/\b(14|15)N\b/g, "<sup>$1</sup>N");
  s = s.replace(/\b(32)P\b/g, "<sup>$1</sup>P");
  s = s.replace(/\b(35)S\b/g, "<sup>$1</sup>S");
  s = s.replace(/\b(14)C\b/g, "<sup>$1</sup>C");
  s = s.replace(/\b(18)O\b/g, "<sup>$1</sup>O");

  // 4. Thế hệ lai (F1, F2, F3, Fa, Fb, P1, P2, B1, B2) & pha phân bào (G1, G2) & allele chỉ số (A1, A2, D1, D2, D3)
  s = s.replace(/\b(F|P|B|G)([1-4ab])\b/g, "$1<sub>$2</sub>");
  s = s.replace(/\b(P)(tc|t\/c)\b/g, "P<sub>tc</sub>");

  // 5. Nhóm máu ABO (IA, IB, IO) và NST giới tính (XAXA, XAXa, XaXa, XAY, XaY, DdXHY, XA, Xa...)
  s = s.replace(/\bI([ABO])\b/g, "I<sup>$1</sup>");
  s = s.replace(/\bI([ABO])I([ABO])\b/g, "I<sup>$1</sup>I<sup>$2</sup>");
  s = s.replace(
    /\b((?:[A-Za-z]{2})*)X([ABDEHMRWabdehmrw])X([ABDEHMRWabdehmrw])\b/g,
    "$1X<sup>$2</sup>X<sup>$3</sup>"
  );
  s = s.replace(
    /\b((?:[A-Za-z]{2})*)X([ABDEHMRWabdehmrw])Y([ABDEHMRWabdehmrw]?)\b/g,
    (_, pre, a, b) => (b ? `${pre}X<sup>${a}</sup>Y<sup>${b}</sup>` : `${pre}X<sup>${a}</sup>Y`)
  );
  // Allele đơn trên NST X (VD: XA quy định mắt đỏ, Xa quy định mắt trắng)
  s = s.replace(/\bX([ABDEHMRWabdehmrw])\b/g, "X<sup>$1</sup>");

  // 6. Kiểu gene liên kết dạng phân số 2 gạch ngang chuẩn SGK (VD: AB/ab, BV/bv, Ab/aB, ABD/abd)
  s = s.replace(/(?<![A-Za-z0-9<\/])([A-Za-z]{2,4})\/([A-Za-z]{2,4})(?![A-Za-z0-9>])/g, (full, top, bot) => {
    if (!isLinkedGenotypePair(top, bot)) return full;
    return `<span class="geno-linked"><span class="geno-top">${top}</span><span class="geno-bot">${bot}</span></span>`;
  });

  // 7. Ký hiệu mạch 5' và 3' thống nhất đẹp
  s = s.replace(/([35])’/g, "$1'");

  return s;
}
