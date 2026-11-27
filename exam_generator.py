"""
Bộ trộn đề trắc nghiệm chuẩn GDPT 2018 (hỗ trợ cả Ma trận 3x3 và trộn trực tiếp từ file Word .docx)
- Hỗ trợ chọn nhiều bài trong nhiều chủ đề hoặc tải file Word (.docx) gốc
- Tự nhập số lượng đề trộn & mã đề 4 số (VD: 1001, 1002, 1003, 1004) + mặc định kèm file Đề gốc mã đề 0000
- Trộn thứ tự câu hỏi, trộn phương án A/B/C/D (MCQ) và ý a/b/c/d (Đúng/Sai), tự động ánh xạ lại đáp án chuẩn
- Giữ nguyên hình ảnh gốc từ Word (theo đúng kích thước hiển thị), hỗ trợ bảng gộp ô (colspan / vMerge)
- Chuẩn hoá công thức Hoá học, Toán học, Sinh học bằng chỉ số dưới (subscript) & chỉ số trên (superscript) thật trong Word
- Các nhãn đáp án (A.; B.; C.; D.) và (a); b); c); d)) in đậm & căn thụt lề đồng bộ 0,5 cm bằng bảng cố định
- Cho phép để trống Trường / Môn (tự động ẩn dòng tiêu đề tương ứng trong file Word xuất ra)
- Xuất trọn bộ file nén (.zip) tách riêng từng mã đề (Ma_de_0000.docx, Ma_de_1001.docx...) + Dap_an.xlsx
"""
import base64
import io
import os
import random
import re
import struct
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

VN_TZ = timezone(timedelta(hours=7))

try:
    import docx
    from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Inches, Pt, RGBColor
except ImportError:
    docx = None
    WD_ALIGN_VERTICAL = WD_TABLE_ALIGNMENT = None
    WD_ALIGN_PARAGRAPH = WD_TAB_ALIGNMENT = None
    OxmlElement = qn = None
    Cm = Inches = Pt = RGBColor = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
EXTRA_UPLOADS_DIR = os.environ.get("UPLOADS_DIR", "").strip()

LEVEL_LABELS = {
    "nhan_biet": "Nhận biết",
    "thong_hieu": "Hiểu",
    "van_dung": "Vận dụng",
}


def format_short_answer_4chars(ans_list: List[str]) -> str:
    """Chuẩn hóa đáp án trả lời ngắn (giữ chính xác giá trị số, chuẩn dấu phẩy thập phân)."""
    if not ans_list:
        return ""
    raw = str(ans_list[0]).strip().replace(".", ",")
    m_frac = re.match(r"^(-?\d+)\s*/\s*(\d+)$", raw)
    if m_frac and int(m_frac.group(2)) != 0:
        val = int(m_frac.group(1)) / int(m_frac.group(2))
        s = f"{val:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        return s
    cleaned = re.sub(r"[^0-9,\-]", "", raw)
    if cleaned:
        return cleaned
    return raw


def normalize_exam_codes(raw_codes, exam_count: int, default_start: int = 1001) -> List[str]:
    """Chuẩn hoá danh sách mã đề (mặc định 4 chữ số: 1001, 1002, 1003, 1004...) khớp đúng số lượng đề trộn."""
    count = max(1, min(30, int(exam_count or 1)))
    if isinstance(raw_codes, str):
        parsed = [c.strip() for c in re.split(r"[,;\s]+", raw_codes) if c.strip()]
    elif isinstance(raw_codes, list):
        parsed = [str(c).strip() for c in raw_codes if str(c).strip()]
    else:
        parsed = []

    if not parsed:
        return [str(default_start + i).zfill(4) for i in range(count)]

    codes = list(parsed[:count])
    if len(codes) < count:
        last_code = codes[-1]
        if last_code.isdigit():
            base_num = int(last_code)
            width = max(4, len(last_code))
            while len(codes) < count:
                base_num += 1
                codes.append(str(base_num).zfill(width))
        else:
            idx = 1
            while len(codes) < count:
                codes.append(f"{last_code}-{idx}")
                idx += 1
    return codes


def _pick_from_pool(pool: List[Dict], count: int, rng: random.Random) -> List[Dict]:
    if count <= 0:
        return []
    if len(pool) <= count:
        chosen = list(pool)
        rng.shuffle(chosen)
        return chosen
    return rng.sample(pool, count)


def _select_questions_by_matrix(
    topics: List[Dict],
    selected_lesson_ids: List[str],
    matrix: Dict[str, Dict[str, int]],
    rng: random.Random,
) -> Tuple[List[Dict], List[Dict], List[Dict], Dict]:
    lesson_set = set(selected_lesson_ids or [])

    pools = {
        "mcq": {"nhan_biet": [], "thong_hieu": [], "van_dung": []},
        "true_false": {"nhan_biet": [], "thong_hieu": [], "van_dung": []},
        "short_answer": {"nhan_biet": [], "thong_hieu": [], "van_dung": []},
    }

    for t in topics:
        rev = t.get("review") or {}
        for kind in ("mcq", "true_false", "short_answer"):
            for q in rev.get(kind, []):
                if lesson_set and q.get("lesson_id") not in lesson_set:
                    continue
                lv = q.get("cognitive_level", "thong_hieu")
                if lv not in pools[kind]:
                    lv = "thong_hieu"
                pools[kind][lv].append(q)

    selected = {"mcq": [], "true_false": [], "short_answer": []}
    actual_counts = {
        "mcq": {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0},
        "true_false": {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0},
        "short_answer": {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0},
    }

    for kind in ("mcq", "true_false", "short_answer"):
        used_ids = set()
        for lv in ("nhan_biet", "thong_hieu", "van_dung"):
            want = int((matrix.get(kind) or {}).get(lv) or 0)
            if want <= 0:
                continue
            avail = [q for q in pools[kind][lv] if q["id"] not in used_ids]
            keyed = [q for q in avail if q.get("answer_key_ready")]
            unkeyed = [q for q in avail if not q.get("answer_key_ready")]

            picked = _pick_from_pool(keyed, min(want, len(keyed)), rng)
            if len(picked) < want:
                picked.extend(_pick_from_pool(unkeyed, want - len(picked), rng))

            for q in picked:
                used_ids.add(q["id"])
                selected[kind].append(q)
            actual_counts[kind][lv] = len(picked)

    return selected["mcq"], selected["true_false"], selected["short_answer"], actual_counts


def _group_and_order_questions(items: List[Dict], rng: random.Random) -> List[Dict]:
    if not items:
        return []
    groups: List[Dict] = []
    for q in items:
        gid = q.get("group_id") or "__default__"
        mode = (q.get("shuffle_mode") or "g3").lower()
        fixed = bool(q.get("group_fixed"))
        if not groups or groups[-1]["id"] != gid:
            groups.append({"id": gid, "mode": mode, "fixed": fixed, "items": []})
        groups[-1]["items"].append(q)

    unfixed_indices = [i for i, g in enumerate(groups) if not g["fixed"]]
    if len(unfixed_indices) >= 2:
        unfixed_objs = [groups[i] for i in unfixed_indices]
        rng.shuffle(unfixed_objs)
        for slot_idx, grp_obj in zip(unfixed_indices, unfixed_objs):
            groups[slot_idx] = grp_obj

    ordered: List[Dict] = []
    for g in groups:
        chunk = list(g["items"])
        if g["mode"] in ("g1", "g3") and len(chunk) >= 2:
            rng.shuffle(chunk)
        ordered.extend(chunk)
    return ordered


def _shuffle_with_fixed_slots(seq: List, fixed_indices: List[int], rng: random.Random) -> List:
    n = len(seq)
    if n < 2:
        return list(seq)
    fixed_set = {i for i in (fixed_indices or []) if 0 <= i < n}
    movable_slots = [i for i in range(n) if i not in fixed_set]
    if len(movable_slots) < 2:
        return list(seq)
    movable_vals = [seq[i] for i in movable_slots]
    rng.shuffle(movable_vals)
    out = list(seq)
    for slot, val in zip(movable_slots, movable_vals):
        out[slot] = val
    return out


def _shuffle_single_exam(
    mcqs: List[Dict],
    tfs: List[Dict],
    sas: List[Dict],
    exam_code: str,
    rng: random.Random,
) -> Dict:
    """Trộn thứ tự câu hỏi và trộn phương án/ý cho 1 mã đề theo đúng thẻ <g0>..<#g3> và cố định đáp án #A..#D."""
    shuffled_mcq = []
    mcq_order = _group_and_order_questions(mcqs, rng)

    for q in mcq_order:
        mode = (q.get("shuffle_mode") or "g3").lower()
        opts = list(q.get("options") or [])
        indexed = list(enumerate(opts))
        fixed_opts = list(q.get("fixed_options") or [])
        has_ref = any(
            re.search(r"(cả\s*[a-d]|tất\s*cả\s*(?:các|đều))", o, re.IGNORECASE)
            for o in opts
        )
        should_shuffle_opts = (mode in ("g2", "g3")) and (not has_ref) and len(indexed) >= 2
        if should_shuffle_opts:
            indexed = _shuffle_with_fixed_slots(indexed, fixed_opts, rng)

        orig_correct = q.get("correct_index")
        new_correct = None
        new_opts = []
        for new_i, (old_i, text) in enumerate(indexed):
            new_opts.append(text)
            if orig_correct is not None and old_i == orig_correct:
                new_correct = new_i

        shuffled_mcq.append(
            {
                "question": q.get("question", ""),
                "stem_blocks": q.get("stem_blocks") or [],
                "images": q.get("images") or [],
                "image_widths": q.get("image_widths") or [],
                "tables": q.get("tables") or [],
                "options": new_opts,
                "correct_letter": "ABCD"[new_correct] if new_correct is not None and new_correct < 4 else "",
                "explanation": q.get("explanation", ""),
                "level": LEVEL_LABELS.get(q.get("cognitive_level", ""), ""),
            }
        )

    shuffled_tf = []
    tf_order = _group_and_order_questions(tfs, rng)
    for q in tf_order:
        mode = (q.get("shuffle_mode") or "g3").lower()
        stmts = list(q.get("statements") or [])[:4]
        fixed_stmt_slots = [i for i, st in enumerate(stmts) if st.get("fixed")]
        if mode in ("g2", "g3") and len(stmts) >= 2:
            stmts = _shuffle_with_fixed_slots(stmts, fixed_stmt_slots, rng)
        new_stmts = []
        ans_keys = {}
        for idx, st in enumerate(stmts):
            k = "abcd"[idx]
            ans_val = st.get("answer")
            new_stmts.append({"key": k, "text": st.get("text", ""), "answer": ans_val})
            ans_keys[k] = "Đ" if ans_val is True else ("S" if ans_val is False else "")
        shuffled_tf.append(
            {
                "stem": q.get("stem") or q.get("question") or "",
                "stem_blocks": q.get("stem_blocks") or [],
                "images": q.get("images") or [],
                "image_widths": q.get("image_widths") or [],
                "tables": q.get("tables") or [],
                "statements": new_stmts,
                "ans_keys": ans_keys,
                "explanation": q.get("explanation", ""),
                "level": LEVEL_LABELS.get(q.get("cognitive_level", ""), ""),
            }
        )

    shuffled_sa = []
    sa_order = _group_and_order_questions(sas, rng)
    for q in sa_order:
        shuffled_sa.append(
            {
                "question": q.get("question", ""),
                "stem_blocks": q.get("stem_blocks") or [],
                "images": q.get("images") or [],
                "image_widths": q.get("image_widths") or [],
                "tables": q.get("tables") or [],
                "answer": format_short_answer_4chars(q.get("accepted_answers") or []),
                "explanation": q.get("explanation", ""),
                "level": LEVEL_LABELS.get(q.get("cognitive_level", ""), ""),
            }
        )

    return {
        "code": exam_code,
        "mcq": shuffled_mcq,
        "true_false": shuffled_tf,
        "short_answer": shuffled_sa,
    }


