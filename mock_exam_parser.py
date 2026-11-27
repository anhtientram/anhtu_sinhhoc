"""
Bộ phân tích đề thi thử Tốt nghiệp THPT (Sinh học 12 - CT GDPT 2018) từ file Word (.docx) hoặc PDF (.pdf).
Tính năng:
  - Hỗ trợ chuẩn cấu trúc 3 phần Bộ GD&ĐT:
      + Phần I: Trắc nghiệm nhiều phương án lựa chọn (A, B, C, D) — 0,25đ / câu
      + Phần II: Trắc nghiệm Đúng / Sai (4 ý a, b, c, d) — 0,1 / 0,25 / 0,5 / 1,0đ
      + Phần III: Trắc nghiệm trả lời ngắn — 0,25đ / câu
  - Tự động trích xuất công thức toán/sinh Word OMML (<m:oMath>)
  - Tự động trích xuất hình ảnh nhúng trong .docx và .pdf dưới dạng Data URL gọn nhẹ (bền vững trên cả SQLite & Wasmer Edge MySQL)
  - Tự động nhận diện đáp án từ:
      + Định dạng Word (gạch chân <w:u>, chữ màu đỏ/xanh nổi bật, tô nền <w:highlight> trên chữ A./B./C./D.)
      + Dòng đáp án & lời giải ngay dưới mỗi câu (Đáp án:, Chọn, Hướng dẫn giải:, Lời giải:)
      + Bảng đáp án / mục ĐÁP ÁN ở cuối đề thi (cả văn bản lẫn bảng biểu)
"""

import base64
import io
import os
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from importer import _clean, _detect_image_ext, _local_tag, _omml_to_text, _safe_zip_read

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


LETTER_TO_IDX = {"A": 0, "B": 1, "C": 2, "D": 3}
IDX_TO_LETTER = {0: "A", 1: "B", 2: "C", 3: "D"}

RE_PART1 = re.compile(
    r"^\s*(?:PHẦN\s*(?:I|1)\b|I\s*[\.\:\-]\s*(?:CÂU\s+HỎI\s+)?TRẮC\s+NGHIỆM\s+(?:NHIỀU|4\s+PHƯƠNG\s+ÁN|KHÁCH\s+QUAN))",
    re.IGNORECASE,
)
RE_PART2 = re.compile(
    r"^\s*(?:PHẦN\s*(?:II|2)\b|II\s*[\.\:\-]\s*(?:CÂU\s+HỎI\s+)?(?:TRẮC\s+NGHIỆM\s+)?ĐÚNG\s*[/\-–]?\s*SAI)",
    re.IGNORECASE,
)
RE_PART3 = re.compile(
    r"^\s*(?:PHẦN\s*(?:III|3)\b|III\s*[\.\:\-]\s*(?:CÂU\s+HỎI\s+)?(?:TRẮC\s+NGHIỆM\s+)?TRẢ\s+LỜI\s+NGẮN)",
    re.IGNORECASE,
)
RE_ANSWER_SECTION = re.compile(
    r"^\s*(?:BẢNG\s+ĐÁP\s+ÁN|ĐÁP\s+ÁN\s*(?:CHÍNH\s+THỨC|CHI\s+TIẾT|THAM\s+KHẢO|VÀ\s+HƯỚNG\s+DẪN(?:\s+GIẢI(?:\s+CHI\s+TIẾT)?)?|&\s*HƯỚNG\s+DẪN(?:\s+GIẢI(?:\s+CHI\s+TIẾT)?)?|ĐỀ\s+THI)?|HƯỚNG\s+DẪN\s+CHẤM|HƯỚNG\s+DẪN\s+GIẢI\s+CHI\s+TIẾT|LỜI\s+GIẢI\s+CHI\s+TIẾT)\s*[:\-–.]?\s*$",
    re.IGNORECASE,
)
RE_Q_START = re.compile(r"^\s*(?:Câu|Question|Bài)\s*(\d+)\s*[:\.\-–\)]?\s*(.*)$", re.IGNORECASE)
RE_GROUP_TAG = re.compile(r"^\s*<\s*(#?)\s*g([0-3])\s*>\s*(.*)$", re.IGNORECASE)
RE_OPT_INLINE = re.compile(r"(?:^|\s)(#?)([A-D])\s*[\.\)]\s+")
RE_STMT_START = re.compile(r"^\s*(#?)([a-d])\s*[\)\.]\s*(.*)$", re.IGNORECASE)
RE_INLINE_ANS = re.compile(
    r"^\s*(?:Đáp\s*án(?:\s*đúng)?|Chọn|Đáp\s*số|Key)\s*[:\.\-–]?\s*(.+)$",
    re.IGNORECASE,
)
RE_SA_PREFIX_A = re.compile(r"^\s*A\s*[\.\:\)]\s*(.+)$")
RE_INLINE_EXPLAIN = re.compile(
    r"^\s*(?:Giải\s+chi\s+tiết|Hướng\s+dẫn\s+giải(?:\s+chi\s+tiết)?|Lời\s+giải(?:\s+chi\s+tiết)?|Giải\s+thích|Gợi\s+ý(?:\s+đáp\s+án)?|HDG|Giải)\s*(?:[:\.\-–]\s*(.*)|$)",
    re.IGNORECASE,
)


def _mime_from_ext(ext: str) -> str:
    ext = (ext or ".png").lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".gif":
        return "image/gif"
    if ext == ".webp":
        return "image/webp"
    return "image/png"


def _blob_to_data_url(blob: bytes, fallback_ext: str = ".png") -> Optional[str]:
    if not blob or len(blob) < 120:
        return None
    ext = _detect_image_ext(blob, fallback_ext)
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return None
    mime = _mime_from_ext(ext)
    b64 = base64.b64encode(blob).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _is_highlight_color(color_val: str) -> bool:
    """Nhận diện màu chữ nổi bật (đỏ, đỏ đậm, xanh dương đậm...) thường dùng đánh dấu đáp án đúng trong Word."""
    val = (color_val or "").strip().upper()
    if not val or val in ("AUTO", "000000", "111111", "222222", "333333", "FFFFFF"):
        return False
    if len(val) == 6:
        try:
            r = int(val[0:2], 16)
            g = int(val[2:4], 16)
            b = int(val[4:6], 16)
            # Đỏ / đỏ gạch (C00000, FF0000, D93025, ...)
            if r >= 150 and g <= 95 and b <= 95:
                return True
            # Xanh lá đậm đánh dấu đáp án
            if g >= 130 and r <= 80 and b <= 90:
                return True
        except ValueError:
            pass
    return False


def _run_is_underlined(run_el) -> bool:
    """Kiểm tra riêng thuộc tính gạch chân (<w:u>) — dùng nhận diện đáp án Đúng trong Phần II Đúng/Sai."""
    for ch in run_el:
        if _local_tag(ch) == "rPr":
            for prop in ch:
                if _local_tag(prop) == "u":
                    val = None
                    for k, v in prop.attrib.items():
                        if k.endswith("}val") or k == "val":
                            val = v
                            break
                    if val is None or val.lower() not in ("none", ""):
                        return True
            break
    return False


def _run_has_answer_mark(run_el) -> bool:
    """Kiểm tra một <w:r> có gạch chân (<w:u>), màu đỏ/xanh nổi bật hoặc highlight hay không."""
    if _run_is_underlined(run_el):
        return True
    rpr = None
    for ch in run_el:
        if _local_tag(ch) == "rPr":
            rpr = ch
            break
    if rpr is None:
        return False
    for prop in rpr:
        t = _local_tag(prop)
        if t == "highlight":
            val = ""
            for k, v in prop.attrib.items():
                if k.endswith("}val") or k == "val":
                    val = v
                    break
            if val.lower() not in ("none", "white", ""):
                return True
        elif t == "color":
            val = ""
            for k, v in prop.attrib.items():
                if k.endswith("}val") or k == "val":
                    val = v
                    break
            if _is_highlight_color(val):
                return True
    return False


