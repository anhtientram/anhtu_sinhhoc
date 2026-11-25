"""
Bộ trộn đề trắc nghiệm theo Ma trận 3x3 (3 dạng câu hỏi x 3 mức độ: Nhận biết - Hiểu - Vận dụng)
- Hỗ trợ chọn nhiều bài trong nhiều chủ đề cùng lúc
- Tự nhập số lượng đề trộn & mã đề (VD: 101, 102, 103, 104)
- Trộn thứ tự câu hỏi, trộn phương án A/B/C/D (MCQ) và ý a/b/c/d (Đúng/Sai), tự động ánh xạ lại đáp án chuẩn
- Thang điểm chuẩn Bộ GD&ĐT:
    + Phần I (4 đáp án): 0,25 điểm / câu
    + Phần II (Đúng/Sai): 1 ý = 0,1đ; 2 ý = 0,25đ; 3 ý = 0,5đ; 4 ý = 1,0đ
    + Phần III (Trả lời ngắn): 0,25 điểm / câu (định dạng giá trị số tối đa 4 ký tự gồm số, dấu âm, dấu phẩy)
- Xuất file Đề trộn dạng Word (.docx) kèm đầy đủ hình ảnh & bảng biểu
- Xuất file Đáp án dạng Excel (.xlsx chuẩn OOXML nhiều sheet, mở thẳng bằng Microsoft Excel không lỗi font)
"""
import io
import os
import random
import re
import zipfile
from datetime import datetime
from typing import Dict, List, Tuple
from xml.sax.saxutils import escape as xml_escape

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Inches, Pt, RGBColor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

LEVEL_LABELS = {
    "nhan_biet": "Nhận biết",
    "thong_hieu": "Hiểu",
    "van_dung": "Vận dụng",
}


def format_short_answer_4chars(ans_list: List[str]) -> str:
    """Chuẩn hóa đáp án trả lời ngắn về giá trị số tối đa 4 ký tự (số, dấu âm, dấu phẩy)."""
    if not ans_list:
        return ""
    raw = str(ans_list[0]).strip().replace(".", ",")
    # Giữ số, dấu âm, dấu phẩy (nếu dạng phân số a/b thì tính sang số thập phân 2 chữ số)
    m_frac = re.match(r"^(-?\d+)\s*/\s*(\d+)$", raw)
    if m_frac and int(m_frac.group(2)) != 0:
        val = int(m_frac.group(1)) / int(m_frac.group(2))
        s = f"{val:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        return s[:4]
    cleaned = re.sub(r"[^0-9,\-]", "", raw)
    if cleaned:
        return cleaned[:4]
    return raw[:4]


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
    """
    Lọc câu hỏi từ các bài được chọn theo đúng số lượng trong ma trận 3x3:
    matrix = {
      'mcq': {'nhan_biet': 8, 'thong_hieu': 6, 'van_dung': 4},
      'true_false': {'nhan_biet': 1, 'thong_hieu': 2, 'van_dung': 1},
      'short_answer': {'nhan_biet': 1, 'thong_hieu': 2, 'van_dung': 3}
    }
    """
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
            # Ưu tiên chọn câu đã có đáp án chuẩn trước
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


def _shuffle_single_exam(
    mcqs: List[Dict],
    tfs: List[Dict],
    sas: List[Dict],
    exam_code: str,
    rng: random.Random,
) -> Dict:
    """Trộn thứ tự câu hỏi và trộn phương án/ý cho 1 mã đề cụ thể."""
    shuffled_mcq = []
    mcq_order = list(mcqs)
    rng.shuffle(mcq_order)

    for q in mcq_order:
        opts = list(q.get("options") or [])
        indexed = list(enumerate(opts))
        # Không trộn nếu đáp án có kiểu "Cả A và B" / "Tất cả đều đúng"
        has_ref = any(
            re.search(r"(cả\s*[a-d]|tất\s*cả\s*(?:các|đều))", o, re.IGNORECASE)
            for o in opts
        )
        if not has_ref and len(indexed) >= 2:
            rng.shuffle(indexed)

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
                "images": q.get("images") or [],
                "tables": q.get("tables") or [],
                "options": new_opts,
                "correct_letter": "ABCD"[new_correct] if new_correct is not None and new_correct < 4 else "",
                "level": LEVEL_LABELS.get(q.get("cognitive_level", ""), ""),
            }
        )

    shuffled_tf = []
    tf_order = list(tfs)
    rng.shuffle(tf_order)
    for q in tf_order:
        stmts = list(q.get("statements") or [])
        rng.shuffle(stmts)
        new_stmts = []
        ans_keys = {}
        for idx, st in enumerate(stmts[:4]):
            k = "abcd"[idx]
            ans_val = st.get("answer")
            new_stmts.append({"key": k, "text": st.get("text", ""), "answer": ans_val})
            ans_keys[k] = "Đ" if ans_val is True else ("S" if ans_val is False else "")
        shuffled_tf.append(
            {
                "stem": q.get("stem", ""),
                "images": q.get("images") or [],
                "tables": q.get("tables") or [],
                "statements": new_stmts,
                "ans_keys": ans_keys,
                "level": LEVEL_LABELS.get(q.get("cognitive_level", ""), ""),
            }
        )

    shuffled_sa = []
    sa_order = list(sas)
    rng.shuffle(sa_order)
    for q in sa_order:
        shuffled_sa.append(
            {
                "question": q.get("question", ""),
                "images": q.get("images") or [],
                "tables": q.get("tables") or [],
                "answer": format_short_answer_4chars(q.get("accepted_answers") or []),
                "level": LEVEL_LABELS.get(q.get("cognitive_level", ""), ""),
            }
        )

    return {
        "code": exam_code,
        "mcq": shuffled_mcq,
        "true_false": shuffled_tf,
        "short_answer": shuffled_sa,
    }