def _build_unshuffled_original_exam(
    mcqs: List[Dict],
    tfs: List[Dict],
    sas: List[Dict],
    exam_code: str = "0000",
) -> Dict:
    """Tạo bản Đề gốc giữ nguyên 100% thứ tự câu hỏi và đáp án, mặc định mã đề '0000'."""
    orig_mcq = []
    for q in mcqs or []:
        opts = list(q.get("options") or [])
        orig_correct = q.get("correct_index")
        orig_mcq.append(
            {
                "question": q.get("question", ""),
                "stem_blocks": q.get("stem_blocks") or [],
                "images": q.get("images") or [],
                "image_widths": q.get("image_widths") or [],
                "tables": q.get("tables") or [],
                "options": opts,
                "correct_letter": "ABCD"[orig_correct] if orig_correct is not None and 0 <= orig_correct < 4 else "",
                "explanation": q.get("explanation", ""),
                "level": LEVEL_LABELS.get(q.get("cognitive_level", ""), ""),
            }
        )

    orig_tf = []
    for q in tfs or []:
        stmts = list(q.get("statements") or [])[:4]
        new_stmts = []
        ans_keys = {}
        for idx, st in enumerate(stmts):
            k = "abcd"[idx]
            ans_val = st.get("answer")
            new_stmts.append({"key": k, "text": st.get("text", ""), "answer": ans_val})
            ans_keys[k] = "Đ" if ans_val is True else ("S" if ans_val is False else "")
        orig_tf.append(
            {
                "stem": q.get("stem") or q.get("question") or "",
                "stem_blocks": q.get("stem_blocks") or [],
                "images": q.get("images") or [],
                "image_widths": q.get("image_widths") or [],
                "tables": q.get("tables") or [],
                "statements": new_stmts,
                "ans_keys": ans_keys,
                "explanation": q.get("explanation", ""),
                "level": LEVEL_LABELS.get(q.get("cognitive_level", ""), ""),
            }
        )

    orig_sa = []
    for q in sas or []:
        orig_sa.append(
            {
                "question": q.get("question", ""),
                "stem_blocks": q.get("stem_blocks") or [],
                "images": q.get("images") or [],
                "image_widths": q.get("image_widths") or [],
                "tables": q.get("tables") or [],
                "answer": format_short_answer_4chars(q.get("accepted_answers") or []),
                "explanation": q.get("explanation", ""),
                "level": LEVEL_LABELS.get(q.get("cognitive_level", ""), ""),
            }
        )

    return {
        "code": exam_code,
        "is_original": True,
        "mcq": orig_mcq,
        "true_false": orig_tf,
        "short_answer": orig_sa,
    }


# ================== CHUẨN HOÁ CÔNG THỨC HOÁ HỌC, TOÁN HỌC & SINH HỌC TRONG WORD ==================

_UNICODE_SUB_MAP = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎", "0123456789+-=()")
_UNICODE_SUP_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ", "0123456789+-=()n")
_RE_UNICODE_SUB = re.compile(r"[₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎]+")
_RE_UNICODE_SUP = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ]+")

_MATH_SYMBOL_RULES = [
    (re.compile(r"<=>|<->"), "↔"),
    (re.compile(r"->"), "→"),
    (re.compile(r"<-"), "←"),
    (re.compile(r"<="), "≤"),
    (re.compile(r">="), "≥"),
    (re.compile(r"!="), "≠"),
    (re.compile(r"\+/-"), "±"),
    (re.compile(r"\^\{?\s*[∘\u2218]\s*\}?"), "°"),
    (re.compile(r"\\Delta\b"), "Δ"),
    (re.compile(r"\\alpha\b"), "α"),
    (re.compile(r"\\beta\b"), "β"),
    (re.compile(r"\\gamma\b"), "γ"),
    (re.compile(r"\\lambda\b"), "λ"),
    (re.compile(r"\\mu\b"), "μ"),
    (re.compile(r"\\pi\b"), "π"),
]