def _extract_docx_elements(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Đọc toàn bộ đoạn văn + bảng + ảnh nhúng (dạng data URL) + dấu đáp án từ file .docx."""
    elements: List[Dict[str, Any]] = []
    rid_to_target: Dict[str, Tuple[str, str]] = {}
    rid_to_data_url: Dict[str, Optional[str]] = {}

    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        names = set(zf.namelist())
        if "word/_rels/document.xml.rels" in names:
            rbytes = _safe_zip_read(zf, "word/_rels/document.xml.rels")
            if rbytes:
                rroot = ET.fromstring(rbytes)
                for rel in rroot:
                    if _local_tag(rel) != "Relationship":
                        continue
                    rid = rel.attrib.get("Id", "")
                    rtype = rel.attrib.get("Type", "")
                    target = rel.attrib.get("Target", "")
                    if not rid or not target:
                        continue
                    if "image" not in rtype.lower() and not re.search(
                        r"\.(png|jpe?g|gif|webp|bmp)$", target, re.IGNORECASE
                    ):
                        continue
                    clean_target = target.lstrip("/")
                    if not clean_target.startswith("word/"):
                        clean_target = posixpath.normpath(posixpath.join("word", clean_target))
                    if clean_target in names:
                        ext = os.path.splitext(clean_target)[1].lower() or ".png"
                        rid_to_target[rid] = (clean_target, ext)

        def get_img_url(rid: str) -> Optional[str]:
            if rid in rid_to_data_url:
                return rid_to_data_url[rid]
            if rid not in rid_to_target:
                return None
            target, ext = rid_to_target[rid]
            blob = _safe_zip_read(zf, target)
            url = _blob_to_data_url(blob, ext) if blob else None
            rid_to_data_url[rid] = url
            return url

        def parse_paragraph(p_el) -> Dict[str, Any]:
            parts: List[str] = []
            marked_segments: List[str] = []
            underlined_segments: List[str] = []
            red_segments: List[str] = []
            imgs: List[str] = []

            for node in p_el:
                nt = _local_tag(node)
                if nt == "r":
                    run_texts: List[str] = []
                    is_u = _run_is_underlined(node)
                    is_marked = is_u or _run_has_answer_mark(node)
                    is_red = False
                    if not is_u and is_marked:
                        is_red = True
                    else:
                        # Kiểm tra thêm màu đỏ trực tiếp ngay cả khi vừa gạch chân vừa tô đỏ
                        for ch_r in node:
                            if _local_tag(ch_r) == "rPr":
                                for prop in ch_r:
                                    if _local_tag(prop) == "color":
                                        cval = ""
                                        for k, v in prop.attrib.items():
                                            if k.endswith("}val") or k == "val":
                                                cval = v
                                                break
                                        if _is_highlight_color(cval):
                                            is_red = True
                    for sub in node.iter():
                        st = _local_tag(sub)
                        if st == "t" and sub.text:
                            run_texts.append(sub.text)
                        elif st == "tab":
                            run_texts.append(" ")
                        elif st == "br":
                            run_texts.append("\n")
                        elif st == "blip":
                            # Bỏ qua ảnh lặp trong mc:Fallback
                            for k, v in sub.attrib.items():
                                if k.endswith("}embed") or k == "embed":
                                    u = get_img_url(v)
                                    if u and u not in imgs:
                                        imgs.append(u)
                        elif st == "imagedata":
                            for k, v in sub.attrib.items():
                                if k.endswith("}id") or k == "id":
                                    u = get_img_url(v)
                                    if u and u not in imgs:
                                        imgs.append(u)
                    rtxt = "".join(run_texts)
                    if rtxt:
                        parts.append(rtxt)
                        if is_marked:
                            marked_segments.append(rtxt)
                        if is_u:
                            underlined_segments.append(rtxt)
                        if is_red:
                            red_segments.append(rtxt)
                elif nt in ("oMath", "oMathPara"):
                    om = _omml_to_text(node)
                    if om:
                        parts.append(om)
                elif nt == "hyperlink":
                    for sub in node.iter():
                        if _local_tag(sub) == "t" and sub.text:
                            parts.append(sub.text)

            raw_text = "".join(parts)
            text = "\n".join(_clean(ln) for ln in raw_text.splitlines() if _clean(ln))

            def _extract_mcq_letters(segs: List[str]) -> List[str]:
                out: List[str] = []
                if not segs:
                    return out
                joined = "".join(segs)
                # Bắt cả dạng "A.", "#A.", "B)", "#B."
                for m in re.finditer(r"(?:^|\s)#?([A-D])\s*[\.\)]", joined):
                    lt = m.group(1)
                    if lt not in out:
                        out.append(lt)
                if not out:
                    for sg in segs:
                        m = re.match(r"^\s*#?([A-D])\s*[\.\)]?\s*$", sg)
                        if m and m.group(1) not in out:
                            out.append(m.group(1))
                if not out:
                    m_start = re.match(r"^\s*#?([A-D])\s*[\.\)]\s+", text)
                    if m_start and not re.search(r"(?:^|\s)#?B\s*[\.\)]\s+", text):
                        first_m = _clean(joined)
                        if len(first_m) >= 1 and first_m in text:
                            out.append(m_start.group(1))
                if not out and re.search(r"(?:^|\s)#?B\s*[\.\)]\s+", text):
                    jc = _clean(joined)
                    if len(jc) >= 2:
                        _, inline_opts = _split_inline_options(text)
                        for lt, otxt, _ in inline_opts:
                            if otxt and (jc in otxt or otxt in jc) and lt not in out:
                                out.append(lt)
                return out

            underlined_letters = _extract_mcq_letters(underlined_segments)
            red_letters = _extract_mcq_letters(red_segments)
            marked_letters = underlined_letters or red_letters or _extract_mcq_letters(marked_segments)

            # Kiểm tra nhãn ý Phần II (a), b), c), d) hoặc #a)...) có được gạch chân (<w:u>) hay tô đỏ không
            tf_underlined = False
            tf_red = False
            m_tf_line = re.match(r"^\s*#?([a-d])\s*[\)\.]", text, re.IGNORECASE)
            if m_tf_line:
                tf_key = m_tf_line.group(1).lower()
                if underlined_segments:
                    u_joined = "".join(underlined_segments).strip()
                    if re.match(rf"^\s*#?{tf_key}\s*[\)\.]?", u_joined, re.IGNORECASE) or len(u_joined) >= max(4, int(len(text) * 0.4)):
                        tf_underlined = True
                if red_segments:
                    r_joined = "".join(red_segments).strip()
                    if re.match(rf"^\s*#?{tf_key}\s*[\)\.]?", r_joined, re.IGNORECASE) or len(r_joined) >= max(4, int(len(text) * 0.4)):
                        tf_red = True

            return {
                "type": "paragraph",
                "text": text,
                "images": imgs,
                "underlined_letters": underlined_letters,
                "red_letters": red_letters,
                "marked_letters": marked_letters,
                "marked_text": _clean(" ".join(marked_segments)),
                "tf_underlined": tf_underlined,
                "tf_red": tf_red,
            }

        def parse_table(tbl_el) -> Dict[str, Any]:
            rows: List[List[str]] = []
            imgs: List[str] = []
            for tr in tbl_el:
                if _local_tag(tr) != "tr":
                    continue
                row: List[str] = []
                for tc in tr:
                    if _local_tag(tc) != "tc":
                        continue
                    cell_lines: List[str] = []
                    for ch in tc:
                        if _local_tag(ch) == "p":
                            p = parse_paragraph(ch)
                            if p["text"]:
                                cell_lines.append(p["text"])
                            for im in p["images"]:
                                if im not in imgs:
                                    imgs.append(im)
                    row.append("\n".join(cell_lines).strip())
                if any(c for c in row):
                    rows.append(row)
            return {"type": "table", "rows": rows, "images": imgs}

        if "word/document.xml" not in names:
            raise ValueError("File Word (.docx) không hợp lệ: thiếu word/document.xml.")
        doc_xml = _safe_zip_read(zf, "word/document.xml")
        if not doc_xml:
            raise ValueError("Không thể đọc nội dung word/document.xml trong file Word.")
        root = ET.fromstring(doc_xml)
        body = next((ch for ch in root if _local_tag(ch) == "body"), root)

        for ch in body:
            tag = _local_tag(ch)
            if tag == "p":
                p = parse_paragraph(ch)
                if p["text"] or p["images"]:
                    elements.append(p)
            elif tag == "tbl":
                t = parse_table(ch)
                if t["rows"] or t["images"]:
                    elements.append(t)

    return elements


def _extract_pdf_elements(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Đọc nội dung văn bản và ảnh nhúng từng trang từ file PDF (.pdf) bằng pypdf."""
    if PdfReader is None:
        raise ValueError("Thiếu thư viện pypdf trên máy chủ để đọc file PDF.")
    reader = PdfReader(io.BytesIO(file_bytes))
    elements: List[Dict[str, Any]] = []

    for page_idx, page in enumerate(reader.pages):
        page_imgs: List[str] = []
        try:
            for img_obj in getattr(page, "images", []) or []:
                blob = getattr(img_obj, "data", b"")
                if not blob or len(blob) < 1500:
                    continue
                name = getattr(img_obj, "name", "img.png") or "img.png"
                ext = os.path.splitext(name)[1].lower() or ".png"
                u = _blob_to_data_url(blob, ext)
                if u and u not in page_imgs:
                    page_imgs.append(u)
        except Exception:
            pass

        txt = ""
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""

        lines = [_clean(ln) for ln in txt.splitlines() if _clean(ln)]
        # Lọc số trang đơn lẻ hoặc dòng tiêu đề lặp "Trang 1/5"
        filtered_lines = [
            ln for ln in lines
            if not re.match(r"^(?:Trang\s*\d+(?:\s*/\s*\d+)?|[-–—]?\s*\d+\s*[-–—]?)$", ln, re.IGNORECASE)
        ]

        # Gắn ảnh trong trang vào câu hỏi có nhắc tới "Hình"/"Sơ đồ"/"Đồ thị"/"Bảng" hoặc câu đầu/cuối trang
        img_attach_indices: Dict[int, List[str]] = {}
        if page_imgs and filtered_lines:
            fig_lines = [
                i for i, ln in enumerate(filtered_lines)
                if re.search(r"\b(?:Hình|Sơ đồ|Đồ thị|Biểu đồ|Phả hệ|Bảng\s+\d|hình\s+bên|hình\s+dưới)\b", ln, re.IGNORECASE)
            ]
            q_lines = [i for i, ln in enumerate(filtered_lines) if RE_Q_START.match(ln)]
            targets = fig_lines or q_lines or [0]
            for k, im in enumerate(page_imgs):
                t_idx = targets[min(k, len(targets) - 1)]
                img_attach_indices.setdefault(t_idx, []).append(im)

        for i, ln in enumerate(filtered_lines):
            elements.append({
                "type": "paragraph",
                "text": ln,
                "images": img_attach_indices.get(i, []),
                "marked_letters": [],
                "marked_text": "",
                "page": page_idx + 1,
            })

        # Nếu trang chỉ toàn ảnh (không có text) vẫn giữ lại để gắn vào câu gần nhất
        if page_imgs and not filtered_lines:
            elements.append({
                "type": "paragraph",
                "text": "",
                "images": page_imgs,
                "marked_letters": [],
                "marked_text": "",
                "page": page_idx + 1,
            })

    return elements


def _split_inline_options(text: str) -> Tuple[str, List[Tuple[str, str, bool]]]:
    """
    Tách các phương án A. ... B. ... C. ... D. ... (hỗ trợ cả dấu # cố định như #A., #D. và dạng nhãn đơn A./B./C./D.) nằm trên cùng hoặc riêng dòng.
    Trả về: (prefix, [(letter, text, is_fixed), ...])
    """
    raw_matches = list(re.finditer(r"(?:^|\s)(#?)([A-D])\s*[\.\)](?:\s+|$)", text))
    if not raw_matches:
        return text, []

    # Nếu chỉ có 1 match nhưng KHÔNG đứng ở đầu dòng và không đi kèm B./C./D. -> tránh nhầm tên như "Vitamin A. ..."
    if len(raw_matches) == 1 and raw_matches[0].start() > 0:
        prefix_before = text[: raw_matches[0].start()].strip()
        # Chỉ tách nếu phía trước rỗng hoặc là phần cuối stem rõ ràng kết thúc bằng ?, :, .
        if prefix_before and not re.search(r"[?:]\s*$", prefix_before):
            return text, []

    # Lọc giữ chuỗi chữ cái tăng dần hợp lệ (A->B->C->D hoặc C->D)
    matches = []
    seen = set()
    for m in raw_matches:
        lt = m.group(2).upper()
        if lt in seen:
            continue
        if matches and ord(lt) <= ord(matches[-1].group(2).upper()):
            continue
        seen.add(lt)
        matches.append(m)
    if not matches:
        return text, []

    prefix = text[: matches[0].start()].strip()
    opts: List[Tuple[str, str, bool]] = []
    for i, m in enumerate(matches):
        is_fixed = bool(m.group(1))
        letter = m.group(2).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        opts.append((letter, text[start:end].strip(), is_fixed))
    return prefix, opts


def _parse_tf_string(val_str: str) -> Optional[List[Optional[bool]]]:
    """Chuyển chuỗi đáp án Đúng/Sai như 'a-Đ, b-S, c-Đ, d-S', 'Đ S Đ Đ', 'a) Đúng; b) Sai' thành [bool, bool, bool, bool]."""
    s = (val_str or "").strip()
    if not s:
        return None
    # Dạng a) Đúng, b) Sai ... hoặc a-Đ b-S c-Đ d-S
    res: Dict[str, bool] = {}
    for m in re.finditer(r"([a-d])\s*[\)\.\-–:]?\s*(Đúng|Sai|Đ|S|True|False|T|F)\b", s, re.IGNORECASE):
        k = m.group(1).lower()
        v = m.group(2).strip().upper()
        res[k] = v in ("ĐÚNG", "Đ", "TRUE", "T")
    if len(res) >= 2:
        return [res.get(k) for k in ("a", "b", "c", "d")]

    # Dạng 4 chữ cái liên tiếp Đ S Đ S hoặc ĐSĐS
    compact = re.sub(r"[^ĐSDTFđsdtf]", "", s).upper()
    if len(compact) == 4:
        return [ch in ("Đ", "D", "T") for ch in compact]

    # Dạng danh sách 4 từ Đúng / Sai
    words = re.findall(r"\b(Đúng|Sai|Đ|S)\b", s, re.IGNORECASE)
    if len(words) == 4:
        return [w.strip().upper() in ("ĐÚNG", "Đ") for w in words]
    return None


def _parse_answer_key_section(
    ans_elements: List[Dict[str, Any]],
) -> Tuple[Dict[int, int], Dict[int, List[Optional[bool]]], Dict[int, List[str]], Dict[Tuple[str, int], str]]:
    """
    Phân tích mục ĐÁP ÁN / HƯỚNG DẪN GIẢI ở cuối đề thi (cả văn bản lẫn bảng).
    Trả về: (mcq_keys, tf_keys, sa_keys, explanations_by_(part, num))
    """
    mcq_keys: Dict[int, int] = {}
    tf_keys: Dict[int, List[Optional[bool]]] = {}
    sa_keys: Dict[int, List[str]] = {}
    explanations: Dict[Tuple[str, int], str] = {}

    cur_part = "mcq"
    cur_exp_target: Optional[Tuple[str, int]] = None

    for el in ans_elements:
        if el["type"] == "paragraph":
            txt = el.get("text", "")
            if not txt:
                continue
            if RE_PART1.match(txt) or re.search(r"PHẦN\s*(?:I|1)\b|TRẮC\s+NGHIỆM\s+(?:NHIỀU|4)", txt, re.IGNORECASE):
                cur_part = "mcq"
                cur_exp_target = None
                continue
            if RE_PART2.match(txt) or re.search(r"PHẦN\s*(?:II|2)\b|ĐÚNG\s*[/\-–]?\s*SAI", txt, re.IGNORECASE):
                cur_part = "true_false"
                cur_exp_target = None
                continue
            if RE_PART3.match(txt) or re.search(r"PHẦN\s*(?:III|3)\b|TRẢ\s+LỜI\s+NGẮN", txt, re.IGNORECASE):
                cur_part = "short_answer"
                cur_exp_target = None
                continue

            if cur_part == "mcq":
                # Bắt nhiều cặp trên cùng 1 dòng: "1.A  2.B  3.C" hoặc "1-A 2-B" hoặc "Câu 1: A"
                pairs = re.findall(r"(?:Câu\s*)?(\d+)\s*[\.\:\-–\s]\s*([A-D])(?![a-zA-ZÀ-ỹ])", txt, re.IGNORECASE)
                # Hoặc dạng dính liền "1A 2B 3C"
                if not pairs:
                    pairs = re.findall(r"\b(\d{1,2})([A-D])\b", txt)
                if pairs and len(pairs) >= 1 and len(txt) < 280 and not re.search(r"vì\s|do\s|giải\s*thích", txt, re.IGNORECASE):
                    for num_s, let in pairs:
                        mcq_keys[int(num_s)] = LETTER_TO_IDX[let.upper()]
                    cur_exp_target = None
                    continue

                # Dạng lời giải chi tiết: "Câu 1: Chọn A. Vì..." hoặc "Câu 1 (A): ..."
                m_exp = re.match(r"^\s*Câu\s*(\d+)\s*(?:\(([A-D])\))?\s*[:\.\-–]\s*(.*)$", txt, re.IGNORECASE)
                if m_exp:
                    qnum = int(m_exp.group(1))
                    body = m_exp.group(3).strip()
                    if m_exp.group(2):
                        mcq_keys[qnum] = LETTER_TO_IDX[m_exp.group(2).upper()]
                    else:
                        m_pick = re.search(r"(?:Chọn|Đáp\s*án)\s*[:\s]*([A-D])\b", body, re.IGNORECASE)
                        if m_pick:
                            mcq_keys[qnum] = LETTER_TO_IDX[m_pick.group(1).upper()]
                    if body:
                        explanations[("mcq", qnum)] = (explanations.get(("mcq", qnum), "") + "\n" + body).strip()
                    cur_exp_target = ("mcq", qnum)
                    continue

            elif cur_part == "true_false":
                # Nhiều câu trên 1 dòng hoặc từng câu: "Câu 1: a-Đ, b-S, c-Đ, d-S" hoặc "Câu 1:" (tiếp theo là từng dòng a), b), c), d))
                m_tf = re.match(r"^\s*(?:Câu\s*)?(\d+)\s*[:\.\-–]?\s*(.*)$", txt, re.IGNORECASE)
                if m_tf and re.match(r"^\s*(?:Câu\s*\d+|\d+\s*[:\.\-–])", txt, re.IGNORECASE):
                    qnum = int(m_tf.group(1))
                    rest = (m_tf.group(2) or "").strip()
                    if rest:
                        parsed = _parse_tf_string(rest)
                        if parsed:
                            tf_keys[qnum] = parsed
                        if len(rest) > 20 or not parsed:
                            explanations[("true_false", qnum)] = (explanations.get(("true_false", qnum), "") + "\n" + rest).strip()
                    cur_exp_target = ("true_false", qnum)
                    continue

            elif cur_part == "short_answer":
                # Nhiều câu trên 1 dòng: "1. 4   2. 0,25   3. 12"
                sa_pairs = re.findall(r"(?:Câu\s*)?(\d+)\s*[:\.\-–]\s*([-+]?\d+(?:[,\.]\d+)?(?:\s*\([^\)]+\))?)", txt, re.IGNORECASE)
                if sa_pairs and len(sa_pairs) >= 2:
                    for num_s, val in sa_pairs:
                        v_clean = re.sub(r"\s*\([^\)]+\)", "", val).strip()
                        acc = [v_clean]
                        if "," in v_clean:
                            acc.append(v_clean.replace(",", "."))
                        elif "." in v_clean:
                            acc.append(v_clean.replace(".", ","))
                        sa_keys[int(num_s)] = acc
                    cur_exp_target = None
                    continue

                m_sa = re.match(r"^\s*(?:Câu\s*)?(\d+)\s*[:\.\-–]?\s*(.*)$", txt, re.IGNORECASE)
                if m_sa and re.match(r"^\s*(?:Câu\s*\d+|\d+\s*[:\.\-–])", txt, re.IGNORECASE):
                    qnum = int(m_sa.group(1))
                    rest = (m_sa.group(2) or "").strip()
                    if rest:
                        m_num = re.match(r"^(?:A\s*[\.\:\)]\s*|(?:Đáp\s*án|Đáp\s*số|Kết\s*quả)\s*[:\.\-–]?\s*)?([-+]?\d+(?:[,\.]\d+)?)", rest, re.IGNORECASE)
                        if m_num:
                            v_clean = m_num.group(1)
                            acc = [v_clean]
                            if "," in v_clean:
                                acc.append(v_clean.replace(",", "."))
                            elif "." in v_clean:
                                acc.append(v_clean.replace(".", ","))
                            sa_keys[qnum] = acc
                        elif len(rest) <= 24:
                            sa_keys[qnum] = [rest]
                        if len(rest) > 10:
                            explanations[("short_answer", qnum)] = (explanations.get(("short_answer", qnum), "") + "\n" + rest).strip()
                    cur_exp_target = ("short_answer", qnum)
                    continue

            if cur_exp_target:
                explanations[cur_exp_target] = (explanations.get(cur_exp_target, "") + "\n" + txt).strip()
                # Tự trích đáp án nếu xuất hiện trong phần Hướng dẫn giải chi tiết cuối đề
                part_k, qnum_k = cur_exp_target
                if part_k == "mcq" and qnum_k not in mcq_keys:
                    mp = re.search(r"(?:Chọn|Đáp\s*án(?:\s*đúng)?)\s*[:\s]*([A-D])\b", txt, re.IGNORECASE)
                    if mp:
                        mcq_keys[qnum_k] = LETTER_TO_IDX[mp.group(1).upper()]
                elif part_k == "true_false":
                    m_st_exp = re.match(r"^\s*([a-d])\s*[\)\.\-–:]?\s*(Đúng|Sai|Đ|S)\b", txt, re.IGNORECASE)
                    if m_st_exp:
                        arr = list(tf_keys.get(qnum_k) or [None, None, None, None])
                        si = ("a", "b", "c", "d").index(m_st_exp.group(1).lower())
                        arr[si] = m_st_exp.group(2).strip().upper() in ("ĐÚNG", "Đ")
                        tf_keys[qnum_k] = arr
                elif part_k == "short_answer" and qnum_k not in sa_keys:
                    msa = re.search(r"(?:Đáp\s*án|Đáp\s*số|Kết\s*quả)\s*[:\s]*([-+]?\d+(?:[,\.]\d+)?)", txt, re.IGNORECASE)
                    if msa:
                        vc = msa.group(1)
                        acc = [vc]
                        if "," in vc:
                            acc.append(vc.replace(",", "."))
                        elif "." in vc:
                            acc.append(vc.replace(".", ","))
                        sa_keys[qnum_k] = acc

        elif el["type"] == "table":
            rows = el.get("rows", [])
            if not rows:
                continue
            # Kiểm tra bảng đáp án ngang (hàng số câu + hàng chữ cái/số)
            for ri in range(len(rows) - 1):
                r_top = rows[ri]
                r_bot = rows[ri + 1]
                if len(r_top) >= 3 and len(r_top) == len(r_bot):
                    nums = []
                    for c in r_top:
                        m = re.match(r"^(?:Câu\s*)?(\d+)$", c.strip(), re.IGNORECASE)
                        if m:
                            nums.append(int(m.group(1)))
                        else:
                            nums.append(None)
                    if sum(1 for x in nums if x is not None) >= 3:
                        for num, val in zip(nums, r_bot):
                            if num is None or not val.strip():
                                continue
                            v = val.strip()
                            if cur_part == "mcq" and re.match(r"^[A-D]$", v, re.IGNORECASE):
                                mcq_keys[num] = LETTER_TO_IDX[v.upper()]
                            elif cur_part == "true_false":
                                parsed = _parse_tf_string(v)
                                if parsed:
                                    tf_keys[num] = parsed
                            elif cur_part == "short_answer":
                                acc = [v]
                                if "," in v:
                                    acc.append(v.replace(",", "."))
                                elif "." in v:
                                    acc.append(v.replace(".", ","))
                                sa_keys[num] = acc

            # Kiểm tra bảng đáp án dọc (mỗi hàng là: Câu 1 | A hoặc Câu 1 | a-Đ, b-S... hoặc Câu 1 | Đ | S | Đ | S)
            for row in rows:
                if len(row) < 2:
                    continue
                m0 = re.match(r"^(?:Câu\s*)?(\d+)[\.\:]?$", row[0].strip(), re.IGNORECASE)
                if m0:
                    qnum = int(m0.group(1))
                    if len(row) >= 5 and all(re.match(r"^(?:Đúng|Sai|Đ|S)$", c.strip(), re.IGNORECASE) for c in row[1:5]):
                        tf_keys[qnum] = [c.strip().upper() in ("ĐÚNG", "Đ") for c in row[1:5]]
                    else:
                        v1 = row[1].strip()
                        if cur_part == "mcq" and re.match(r"^[A-D]$", v1, re.IGNORECASE):
                            mcq_keys[qnum] = LETTER_TO_IDX[v1.upper()]
                        elif cur_part == "true_false":
                            parsed = _parse_tf_string(" ".join(row[1:]))
                            if parsed:
                                tf_keys[qnum] = parsed
                        elif cur_part == "short_answer" and v1:
                            acc = [v1]
                            if "," in v1:
                                acc.append(v1.replace(",", "."))
                            elif "." in v1:
                                acc.append(v1.replace(".", ","))
                            sa_keys[qnum] = acc
                # Cặp nhiều cột trên 1 hàng: [Câu 1, A, Câu 10, B]
                if cur_part == "mcq" and len(row) >= 4 and len(row) % 2 == 0:
                    for ci in range(0, len(row), 2):
                        mc = re.match(r"^(?:Câu\s*)?(\d+)[\.\:]?$", row[ci].strip(), re.IGNORECASE)
                        mv = re.match(r"^([A-D])$", row[ci + 1].strip(), re.IGNORECASE)
                        if mc and mv:
                            mcq_keys[int(mc.group(1))] = LETTER_TO_IDX[mv.group(1).upper()]

    return mcq_keys, tf_keys, sa_keys, explanations


def parse_mock_exam_document(
    file_bytes: bytes,
    filename: str,
    next_order_number: int = 1,
) -> Dict[str, Any]:
    """
    Phân tích file Word (.docx) hoặc PDF (.pdf) thành bản nháp Đề thi thử Tốt nghiệp THPT
    để Giáo viên/Quản trị viên xem trước, làm đẹp ảnh và chỉnh sửa từng câu trước khi lưu.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".docx":
        elements = _extract_docx_elements(file_bytes)
    elif ext == ".pdf":
        elements = _extract_pdf_elements(file_bytes)
    else:
        raise ValueError("Chỉ hỗ trợ tải lên file Word (.docx) hoặc file PDF (.pdf).")

    if not elements:
        raise ValueError("Không trích xuất được nội dung từ tệp đã tải lên.")

    # Tách phần đề thi và phần đáp án cuối đề (nếu có).
    # Bảo vệ cực chặt: phân biệt "Hướng dẫn giải chi tiết" đặt NGAY DƯỚI từng câu (inline)
    # với mục "BẢNG ĐÁP ÁN / HƯỚNG DẪN GIẢI CHI TIẾT" tổng hợp ở CUỐI ĐỀ!
    ans_split_idx = None
    seen_questions = 0
    seen_inline_explain_before = False
    seen_part3 = False
    for idx, el in enumerate(elements):
        if el["type"] == "paragraph":
            txt = el.get("text", "")
            if RE_PART3.match(txt):
                seen_part3 = True
            if RE_Q_START.match(txt):
                seen_questions += 1
            if seen_questions < 3 and RE_INLINE_EXPLAIN.match(txt):
                seen_inline_explain_before = True
            if seen_questions >= 3 and RE_ANSWER_SECTION.match(txt):
                is_explain_only_heading = bool(re.match(r"^\s*(?:HƯỚNG\s+DẪN\s+GIẢI|LỜI\s+GIẢI)", txt, re.IGNORECASE))
                # Nếu các câu trước đã dùng "Hướng dẫn giải chi tiết" ngay dưới từng câu -> đây cũng là inline!
                if is_explain_only_heading and seen_inline_explain_before:
                    continue
                tail_has_more_exam_body = False
                for nxt in elements[idx + 1 : idx + 30]:
                    if nxt["type"] == "paragraph":
                        ntxt = nxt.get("text", "")
                        # Nếu phía sau còn xuất hiện PHẦN III lần đầu tiên (chưa gặp ở thân đề) -> vẫn đang ở thân đề!
                        if not seen_part3 and RE_PART3.match(ntxt):
                            tail_has_more_exam_body = True
                            break
                        if re.search(r"(?:^|\s)A\.\s+\S+.*(?:^|\s)B\.\s+\S+", ntxt):
                            tail_has_more_exam_body = True
                            break
                        if re.match(r"^\s*B\.\s+\S+", ntxt) and any(
                            re.match(r"^\s*C\.\s+\S+", x.get("text", ""))
                            for x in elements[idx + 1 : idx + 30]
                            if x["type"] == "paragraph"
                        ):
                            tail_has_more_exam_body = True
                            break
                if not tail_has_more_exam_body:
                    ans_split_idx = idx
                    break

    body_elements = elements[:ans_split_idx] if ans_split_idx is not None else elements
    ans_elements = elements[ans_split_idx + 1 :] if ans_split_idx is not None else []

    mcq_list: List[Dict[str, Any]] = []
    tf_list: List[Dict[str, Any]] = []
    sa_list: List[Dict[str, Any]] = []

    cur_part = "mcq"
    cur_q: Optional[Dict[str, Any]] = None
    in_explanation = False
    warnings: List[str] = []

    # Theo dõi thẻ nhóm trộn chuẩn Young Mix: <g0>, <g1>, <g2>, <g3>, <#g0>, <#g1>, <#g2>, <#g3>
    group_counter = 1
    cur_group = {
        "id": "grp-1",
        "mode": "g3",
        "fixed": False,
        "tag": "<g3>",
        "explicit": False,
        "has_questions": False,
    }
    detected_groups: List[Dict[str, Any]] = []

    def start_new_group(mode: str, fixed: bool, explicit: bool = True):
        nonlocal group_counter, cur_group
        if explicit and not cur_group["has_questions"] and not cur_group["explicit"]:
            cur_group["mode"] = mode
            cur_group["fixed"] = fixed
            cur_group["tag"] = f"<{'#' if fixed else ''}{mode}>"
            cur_group["explicit"] = True
            return
        group_counter += 1
        cur_group = {
            "id": f"grp-{group_counter}",
            "mode": mode,
            "fixed": fixed,
            "tag": f"<{'#' if fixed else ''}{mode}>",
            "explicit": explicit,
            "has_questions": False,
        }

    def finalize_current():
        nonlocal cur_q, in_explanation
        if not cur_q:
            return
        in_explanation = False
        qtype = cur_q.pop("_type")

        # Nếu phân loại mặc định là mcq nhưng không có phương án A-D, tự động nhận diện lại
        if qtype == "mcq" and len(cur_q.get("options", [])) == 0:
            if len(cur_q.get("statements", [])) >= 2:
                qtype = "true_false"
            elif cur_q.get("question"):
                qtype = "short_answer"

        if qtype == "mcq":
            opts = cur_q.get("options", [])
            while len(opts) < 4:
                opts.append("")
            cur_q["options"] = opts[:4]
            cur_q["fixed_options"] = sorted(set(cur_q.get("fixed_options") or []))
            cur_q.pop("statements", None)
            cur_q.pop("accepted_answers", None)
            cur_q["id"] = f"mcq-{len(mcq_list) + 1}"
            mcq_list.append(cur_q)
        elif qtype == "true_false":
            stmts = cur_q.get("statements", [])
            existing_keys = {s["key"] for s in stmts}
            for k in ("a", "b", "c", "d"):
                if k not in existing_keys:
                    stmts.append({"key": k, "text": "", "answer": None, "fixed": False})
            stmts.sort(key=lambda s: ("a", "b", "c", "d").index(s["key"]) if s["key"] in ("a", "b", "c", "d") else 9)
            cur_q["statements"] = stmts[:4]
            cur_q.pop("options", None)
            cur_q.pop("fixed_options", None)
            cur_q.pop("correct_index", None)
            cur_q.pop("accepted_answers", None)
            cur_q["id"] = f"tf-{len(tf_list) + 1}"
            tf_list.append(cur_q)
        else:
            cur_q.pop("options", None)
            cur_q.pop("fixed_options", None)
            cur_q.pop("correct_index", None)
            cur_q.pop("statements", None)
            cur_q.setdefault("accepted_answers", [])
            cur_q["id"] = f"sa-{len(sa_list) + 1}"
            sa_list.append(cur_q)
        cur_q = None

    for el in body_elements:
        if el["type"] == "table":
            if cur_q is not None:
                if el.get("rows"):
                    cur_q["tables"].append(el["rows"])
                for im in el.get("images", []):
                    if im not in cur_q["images"]:
                        cur_q["images"].append(im)
            continue

        txt = el.get("text", "")
        imgs = el.get("images", [])
        marked_letters = el.get("marked_letters", [])

        # Nhận diện thẻ nhóm trộn <g0>, <g1>, <g2>, <g3>, <#g0>, <#g1>, <#g2>, <#g3>
        m_grp = RE_GROUP_TAG.match(txt)
        if m_grp:
            finalize_current()
            g_fixed = bool(m_grp.group(1))
            g_mode = f"g{m_grp.group(2)}"
            start_new_group(g_mode, g_fixed, explicit=True)
            txt = (m_grp.group(3) or "").strip()
            if not txt:
                continue

        # Bỏ qua các dòng tiêu đề đề thi trước câu 1
        if RE_PART1.match(txt):
            finalize_current()
            cur_part = "mcq"
            if cur_group["has_questions"]:
                start_new_group("g3", False, explicit=False)
            continue
        if RE_PART2.match(txt):
            finalize_current()
            cur_part = "true_false"
            if cur_group["has_questions"]:
                start_new_group("g3", False, explicit=False)
            continue
        if RE_PART3.match(txt):
            finalize_current()
            cur_part = "short_answer"
            if cur_group["has_questions"]:
                start_new_group("g3", False, explicit=False)
            continue

        # Bắt đầu câu hỏi mới
        m_q = RE_Q_START.match(txt)
        if m_q:
            finalize_current()
            qnum = int(m_q.group(1))
            rest = m_q.group(2).strip()
            in_explanation = False
            cur_group["has_questions"] = True
            cur_q = {
                "_type": cur_part,
                "orig_num": qnum,
                "group_id": cur_group["id"],
                "shuffle_mode": cur_group["mode"],
                "group_fixed": cur_group["fixed"],
                "group_tag": cur_group["tag"],
                "question": "",
                "images": list(imgs),
                "tables": [],
                "options": [],
                "fixed_options": [],
                "correct_index": None,
                "statements": [],
                "accepted_answers": [],
                "explanation": "",
            }
            if cur_part == "mcq" and rest:
                prefix, opts = _split_inline_options(rest)
                cur_q["question"] = prefix
                for lt, otxt, is_fixed in opts:
                    idx = LETTER_TO_IDX[lt]
                    while len(cur_q["options"]) <= idx:
                        cur_q["options"].append("")
                    cur_q["options"][idx] = otxt
                    if is_fixed and idx not in cur_q["fixed_options"]:
                        cur_q["fixed_options"].append(idx)
                if marked_letters and len(marked_letters) == 1 and cur_q["correct_index"] is None:
                    cur_q["correct_index"] = LETTER_TO_IDX.get(marked_letters[0])
            else:
                cur_q["question"] = rest
            continue

        if cur_q is None:
            continue

        # Gắn ảnh rời rạc vào câu hỏi hiện tại
        for im in imgs:
            if im not in cur_q["images"]:
                cur_q["images"].append(im)
        if not txt:
            continue

        # Dòng giải thích / hướng dẫn giải chi tiết ngay dưới câu hỏi
        m_exp = RE_INLINE_EXPLAIN.match(txt)
        if m_exp:
            in_explanation = True
            ex_txt = (m_exp.group(1) or "").strip()
            if ex_txt:
                cur_q["explanation"] = (cur_q["explanation"] + "\n" + ex_txt).strip()
            continue

        # Dòng đáp án ngay dưới câu hỏi (nếu đang trong khối Hướng dẫn giải chi tiết vẫn lưu vào gợi ý!)
        m_ans = RE_INLINE_ANS.match(txt)
        if m_ans:
            val = m_ans.group(1).strip()
            if cur_q["_type"] == "mcq":
                m_l = re.match(r"^([A-D])\b", val, re.IGNORECASE)
                if m_l:
                    cur_q["correct_index"] = LETTER_TO_IDX[m_l.group(1).upper()]
                    extra = val[m_l.end() :].lstrip(" .:-–").strip()
                    if extra:
                        cur_q["explanation"] = (cur_q["explanation"] + "\n" + extra).strip()
                    continue
            elif cur_q["_type"] == "true_false":
                parsed_tf = _parse_tf_string(val)
                if parsed_tf:
                    for idx, st in enumerate(cur_q.get("statements", [])):
                        if idx < len(parsed_tf) and parsed_tf[idx] is not None:
                            st["answer"] = parsed_tf[idx]
                    continue
            else:
                v_clean = re.sub(r"\s*\([^\)]+\)", "", val).strip()
                if v_clean and not re.match(r"^[…\.\-_]+$", v_clean):
                    acc = [v_clean]
                    if "," in v_clean:
                        acc.append(v_clean.replace(",", "."))
                    elif "." in v_clean:
                        acc.append(v_clean.replace(".", ","))
                    cur_q["accepted_answers"] = acc
                    continue

        if in_explanation:
            cur_q["explanation"] = (cur_q["explanation"] + "\n" + txt).strip()
            # Nếu trong lời giải chi tiết có ghi "Chọn A" / "a) Đúng" / "Đáp số: 8" mà câu chưa có key -> tự bắt luôn
            if cur_q["_type"] == "mcq" and cur_q.get("correct_index") is None:
                mp = re.search(r"(?:Chọn|Đáp\s*án(?:\s*đúng)?)\s*[:\s]*([A-D])\b", txt, re.IGNORECASE)
                if mp:
                    cur_q["correct_index"] = LETTER_TO_IDX[mp.group(1).upper()]
            elif cur_q["_type"] == "true_false":
                m_st_e = re.match(r"^\s*([a-d])\s*[\)\.\-–:]?\s*(Đúng|Sai)\b", txt, re.IGNORECASE)
                if m_st_e:
                    sk = m_st_e.group(1).lower()
                    sv = m_st_e.group(2).strip().upper() == "ĐÚNG"
                    for st in cur_q.get("statements", []):
                        if st["key"] == sk and st.get("answer") is None:
                            st["answer"] = sv
            elif cur_q["_type"] == "short_answer" and not cur_q.get("accepted_answers"):
                msa = re.search(r"(?:Đáp\s*án|Đáp\s*số|Kết\s*quả)\s*[:\s]*([-+]?\d+(?:[,\.]\d+)?)", txt, re.IGNORECASE)
                if msa:
                    vc = msa.group(1)
                    acc = [vc]
                    if "," in vc:
                        acc.append(vc.replace(",", "."))
                    elif "." in vc:
                        acc.append(vc.replace(".", ","))
                    cur_q["accepted_answers"] = acc
            continue

        # Xử lý từng dòng theo loại câu hỏi
        if cur_q["_type"] == "mcq":
            prefix, opts = _split_inline_options(txt)
            if opts:
                if prefix:
                    if not cur_q["options"]:
                        cur_q["question"] = (cur_q["question"] + "\n" + prefix).strip()
                    else:
                        cur_q["options"][-1] = (cur_q["options"][-1] + " " + prefix).strip()
                for lt, otxt, is_fixed in opts:
                    idx = LETTER_TO_IDX[lt]
                    while len(cur_q["options"]) <= idx:
                        cur_q["options"].append("")
                    cur_q["options"][idx] = otxt
                    if is_fixed and idx not in cur_q["fixed_options"]:
                        cur_q["fixed_options"].append(idx)
                if marked_letters and len(marked_letters) == 1 and cur_q["correct_index"] is None:
                    cur_q["correct_index"] = LETTER_TO_IDX.get(marked_letters[0])
            else:
                if cur_q["options"]:
                    cur_q["options"][-1] = (cur_q["options"][-1] + " " + txt).strip()
                else:
                    cur_q["question"] = (cur_q["question"] + "\n" + txt).strip()

        elif cur_q["_type"] == "true_false":
            m_st = RE_STMT_START.match(txt)
            if m_st:
                is_fixed_st = bool(m_st.group(1))
                key = m_st.group(2).lower()
                st_text = m_st.group(3).strip()
                # Kiểm tra xem cuối mệnh đề có ghi sẵn (Đúng)/(Sai) không
                st_ans = None
                m_tail = re.search(r"[\(\[]\s*(Đúng|Sai|Đ|S)\s*[\)\]]\s*$", st_text, re.IGNORECASE)
                if m_tail:
                    st_ans = m_tail.group(1).strip().upper() in ("ĐÚNG", "Đ")
                    st_text = st_text[: m_tail.start()].strip()
                cur_q["statements"].append({
                    "key": key,
                    "text": st_text,
                    "answer": st_ans,
                    "fixed": is_fixed_st,
                    "_underlined": bool(el.get("tf_underlined")),
                    "_red": bool(el.get("tf_red")),
                })
            else:
                if cur_q["statements"]:
                    cur_q["statements"][-1]["text"] = (cur_q["statements"][-1]["text"] + " " + txt).strip()
                else:
                    cur_q["question"] = (cur_q["question"] + "\n" + txt).strip()

        else:  # short_answer
            # Quy ước chuẩn: Trả lời ngắn ghi đáp án sau từ "A." (VD: "A. 12,5" hoặc "A. 4. Giải chi tiết: ...")
            m_sa_a = RE_SA_PREFIX_A.match(txt)
            if m_sa_a:
                raw_a = m_sa_a.group(1).strip()
                m_exp_in = re.search(
                    r"\b(Giải\s+chi\s+tiết|Hướng\s+dẫn\s+giải(?:\s+chi\s+tiết)?|Lời\s+giải(?:\s+chi\s+tiết)?)\s*[:\.\-–]?\s*(.*)$",
                    raw_a,
                    re.IGNORECASE,
                )
                ans_part = raw_a
                if m_exp_in:
                    ans_part = raw_a[: m_exp_in.start()].strip(" .;-–")
                    exp_in = (m_exp_in.group(2) or "").strip()
                    in_explanation = True
                    if exp_in:
                        cur_q["explanation"] = (cur_q["explanation"] + "\n" + exp_in).strip()
                v_clean = re.sub(r"\s*\([^\)]+\)", "", ans_part).strip().rstrip(".")
                if v_clean and not re.match(r"^[…\.\-_]+$", v_clean):
                    acc = [v_clean]
                    if "," in v_clean:
                        acc.append(v_clean.replace(",", "."))
                    elif "." in v_clean:
                        acc.append(v_clean.replace(".", ","))
                    cur_q["accepted_answers"] = acc
                continue
            # Bỏ dòng "Đáp số: ...." rỗng
            if re.match(r"^(?:Đáp\s*số|Đáp\s*án)\s*[:\-–]?\s*[…\.\-_]+$", txt, re.IGNORECASE):
                continue
            cur_q["question"] = (cur_q["question"] + "\n" + txt).strip()

    finalize_current()

    # Áp dụng bảng đáp án cuối đề (nếu tìm thấy)
    mcq_keys, tf_keys, sa_keys, ans_explanations = _parse_answer_key_section(ans_elements)

    for idx, q in enumerate(mcq_list, start=1):
        on = int(q.get("orig_num") or idx)
        if q.get("correct_index") is None:
            if on in mcq_keys:
                q["correct_index"] = mcq_keys[on]
            elif idx in mcq_keys:
                q["correct_index"] = mcq_keys[idx]
        if not q.get("explanation"):
            q["explanation"] = ans_explanations.get(("mcq", on)) or ans_explanations.get(("mcq", idx)) or ""

    # Quy tắc gạch chân hoặc tô đỏ cho Phần II (Đúng/Sai): ý đánh dấu = Đúng, không đánh dấu = Sai
    any_tf_underlined = any(
        st.get("_underlined") for q in tf_list for st in q.get("statements", [])
    )
    any_tf_red = any(
        st.get("_red") for q in tf_list for st in q.get("statements", [])
    )
    tf_mark_key = "_underlined" if any_tf_underlined else ("_red" if any_tf_red else "")

    for idx, q in enumerate(tf_list, start=1):
        on = int(q.get("orig_num") or idx)
        has_mark_here = bool(tf_mark_key) and any(st.get(tf_mark_key) for st in q.get("statements", []))
        vals = tf_keys.get(on) or tf_keys.get(idx)
        if has_mark_here:
            for st in q.get("statements", []):
                if st.get("answer") is None:
                    st["answer"] = bool(st.get(tf_mark_key))
        elif vals:
            for si, st in enumerate(q.get("statements", [])):
                if st.get("answer") is None and si < len(vals) and vals[si] is not None:
                    st["answer"] = vals[si]
        elif tf_mark_key:
            for st in q.get("statements", []):
                if st.get("answer") is None:
                    st["answer"] = False
        # Dọn cờ tạm trước khi trả JSON
        for st in q.get("statements", []):
            st.pop("_underlined", None)
            st.pop("_red", None)
        if not q.get("explanation"):
            q["explanation"] = ans_explanations.get(("true_false", on)) or ans_explanations.get(("true_false", idx)) or ""

    for idx, q in enumerate(sa_list, start=1):
        on = int(q.get("orig_num") or idx)
        if not q.get("accepted_answers"):
            acc = sa_keys.get(on) or sa_keys.get(idx)
            if acc:
                q["accepted_answers"] = acc
        if not q.get("explanation"):
            q["explanation"] = ans_explanations.get(("short_answer", on)) or ans_explanations.get(("short_answer", idx)) or ""

    total_q = len(mcq_list) + len(tf_list) + len(sa_list)
    if total_q == 0:
        warnings.append("Chưa nhận diện tự động được câu hỏi nào — Thầy/Cô có thể thêm câu hỏi trực tiếp trong trình biên tập.")

    mcq_keyed = sum(1 for q in mcq_list if q.get("correct_index") is not None)
    tf_keyed = sum(
        1 for q in tf_list
        if q.get("statements") and all(st.get("answer") is not None for st in q["statements"])
    )
    sa_keyed = sum(1 for q in sa_list if q.get("accepted_answers"))
    total_imgs = sum(len(q.get("images", [])) for q in (mcq_list + tf_list + sa_list))
    max_score = round(len(mcq_list) * 0.25 + len(tf_list) * 1.0 + len(sa_list) * 0.25, 2)

    if total_q > 0 and (mcq_keyed + tf_keyed + sa_keyed) < total_q:
        warnings.append(
            f"Có {total_q - (mcq_keyed + tf_keyed + sa_keyed)} câu chưa tự nhận diện được đáp án — vui lòng chọn/nhập bổ sung ngay tại khung xem trước bên dưới."
        )

    content_obj = {
        "mcq": mcq_list,
        "true_false": tf_list,
        "short_answer": sa_list,
    }
    # Nhận diện tự động 2 dạng đề chuẩn:
    #   - Dạng 1: Đề TN gồm 3 phần chuẩn 2025 (có Phần II Đúng/Sai hoặc Phần III Trả lời ngắn)
    #   - Dạng 2: Đề TN gồm 1 phần chỉ có câu trắc nghiệm 4 đáp án (VD: 40 câu)
    if len(tf_list) > 0 or len(sa_list) > 0:
        exam_format = "format_2025_3parts"
        exam_format_label = "Dạng 1 · Đề TN 3 phần chuẩn 2025"
    else:
        exam_format = "format_1part_mcq"
        exam_format_label = f"Dạng 2 · Đề TN 1 phần ({len(mcq_list)} câu 4 đáp án)"

    # Tổng hợp danh sách nhóm thẻ <g0>..<#g3> đã nhận diện
    grp_summary_map: Dict[str, Dict[str, Any]] = {}
    for p_name, q_arr in (("Phần I", mcq_list), ("Phần II", tf_list), ("Phần III", sa_list)):
        for q in q_arr:
            gid = f"{p_name}:{q.get('group_id', 'grp-1')}"
            if gid not in grp_summary_map:
                grp_summary_map[gid] = {
                    "part": p_name,
                    "tag": q.get("group_tag") or "<g3>",
                    "mode": q.get("shuffle_mode") or "g3",
                    "fixed": bool(q.get("group_fixed")),
                    "count": 0,
                }
            grp_summary_map[gid]["count"] += 1
    groups_summary = list(grp_summary_map.values())
    fixed_options_count = sum(len(q.get("fixed_options") or []) for q in mcq_list)

    try:
        from content_standardizer import standardize_exam_content
        spelling_report = standardize_exam_content(content_obj)
    except Exception:
        spelling_report = {"auto_fixed_count": 0, "fixes_examples": [], "suspect_words": []}

    return {
        "draft": {
            "order_number": next_order_number,
            "header_label": "PHÒNG LUYỆN TẬP",
            "title": f"Đề số {next_order_number}",
            "subtitle": "",
            "duration_minutes": 45,
            "source_filename": filename or "",
            "content": content_obj,
        },
        "stats": {
            "exam_format": exam_format,
            "exam_format_label": exam_format_label,
            "total_questions": total_q,
            "mcq_count": len(mcq_list),
            "tf_count": len(tf_list),
            "sa_count": len(sa_list),
            "mcq_keyed": mcq_keyed,
            "tf_keyed": tf_keyed,
            "sa_keyed": sa_keyed,
            "images_count": total_imgs,
            "max_score": max_score,
            "spelling_auto_fixed": spelling_report.get("auto_fixed_count", 0),
            "groups_summary": groups_summary,
            "fixed_options_count": fixed_options_count,
        },
        "spelling_report": spelling_report,
        "warnings": warnings,
    }


def compute_exam_max_score(content: Dict[str, Any]) -> Tuple[int, float]:
    mcq = content.get("mcq") or []
    tf = content.get("true_false") or []
    sa = content.get("short_answer") or []
    total_q = len(mcq) + len(tf) + len(sa)
    max_score = round(len(mcq) * 0.25 + len(tf) * 1.0 + len(sa) * 0.25, 2)
    return total_q, max_score


def normalize_sa_answer(val: Any) -> str:
    s = str(val or "").strip().lower()
    s = s.replace(",", ".")
    s = re.sub(r"\s+", "", s)
    return s


def grade_mock_exam_submission(content: Dict[str, Any], answers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chấm điểm chính thức theo thang điểm Bộ GD&ĐT (GDPT 2018):
      - Phần I (MCQ): 0,25 điểm / câu đúng
      - Phần II (Đúng/Sai): 1 ý đúng = 0,1đ; 2 ý = 0,25đ; 3 ý = 0,5đ; 4 ý = 1,0đ
      - Phần III (Trả lời ngắn): 0,25 điểm / câu đúng
    """
    ans_mcq = (answers or {}).get("mcq") or {}
    ans_tf = (answers or {}).get("true_false") or {}
    ans_sa = (answers or {}).get("short_answer") or {}

    tf_scale = {0: 0.0, 1: 0.1, 2: 0.25, 3: 0.5, 4: 1.0}

    p1_score = 0.0
    p1_max = 0.0
    p1_correct = 0
    mcq_results = []
    for q in content.get("mcq") or []:
        qid = q.get("id")
        corr = q.get("correct_index")
        user_pick = ans_mcq.get(qid)
        if user_pick is not None and str(user_pick) != "":
            try:
                user_pick = int(user_pick)
            except Exception:
                user_pick = None
        else:
            user_pick = None
        p1_max += 0.25
        is_right = corr is not None and user_pick is not None and int(user_pick) == int(corr)
        if is_right:
            p1_score += 0.25
            p1_correct += 1
        mcq_results.append({
            "id": qid,
            "user_answer": user_pick,
            "correct_index": corr,
            "is_correct": is_right,
            "points": 0.25 if is_right else 0.0,
            "explanation": q.get("explanation") or "",
        })

    p2_score = 0.0
    p2_max = 0.0
    p2_correct_full = 0
    tf_results = []
    for q in content.get("true_false") or []:
        qid = q.get("id")
        stmts = q.get("statements") or []
        p2_max += 1.0
        right_stmts = 0
        stmt_res = []
        for st in stmts:
            sk = st.get("key")
            uval = ans_tf.get(f"{qid}:{sk}")
            if isinstance(uval, str):
                uval = True if uval.lower() in ("true", "1", "đ", "đúng") else (False if uval.lower() in ("false", "0", "s", "sai") else None)
            cval = st.get("answer")
            ok = cval is not None and uval is not None and bool(uval) == bool(cval)
            if ok:
                right_stmts += 1
            stmt_res.append({
                "key": sk,
                "user_answer": uval,
                "correct_answer": cval,
                "is_correct": ok,
            })
        pts = tf_scale.get(min(4, right_stmts), 0.0)
        p2_score += pts
        if right_stmts == len(stmts) and len(stmts) > 0:
            p2_correct_full += 1
        tf_results.append({
            "id": qid,
            "right_statements": right_stmts,
            "total_statements": len(stmts),
            "points": pts,
            "statements": stmt_res,
            "explanation": q.get("explanation") or "",
        })

    p3_score = 0.0
    p3_max = 0.0
    p3_correct = 0
    sa_results = []
    for q in content.get("short_answer") or []:
        qid = q.get("id")
        u_raw = str(ans_sa.get(qid) or "").strip()
        u_norm = normalize_sa_answer(u_raw)
        acc = [str(x).strip() for x in (q.get("accepted_answers") or []) if str(x).strip()]
        acc_norm = [normalize_sa_answer(x) for x in acc]
        p3_max += 0.25
        is_right = bool(u_norm) and bool(acc_norm) and (u_norm in acc_norm)
        if is_right:
            p3_score += 0.25
            p3_correct += 1
        sa_results.append({
            "id": qid,
            "user_answer": u_raw,
            "accepted_answers": acc,
            "is_correct": is_right,
            "points": 0.25 if is_right else 0.0,
            "explanation": q.get("explanation") or "",
        })

    total_score = round(p1_score + p2_score + p3_score, 2)
    max_score = round(p1_max + p2_max + p3_max, 2)
    total_q = len(mcq_results) + len(tf_results) + len(sa_results)
    correct_count = p1_correct + p2_correct_full + p3_correct

    return {
        "score": total_score,
        "max_score": max_score,
        "part1_score": round(p1_score, 2),
        "part1_max": round(p1_max, 2),
        "part1_correct": p1_correct,
        "part2_score": round(p2_score, 2),
        "part2_max": round(p2_max, 2),
        "part2_correct_full": p2_correct_full,
        "part3_score": round(p3_score, 2),
        "part3_max": round(p3_max, 2),
        "part3_correct": p3_correct,
        "correct_count": correct_count,
        "total_questions": total_q,
        "details": {
            "mcq": mcq_results,
            "true_false": tf_results,
            "short_answer": sa_results,
        },
    }