def _add_question_media_to_docx(doc, images: List[str], tables: List[List[List[str]]]):
    for img_url in images or []:
        rel = img_url.lstrip("/")
        if rel.startswith("sinhhoc12/"):
            rel = rel[len("sinhhoc12/") :]
        fpath = os.path.join(STATIC_DIR, rel)
        if os.path.isfile(fpath) and not fpath.lower().endswith(".svg"):
            try:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(4)
                p.add_run().add_picture(fpath, width=Inches(4.3))
            except Exception:
                pass

    for rows in tables or []:
        if not rows:
            continue
        ncols = max(len(r) for r in rows)
        if ncols <= 0:
            continue
        tb = doc.add_table(rows=len(rows), cols=ncols)
        tb.style = "Table Grid"
        for ri, row in enumerate(rows):
            for ci in range(ncols):
                val = row[ci] if ci < len(row) else ""
                cell = tb.rows[ri].cells[ci]
                cell.text = val
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.name = "Times New Roman"
                        r.font.size = Pt(11)
                        if ri == 0:
                            r.bold = True


def build_exams_docx(exams: List[Dict], meta: Dict, actual_counts: Dict) -> bytes:
    """Tạo file Word (.docx) chứa toàn bộ các mã đề đã trộn, định dạng chuẩn đề thi THPT."""
    doc = docx.Document()

    # Căn lề chuẩn đề thi
    for sec in doc.sections:
        sec.top_margin = Cm(1.8)
        sec.bottom_margin = Cm(1.8)
        sec.left_margin = Cm(2.0)
        sec.right_margin = Cm(1.8)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Times New Roman"
    normal_style.font.size = Pt(12)

    exam_title = meta.get("title") or "ĐỀ KIỂM TRA MÔN SINH HỌC 12"
    school_name = meta.get("school_name") or "TRƯỜNG THPT"
    duration_min = int(meta.get("duration_minutes") or 50)

    for e_idx, ex in enumerate(exams):
        if e_idx > 0:
            doc.add_page_break()

        # Header bảng 2 cột: Trường & Tiêu đề kỳ thi + Mã đề
        hdr_tbl = doc.add_table(rows=1, cols=2)
        hdr_tbl.autofit = True
        c0, c1 = hdr_tbl.rows[0].cells[0], hdr_tbl.rows[0].cells[1]

        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(f"{school_name.upper()}\n")
        r0.bold = True
        r0.font.size = Pt(11)
        r0b = p0.add_run("TỔ SINH HỌC\n(Đề thi gồm nhiều trang)")
        r0b.italic = True
        r0b.font.size = Pt(10)

        p1 = c1.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = p1.add_run(f"{exam_title.upper()}\n")
        r1.bold = True
        r1.font.size = Pt(12)
        r1b = p1.add_run(f"Môn: Sinh học 12 — Thời gian làm bài: {duration_min} phút\n")
        r1b.font.size = Pt(11)
        r1c = p1.add_run(f"MÃ ĐỀ: {ex['code']}")
        r1c.bold = True
        r1c.font.size = Pt(12)
        r1c.font.color.rgb = RGBColor(0x0F, 0x76, 0x6E)

        p_info = doc.add_paragraph("Họ và tên thí sinh: .................................................................  Lớp: .................  SBD: ...................")
        p_info.paragraph_format.space_before = Pt(6)
        p_info.paragraph_format.space_after = Pt(8)

        # PHẦN I: Trắc nghiệm 4 đáp án (0,25 điểm / câu)
        if ex["mcq"]:
            p_sec1 = doc.add_paragraph()
            r_s1 = p_sec1.add_run(
                f"PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn ({len(ex['mcq'])} câu — mỗi câu trả lời đúng được 0,25 điểm)."
            )
            r_s1.bold = True
            p_sec1.paragraph_format.space_after = Pt(4)

            for i, q in enumerate(ex["mcq"], 1):
                pq = doc.add_paragraph()
                pq.paragraph_format.space_before = Pt(4)
                pq.paragraph_format.space_after = Pt(2)
                rq = pq.add_run(f"Câu {i}: ")
                rq.bold = True
                pq.add_run(q["question"])

                _add_question_media_to_docx(doc, q["images"], q["tables"])

                opts = q["options"]
                if all(len(o) <= 22 for o in opts) and len(opts) == 4:
                    po = doc.add_paragraph(
                        f"A. {opts[0]}        B. {opts[1]}        C. {opts[2]}        D. {opts[3]}"
                    )
                    po.paragraph_format.space_after = Pt(3)
                else:
                    for oi, otxt in enumerate(opts):
                        po = doc.add_paragraph()
                        po.paragraph_format.left_indent = Cm(0.5)
                        po.paragraph_format.space_after = Pt(1)
                        ro = po.add_run(f"{'ABCD'[oi]}. ")
                        ro.bold = True
                        po.add_run(otxt)

        # PHẦN II: Trắc nghiệm Đúng/Sai
        if ex["true_false"]:
            p_sec2 = doc.add_paragraph()
            p_sec2.paragraph_format.space_before = Pt(10)
            p_sec2.paragraph_format.space_after = Pt(4)
            r_s2 = p_sec2.add_run(
                f"PHẦN II. Câu trắc nghiệm đúng sai ({len(ex['true_false'])} câu — đúng 1 ý: 0,1đ; 2 ý: 0,25đ; 3 ý: 0,5đ; 4 ý: 1,0đ)."
            )
            r_s2.bold = True

            for i, q in enumerate(ex["true_false"], 1):
                pq = doc.add_paragraph()
                pq.paragraph_format.space_before = Pt(5)
                pq.paragraph_format.space_after = Pt(2)
                rq = pq.add_run(f"Câu {i}: ")
                rq.bold = True
                pq.add_run(q["stem"])

                _add_question_media_to_docx(doc, q["images"], q["tables"])

                for st in q["statements"]:
                    ps = doc.add_paragraph()
                    ps.paragraph_format.left_indent = Cm(0.5)
                    ps.paragraph_format.space_after = Pt(1)
                    rs = ps.add_run(f"{st['key']}) ")
                    rs.bold = True
                    ps.add_run(st["text"])

        # PHẦN III: Trắc nghiệm trả lời ngắn (0,25 điểm / câu; tối đa 4 ký tự số)
        if ex["short_answer"]:
            p_sec3 = doc.add_paragraph()
            p_sec3.paragraph_format.space_before = Pt(10)
            p_sec3.paragraph_format.space_after = Pt(4)
            r_s3 = p_sec3.add_run(
                f"PHẦN III. Câu trắc nghiệm trả lời ngắn ({len(ex['short_answer'])} câu — mỗi câu trả lời đúng được 0,25 điểm; ghi giá trị số tối đa 4 ký tự gồm số, dấu âm, dấu phẩy)."
            )
            r_s3.bold = True

            for i, q in enumerate(ex["short_answer"], 1):
                pq = doc.add_paragraph()
                pq.paragraph_format.space_before = Pt(5)
                pq.paragraph_format.space_after = Pt(2)
                rq = pq.add_run(f"Câu {i}: ")
                rq.bold = True
                pq.add_run(q["question"])

                _add_question_media_to_docx(doc, q["images"], q["tables"])

                pa = doc.add_paragraph("Đáp án (tối đa 4 ký tự): [    ] [    ] [    ] [    ]")
                pa.paragraph_format.space_after = Pt(4)

        p_end = doc.add_paragraph("---------------- HẾT ----------------")
        p_end.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_end.paragraph_format.space_before = Pt(10)
        p_end.runs[0].bold = True

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


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