# Các công thức thường gặp trong Hoá học, Toán học và Sinh học
_CHEM_BIO_AUTO_RULES = [
    # 1. Cú pháp chỉ số từ OMML/LaTeX thô (VD: _11Na -> _{11}Na, Y_2O_5 -> Y_{2}O_{5}, C_2H_2 -> C_{2}H_{2}, log_2 -> log_{2})
    (re.compile(r"(?<![A-Za-z0-9}])_(\d{1,3})([A-Z][a-z]?)"), r"_{\1}\2"),
    (re.compile(r"([A-Za-z0-9\)\]])_(\d{1,3}|[nmxyz])(?![A-Za-z0-9{])"), r"\1_{\2}"),
    (re.compile(r"([A-Za-z0-9\)\]])\^([+-]?\d{1,3}[+-]?|[+-]|[nmxy])(?![A-Za-z0-9{])"), r"\1^{\2}"),
    # 2. Đồng vị phóng xạ & phân tử đánh dấu trong Sinh học / Hoá học
    (re.compile(r"\bH2O18\b"), "H_{2}O^{18}"),
    (re.compile(r"\bH2O16\b"), "H_{2}O^{16}"),
    (re.compile(r"\bCO2\b"), "CO_{2}"),
    (re.compile(r"\bH2O2\b"), "H_{2}O_{2}"),
    (re.compile(r"\bH2O\b"), "H_{2}O"),
    (re.compile(r"\bO18\b"), "O^{18}"),
    (re.compile(r"\bO16\b"), "O^{16}"),
    (re.compile(r"\bN15\b"), "N^{15}"),
    (re.compile(r"\bN14\b"), "N^{14}"),
    (re.compile(r"\bP32\b"), "P^{32}"),
    (re.compile(r"\bS35\b"), "S^{35}"),
    (re.compile(r"\bC14\b"), "C^{14}"),
    # 3. Sinh học: NADH2, NADPH2, FADH2, NADP+, NAD+, thực vật C3/C4, thế hệ F1/F2/F3/Fb, Ptc, mRNA1...
    (re.compile(r"\bNADPH2\b"), "NADPH_{2}"),
    (re.compile(r"\bNADH2\b"), "NADH_{2}"),
    (re.compile(r"\bFADH2\b"), "FADH_{2}"),
    (re.compile(r"\bNADP\+"), "NADP^{+}"),
    (re.compile(r"\bNAD\+"), "NAD^{+}"),
    (re.compile(r"\bFAD\+"), "FAD^{+}"),
    (re.compile(r"\b(mRNA|tRNA|rRNA|DNA|RNA)([1-9])\b"), r"\1_{\2}"),
    (re.compile(r"\bC([34])\b"), r"C_{\1}"),
    (re.compile(r"\bF([123bB])\b"), r"F_{\1}"),
    (re.compile(r"\bP(t/c|tc)\b"), r"P_{\1}"),
    # 4. Công thức hữu cơ & sinh hoá phổ biến
    (re.compile(r"\bC12H22O11\b"), "C_{12}H_{22}O_{11}"),
    (re.compile(r"\bC6H12O6\b"), "C_{6}H_{12}O_{6}"),
    (re.compile(r"\bC6H10O5\b"), "C_{6}H_{10}O_{5}"),
    (re.compile(r"\bC6H6\b"), "C_{6}H_{6}"),
    (re.compile(r"\bC3H8\b"), "C_{3}H_{8}"),
    (re.compile(r"\bC3H6\b"), "C_{3}H_{6}"),
    (re.compile(r"\bC3H4\b"), "C_{3}H_{4}"),
    (re.compile(r"\bC2H6\b"), "C_{2}H_{6}"),
    (re.compile(r"\bC2H4\b"), "C_{2}H_{4}"),
    (re.compile(r"\bC2H2\b"), "C_{2}H_{2}"),
    (re.compile(r"\bC2H5OH\b"), "C_{2}H_{5}OH"),
    (re.compile(r"\bCH3COOH\b"), "CH_{3}COOH"),
    (re.compile(r"\bCH3OH\b"), "CH_{3}OH"),
    (re.compile(r"\bCH4\b"), "CH_{4}"),
    # 5. Axit, bazơ, muối, oxit & đơn chất vô cơ
    (re.compile(r"\bH2SO4\b"), "H_{2}SO_{4}"),
    (re.compile(r"\bH2SO3\b"), "H_{2}SO_{3}"),
    (re.compile(r"\bH2CO3\b"), "H_{2}CO_{3}"),
    (re.compile(r"\bH3PO4\b"), "H_{3}PO_{4}"),
    (re.compile(r"\bHNO3\b"), "HNO_{3}"),
    (re.compile(r"\bHNO2\b"), "HNO_{2}"),
    (re.compile(r"\bH2S\b"), "H_{2}S"),
    (re.compile(r"\bNH4NO3\b"), "NH_{4}NO_{3}"),
    (re.compile(r"\bNH4Cl\b"), "NH_{4}Cl"),
    (re.compile(r"\b(NH4)2SO4\b"), "(NH_{4})_{2}SO_{4}"),
    (re.compile(r"\bNH4\+"), "NH_{4}^{+}"),
    (re.compile(r"\bNH3\b"), "NH_{3}"),
    (re.compile(r"\bNO3-"), "NO_{3}^{-}"),
    (re.compile(r"\bNO2-"), "NO_{2}^{-}"),
    (re.compile(r"\bNO2\b"), "NO_{2}"),
    (re.compile(r"\bN2O\b"), "N_{2}O"),
    (re.compile(r"\bSO3\b"), "SO_{3}"),
    (re.compile(r"\bSO2\b"), "SO_{2}"),
    (re.compile(r"\bSO42-"), "SO_{4}^{2-}"),
    (re.compile(r"\bCO32-"), "CO_{3}^{2-}"),
    (re.compile(r"\bHCO3-"), "HCO_{3}^{-}"),
    (re.compile(r"\bH2PO4-"), "H_{2}PO_{4}^{-}"),
    (re.compile(r"\bHPO42-"), "HPO_{4}^{2-}"),
    (re.compile(r"\bPO43-"), "PO_{4}^{3-}"),
    (re.compile(r"\bCa\(OH\)2\b"), "Ca(OH)_{2}"),
    (re.compile(r"\bBa\(OH\)2\b"), "Ba(OH)_{2}"),
    (re.compile(r"\bMg\(OH\)2\b"), "Mg(OH)_{2}"),
    (re.compile(r"\bCu\(OH\)2\b"), "Cu(OH)_{2}"),
    (re.compile(r"\bFe\(OH\)2\b"), "Fe(OH)_{2}"),
    (re.compile(r"\bFe\(OH\)3\b"), "Fe(OH)_{3}"),
    (re.compile(r"\bAl\(OH\)3\b"), "Al(OH)_{3}"),
    (re.compile(r"\bCaCO3\b"), "CaCO_{3}"),
    (re.compile(r"\bMgCO3\b"), "MgCO_{3}"),
    (re.compile(r"\bBaCO3\b"), "BaCO_{3}"),
    (re.compile(r"\bNa2CO3\b"), "Na_{2}CO_{3}"),
    (re.compile(r"\bNaHCO3\b"), "NaHCO_{3}"),
    (re.compile(r"\bK2CO3\b"), "K_{2}CO_{3}"),
    (re.compile(r"\bKHCO3\b"), "KHCO_{3}"),
    (re.compile(r"\bNa2SO4\b"), "Na_{2}SO_{4}"),
    (re.compile(r"\bK2SO4\b"), "K_{2}SO_{4}"),
    (re.compile(r"\bCuSO4\b"), "CuSO_{4}"),
    (re.compile(r"\bFeSO4\b"), "FeSO_{4}"),
    (re.compile(r"\bFe2\(SO4\)3\b"), "Fe_{2}(SO_{4})_{3}"),
    (re.compile(r"\bAl2\(SO4\)3\b"), "Al_{2}(SO_{4})_{3}"),
    (re.compile(r"\bMgSO4\b"), "MgSO_{4}"),
    (re.compile(r"\bCaSO4\b"), "CaSO_{4}"),
    (re.compile(r"\bBaSO4\b"), "BaSO_{4}"),
    (re.compile(r"\bZnSO4\b"), "ZnSO_{4}"),
    (re.compile(r"\bAgNO3\b"), "AgNO_{3}"),
    (re.compile(r"\bKNO3\b"), "KNO_{3}"),
    (re.compile(r"\bNaNO3\b"), "NaNO_{3}"),
    (re.compile(r"\bCa\(NO3\)2\b"), "Ca(NO_{3})_{2}"),
    (re.compile(r"\bMg\(NO3\)2\b"), "Mg(NO_{3})_{2}"),
    (re.compile(r"\bCu\(NO3\)2\b"), "Cu(NO_{3})_{2}"),
    (re.compile(r"\bFe\(NO3\)3\b"), "Fe(NO_{3})_{3}"),
    (re.compile(r"\bFe2O3\b"), "Fe_{2}O_{3}"),
    (re.compile(r"\bFe3O4\b"), "Fe_{3}O_{4}"),
    (re.compile(r"\bAl2O3\b"), "Al_{2}O_{3}"),
    (re.compile(r"\bP2O5\b"), "P_{2}O_{5}"),
    (re.compile(r"\bSiO2\b"), "SiO_{2}"),
    (re.compile(r"\bMnO2\b"), "MnO_{2}"),
    (re.compile(r"\bCr2O3\b"), "Cr_{2}O_{3}"),
    (re.compile(r"\bNa2O\b"), "Na_{2}O"),
    (re.compile(r"\bK2O\b"), "K_{2}O"),
    (re.compile(r"\bCaCl2\b"), "CaCl_{2}"),
    (re.compile(r"\bMgCl2\b"), "MgCl_{2}"),
    (re.compile(r"\bBaCl2\b"), "BaCl_{2}"),
    (re.compile(r"\bFeCl2\b"), "FeCl_{2}"),
    (re.compile(r"\bFeCl3\b"), "FeCl_{3}"),
    (re.compile(r"\bAlCl3\b"), "AlCl_{3}"),
    (re.compile(r"\bCuCl2\b"), "CuCl_{2}"),
    (re.compile(r"\bZnCl2\b"), "ZnCl_{2}"),
    (re.compile(r"\bK2Cr2O7\b"), "K_{2}Cr_{2}O_{7}"),
    (re.compile(r"\bKMnO4\b"), "KMnO_{4}"),
    (re.compile(r"\bKClO3\b"), "KClO_{3}"),
    (re.compile(r"\bNa2S\b"), "Na_{2}S"),
    (re.compile(r"\bO3\b"), "O_{3}"),
    (re.compile(r"\bO2\b"), "O_{2}"),
    (re.compile(r"\bH2\b"), "H_{2}"),
    (re.compile(r"\bN2\b"), "N_{2}"),
    (re.compile(r"\bCl2\b"), "Cl_{2}"),
    (re.compile(r"\bBr2\b"), "Br_{2}"),
    (re.compile(r"\bI2\b"), "I_{2}"),
    (re.compile(r"\bF2\b"), "F_{2}"),
    # 6. Ion kim loại / phi kim & đơn vị diện tích/thể tích
    (re.compile(r"\b(Ca|Mg|Ba|Fe|Cu|Zn|Pb|Mn)2\+"), r"\1^{2+}"),
    (re.compile(r"\b(Fe|Al|Cr)3\+"), r"\1^{3+}"),
    (re.compile(r"\b(Na|K|Li|Ag|H)\+"), r"\1^{+}"),
    (re.compile(r"\b(OH|Cl|Br|I|F)-"), r"\1^{-}"),
    (re.compile(r"\b(mm|cm|dm|km|m)([23])\b"), r"\1^{\2}"),
]

_RE_EXISTING_SCRIPT = re.compile(r"([_^]\{[^{}]+\})")
_RE_SCRIPT_TOKEN = re.compile(r"(_\{([^{}]+)\}|\^\{([^{}]+)\})")


def _normalize_formulas_to_markup(text: str) -> str:
    """Chuyển đổi ký hiệu Unicode/plain/OMML thành markup chuẩn _{...} và ^{...} an toàn (không lồng nhau)."""
    if not text:
        return ""
    s = str(text)

    # Đưa các ký tự subscript/superscript Unicode về markup thống nhất để render bằng run thật trong Word
    s = _RE_UNICODE_SUB.sub(lambda m: f"_{{{m.group(0).translate(_UNICODE_SUB_MAP)}}}", s)
    s = _RE_UNICODE_SUP.sub(lambda m: f"^{{{m.group(0).translate(_UNICODE_SUP_MAP)}}}", s)

    for pat, repl in _MATH_SYMBOL_RULES:
        s = pat.sub(repl, s)

    # Bảo vệ các cặp _{...} / ^{...} đã chuẩn để không bị áp quy tắc chồng chéo
    protected: List[str] = []

    def _stash(m):
        protected.append(m.group(1))
        return f"\x00SCR{len(protected) - 1}\x00"

    s = _RE_EXISTING_SCRIPT.sub(_stash, s)
    for pat, repl in _CHEM_BIO_AUTO_RULES:
        s = pat.sub(repl, s)
        s = _RE_EXISTING_SCRIPT.sub(_stash, s)

    for idx, tok in enumerate(protected):
        s = s.replace(f"\x00SCR{idx}\x00", tok)
    return s


def _add_formatted_runs(
    paragraph,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    font_size_pt: float = 12.0,
    font_name: str = "Times New Roman",
    color_rgb=None,
):
    """Thêm các run văn bản có hỗ trợ subscript (_{...}) và superscript (^{...}) chuẩn Word."""
    markup = _normalize_formulas_to_markup(text)
    if not markup:
        return

    def _style_run(r, sub=False, sup=False):
        r.font.name = font_name
        r.font.size = Pt(font_size_pt)
        if bold:
            r.bold = True
        if italic:
            r.italic = True
        if color_rgb is not None:
            r.font.color.rgb = color_rgb
        if sub:
            r.font.subscript = True
        if sup:
            r.font.superscript = True

    pos = 0
    for m in _RE_SCRIPT_TOKEN.finditer(markup):
        if m.start() > pos:
            r = paragraph.add_run(markup[pos : m.start()])
            _style_run(r)
        if m.group(2) is not None:
            r = paragraph.add_run(m.group(2))
            _style_run(r, sub=True)
        elif m.group(3) is not None:
            r = paragraph.add_run(m.group(3))
            _style_run(r, sup=True)
        pos = m.end()

    if pos < len(markup):
        r = paragraph.add_run(markup[pos:])
        _style_run(r)


