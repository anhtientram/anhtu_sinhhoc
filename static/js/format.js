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

  // 1. Ký hiệu toán học cơ bản & chỉ số trên/dưới có ngoặc nhọn (từ Word <w:vertAlign> hoặc OMML)
  s = s.replace(/&lt;-&gt;|&lt;=&gt;/g, "↔");
  s = s.replace(/-&gt;/g, "→");
  s = s.replace(/&lt;=/g, "≤");
  s = s.replace(/&gt;=/g, "≥");
  s = s.replace(/!=/g, "≠");
  s = s.replace(/\+\/-|\+-/g, "±");
  s = s.replace(/\^[∘\u2218]/g, "°");
  s = s.replace(/\^\{([^{}]+)\}/g, "<sup>$1</sup>");
  s = s.replace(/_\{([^{}]+)\}/g, "<sub>$1</sub>");
  s = s.replace(/\blog_(\d+|a|e)\b/g, "log<sub>$1</sub>");
  s = s.replace(/(^|[^A-Za-z0-9_])_(\d{1,3})(?=[A-Z])/g, "$1<sub>$2</sub>");
  // Ký hiệu nhóm máu ABO & NST giới tính có dấu mũ liền kề (I^AI^O, X^AX^a, X^AY, X^DEX^de)
  s = s.replace(/I\^([ABO])/g, "I<sup>$1</sup>");
  s = s.replace(/([XY])\^([A-Za-z]{1,2}?)(?=[XYI]|[^A-Za-z0-9]|$)/g, "$1<sup>$2</sup>");
  // Ký hiệu lũy thừa/chỉ số tường minh từ OMML: 2^n, 2^k, 10^-6, PO4^3-, C^r, C^p, C^y
  s = s.replace(/([A-Za-z0-9\)])\^([A-Za-z0-9\+\-]+)/g, "$1<sup>$2</sup>");
  // Chỉ số dưới dạng số (Y_2O, C_2H_5OH) và biến toán (x_n, u_n — tránh làm hỏng kiểu hình A_B_, A_bb)
  s = s.replace(/([A-Za-z\)])_([0-9]{1,3})(?![0-9_])/g, "$1<sub>$2</sub>");
  s = s.replace(/([A-Za-z])_([nkmxij])(?![A-Za-z0-9_])/g, "$1<sub>$2</sub>");

  // 2. Công thức phân tử đa nguyên tử cụ thể (tránh nhầm chữ thường)
  const exactFormulas = [
    [/\bH2O18\b/g, "H<sub>2</sub>O<sup>18</sup>"],
    [/\bH2O16\b/g, "H<sub>2</sub>O<sup>16</sup>"],
    [/\bC5H10O4\b/g, "C<sub>5</sub>H<sub>10</sub>O<sub>4</sub>"],
    [/\bC5H10O5\b/g, "C<sub>5</sub>H<sub>10</sub>O<sub>5</sub>"],
    [/\bC6H12O6\b/g, "C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>"],
    [/\bC12H22O11\b/g, "C<sub>12</sub>H<sub>22</sub>O<sub>11</sub>"],
    [/\bC2H5OH\b/g, "C<sub>2</sub>H<sub>5</sub>OH"],
    [/\bCH3COOH\b/g, "CH<sub>3</sub>COOH"],
    [/\bC2H4\b/g, "C<sub>2</sub>H<sub>4</sub>"],
    [/\bC2H2\b/g, "C<sub>2</sub>H<sub>2</sub>"],
    [/\bC6H6\b/g, "C<sub>6</sub>H<sub>6</sub>"],
    [/\bCa3\(PO4\)2\b/g, "Ca<sub>3</sub>(PO<sub>4</sub>)<sub>2</sub>"],
    [/\b(Ca|Mg|Ba|Cu|Fe|Zn)\(OH\)2\b/g, "$1(OH)<sub>2</sub>"],
    [/\b(Fe|Al)\(OH\)3\b/g, "$1(OH)<sub>3</sub>"],
    [/\bH3PO4\b/g, "H<sub>3</sub>PO<sub>4</sub>"],
    [/\bH2SO4\b/g, "H<sub>2</sub>SO<sub>4</sub>"],
    [/\bH2CO3\b/g, "H<sub>2</sub>CO<sub>3</sub>"],
    [/\bHNO3\b/g, "HNO<sub>3</sub>"],
    [/\bNaHCO3\b/g, "NaHCO<sub>3</sub>"],
    [/\bNa2CO3\b/g, "Na<sub>2</sub>CO<sub>3</sub>"],
    [/\bNa2SO4\b/g, "Na<sub>2</sub>SO<sub>4</sub>"],
    [/\bCaCO3\b/g, "CaCO<sub>3</sub>"],
    [/\bCuSO4\b/g, "CuSO<sub>4</sub>"],
    [/\bBaSO4\b/g, "BaSO<sub>4</sub>"],
    [/\bAgNO3\b/g, "AgNO<sub>3</sub>"],
    [/\bFe2O3\b/g, "Fe<sub>2</sub>O<sub>3</sub>"],
    [/\bFe3O4\b/g, "Fe<sub>3</sub>O<sub>4</sub>"],
    [/\bAl2O3\b/g, "Al<sub>2</sub>O<sub>3</sub>"],
    [/\bMgCl2\b/g, "MgCl<sub>2</sub>"],
    [/\bCaCl2\b/g, "CaCl<sub>2</sub>"],
    [/\bH2PO4-/g, "H<sub>2</sub>PO<sub>4</sub><sup>−</sup>"],
    [/\bHPO42-/g, "HPO<sub>4</sub><sup>2−</sup>"],
    [/\bHSO4-/g, "HSO<sub>4</sub><sup>−</sup>"],
    [/\bNH4\+/g, "NH<sub>4</sub><sup>+</sup>"],
    [/\bNADP\+/g, "NADP<sup>+</sup>"],
    [/\bNAD\+/g, "NAD<sup>+</sup>"],
    [/\bFAD\+/g, "FAD<sup>+</sup>"],
    [/\bNH3\b/g, "NH<sub>3</sub>"],
    [/\bNH2\b/g, "NH<sub>2</sub>"],
    [/\bCH4\b/g, "CH<sub>4</sub>"],
    [/\bCH3\b/g, "CH<sub>3</sub>"],
    [/\bCH2\b/g, "CH<sub>2</sub>"],
    [/\bH2O2\b/g, "H<sub>2</sub>O<sub>2</sub>"],
    [/\bH2O\b/g, "H<sub>2</sub>O"],
    [/\bCO2\b/g, "CO<sub>2</sub>"],
    [/\bSO([23])\b/g, "SO<sub>$1</sub>"],
    [/\bNO2\b/g, "NO<sub>2</sub>"],
    [/\bNO3-/g, "NO<sub>3</sub><sup>−</sup>"],
    [/\bSO42-/g, "SO<sub>4</sub><sup>2−</sup>"],
    [/\bPO43-/g, "PO<sub>4</sub><sup>3−</sup>"],
    [/(-?)PO4\b/g, "$1PO<sub>4</sub>"],
    [/\bO([23])\b/g, "O<sub>$1</sub>"],
    [/\bH2\b/g, "H<sub>2</sub>"],
    [/\bN2\b/g, "N<sub>2</sub>"],
    [/\bCl2\b/g, "Cl<sub>2</sub>"],
    [/\bCa2\+/g, "Ca<sup>2+</sup>"],
    [/\bMg2\+/g, "Mg<sup>2+</sup>"],
    [/\bFe2\+/g, "Fe<sup>2+</sup>"],
    [/\bFe3\+/g, "Fe<sup>3+</sup>"],
    [/\bCu2\+/g, "Cu<sup>2+</sup>"],
    [/\bZn2\+/g, "Zn<sup>2+</sup>"],
    [/\bAl3\+/g, "Al<sup>3+</sup>"],
    [/\bAg\+(?=\s|,|\.|;|\)|$)/g, "Ag<sup>+</sup>"],
    [/\bK\+(?=\s|,|\.|;|\)|$)/g, "K<sup>+</sup>"],
    [/\bNa\+(?=\s|,|\.|;|\)|$)/g, "Na<sup>+</sup>"],
    [/\bH\+(?=\s|,|\.|;|\)|$)/g, "H<sup>+</sup>"],
    [/\bOH-(?=\s|,|\.|;|\)|$)/g, "OH<sup>−</sup>"],
    [/\bCl-(?=\s|,|\.|;|\)|$)/g, "Cl<sup>−</sup>"],
    [/\bmRNA([1-4])\b/g, "mRNA<sub>$1</sub>"],
  ];
  for (const [re, rep] of exactFormulas) {
    s = s.replace(re, rep);
  }

  // 3. Đồng vị phóng xạ phổ biến & đơn vị diện tích/thể tích trong Sinh học 12
  s = s.replace(/\b(14|15)N\b/g, "<sup>$1</sup>N");
  s = s.replace(/\b(32)P\b/g, "<sup>$1</sup>P");
  s = s.replace(/\b(35)S\b/g, "<sup>$1</sup>S");
  s = s.replace(/\b(14)C\b/g, "<sup>$1</sup>C");
  s = s.replace(/\b(18|16)O\b/g, "<sup>$1</sup>O");
  s = s.replace(/\bO(18|16)\b/g, "O<sup>$1</sup>");
  s = s.replace(/\bN(15|14)\b/g, "N<sup>$1</sup>");
  s = s.replace(/\b(mm|cm|dm|km|m)([23])\b/g, "$1<sup>$2</sup>");

  // 4. Thế hệ lai (F1, F2, F3, Fa, Fb, P1, P2, B1, B2) & mạch đơn DNA (A1, T1, G1, C1, A2, T2, G2, C2) & allele chỉ số (A1..A4, D1..D3)
  s = s.replace(/\bF([1-4ab])\b/g, "F<sub>$1</sub>");
  s = s.replace(/\b(P|B|G)([1-4])\b/g, "$1<sub>$2</sub>");
  s = s.replace(/\b(A|T|C|U|D)([1-4])\b/g, "$1<sub>$2</sub>");
  s = s.replace(/\b(A|T|G|C)([12])%/g, "$1<sub>$2</sub>%");
  s = s.replace(/\b(P)(tc|t\/c)\b/g, "P<sub>tc</sub>");

  // 5. Nhóm máu ABO (IA, IB, IO) và NST giới tính (XAXA, XAXa, XaXa, XAXaXa, XAY, XaY, XY^a, DdXHY, XA, Xa...)
  s = s.replace(/\bI([ABO])I([ABO])\b/g, "I<sup>$1</sup>I<sup>$2</sup>");
  s = s.replace(/\bI([ABO])\b/g, "I<sup>$1</sup>");
  s = s.replace(
    /\b((?:[A-Za-z]{2})*)X([ABDEHMRWabdehmrw])X([ABDEHMRWabdehmrw])X([ABDEHMRWabdehmrw])\b/g,
    "$1X<sup>$2</sup>X<sup>$3</sup>X<sup>$4</sup>"
  );
  s = s.replace(
    /\b((?:[A-Za-z]{2})*)X([ABDEHMRWabdehmrw])X([ABDEHMRWabdehmrw])\b/g,
    "$1X<sup>$2</sup>X<sup>$3</sup>"
  );
  s = s.replace(
    /\b((?:[A-Za-z]{2})*)X([ABDEHMRWabdehmrw])Y([ABDEHMRWabdehmrw]?)\b/g,
    (_, pre, a, b) => (b ? `${pre}X<sup>${a}</sup>Y<sup>${b}</sup>` : `${pre}X<sup>${a}</sup>Y`)
  );
  s = s.replace(/\bXY([ABDEHMRWabdehmrw])\b/g, "XY<sup>$1</sup>");
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