def build_answer_keys_xlsx(exams: List[Dict], meta: Dict, actual_counts: Dict) -> bytes:
    """Tạo file Excel .xlsx nhiều sheet cho toàn bộ mã đề trộn."""
    codes = [ex["code"] for ex in exams]

    # Sheet 1: Trắc nghiệm 4 đáp án
    s1_rows = [["Câu (Phần I - 0,25đ/câu)"] + [f"Mã đề {c}" for c in codes]]
    max_mcq = max((len(ex["mcq"]) for ex in exams), default=0)
    for i in range(max_mcq):
        row = [f"Câu {i + 1}"]
        for ex in exams:
            row.append(ex["mcq"][i]["correct_letter"] if i < len(ex["mcq"]) else "")
        s1_rows.append(row)

    # Sheet 2: Trắc nghiệm Đúng/Sai
    s2_rows = [["Câu / Ý (Phần II - 1,0đ/câu)"] + [f"Mã đề {c}" for c in codes]]
    max_tf = max((len(ex["true_false"]) for ex in exams), default=0)
    for i in range(max_tf):
        for k in ("a", "b", "c", "d"):
            row = [f"Câu {i + 1} - Ý {k})"]
            for ex in exams:
                if i < len(ex["true_false"]):
                    row.append(ex["true_false"][i]["ans_keys"].get(k, ""))
                else:
                    row.append("")
            s2_rows.append(row)

    # Sheet 3: Trắc nghiệm trả lời ngắn
    s3_rows = [["Câu (Phần III - 0,25đ/câu, tối đa 4 ký tự)"] + [f"Mã đề {c}" for c in codes]]
    max_sa = max((len(ex["short_answer"]) for ex in exams), default=0)
    for i in range(max_sa):
        row = [f"Câu {i + 1}"]
        for ex in exams:
            row.append(ex["short_answer"][i]["answer"] if i < len(ex["short_answer"]) else "")
        s3_rows.append(row)

    # Sheet 4: Ma trận đề & Thang điểm
    mcq_n = sum(actual_counts["mcq"].values())
    tf_n = sum(actual_counts["true_false"].values())
    sa_n = sum(actual_counts["short_answer"].values())
    total_pts = round(mcq_n * 0.25 + tf_n * 1.0 + sa_n * 0.25, 2)

    s4_rows = [
        ["Mức độ \\ Dạng câu hỏi", "Trắc nghiệm 4 đáp án (0,25đ)", "Trắc nghiệm Đúng/Sai (1,0đ)", "Trả lời ngắn (0,25đ)", "Tổng số câu"],
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
        ["", "", "", "", ""],
        ["Kỳ kiểm tra", meta.get("title") or "Đề kiểm tra Sinh học 12", "", "Số lượng đề", len(exams)],
        ["Danh sách Mã đề", ", ".join(codes), "", "Ngày xuất", datetime.now().strftime("%d/%m/%Y %H:%M")],
    ]

    sheets = [
        ("Dap an 4 dap an", s1_rows),
        ("Dap an Dung Sai", s2_rows),
        ("Dap an Tra loi ngan", s3_rows),
        ("Ma tran de", s4_rows),
    ]

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

        # Đếm câu hỏi cho từng bài
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
    """Sinh trọn bộ đề trộn (.docx) + đáp án Excel (.xlsx) từ ma trận."""
    rng = random.Random()
    mcqs, tfs, sas, actual_counts = _select_questions_by_matrix(topics, selected_lesson_ids, matrix, rng)

    if not mcqs and not tfs and not sas:
        raise ValueError("Không có câu hỏi nào phù hợp với các bài học và ma trận đã nhập.")

    codes = [c.strip() for c in exam_codes if c.strip()] or ["101"]
    exams = [_shuffle_single_exam(mcqs, tfs, sas, code, rng) for code in codes]

    docx_bytes = build_exams_docx(exams, meta, actual_counts)
    xlsx_bytes = build_answer_keys_xlsx(exams, meta, actual_counts)

    mcq_n = len(mcqs)
    tf_n = len(tfs)
    sa_n = len(sas)
    max_score = round(mcq_n * 0.25 + tf_n * 1.0 + sa_n * 0.25, 2)

    return {
        "docx_bytes": docx_bytes,
        "xlsx_bytes": xlsx_bytes,
        "summary": {
            "exam_count": len(exams),
            "exam_codes": codes,
            "mcq_count": mcq_n,
            "true_false_count": tf_n,
            "short_answer_count": sa_n,
            "max_score": max_score,
            "actual_counts": actual_counts,
        },
    }