# ================== HÌNH ẢNH & BẢNG BIỂU CHUẨN WORD ==================

def _get_image_pixel_size(raw_bytes: bytes) -> Optional[Tuple[int, int]]:
    """Đọc kích thước pixel (width, height) từ header PNG/JPEG/GIF/WEBP (thuần Python)."""
    if not raw_bytes or len(raw_bytes) < 24:
        return None
    try:
        # PNG
        if raw_bytes[:8] == b"\x89PNG\r\n\x1a\n" and raw_bytes[12:16] == b"IHDR":
            w, h = struct.unpack(">II", raw_bytes[16:24])
            if w > 0 and h > 0:
                return w, h
        # GIF
        if raw_bytes[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", raw_bytes[6:10])
            if w > 0 and h > 0:
                return w, h
        # WEBP
        if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
            chunk = raw_bytes[12:16]
            if chunk == b"VP8X" and len(raw_bytes) >= 30:
                w = 1 + int.from_bytes(raw_bytes[24:27], "little")
                h = 1 + int.from_bytes(raw_bytes[27:30], "little")
                return w, h
            if chunk == b"VP8 " and len(raw_bytes) >= 30:
                w, h = struct.unpack("<HH", raw_bytes[26:30])
                return w & 0x3FFF, h & 0x3FFF
        # JPEG
        if raw_bytes[:2] == b"\xff\xd8":
            idx = 2
            n = len(raw_bytes)
            while idx < n - 8:
                if raw_bytes[idx] != 0xFF:
                    idx += 1
                    continue
                while idx < n and raw_bytes[idx] == 0xFF:
                    idx += 1
                if idx >= n:
                    break
                marker = raw_bytes[idx]
                idx += 1
                if marker in (0xD8, 0xD9, 0x01) or (0xD0 <= marker <= 0xD7):
                    continue
                if idx + 2 > n:
                    break
                seg_len = struct.unpack(">H", raw_bytes[idx : idx + 2])[0]
                if seg_len < 2 or idx + seg_len > n:
                    break
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    if idx + 7 <= n:
                        h, w = struct.unpack(">HH", raw_bytes[idx + 3 : idx + 7])
                        if w > 0 and h > 0:
                            return w, h
                    break
                idx += seg_len
    except Exception:
        pass
    return None


def _compute_picture_width_inches(
    raw_bytes: bytes,
    orig_width_inches: Optional[float] = None,
    max_width_inches: float = 4.8,
) -> float:
    """Tính chiều rộng hợp lý cho ảnh: ưu tiên giữ đúng kích thước gốc trong Word, không phóng to mờ ảnh nhỏ."""
    pix = _get_image_pixel_size(raw_bytes)
    if orig_width_inches and orig_width_inches > 0.25:
        w_in = min(float(orig_width_inches), max_width_inches)
        if pix:
            pw, ph = pix
            # Tránh phóng to quá mức các ảnh biểu tượng nhỏ
            natural_in = pw / 96.0
            if natural_in < 2.2 and w_in > natural_in * 1.45:
                w_in = min(w_in, max(0.5, natural_in * 1.25))
            # Nếu ảnh quá cao (dọc), thu gọn để vừa trang giấy
            if pw > 0 and ph > 0:
                h_in = w_in * (ph / pw)
                if h_in > 4.6:
                    w_in = max(1.2, 4.6 * (pw / ph))
        return max(0.45, min(w_in, max_width_inches))

    if pix:
        pw, ph = pix
        natural_in = pw / 96.0
        w_in = min(natural_in, max_width_inches)
        if w_in < 1.2 and pw >= 160:
            w_in = min(2.4, natural_in * 1.15)
        if pw > 0 and ph > 0:
            h_in = w_in * (ph / pw)
            if h_in > 4.5:
                w_in = max(1.2, 4.5 * (pw / ph))
        return max(0.45, min(w_in, max_width_inches))

    return 4.0


def _load_image_bytes(img_url: str) -> Optional[bytes]:
    if not img_url or not isinstance(img_url, str):
        return None
    if img_url.startswith("data:image/"):
        try:
            _, b64_part = img_url.split(",", 1)
            return base64.b64decode(b64_part)
        except Exception:
            return None

    rel = img_url.lstrip("/")
    if rel.startswith("sinhhoc12/"):
        rel = rel[len("sinhhoc12/") :]
    fpath = ""
    if rel.startswith("uploads/") and EXTRA_UPLOADS_DIR:
        candidate = os.path.join(EXTRA_UPLOADS_DIR, rel[len("uploads/") :])
        if os.path.isfile(candidate):
            fpath = candidate
    if not fpath:
        fpath = os.path.join(STATIC_DIR, rel)
    if os.path.isfile(fpath) and not fpath.lower().endswith(".svg"):
        try:
            with open(fpath, "rb") as f:
                return f.read()
        except Exception:
            return None
    return None


def _add_single_image_to_docx(doc, img_url: str, width_inches: Optional[float] = None):
    raw_img = _load_image_bytes(img_url)
    if not raw_img:
        return
    try:
        w_in = _compute_picture_width_inches(raw_img, orig_width_inches=width_inches)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(4)
        p.add_run().add_picture(io.BytesIO(raw_img), width=Inches(w_in))
    except Exception:
        pass


def _set_table_borders(table, border_val: str = "none", sz: str = "4", color: str = "000000"):
    tbl_pr = table._tbl.tblPr
    existing = tbl_pr.find(qn("w:tblBorders"))
    if existing is not None:
        tbl_pr.remove(existing)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), border_val)
        if border_val != "none":
            el.set(qn("w:sz"), sz)
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), color)
        borders.append(el)
    tbl_pr.append(borders)


def _set_cell_box_border(cell, sz: str = "8", color: str = "000000"):
    tc_pr = cell._tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:tcBorders"))
    if existing is not None:
        tc_pr.remove(existing)
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), sz)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tc_pr.append(borders)


def _set_table_layout_fixed(table):
    tbl_pr = table._tbl.tblPr
    existing = tbl_pr.find(qn("w:tblLayout"))
    if existing is not None:
        tbl_pr.remove(existing)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)


def _set_table_left_indent(table, indent_dxa: int = 284):
    """Đặt thụt lề trái chuẩn cho bảng (284 dxa ≈ 0,5 cm) để mọi đáp án A/B/C/D & a/b/c/d thẳng hàng đồng bộ."""
    tbl_pr = table._tbl.tblPr
    existing = tbl_pr.find(qn("w:tblInd"))
    if existing is not None:
        tbl_pr.remove(existing)
    ind = OxmlElement("w:tblInd")
    ind.set(qn("w:w"), str(int(indent_dxa)))
    ind.set(qn("w:type"), "dxa")
    tbl_pr.append(ind)


def _set_table_cell_margins(table, top: int = 30, bottom: int = 30, left: int = 40, right: int = 40):
    tbl_pr = table._tbl.tblPr
    existing = tbl_pr.find(qn("w:tblCellMar"))
    if existing is not None:
        tbl_pr.remove(existing)
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tbl_pr.append(mar)


def _set_row_cant_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def _add_single_table_to_docx(doc, rows: List[List[str]], spans: Optional[List[List[Dict]]] = None):
    if not rows:
        return
    ncols = max((len(r) for r in rows), default=0)
    if ncols <= 0:
        return
    tb = doc.add_table(rows=len(rows), cols=ncols)
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tb, border_val="single", sz="4", color="404040")
    _set_table_cell_margins(tb, top=45, bottom=45, left=80, right=80)

    # Điền nội dung trước khi merge ô
    for ri, row in enumerate(rows):
        _set_row_cant_split(tb.rows[ri])
        for ci in range(ncols):
            val = row[ci] if ci < len(row) else ""
            cell = tb.rows[ri].cells[ci]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if ri == 0 else WD_ALIGN_PARAGRAPH.LEFT
            _add_formatted_runs(p, val, bold=(ri == 0), font_size_pt=11.0)

    # Khôi phục gộp ô ngang (colspan) và dọc (vMerge) nếu có
    if spans and len(spans) == len(rows):
        try:
            for ri, sp_row in enumerate(spans):
                if not isinstance(sp_row, list):
                    continue
                ci = 0
                while ci < min(len(sp_row), ncols):
                    meta_sp = sp_row[ci] if isinstance(sp_row[ci], dict) else {}
                    cspan = max(1, int(meta_sp.get("colspan") or 1))
                    if cspan > 1 and ci + cspan - 1 < ncols:
                        tb.cell(ri, ci).merge(tb.cell(ri, ci + cspan - 1))
                    ci += cspan

            for ci in range(ncols):
                ri = 0
                while ri < len(spans):
                    sp_row = spans[ri] if isinstance(spans[ri], list) else []
                    meta_sp = sp_row[ci] if (ci < len(sp_row) and isinstance(sp_row[ci], dict)) else {}
                    if meta_sp.get("vmerge") == "restart":
                        end_ri = ri
                        while end_ri + 1 < len(spans):
                            nxt_row = spans[end_ri + 1] if isinstance(spans[end_ri + 1], list) else []
                            nxt_meta = nxt_row[ci] if (ci < len(nxt_row) and isinstance(nxt_row[ci], dict)) else {}
                            if nxt_meta.get("vmerge") == "continue":
                                end_ri += 1
                            else:
                                break
                        if end_ri > ri:
                            tb.cell(ri, ci).merge(tb.cell(end_ri, ci))
                        ri = end_ri + 1
                    else:
                        ri += 1
        except Exception:
            pass

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(3)


def _render_question_stem_to_docx(
    doc,
    q_num: int,
    text: str,
    stem_blocks: Optional[List[Dict]],
    images: List[str],
    image_widths: List[Optional[float]],
    tables: List[List[List[str]]],
):
    """Render đề dẫn câu hỏi đúng thứ tự xen kẽ văn bản – hình ảnh – bảng biểu như file gốc."""
    blocks = [b for b in (stem_blocks or []) if isinstance(b, dict)]
    if blocks:
        started_q = False
        for blk in blocks:
            btype = blk.get("type")
            if btype == "text":
                btxt = (blk.get("text") or "").strip()
                if not btxt:
                    continue
                pq = doc.add_paragraph()
                pq.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                pq.paragraph_format.space_before = Pt(4 if not started_q else 2)
                pq.paragraph_format.space_after = Pt(2)
                if not started_q:
                    rq = pq.add_run(f"Câu {q_num}. ")
                    rq.bold = True
                    rq.font.name = "Times New Roman"
                    rq.font.size = Pt(12)
                    started_q = True
                _add_formatted_runs(pq, btxt, font_size_pt=12.0)
            elif btype == "image":
                if not started_q:
                    pq = doc.add_paragraph()
                    pq.paragraph_format.space_before = Pt(4)
                    pq.paragraph_format.space_after = Pt(2)
                    rq = pq.add_run(f"Câu {q_num}.")
                    rq.bold = True
                    rq.font.name = "Times New Roman"
                    rq.font.size = Pt(12)
                    started_q = True
                _add_single_image_to_docx(doc, blk.get("src") or "", blk.get("width_inches"))
            elif btype == "table":
                if not started_q:
                    pq = doc.add_paragraph()
                    pq.paragraph_format.space_before = Pt(4)
                    pq.paragraph_format.space_after = Pt(2)
                    rq = pq.add_run(f"Câu {q_num}.")
                    rq.bold = True
                    rq.font.name = "Times New Roman"
                    rq.font.size = Pt(12)
                    started_q = True
                _add_single_table_to_docx(doc, blk.get("rows") or [], blk.get("spans"))
        if not started_q:
            pq = doc.add_paragraph()
            pq.paragraph_format.space_before = Pt(4)
            pq.paragraph_format.space_after = Pt(2)
            rq = pq.add_run(f"Câu {q_num}. ")
            rq.bold = True
            rq.font.name = "Times New Roman"
            rq.font.size = Pt(12)
            _add_formatted_runs(pq, text or "", font_size_pt=12.0)
        return

    # Fallback khi câu hỏi từ Ngân hàng Ma trận (không có stem_blocks)
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()] or [""]
    for idx_l, ln in enumerate(lines):
        pq = doc.add_paragraph()
        pq.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pq.paragraph_format.space_before = Pt(4 if idx_l == 0 else 2)
        pq.paragraph_format.space_after = Pt(2)
        if idx_l == 0:
            rq = pq.add_run(f"Câu {q_num}. ")
            rq.bold = True
            rq.font.name = "Times New Roman"
            rq.font.size = Pt(12)
        _add_formatted_runs(pq, ln, font_size_pt=12.0)

    for idx_i, img_url in enumerate(images or []):
        w_in = image_widths[idx_i] if idx_i < len(image_widths or []) else None
        _add_single_image_to_docx(doc, img_url, w_in)
    for rows in tables or []:
        _add_single_table_to_docx(doc, rows)


def _strip_leading_option_label(text: str) -> str:
    return re.sub(r"^\s*#?[A-Da-d]\s*[\.\)]\s*", "", (text or "").strip())


def _add_mcq_options_to_docx(doc, opts: List[str]):
    """
    Trình bày đáp án A. B. C. D. bằng bảng ẩn viền kích thước cố định,
    thụt lề trái đồng bộ 0,5 cm (284 dxa) cho mọi bố cục (4 cột / 2 cột / 1 cột)
    và in đậm 100% nhãn A., B., C., D.
    Chiều rộng vùng nội dung A4 (lề trái 1,8 cm + phải 1,5 cm) = 17,7 cm -> bảng 17,2 cm sau thụt lề 0,5 cm.
    """
    clean_opts = [_strip_leading_option_label(o) for o in (opts or [])]
    if not clean_opts:
        return
    max_len = max((len(o) for o in clean_opts), default=0)
    has_nl = any("\n" in o for o in clean_opts)

    if len(clean_opts) == 4 and not has_nl and max_len <= 19:
        # 1 hàng x 8 cột (4 phương án cùng 1 dòng)
        tbl = doc.add_table(rows=1, cols=8)
        widths = [0.65, 3.65, 0.65, 3.65, 0.65, 3.65, 0.65, 3.65]
        _set_table_borders(tbl, "none")
        _set_table_layout_fixed(tbl)
        _set_table_left_indent(tbl, 284)
        _set_table_cell_margins(tbl, top=20, bottom=24, left=15, right=30)
        _set_row_cant_split(tbl.rows[0])
        for ci, w_cm in enumerate(widths):
            tbl.columns[ci].width = Cm(w_cm)
            tbl.rows[0].cells[ci].width = Cm(w_cm)
        for oi, otxt in enumerate(clean_opts):
            c_lbl = tbl.rows[0].cells[oi * 2]
            c_txt = tbl.rows[0].cells[oi * 2 + 1]
            c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            c_txt.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            pl = c_lbl.paragraphs[0]
            pl.paragraph_format.space_before = Pt(0)
            pl.paragraph_format.space_after = Pt(1)
            rl = pl.add_run(f"{'ABCD'[oi]}.")
            rl.bold = True
            rl.font.name = "Times New Roman"
            rl.font.size = Pt(12)
            pt = c_txt.paragraphs[0]
            pt.paragraph_format.space_before = Pt(0)
            pt.paragraph_format.space_after = Pt(1)
            _add_formatted_runs(pt, otxt, font_size_pt=12.0)
        return

    if len(clean_opts) == 4 and not has_nl and max_len <= 44:
        # 2 hàng x 4 cột (A, B hàng 1; C, D hàng 2)
        tbl = doc.add_table(rows=2, cols=4)
        widths = [0.68, 7.92, 0.68, 7.92]
        _set_table_borders(tbl, "none")
        _set_table_layout_fixed(tbl)
        _set_table_left_indent(tbl, 284)
        _set_table_cell_margins(tbl, top=20, bottom=24, left=15, right=35)
        for r_idx in range(2):
            _set_row_cant_split(tbl.rows[r_idx])
            for ci, w_cm in enumerate(widths):
                tbl.rows[r_idx].cells[ci].width = Cm(w_cm)
        for ci, w_cm in enumerate(widths):
            tbl.columns[ci].width = Cm(w_cm)
        for oi, otxt in enumerate(clean_opts):
            r_idx = oi // 2
            c_base = (oi % 2) * 2
            c_lbl = tbl.rows[r_idx].cells[c_base]
            c_txt = tbl.rows[r_idx].cells[c_base + 1]
            c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            c_txt.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            pl = c_lbl.paragraphs[0]
            pl.paragraph_format.space_before = Pt(0)
            pl.paragraph_format.space_after = Pt(1)
            rl = pl.add_run(f"{'ABCD'[oi]}.")
            rl.bold = True
            rl.font.name = "Times New Roman"
            rl.font.size = Pt(12)
            pt = c_txt.paragraphs[0]
            pt.paragraph_format.space_before = Pt(0)
            pt.paragraph_format.space_after = Pt(1)
            _add_formatted_runs(pt, otxt, font_size_pt=12.0)
        return

    # 4 hàng x 2 cột (1 phương án / dòng, thụt lề 0,5 cm đồng bộ, căn đều 2 bên)
    tbl = doc.add_table(rows=len(clean_opts), cols=2)
    widths = [0.72, 16.48]
    _set_table_borders(tbl, "none")
    _set_table_layout_fixed(tbl)
    _set_table_left_indent(tbl, 284)
    _set_table_cell_margins(tbl, top=18, bottom=22, left=15, right=20)
    for ci, w_cm in enumerate(widths):
        tbl.columns[ci].width = Cm(w_cm)
    for oi, otxt in enumerate(clean_opts):
        row = tbl.rows[oi]
        _set_row_cant_split(row)
        c_lbl, c_txt = row.cells[0], row.cells[1]
        c_lbl.width = Cm(widths[0])
        c_txt.width = Cm(widths[1])
        c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        c_txt.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        pl = c_lbl.paragraphs[0]
        pl.paragraph_format.space_before = Pt(0)
        pl.paragraph_format.space_after = Pt(1)
        rl = pl.add_run(f"{'ABCD'[oi] if oi < 4 else str(oi + 1)}.")
        rl.bold = True
        rl.font.name = "Times New Roman"
        rl.font.size = Pt(12)
        pt = c_txt.paragraphs[0]
        pt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pt.paragraph_format.space_before = Pt(0)
        pt.paragraph_format.space_after = Pt(1)
        _add_formatted_runs(pt, otxt, font_size_pt=12.0)


def _add_tf_statements_to_docx(doc, statements: List[Dict]):
    """Trình bày 4 ý Đúng/Sai a) b) c) d) in đậm & thụt lề trái đồng bộ 0,5 cm (284 dxa) bằng bảng ẩn viền."""
    if not statements:
        return
    tbl = doc.add_table(rows=len(statements), cols=2)
    widths = [0.72, 16.48]
    _set_table_borders(tbl, "none")
    _set_table_layout_fixed(tbl)
    _set_table_left_indent(tbl, 284)
    _set_table_cell_margins(tbl, top=18, bottom=22, left=15, right=20)
    for ci, w_cm in enumerate(widths):
        tbl.columns[ci].width = Cm(w_cm)

    for idx, st in enumerate(statements):
        row = tbl.rows[idx]
        _set_row_cant_split(row)
        c_lbl, c_txt = row.cells[0], row.cells[1]
        c_lbl.width = Cm(widths[0])
        c_txt.width = Cm(widths[1])
        c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        c_txt.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        pl = c_lbl.paragraphs[0]
        pl.paragraph_format.space_before = Pt(0)
        pl.paragraph_format.space_after = Pt(1)
        key_str = (st.get("key") or ("abcd"[idx] if idx < 4 else str(idx + 1))).strip()
        rl = pl.add_run(f"{key_str})")
        rl.bold = True
        rl.font.name = "Times New Roman"
        rl.font.size = Pt(12)
        pt = c_txt.paragraphs[0]
        pt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pt.paragraph_format.space_before = Pt(0)
        pt.paragraph_format.space_after = Pt(1)
        st_text = re.sub(r"^\s*#?[a-dA-D]\s*[\)\.]\s*", "", (st.get("text") or "").strip())
        _add_formatted_runs(pt, st_text, font_size_pt=12.0)


def _append_word_field(paragraph, field_name: str, *, italic: bool = False, bold: bool = False, font_size_pt: float = 11.0):
    """Chèn trường động Word (PAGE / NUMPAGES) tự cập nhật số trang khi mở bằng Microsoft Word."""
    r_begin = paragraph.add_run()
    r_begin.font.name = "Times New Roman"
    r_begin.font.size = Pt(font_size_pt)
    r_begin.italic = italic
    r_begin.bold = bold
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    r_begin._r.append(fld_begin)

    r_instr = paragraph.add_run()
    r_instr.font.name = "Times New Roman"
    r_instr.font.size = Pt(font_size_pt)
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {field_name} "
    r_instr._r.append(instr)

    r_sep = paragraph.add_run()
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    r_sep._r.append(fld_sep)

    r_val = paragraph.add_run("1")
    r_val.font.name = "Times New Roman"
    r_val.font.size = Pt(font_size_pt)
    r_val.italic = italic
    r_val.bold = bold

    r_end = paragraph.add_run()
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r_end._r.append(fld_end)


def _add_page_number_footer(section, exam_code: str):
    """Thêm chân trang chuẩn đề thi: Trang X/Y - Mã đề XXXX."""
    footer = section.footer
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    r1 = p.add_run("Trang ")
    r1.font.name = "Times New Roman"
    r1.font.size = Pt(10.5)
    _append_word_field(p, "PAGE", font_size_pt=10.5)
    r2 = p.add_run("/")
    r2.font.name = "Times New Roman"
    r2.font.size = Pt(10.5)
    _append_word_field(p, "NUMPAGES", font_size_pt=10.5)
    if exam_code:
        r3 = p.add_run(f" - Mã đề {exam_code}")
        r3.font.name = "Times New Roman"
        r3.font.size = Pt(10.5)
        r3.bold = True


def build_exams_docx(exams: List[Dict], meta: Dict, actual_counts: Dict) -> bytes:
    """
    Tạo file Word (.docx) theo định dạng chuẩn đề thi (mẫu Mã đề 3210):
      - Tiêu đề căn giữa; tự động ẨN dòng Trường và/hoặc Môn nếu người dùng để trống
      - Thanh thông tin 3 cột: Họ và tên | Số báo danh | [Mã đề XXXX] (đóng khung)
      - Đáp án A./B./C./D. và ý a)/b)/c)/d) in đậm, căn thụt lề đồng bộ 0,5 cm
      - Công thức Hoá/Toán/Sinh hiển thị bằng subscript/superscript thật của Word
      - Hình ảnh giữ đúng ảnh gốc từ Word, bảng biểu hỗ trợ gộp ô
    """
    if docx is None:
        raise RuntimeError(
            "Thiếu thư viện python-docx trên máy chủ. Hãy cài đặt python-docx để xuất đề Word."
        )
    doc = docx.Document()

    # Khổ giấy A4 chuẩn đề thi (vùng nội dung 17,7 cm)
    for sec in doc.sections:
        sec.page_width = Cm(21.0)
        sec.page_height = Cm(29.7)
        sec.top_margin = Cm(1.5)
        sec.bottom_margin = Cm(1.5)
        sec.left_margin = Cm(1.8)
        sec.right_margin = Cm(1.5)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Times New Roman"
    normal_style.font.size = Pt(12)
    normal_style.paragraph_format.line_spacing = 1.15

    exam_period = (meta.get("exam_period") or meta.get("title") or "KIỂM TRA ĐỊNH KÌ").strip()
    school_name = (meta.get("school_name") or "").strip()
    school_year = (meta.get("school_year") or "2026 - 2027").strip()
    subject = (meta.get("subject") or "").strip()
    duration_min = int(meta.get("duration_minutes") or 45)
    is_single_file = len(exams) == 1

    if is_single_file:
        _add_page_number_footer(doc.sections[0], exams[0].get("code", ""))

    for e_idx, ex in enumerate(exams):
        if e_idx > 0:
            doc.add_page_break()

        total_q_in_ex = len(ex["mcq"]) + len(ex["true_false"]) + len(ex["short_answer"])

        # 1. TIÊU ĐỀ CĂN GIỮA CHUẨN MẪU (ẩn Trường / Môn nếu để trống)
        if school_name:
            p_sch = doc.add_paragraph()
            p_sch.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_sch.paragraph_format.space_before = Pt(0)
            p_sch.paragraph_format.space_after = Pt(1)
            r_sch = p_sch.add_run(school_name.upper())
            r_sch.bold = True
            r_sch.font.name = "Times New Roman"
            r_sch.font.size = Pt(12)

        p_per = doc.add_paragraph()
        p_per.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_per.paragraph_format.space_before = Pt(0)
        p_per.paragraph_format.space_after = Pt(1)
        period_line = f"{exam_period.upper()} - NĂM HỌC {school_year}" if school_year else exam_period.upper()
        r_per = p_per.add_run(period_line)
        r_per.bold = True
        r_per.font.name = "Times New Roman"
        r_per.font.size = Pt(12.5)

        if subject:
            p_sub = doc.add_paragraph()
            p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_sub.paragraph_format.space_before = Pt(0)
            p_sub.paragraph_format.space_after = Pt(1)
            sub_up = subject.upper()
            sub_line = sub_up if sub_up.startswith("MÔN ") else f"MÔN {sub_up}"
            r_sub = p_sub.add_run(sub_line)
            r_sub.bold = True
            r_sub.font.name = "Times New Roman"
            r_sub.font.size = Pt(12)

        p_dur = doc.add_paragraph()
        p_dur.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_dur.paragraph_format.space_before = Pt(0)
        p_dur.paragraph_format.space_after = Pt(1)
        r_dur1 = p_dur.add_run(f"Thời gian làm bài: {duration_min} phút")
        r_dur1.italic = True
        r_dur1.bold = True
        r_dur1.font.name = "Times New Roman"
        r_dur1.font.size = Pt(11)
        r_dur2 = p_dur.add_run(" (không kể thời gian phát đề)")
        r_dur2.italic = True
        r_dur2.font.name = "Times New Roman"
        r_dur2.font.size = Pt(11)

        p_pg = doc.add_paragraph()
        p_pg.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_pg.paragraph_format.space_before = Pt(0)
        p_pg.paragraph_format.space_after = Pt(6)
        if is_single_file:
            rp1 = p_pg.add_run("(Đề có ")
            rp1.italic = True
            rp1.font.name = "Times New Roman"
            rp1.font.size = Pt(11)
            _append_word_field(p_pg, "NUMPAGES", italic=True, font_size_pt=11.0)
            rp2 = p_pg.add_run(" trang)")
            rp2.italic = True
            rp2.font.name = "Times New Roman"
            rp2.font.size = Pt(11)
        else:
            rp = p_pg.add_run(f"(Đề kiểm tra gồm {total_q_in_ex} câu)")
            rp.italic = True
            rp.font.name = "Times New Roman"
            rp.font.size = Pt(11)

        # 2. THANH THÔNG TIN THÍ SINH 3 CỘT: Họ và tên | Số báo danh | [Mã đề XXXX]
        info_tbl = doc.add_table(rows=1, cols=3)
        info_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(info_tbl, "none")
        _set_table_layout_fixed(info_tbl)
        _set_table_cell_margins(info_tbl, top=40, bottom=40, left=50, right=50)
        _set_row_cant_split(info_tbl.rows[0])
        info_widths = [9.2, 5.1, 3.4]
        for ci, w_cm in enumerate(info_widths):
            info_tbl.columns[ci].width = Cm(w_cm)
            info_tbl.rows[0].cells[ci].width = Cm(w_cm)
            info_tbl.rows[0].cells[ci].vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        c_name, c_sbd, c_code = info_tbl.rows[0].cells
        pn = c_name.paragraphs[0]
        pn.paragraph_format.space_before = Pt(0)
        pn.paragraph_format.space_after = Pt(0)
        rn1 = pn.add_run("Họ và tên: ")
        rn1.bold = True
        rn1.font.name = "Times New Roman"
        rn1.font.size = Pt(11.5)
        rn2 = pn.add_run("..................................................")
        rn2.font.name = "Times New Roman"
        rn2.font.size = Pt(11.5)

        psbd = c_sbd.paragraphs[0]
        psbd.paragraph_format.space_before = Pt(0)
        psbd.paragraph_format.space_after = Pt(0)
        rs1 = psbd.add_run("Số báo danh: ")
        rs1.bold = True
        rs1.font.name = "Times New Roman"
        rs1.font.size = Pt(11.5)
        rs2 = psbd.add_run(".................")
        rs2.font.name = "Times New Roman"
        rs2.font.size = Pt(11.5)

        _set_cell_box_border(c_code, sz="8", color="000000")
        pcode = c_code.paragraphs[0]
        pcode.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pcode.paragraph_format.space_before = Pt(0)
        pcode.paragraph_format.space_after = Pt(0)
        rc = pcode.add_run(f"Mã đề {ex['code']}")
        rc.bold = True
        rc.font.name = "Times New Roman"
        rc.font.size = Pt(12)

        sp_hdr = doc.add_paragraph()
        sp_hdr.paragraph_format.space_before = Pt(0)
        sp_hdr.paragraph_format.space_after = Pt(4)

        # 3. PHẦN I: Trắc nghiệm nhiều phương án lựa chọn
        is_single_mcq_only = bool(ex["mcq"]) and not ex["true_false"] and not ex["short_answer"]
        if ex["mcq"]:
            p_sec1 = doc.add_paragraph()
            p_sec1.paragraph_format.space_before = Pt(2)
            p_sec1.paragraph_format.space_after = Pt(4)
            mcq_sec_title = (
                f"CÂU HỎI TRẮC NGHIỆM KHÁCH QUAN ({len(ex['mcq'])} câu)."
                if is_single_mcq_only
                else "PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn."
            )
            r_s1 = p_sec1.add_run(mcq_sec_title)
            r_s1.bold = True
            r_s1.font.name = "Times New Roman"
            r_s1.font.size = Pt(12)
            if not is_single_mcq_only:
                r_s1_note = p_sec1.add_run(
                    f" Thí sinh trả lời từ câu 1 đến câu {len(ex['mcq'])}. Mỗi câu hỏi thí sinh chỉ chọn một phương án."
                )
                r_s1_note.font.name = "Times New Roman"
                r_s1_note.font.size = Pt(12)

            for i, q in enumerate(ex["mcq"], 1):
                _render_question_stem_to_docx(
                    doc,
                    i,
                    q.get("question", ""),
                    q.get("stem_blocks"),
                    q.get("images") or [],
                    q.get("image_widths") or [],
                    q.get("tables") or [],
                )
                _add_mcq_options_to_docx(doc, q.get("options") or [])

        # 4. PHẦN II: Trắc nghiệm Đúng/Sai
        if ex["true_false"]:
            p_sec2 = doc.add_paragraph()
            p_sec2.paragraph_format.space_before = Pt(8)
            p_sec2.paragraph_format.space_after = Pt(4)
            r_s2 = p_sec2.add_run("PHẦN II. Câu trắc nghiệm đúng sai.")
            r_s2.bold = True
            r_s2.font.name = "Times New Roman"
            r_s2.font.size = Pt(12)
            r_s2_note = p_sec2.add_run(
                f" Thí sinh trả lời từ câu 1 đến câu {len(ex['true_false'])}. Trong mỗi ý a), b), c), d) ở mỗi câu, thí sinh chọn đúng hoặc sai."
            )
            r_s2_note.font.name = "Times New Roman"
            r_s2_note.font.size = Pt(12)

            for i, q in enumerate(ex["true_false"], 1):
                _render_question_stem_to_docx(
                    doc,
                    i,
                    q.get("stem", ""),
                    q.get("stem_blocks"),
                    q.get("images") or [],
                    q.get("image_widths") or [],
                    q.get("tables") or [],
                )
                _add_tf_statements_to_docx(doc, q.get("statements") or [])

        # 5. PHẦN III: Trắc nghiệm trả lời ngắn
        if ex["short_answer"]:
            p_sec3 = doc.add_paragraph()
            p_sec3.paragraph_format.space_before = Pt(8)
            p_sec3.paragraph_format.space_after = Pt(4)
            r_s3 = p_sec3.add_run("PHẦN III. Câu trắc nghiệm trả lời ngắn.")
            r_s3.bold = True
            r_s3.font.name = "Times New Roman"
            r_s3.font.size = Pt(12)
            r_s3_note = p_sec3.add_run(
                f" Thí sinh trả lời từ câu 1 đến câu {len(ex['short_answer'])}."
            )
            r_s3_note.font.name = "Times New Roman"
            r_s3_note.font.size = Pt(12)

            for i, q in enumerate(ex["short_answer"], 1):
                _render_question_stem_to_docx(
                    doc,
                    i,
                    q.get("question", ""),
                    q.get("stem_blocks"),
                    q.get("images") or [],
                    q.get("image_widths") or [],
                    q.get("tables") or [],
                )

        # 6. CHÂN ĐỀ THI
        p_end = doc.add_paragraph()
        p_end.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_end.paragraph_format.space_before = Pt(10)
        p_end.paragraph_format.space_after = Pt(2)
        r_end = p_end.add_run("------ HẾT ------")
        r_end.bold = True
        r_end.font.name = "Times New Roman"
        r_end.font.size = Pt(12)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_single_exam_docx(exam: Dict, meta: Dict, actual_counts: Dict) -> bytes:
    """Tạo file Word (.docx) riêng cho đúng 1 mã đề (có tổng số trang & chân trang chuẩn)."""
    return build_exams_docx([exam], meta, actual_counts)


# ================== PURE-PYTHON XLSX GENERATOR (CHUẨN EXCEL OOXML, KHÔNG CẦN OPENPYXL) ==================

def _col_letter(idx_1based: int) -> str:
    res = ""
    n = idx_1based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        res = chr(65 + rem) + res
    return res


def _build_sheet_xml(rows: List[List[str]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for r_idx, row in enumerate(rows, 1):
        lines.append(f'<row r="{r_idx}">')
        for c_idx, val in enumerate(row, 1):
            col = _col_letter(c_idx)
            sval = "" if val is None else str(val)
            style_attr = ' s="1"' if r_idx == 1 else ""
            lines.append(
                f'<c r="{col}{r_idx}" t="inlineStr"{style_attr}><is><t>{xml_escape(sval)}</t></is></c>'
            )
        lines.append("</row>")
    lines.append("</sheetData></worksheet>")
    return "".join(lines)


def build_answer_keys_xlsx(
    exams: List[Dict],
    meta: Dict,
    actual_counts: Dict,
    original_exam: Optional[Dict] = None,
) -> bytes:
    """Tạo file Excel .xlsx nhiều sheet cho toàn bộ mã đề trộn (kèm cột Mã đề 0000 - Đề gốc nếu có)."""
    all_exams: List[Dict] = []
    col_headers: List[str] = []
    if original_exam is not None:
        all_exams.append(original_exam)
        col_headers.append(f"Mã đề {original_exam['code']} (Đề gốc)")
    for ex in exams:
        all_exams.append(ex)
        col_headers.append(f"Mã đề {ex['code']}")

    shuffled_codes = [ex["code"] for ex in exams]

    # Sheet 1: Trắc nghiệm 4 đáp án
    s1_rows = [["Câu (Phần I - 0,25đ/câu)"] + col_headers]
    max_mcq = max((len(ex["mcq"]) for ex in all_exams), default=0)
    for i in range(max_mcq):
        row = [f"Câu {i + 1}"]
        for ex in all_exams:
            row.append(ex["mcq"][i]["correct_letter"] if i < len(ex["mcq"]) else "")
        s1_rows.append(row)

    # Sheet 2: Trắc nghiệm Đúng/Sai
    s2_rows = [["Câu / Ý (Phần II - 1,0đ/câu)"] + col_headers]
    max_tf = max((len(ex["true_false"]) for ex in all_exams), default=0)
    for i in range(max_tf):
        for k in ("a", "b", "c", "d"):
            row = [f"Câu {i + 1} - Ý {k})"]
            for ex in all_exams:
                if i < len(ex["true_false"]):
                    row.append(ex["true_false"][i]["ans_keys"].get(k, ""))
                else:
                    row.append("")
            s2_rows.append(row)

    # Sheet 3: Trắc nghiệm trả lời ngắn
    s3_rows = [["Câu (Phần III - 0,25đ/câu, tối đa 4 ký tự)"] + col_headers]
    max_sa = max((len(ex["short_answer"]) for ex in all_exams), default=0)
    for i in range(max_sa):
        row = [f"Câu {i + 1}"]
        for ex in all_exams:
            row.append(ex["short_answer"][i]["answer"] if i < len(ex["short_answer"]) else "")
        s3_rows.append(row)

    # Sheet 4: Thông tin đề & Ma trận
    mcq_n = max((len(ex["mcq"]) for ex in all_exams), default=0)
    tf_n = max((len(ex["true_false"]) for ex in all_exams), default=0)
    sa_n = max((len(ex["short_answer"]) for ex in all_exams), default=0)
    total_pts = round(mcq_n * 0.25 + tf_n * 1.0 + sa_n * 0.25, 2)

    s4_rows = [
        ["Thông tin kỳ kiểm tra", "Nội dung chi tiết", "", "Thống kê đề trộn", "Giá trị"],
        ["Trường", (meta.get("school_name") or "").strip(), "", "Số lượng đề trộn", len(exams)],
        [
            "Kỳ kiểm tra",
            meta.get("exam_period") or meta.get("title") or "Kiểm tra định kì",
            "",
            "Mã đề gốc + Mã đề trộn",
            (f"{original_exam['code']} (gốc), " if original_exam else "") + ", ".join(shuffled_codes),
        ],
        ["Năm học", meta.get("school_year") or "2026 - 2027", "", "Tổng số câu", mcq_n + tf_n + sa_n],
        ["Môn", (meta.get("subject") or "").strip(), "", "Thang điểm tổng", f"{total_pts:.2f}"],
        ["Thời gian", f"{int(meta.get('duration_minutes') or 45)} phút", "", "Ngày xuất (giờ VN)", datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")],
        ["", "", "", "", ""],
        ["Mức độ \\ Dạng câu hỏi", "Phần I - 4 đáp án (0,25đ)", "Phần II - Đúng/Sai (1,0đ)", "Phần III - Trả lời ngắn (0,25đ)", "Tổng số câu"],
        [
            "Nhận biết",
            actual_counts["mcq"]["nhan_biet"],
            actual_counts["true_false"]["nhan_biet"],
            actual_counts["short_answer"]["nhan_biet"],
            actual_counts["mcq"]["nhan_biet"] + actual_counts["true_false"]["nhan_biet"] + actual_counts["short_answer"]["nhan_biet"],
        ],
        [
            "Hiểu (Thông hiểu)",
            actual_counts["mcq"]["thong_hieu"],
            actual_counts["true_false"]["thong_hieu"],
            actual_counts["short_answer"]["thong_hieu"],
            actual_counts["mcq"]["thong_hieu"] + actual_counts["true_false"]["thong_hieu"] + actual_counts["short_answer"]["thong_hieu"],
        ],
        [
            "Vận dụng",
            actual_counts["mcq"]["van_dung"],
            actual_counts["true_false"]["van_dung"],
            actual_counts["short_answer"]["van_dung"],
            actual_counts["mcq"]["van_dung"] + actual_counts["true_false"]["van_dung"] + actual_counts["short_answer"]["van_dung"],
        ],
        ["Tổng số câu", mcq_n, tf_n, sa_n, mcq_n + tf_n + sa_n],
        ["Tổng điểm phần", f"{mcq_n * 0.25:.2f}", f"{tf_n * 1.0:.2f}", f"{sa_n * 0.25:.2f}", f"{total_pts:.2f}"],
    ]

    # Sheet 5 (tuỳ chọn): Giải chi tiết cho từng mã đề nếu đề gốc có phần "Giải chi tiết"
    s5_rows = [["Mã đề", "Phần", "Câu", "Đáp án đúng", "Giải chi tiết"]]
    for ex in all_exams:
        for i, q in enumerate(ex["mcq"], 1):
            if q.get("explanation"):
                s5_rows.append([ex["code"], "Phần I (TN)", f"Câu {i}", q.get("correct_letter", ""), q["explanation"]])
        for i, q in enumerate(ex["true_false"], 1):
            if q.get("explanation"):
                ak = " | ".join(f"{k}-{q['ans_keys'].get(k, '')}" for k in ("a", "b", "c", "d"))
                s5_rows.append([ex["code"], "Phần II (Đ/S)", f"Câu {i}", ak, q["explanation"]])
        for i, q in enumerate(ex["short_answer"], 1):
            if q.get("explanation"):
                s5_rows.append([ex["code"], "Phần III (TLN)", f"Câu {i}", q.get("answer", ""), q["explanation"]])

    sheets = []
    if max_mcq > 0:
        sheets.append(("Dap an 4 dap an", s1_rows))
    if max_tf > 0:
        sheets.append(("Dap an Dung Sai", s2_rows))
    if max_sa > 0:
        sheets.append(("Dap an Tra loi ngan", s3_rows))
    sheets.append(("Thong tin va Ma tran", s4_rows))
    if len(s5_rows) > 1:
        sheets.append(("Giai chi tiet", s5_rows))

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for i in range(1, len(sheets) + 1):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    content_types.append("</Types>")

    rels_root = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    wb_sheets_xml = "".join(
        f'<sheet name="{xml_escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        for i, (name, _) in enumerate(sheets, 1)
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{wb_sheets_xml}</sheets></workbook>"
    )

    wb_rels = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for i in range(1, len(sheets) + 1):
        wb_rels.append(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        )
    wb_rels.append(
        f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    wb_rels.append("</Relationships>")

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
        "</fonts>"
        '<fills count="3">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF0F766E"/></patternFill></fill>'
        "</fills>"
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
        "</cellXfs>"
        "</styleSheet>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "".join(content_types))
        zf.writestr("_rels/.rels", rels_root)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", "".join(wb_rels))
        zf.writestr("xl/styles.xml", styles_xml)
        for i, (_, rows) in enumerate(sheets, 1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", _build_sheet_xml(rows))
    return buf.getvalue()


def _safe_code_filename(code: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_\-]", "_", str(code or "0000").strip())
    return clean or "0000"


def build_exam_zip_bundle(
    original_exam: Dict,
    shuffled_exams: List[Dict],
    xlsx_bytes: bytes,
    meta: Dict,
    actual_counts: Dict,
) -> Tuple[bytes, Dict[str, bytes], List[str]]:
    """
    Đóng gói trọn bộ file nén (.zip) gồm:
      - File đề gốc riêng mặc định mã đề 0000: Ma_de_0000.docx
      - Các file đề trộn riêng theo từng mã đề: Ma_de_1001.docx, Ma_de_1002.docx, ...
      - File đáp án Excel tổng hợp: Dap_an.xlsx
    """
    individual_files: Dict[str, bytes] = {}
    file_order: List[str] = []

    if original_exam is not None:
        orig_fname = f"Ma_de_{_safe_code_filename(original_exam.get('code', '0000'))}.docx"
        individual_files[orig_fname] = build_single_exam_docx(original_exam, meta, actual_counts)
        file_order.append(orig_fname)

    for ex in shuffled_exams:
        fname = f"Ma_de_{_safe_code_filename(ex.get('code', ''))}.docx"
        # Tránh trùng tên nếu người dùng cố ý nhập mã 0000
        if fname in individual_files:
            fname = f"Ma_de_{_safe_code_filename(ex.get('code', ''))}_tron.docx"
        individual_files[fname] = build_single_exam_docx(ex, meta, actual_counts)
        file_order.append(fname)

    ans_fname = "Dap_an.xlsx"
    individual_files[ans_fname] = xlsx_bytes
    file_order.append(ans_fname)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in file_order:
            zf.writestr(fname, individual_files[fname])

    return zip_buf.getvalue(), individual_files, file_order


def build_exam_pool_summary(topics: List[Dict]) -> List[Dict]:
    """Trả về cây Chủ đề -> Danh sách Bài học kèm số lượng câu hỏi theo Ma trận 3x3."""
    result = []
    for t in topics:
        rev = t.get("review") or {}
        lessons_meta = []
        lesson_map = {}

        for ls in t.get("lessons") or []:
            lid = ls.get("id") or ""
            if not lid:
                continue
            item = {
                "id": lid,
                "number": ls.get("number") or "",
                "title": ls.get("title") or "",
                "counts": {
                    "mcq": {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0},
                    "true_false": {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0},
                    "short_answer": {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0},
                },
            }
            lessons_meta.append(item)
            lesson_map[lid] = item

        other_item = None
        for kind in ("mcq", "true_false", "short_answer"):
            for q in rev.get(kind, []):
                lid = q.get("lesson_id") or ""
                lv = q.get("cognitive_level", "thong_hieu")
                if lv not in ("nhan_biet", "thong_hieu", "van_dung"):
                    lv = "thong_hieu"
                if lid in lesson_map:
                    lesson_map[lid]["counts"][kind][lv] += 1
                else:
                    if other_item is None:
                        other_item = {
                            "id": f"{t.get('id', 'topic')}-khac",
                            "number": "Khác",
                            "title": "Câu hỏi tổng hợp chủ đề",
                            "counts": {
                                "mcq": {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0},
                                "true_false": {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0},
                                "short_answer": {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0},
                            },
                        }
                        lessons_meta.append(other_item)
                    other_item["counts"][kind][lv] += 1

        result.append(
            {
                "id": t.get("id"),
                "order_index": t.get("order_index", 1),
                "title": t.get("title") or "",
                "lessons": lessons_meta,
            }
        )
    return result


def generate_shuffled_exam_package(
    topics: List[Dict],
    selected_lesson_ids: List[str],
    matrix: Dict[str, Dict[str, int]],
    exam_codes: List[str],
    meta: Dict,
) -> Dict:
    """Sinh trọn bộ file nén (.zip) tách riêng từng mã đề + đề gốc 0000 + đáp án Excel (.xlsx) từ ma trận."""
    rng = random.Random()
    mcqs, tfs, sas, actual_counts = _select_questions_by_matrix(topics, selected_lesson_ids, matrix, rng)

    if not mcqs and not tfs and not sas:
        raise ValueError("Không có câu hỏi nào phù hợp với các bài học và ma trận đã nhập.")

    codes = [c.strip() for c in exam_codes if c.strip()] or ["1001"]
    original_exam = _build_unshuffled_original_exam(mcqs, tfs, sas, exam_code="0000")
    exams = [_shuffle_single_exam(mcqs, tfs, sas, code, rng) for code in codes]

    docx_bytes = build_exams_docx(exams, meta, actual_counts)
    xlsx_bytes = build_answer_keys_xlsx(exams, meta, actual_counts, original_exam=original_exam)
    zip_bytes, individual_files, files_in_zip = build_exam_zip_bundle(
        original_exam, exams, xlsx_bytes, meta, actual_counts
    )

    mcq_n = len(mcqs)
    tf_n = len(tfs)
    sa_n = len(sas)
    max_score = round(mcq_n * 0.25 + tf_n * 1.0 + sa_n * 0.25, 2)

    return {
        "zip_bytes": zip_bytes,
        "docx_bytes": docx_bytes,
        "xlsx_bytes": xlsx_bytes,
        "individual_files": individual_files,
        "summary": {
            "exam_count": len(exams),
            "exam_codes": codes,
            "original_code": "0000",
            "files_in_zip": files_in_zip,
            "mcq_count": mcq_n,
            "true_false_count": tf_n,
            "short_answer_count": sa_n,
            "max_score": max_score,
            "actual_counts": actual_counts,
        },
    }


def generate_shuffled_exam_from_content(
    content: Dict,
    exam_codes: List[str],
    meta: Dict,
) -> Dict:
    """
    Trộn đề trực tiếp từ nội dung đề gốc (file Word .docx).
    Xuất trọn bộ file nén (.zip) gồm: Ma_de_0000.docx (đề gốc) + từng file Ma_de_XXXX.docx riêng + Dap_an.xlsx.
    """
    mcqs = list((content or {}).get("mcq") or [])
    tfs = list((content or {}).get("true_false") or [])
    sas = list((content or {}).get("short_answer") or [])

    if not mcqs and not tfs and not sas:
        raise ValueError("File Word chưa có câu hỏi nào để trộn đề.")

    rng = random.Random()
    codes = [c.strip() for c in exam_codes if c.strip()] or ["1001"]
    original_exam = _build_unshuffled_original_exam(mcqs, tfs, sas, exam_code="0000")
    exams = [_shuffle_single_exam(mcqs, tfs, sas, code, rng) for code in codes]

    actual_counts = {
        "mcq": {"nhan_biet": len(mcqs), "thong_hieu": 0, "van_dung": 0},
        "true_false": {"nhan_biet": len(tfs), "thong_hieu": 0, "van_dung": 0},
        "short_answer": {"nhan_biet": len(sas), "thong_hieu": 0, "van_dung": 0},
    }

    docx_bytes = build_exams_docx(exams, meta, actual_counts)
    xlsx_bytes = build_answer_keys_xlsx(exams, meta, actual_counts, original_exam=original_exam)
    zip_bytes, individual_files, files_in_zip = build_exam_zip_bundle(
        original_exam, exams, xlsx_bytes, meta, actual_counts
    )

    mcq_n = len(mcqs)
    tf_n = len(tfs)
    sa_n = len(sas)
    max_score = round(mcq_n * 0.25 + tf_n * 1.0 + sa_n * 0.25, 2)

    return {
        "zip_bytes": zip_bytes,
        "docx_bytes": docx_bytes,
        "xlsx_bytes": xlsx_bytes,
        "individual_files": individual_files,
        "summary": {
            "exam_count": len(exams),
            "exam_codes": codes,
            "original_code": "0000",
            "files_in_zip": files_in_zip,
            "mcq_count": mcq_n,
            "true_false_count": tf_n,
            "short_answer_count": sa_n,
            "max_score": max_score,
            "actual_counts": actual_counts,
            "school_name": (meta.get("school_name") or "").strip(),
            "exam_period": (meta.get("exam_period") or "").strip(),
            "school_year": (meta.get("school_year") or "").strip(),
            "subject": (meta.get("subject") or "").strip(),
            "duration_minutes": meta.get("duration_minutes", 45),
        },
    }
