"""
Bộ trích xuất nội dung chuẩn xác 100% từ file Word (.docx), PDF (.pdf), TXT (.txt)
Hỗ trợ đầy đủ:
- Đọc theo đúng thứ tự thân tài liệu (Paragraph + Table xen kẽ)
- Giải mã công thức toán học Word OMML (<m:oMath>: phân số AB/ab, lũy thừa, chỉ số dưới, căn bậc 2)
- Trích xuất toàn bộ hình ảnh nhúng (.docx) gắn đúng vào từng bài Lý thuyết, Hệ thống kiến thức và từng câu hỏi
- Trích xuất trọn vẹn từng Bài:
    1. Lý thuyết (blocks theo đúng trình tự văn bản + hình ảnh + bảng)
    2. Hệ thống kiến thức (đúng theo mục 'HỆ THỐNG KIẾN THỨC' + sơ đồ tư duy + bảng + flashcards)
    3. Hệ thống ôn tập 3 phần (3.1 Trắc nghiệm 4 đáp án, 3.2 Đúng/Sai 4 ý, 3.3 Trả lời ngắn)
    4. Video tương tác thuyết minh tiếng Việt tự sinh bám sát từng Bài
"""
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional, Tuple

try:
    import docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError:
    docx = None
    qn = None
    Table = None
    Paragraph = Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.environ.get("UPLOADS_DIR") or os.path.join(BASE_DIR, "static", "uploads")

# Bản đồ mô phỏng tương tác bổ trợ riêng cho Chủ đề 1
TOPIC1_DIAGRAMS = ["dna-replication", "codon-translator", "operon-lac", "mutation-lab"]


def _clean(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def _omml_to_text(node) -> str:
    """Chuyển đổi cây XML công thức Word OMML (<m:oMath>) sang chuỗi dễ đọc, bảo toàn phân số & mũ."""
    tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag

    if tag == "t":
        return node.text or ""

    if tag == "f":  # Fraction: num / den
        num = ""
        den = ""
        for ch in node:
            ctag = ch.tag.split("}")[-1]
            if ctag == "num":
                num = _omml_to_text(ch).strip()
            elif ctag == "den":
                den = _omml_to_text(ch).strip()
        if not num and not den:
            return ""
        if len(num) <= 4 and len(den) <= 4 and " " not in num and " " not in den:
            return f"{num}/{den}"
        return f"({num})/({den})"

    if tag == "sSup":  # Superscript
        base, sup = "", ""
        for ch in node:
            ctag = ch.tag.split("}")[-1]
            if ctag == "e":
                base = _omml_to_text(ch)
            elif ctag == "sup":
                sup = _omml_to_text(ch)
        return f"{base}^{sup}" if sup else base

    if tag == "sSub":  # Subscript
        base, sub = "", ""
        for ch in node:
            ctag = ch.tag.split("}")[-1]
            if ctag == "e":
                base = _omml_to_text(ch)
            elif ctag == "sub":
                sub = _omml_to_text(ch)
        return f"{base}_{sub}" if sub else base

    if tag == "sSubSup":
        base, sub, sup = "", "", ""
        for ch in node:
            ctag = ch.tag.split("}")[-1]
            if ctag == "e":
                base = _omml_to_text(ch)
            elif ctag == "sub":
                sub = _omml_to_text(ch)
            elif ctag == "sup":
                sup = _omml_to_text(ch)
        return f"{base}_{sub}^{sup}"

    if tag == "rad":  # Square root
        deg, inner = "", ""
        for ch in node:
            ctag = ch.tag.split("}")[-1]
            if ctag == "deg":
                deg = _omml_to_text(ch).strip()
            elif ctag == "e":
                inner = _omml_to_text(ch).strip()
        return f"√({inner})" if not deg else f"{deg}√({inner})"

    return "".join(_omml_to_text(ch) for ch in node)


def _extract_paragraph_text_with_math(p_elem) -> str:
    """Đọc đầy đủ văn bản trong <w:p> bao gồm cả công thức OMML (<m:oMath>) đúng vị trí."""
    parts = []
    for child in p_elem:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "r":
            for rch in child:
                rtag = rch.tag.split("}")[-1] if "}" in rch.tag else rch.tag
                if rtag == "t":
                    parts.append(rch.text or "")
                elif rtag == "tab":
                    parts.append("\t")
                elif rtag == "br":
                    parts.append("\n")
        elif tag in ("oMath", "oMathPara"):
            parts.append(_omml_to_text(child))
        elif tag == "hyperlink":
            parts.append(_extract_paragraph_text_with_math(child))
        elif tag == "smartTag":
            parts.append(_extract_paragraph_text_with_math(child))
    return "".join(parts)


def _extract_marked_letters_from_paragraph(p: Paragraph) -> List[str]:
    """
    Tìm các chữ cái đáp án (A/B/C/D) được đánh dấu gạch chân hoặc tô màu đỏ trong đoạn Word.
    Rất phổ biến trong đề trắc nghiệm Việt Nam (VD: A. ... [B. gạch chân] ...).
    """
    marked = []
    for run in p.runs:
        rt = (run.text or "").strip()
        if not rt:
            continue
        is_red = False
        try:
            if run.font and run.font.color and run.font.color.rgb:
                rgb = str(run.font.color.rgb).upper()
                if len(rgb) == 6:
                    r, g, b = int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)
                    if r >= 150 and g <= 80 and b <= 80:
                        is_red = True
        except Exception:
            pass
        is_hl = bool(run.font and run.font.highlight_color)
        if run.underline or is_red or is_hl:
            m = re.match(r"^([A-D])\s*[\.\)]?$", rt)
            if m:
                marked.append(m.group(1))
            else:
                m2 = re.match(r"^([A-D])[\.\)]\s+", rt)
                if m2:
                    marked.append(m2.group(1))
                else:
                    marked.append("*")
    return marked


CROP_BIN = os.path.join(BASE_DIR, "tools", "crop_img_bin")


def _extract_images_from_elem(elem, image_resolver) -> List[str]:
    """
    Trích xuất ảnh kèm tọa độ cắt <a:srcRect l t r b> của Word để mỗi hình ảnh
    đều được cắt đúng khung câu hỏi (không dính chữ thừa của câu khác).
    Tránh lặp ảnh nằm trong <mc:Fallback>.
    """
    imgs = []
    # Tìm các blipFill trực tiếp hoặc nằm trong drawing (bỏ qua mc:Fallback)
    for bf in elem.xpath(".//*[local-name()='blipFill']"):
        # Bỏ qua nếu nằm bên trong mc:Fallback
        anc = bf.getparent()
        in_fallback = False
        while anc is not None:
            if anc.tag.endswith("}Fallback"):
                in_fallback = True
                break
            anc = anc.getparent()
        if in_fallback:
            continue

        blips = bf.xpath("./*[local-name()='blip']")
        if not blips:
            continue
        rid = blips[0].get(qn("r:embed"))
        if not rid:
            continue

        l = t = r = b = 0
        srects = bf.xpath("./*[local-name()='srcRect']")
        if srects:
            sr = srects[0]
            try:
                l = int(sr.get("l") or 0)
                t = int(sr.get("t") or 0)
                r = int(sr.get("r") or 0)
                b = int(sr.get("b") or 0)
            except Exception:
                l = t = r = b = 0

        # Kiểm tra góc xoay <a:xfrm rot="..."> trên thẻ cha <pic:pic>
        rot_deg = 0
        pic_parent = bf.getparent()
        if pic_parent is not None:
            xfrms = pic_parent.xpath(".//*[local-name()='xfrm']")
            if xfrms and xfrms[0].get("rot"):
                try:
                    raw_rot = int(xfrms[0].get("rot"))
                    rot_deg = int(round(raw_rot / 60000.0)) % 360
                except Exception:
                    rot_deg = 0

        url = image_resolver(rid, l, t, r, b, rot_deg)
        if url and url not in imgs:
            imgs.append(url)

    return imgs


def _local_tag(el) -> str:
    tag = el.tag or ""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _get_w_attr(el, name: str, default: str = "") -> str:
    w_key = f"{{http://schemas.openxmlformats.org/wordprocessingml/2006/main}}{name}"
    if w_key in el.attrib:
        return el.attrib[w_key]
    if name in el.attrib:
        return el.attrib[name]
    for k, v in el.attrib.items():
        if k.endswith(f"}}{name}"):
            return v
    return default


def _extract_images_from_elem_stdlib(elem, image_resolver, cur_rot: int = 0) -> List[str]:
    imgs = []

    def walk(node, rot_deg: int):
        lt = _local_tag(node)
        if lt == "Fallback":
            return
        if lt == "pic":
            for sp in node:
                if _local_tag(sp) == "spPr":
                    for x in sp:
                        if _local_tag(x) == "xfrm":
                            raw_rot = x.attrib.get("rot")
                            if raw_rot:
                                try:
                                    rot_deg = int(round(int(raw_rot) / 60000.0)) % 360
                                except Exception:
                                    pass
        if lt == "blipFill":
            rid = ""
            l = t = r = b = 0
            for ch in node:
                clt = _local_tag(ch)
                if clt == "blip":
                    for ak, av in ch.attrib.items():
                        if ak == "embed" or ak.endswith("}embed"):
                            rid = av
                            break
                elif clt == "srcRect":
                    try:
                        l = int(ch.attrib.get("l") or 0)
                        t = int(ch.attrib.get("t") or 0)
                        r = int(ch.attrib.get("r") or 0)
                        b = int(ch.attrib.get("b") or 0)
                    except Exception:
                        l = t = r = b = 0
            if rid:
                url = image_resolver(rid, l, t, r, b, rot_deg)
                if url and url not in imgs:
                    imgs.append(url)
            return
        for ch in node:
            walk(ch, rot_deg)

    walk(elem, cur_rot)
    return imgs


def _analyze_paragraph_stdlib(p_elem, style_map: Dict[str, str]):
    style_id = ""
    has_numpr = False
    non_empty_bold = []
    marked = []

    for child in p_elem:
        ct = _local_tag(child)
        if ct == "pPr":
            for pchild in child:
                pct = _local_tag(pchild)
                if pct == "pStyle":
                    style_id = _get_w_attr(pchild, "val", "")
                elif pct == "numPr":
                    has_numpr = True
        elif ct in ("r", "hyperlink", "smartTag"):
            runs = [child] if ct == "r" else [rc for rc in child if _local_tag(rc) == "r"]
            for r_el in runs:
                r_texts = []
                r_bold = False
                r_under = False
                r_red = False
                r_hl = False
                for rch in r_el:
                    rt = _local_tag(rch)
                    if rt == "t" and rch.text:
                        r_texts.append(rch.text)
                    elif rt == "rPr":
                        for rp in rch:
                            rpt = _local_tag(rp)
                            if rpt == "b":
                                val = _get_w_attr(rp, "val", "1").lower()
                                r_bold = val not in ("0", "false", "off")
                            elif rpt == "u":
                                val = _get_w_attr(rp, "val", "single").lower()
                                r_under = val not in ("none", "0", "false", "")
                            elif rpt == "color":
                                rgb = _get_w_attr(rp, "val", "").upper()
                                if len(rgb) == 6:
                                    try:
                                        rr, gg, bb = int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)
                                        if rr >= 150 and gg <= 80 and bb <= 80:
                                            r_red = True
                                    except Exception:
                                        pass
                            elif rpt == "highlight":
                                val = _get_w_attr(rp, "val", "").lower()
                                r_hl = bool(val and val != "none")
                rt_str = "".join(r_texts).strip()
                if not rt_str:
                    continue
                non_empty_bold.append(r_bold)
                if r_under or r_red or r_hl:
                    m = re.match(r"^([A-D])\s*[\.\)]?$", rt_str)
                    if m:
                        marked.append(m.group(1))
                    else:
                        m2 = re.match(r"^([A-D])[\.\)]\s+", rt_str)
                        if m2:
                            marked.append(m2.group(1))
                        else:
                            marked.append("*")

    style_name = style_map.get(style_id, style_id or "")
    heading_level = 0
    hm = re.match(r"Heading\s*(\d+)", style_name, re.IGNORECASE) or re.match(
        r"Heading\s*(\d+)", style_id or "", re.IGNORECASE
    )
    if hm:
        heading_level = int(hm.group(1))
    elif style_name.lower().startswith("title") or (style_id or "").lower().startswith("title"):
        heading_level = 1

    is_all_bold = bool(non_empty_bold) and all(non_empty_bold)
    return style_name, heading_level, is_all_bold, has_numpr, marked


def _extract_body_items_from_docx_stdlib(file_bytes: bytes, topic_id: str) -> Dict:
    """Trình đọc .docx thuần Python stdlib (zipfile + ElementTree), không phụ thuộc python-docx/lxml."""
    topic_upload_dir = os.path.join(UPLOADS_DIR, topic_id)
    os.makedirs(topic_upload_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="bio12_crop_")

    rid_raw_info = {}
    style_map = {}
    items = []
    tables_count = 0
    crop_cache = {}
    crop_jobs = []
    extracted_images = []

    def resolve_image(rid: str, l: int, t: int, r: int, b: int, rot: int = 0) -> Optional[str]:
        if rid not in rid_raw_info:
            return None
        key = (rid, l, t, r, b, rot)
        if key in crop_cache:
            return crop_cache[key]
        raw_path, ext, blob = rid_raw_info[rid]
        sig = hashlib.md5(f"{topic_id}:{rid}:{l}:{t}:{r}:{b}:{rot}".encode()).hexdigest()[:10]
        needs_transform = any(v > 0 for v in (l, t, r, b)) or (rot % 360 != 0)
        out_ext = ".png" if ext == ".png" else ".jpg"
        fname = f"img_{sig}{out_ext}"
        dst_path = os.path.join(topic_upload_dir, fname)
        url = f"/uploads/{topic_id}/{fname}"
        if needs_transform and sys.platform == "darwin" and os.path.exists(CROP_BIN):
            crop_jobs.append({"src": raw_path, "dst": dst_path, "l": l, "t": t, "r": r, "b": b, "rot": rot})
        else:
            with open(dst_path, "wb") as f:
                f.write(blob)
        crop_cache[key] = url
        extracted_images.append(url)
        return url

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            names = set(zf.namelist())

            if "word/styles.xml" in names:
                try:
                    sroot = ET.fromstring(zf.read("word/styles.xml"))
                    for st_el in sroot:
                        if _local_tag(st_el) == "style":
                            sid = _get_w_attr(st_el, "styleId", "")
                            sname = ""
                            for ch in st_el:
                                if _local_tag(ch) == "name":
                                    sname = _get_w_attr(ch, "val", "")
                                    break
                            if sid:
                                style_map[sid] = sname or sid
                except Exception:
                    pass

            if "word/_rels/document.xml.rels" in names:
                try:
                    rroot = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
                    for rel_el in rroot:
                        if _local_tag(rel_el) != "Relationship":
                            continue
                        rid = rel_el.attrib.get("Id", "")
                        rtype = rel_el.attrib.get("Type", "")
                        target = rel_el.attrib.get("Target", "")
                        if not rid or not target:
                            continue
                        if "image" not in rtype.lower() and not re.search(
                            r"\.(png|jpe?g|gif|webp|bmp|emf|wmf)$", target, re.IGNORECASE
                        ):
                            continue
                        clean_target = target.lstrip("/")
                        if not clean_target.startswith("word/"):
                            clean_target = posixpath.normpath(posixpath.join("word", clean_target))
                        if clean_target not in names:
                            continue
                        blob = zf.read(clean_target)
                        if len(blob) < 100:
                            continue
                        ext = os.path.splitext(clean_target)[1].lower() or ".png"
                        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                            ext = ".png"
                        raw_path = os.path.join(tmp_dir, f"{rid}{ext}")
                        with open(raw_path, "wb") as f:
                            f.write(blob)
                        rid_raw_info[rid] = (raw_path, ext, blob)
                except Exception:
                    pass

            if "word/document.xml" not in names:
                raise ValueError("File Word (.docx) không hợp lệ: thiếu word/document.xml.")

            doc_root = ET.fromstring(zf.read("word/document.xml"))
            body_el = None
            for ch in doc_root:
                if _local_tag(ch) == "body":
                    body_el = ch
                    break
            if body_el is None:
                body_el = doc_root

            for child in body_el:
                tag = _local_tag(child)
                if tag == "p":
                    raw_text = _extract_paragraph_text_with_math(child)
                    clean_lines = [_clean(x) for x in raw_text.splitlines()]
                    text = "\n".join(x for x in clean_lines if x).strip()
                    imgs = _extract_images_from_elem_stdlib(child, resolve_image)
                    if not text and not imgs:
                        continue
                    style_name, heading_level, is_all_bold, has_numpr, marked_letters = _analyze_paragraph_stdlib(
                        child, style_map
                    )
                    items.append(
                        {
                            "type": "p",
                            "text": text,
                            "raw_text": raw_text,
                            "style": style_name,
                            "heading_level": heading_level,
                            "is_bold": is_all_bold,
                            "has_numpr": has_numpr,
                            "marked_letters": marked_letters,
                            "images": imgs,
                        }
                    )
                elif tag == "tbl":
                    rows_data = []
                    tbl_images = []
                    for tr in child:
                        if _local_tag(tr) != "tr":
                            continue
                        row_cells = []
                        for tc in tr:
                            if _local_tag(tc) != "tc":
                                continue
                            cell_parts = []
                            for cp in tc:
                                if _local_tag(cp) != "p":
                                    continue
                                ct = _clean(_extract_paragraph_text_with_math(cp))
                                if ct:
                                    cell_parts.append(ct)
                                for im in _extract_images_from_elem_stdlib(cp, resolve_image):
                                    if im not in tbl_images:
                                        tbl_images.append(im)
                            row_cells.append(" ".join(cell_parts).strip())
                        if any(row_cells) or tbl_images:
                            rows_data.append(row_cells)
                    if rows_data or tbl_images:
                        tables_count += 1
                        items.append(
                            {
                                "type": "table",
                                "rows": rows_data,
                                "images": tbl_images,
                            }
                        )

        if crop_jobs and sys.platform == "darwin" and os.path.exists(CROP_BIN):
            jobs_file = os.path.join(tmp_dir, "jobs.json")
            with open(jobs_file, "w", encoding="utf-8") as jf:
                json.dump(crop_jobs, jf)
            subprocess.run([CROP_BIN, jobs_file], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return {
        "items": items,
        "images": extracted_images,
        "tables_count": tables_count,
    }


def extract_body_items_from_docx(file_bytes: bytes, topic_id: str) -> Dict:
    """Đọc toàn bộ file Word theo đúng thứ tự tự nhiên: paragraph + table + ảnh (đã cắt đúng srcRect) + công thức."""
    if docx is None:
        return _extract_body_items_from_docx_stdlib(file_bytes, topic_id)
    try:
        return _extract_body_items_from_docx_python_docx(file_bytes, topic_id)
    except Exception:
        return _extract_body_items_from_docx_stdlib(file_bytes, topic_id)


def _extract_body_items_from_docx_python_docx(file_bytes: bytes, topic_id: str) -> Dict:

    doc = docx.Document(io.BytesIO(file_bytes))
    topic_upload_dir = os.path.join(UPLOADS_DIR, topic_id)
    os.makedirs(topic_upload_dir, exist_ok=True)

    # Lưu tạm ảnh thô theo rId để cắt chính xác theo từng srcRect
    tmp_dir = tempfile.mkdtemp(prefix="bio12_crop_")
    rid_raw_info = {}
    for rel_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            try:
                blob = rel.target_part.blob
                if len(blob) < 100:
                    continue
                ext = os.path.splitext(rel.target_ref)[1].lower() or ".png"
                if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                    ext = ".png"
                raw_path = os.path.join(tmp_dir, f"{rel_id}{ext}")
                with open(raw_path, "wb") as f:
                    f.write(blob)
                rid_raw_info[rel_id] = (raw_path, ext, blob)
            except Exception:
                continue

    crop_cache = {}  # (rid, l, t, r, b) -> url
    crop_jobs = []
    extracted_images = []

    def resolve_image(rid: str, l: int, t: int, r: int, b: int, rot: int = 0) -> Optional[str]:
        if rid not in rid_raw_info:
            return None
        key = (rid, l, t, r, b, rot)
        if key in crop_cache:
            return crop_cache[key]

        raw_path, ext, blob = rid_raw_info[rid]
        sig = hashlib.md5(f"{topic_id}:{rid}:{l}:{t}:{r}:{b}:{rot}".encode()).hexdigest()[:10]
        needs_transform = any(v > 0 for v in (l, t, r, b)) or (rot % 360 != 0)
        out_ext = ".png" if ext == ".png" else ".jpg"
        fname = f"img_{sig}{out_ext}"
        dst_path = os.path.join(topic_upload_dir, fname)
        url = f"/uploads/{topic_id}/{fname}"

        if needs_transform and sys.platform == "darwin" and os.path.exists(CROP_BIN):
            crop_jobs.append({"src": raw_path, "dst": dst_path, "l": l, "t": t, "r": r, "b": b, "rot": rot})
        else:
            with open(dst_path, "wb") as f:
                f.write(blob)

        crop_cache[key] = url
        extracted_images.append(url)
        return url

    items = []
    tables_count = 0

    for child in doc.element.body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            p = Paragraph(child, doc)
            raw_text = _extract_paragraph_text_with_math(child)
            clean_lines = [_clean(x) for x in raw_text.splitlines()]
            text = "\n".join(x for x in clean_lines if x).strip()
            imgs = _extract_images_from_elem(child, resolve_image)
            if not text and not imgs:
                continue

            style_name = (p.style.name if p.style else "") or ""
            heading_level = 0
            hm = re.match(r"Heading\s*(\d+)", style_name, re.IGNORECASE)
            if hm:
                heading_level = int(hm.group(1))
            elif style_name.lower().startswith("title"):
                heading_level = 1

            is_all_bold = False
            non_empty_runs = [r for r in p.runs if (r.text or "").strip()]
            if non_empty_runs and all(r.bold for r in non_empty_runs):
                is_all_bold = True

            marked_letters = _extract_marked_letters_from_paragraph(p)
            has_numpr = bool(child.xpath(".//*[local-name()='numPr']"))

            items.append(
                {
                    "type": "p",
                    "text": text,
                    "raw_text": raw_text,
                    "style": style_name,
                    "heading_level": heading_level,
                    "is_bold": is_all_bold,
                    "has_numpr": has_numpr,
                    "marked_letters": marked_letters,
                    "images": imgs,
                }
            )

        elif tag == "tbl":
            tbl = Table(child, doc)
            rows_data = []
            tbl_images = []
            for row in tbl.rows:
                row_cells = []
                prev_tc = None
                for cell in row.cells:
                    if cell._tc is prev_tc:
                        continue
                    prev_tc = cell._tc
                    cell_parts = []
                    for cp in cell._tc.xpath("./*[local-name()='p']"):
                        ct = _clean(_extract_paragraph_text_with_math(cp))
                        if ct:
                            cell_parts.append(ct)
                        cimgs = _extract_images_from_elem(cp, resolve_image)
                        for im in cimgs:
                            if im not in tbl_images:
                                tbl_images.append(im)
                    row_cells.append(" ".join(cell_parts).strip())
                if any(row_cells) or tbl_images:
                    rows_data.append(row_cells)

            if rows_data or tbl_images:
                tables_count += 1
                items.append(
                    {
                        "type": "table",
                        "rows": rows_data,
                        "images": tbl_images,
                    }
                )

    # Thực thi cắt hàng loạt tất cả các ảnh có srcRect trong 1 lần gọi CoreGraphics
    if crop_jobs and sys.platform == "darwin" and os.path.exists(CROP_BIN):
        jobs_file = os.path.join(tmp_dir, "jobs.json")
        with open(jobs_file, "w", encoding="utf-8") as jf:
            json.dump(crop_jobs, jf)
        subprocess.run([CROP_BIN, jobs_file], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Dọn thư mục tạm
    try:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    return {
        "items": items,
        "images": extracted_images,
        "tables_count": tables_count,
    }


def extract_body_items_from_pdf(file_bytes: bytes, topic_id: str = "chu-de-new") -> Dict:
    if PdfReader is None:
        raise RuntimeError("Thiếu thư viện pypdf trên máy chủ.")
    reader = PdfReader(io.BytesIO(file_bytes))
    topic_upload_dir = os.path.join(UPLOADS_DIR, topic_id)
    os.makedirs(topic_upload_dir, exist_ok=True)

    items = []
    extracted_images = []
    seen_hashes = set()

    for page_idx, page in enumerate(reader.pages):
        page_imgs = []
        try:
            for img_obj in getattr(page, "images", []) or []:
                img_bytes = getattr(img_obj, "data", None)
                if not img_bytes or len(img_bytes) < 512:
                    continue
                h = hashlib.sha1(img_bytes).hexdigest()[:10]
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                raw_name = getattr(img_obj, "name", "") or f"pdf_p{page_idx + 1}.png"
                ext = os.path.splitext(raw_name)[1].lower()
                if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                    ext = ".png"
                fname = f"img_{h}{ext}"
                dst = os.path.join(topic_upload_dir, fname)
                with open(dst, "wb") as f:
                    f.write(img_bytes)
                url = f"/uploads/{topic_id}/{fname}"
                page_imgs.append(url)
                extracted_images.append(url)
        except Exception:
            pass

        raw = page.extract_text() or ""
        lines = [ln for ln in (_clean(l) for l in raw.splitlines()) if ln]
        for li, txt in enumerate(lines):
            # Tự nhận diện dòng tiêu đề trên PDF (chữ in hoa hoặc bắt đầu bằng BÀI / CHỦ ĐỀ / 5.1.)
            is_upper_heading = len(txt) >= 6 and len(txt) <= 120 and txt == txt.upper() and any(ch.isalpha() for ch in txt)
            is_bold = bool(
                is_upper_heading
                or re.match(r"^(?:CHỦ\s*ĐỀ|BÀI\s*\d+|PHẦN\s+[I1-3ABC]|I+\.|[1-9]\.\d+\.)", txt, re.IGNORECASE)
            )
            items.append(
                {
                    "type": "p",
                    "text": txt,
                    "raw_text": txt,
                    "style": "Heading 1" if is_upper_heading else "Normal",
                    "heading_level": 1 if is_upper_heading else 0,
                    "is_bold": is_bold,
                    "marked_letters": [],
                    "images": page_imgs if (li == len(lines) - 1 and page_imgs) else [],
                }
            )
        if not lines and page_imgs:
            items.append(
                {
                    "type": "p",
                    "text": "",
                    "raw_text": "",
                    "style": "Normal",
                    "heading_level": 0,
                    "is_bold": False,
                    "marked_letters": [],
                    "images": page_imgs,
                }
            )
    return {"items": items, "images": extracted_images, "tables_count": 0}


def extract_body_items_from_txt(file_bytes: bytes) -> Dict:
    try:
        raw = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = file_bytes.decode("latin-1", errors="ignore")
    items = []
    for ln in raw.splitlines():
        txt = _clean(ln)
        if txt:
            items.append(
                {
                    "type": "p",
                    "text": txt,
                    "raw_text": txt,
                    "style": "Normal",
                    "heading_level": 0,
                    "is_bold": False,
                    "marked_letters": [],
                    "images": [],
                }
            )
    return {"items": items, "images": [], "tables_count": 0}


# ================== REGEX NHẬN DIỆN CẤU TRÚC TÀI LIỆU SINH HỌC 12 ==================

RE_TOPIC_TITLE = re.compile(r"^CHỦ\s*ĐỀ\s*\d+\s*[:\.\-]?\s*(.*)$", re.IGNORECASE)
RE_HTKT_MARKER = re.compile(r"^(?:PHẦN\s+)?HỆ\s*THỐNG\s*KIẾN\s*THỨC\b", re.IGNORECASE)
RE_MCQ_MARKER = re.compile(
    r"^(?:PHẦN\s*(?:I\b|1\b)\s*[\.\:\-]\s*.*TRẮC\s*NGHIỆM|CÂU\s*HỎI\s*TRẮC\s*NGHIỆM\s*NHIỀU|TRẮC\s*NGHIỆM\s*(?:4\s*ĐÁP\s*ÁN|NHIỀU))",
    re.IGNORECASE,
)
RE_TF_MARKER = re.compile(
    r"^(?:PHẦN\s*(?:II\b|2\b)\s*[\.\:\-]\s*.*ĐÚNG|CÂU\s*HỎI\s*TRẮC\s*NGHIỆM\s*ĐÚNG\s*[/\-]?\s*SAI|TRẮC\s*NGHIỆM\s*ĐÚNG\s*[/\-]?\s*SAI)",
    re.IGNORECASE,
)
RE_SA_MARKER = re.compile(
    r"^(?:PHẦN\s*(?:III\b|3\b)\s*[\.\:\-]\s*.*TRẢ\s*LỜI|CÂU\s*HỎI\s*TRẮC\s*NGHIỆM\s*TRẢ\s*LỜI\s*NGẮN|TRẮC\s*NGHIỆM\s*TRẢ\s*LỜI\s*NGẮN)",
    re.IGNORECASE,
)

# Nhận diện tiêu đề Bài học mới (phân biệt chữ HOA/thường để không nhầm đáp án A., B., C., D. hay tiểu mục)
RE_BAI_LESSON = re.compile(r"^(?:BÀI\s*\d+\s*[:\.\-]|CHỦ\s*ĐỀ\s*BÀI\s*TẬP\b)", re.IGNORECASE)
RE_UPPER_SECTION_LESSON = re.compile(r"^(?:[A-B]\.\s+[A-ZÀ-ỸĐ]|[1-9]\.\d+[\.:]?\s+[A-ZÀ-ỸĐ]{2,})")

RE_QUESTION_START = re.compile(r"^(?:Câu|Question)\s*([lI]?\d+)\s*[:\.\)]\s*(.*)$", re.IGNORECASE)
RE_OPT_LINE = re.compile(r"^([A-D])\s*[\.\)]\s*(.+)$")
RE_TF_STMT = re.compile(r"^[\.\…\s\-–•]*([a-dA-D])\s*[\.\)]\s+(.+)$")
RE_ANSWER_LINE = re.compile(r"^(?:Đáp\s*án|ĐA|Trả\s*lời|Kết\s*quả)\s*[:\.\-]?\s*(.*)$", re.IGNORECASE)
RE_EXPLAIN_LINE = re.compile(r"^(?:Giải\s*thích|Hướng\s*dẫn(?:\s*giải)?|Lời\s*giải|HD)\s*[:\-]\s*(.+)$", re.IGNORECASE)
RE_CAPTION = re.compile(r"^(?:Hình|Sơ\s*đồ|Bảng)\s*\d+", re.IGNORECASE)


def _is_all_upper_vietnamese(txt: str) -> bool:
    letters = [ch for ch in txt if ch.isalpha()]
    return len(letters) >= 8 and all(ch == ch.upper() for ch in letters)


def _is_new_lesson_header(item: Dict, current_mode: str, has_lessons: bool) -> bool:
    if item["type"] != "p":
        return False
    txt = item["text"]
    if not txt or len(txt) > 150:
        return False
    if RE_TOPIC_TITLE.match(txt):
        return False
    if RE_HTKT_MARKER.match(txt) or RE_MCQ_MARKER.match(txt) or RE_TF_MARKER.match(txt) or RE_SA_MARKER.match(txt):
        return False
    if RE_QUESTION_START.match(txt):
        return False

    # 1. Rõ ràng bắt đầu bằng "BÀI 1: ...", "BÀI 2: ..." hoặc "CHỦ ĐỀ BÀI TẬP..."
    if RE_BAI_LESSON.match(txt):
        return True

# 2. Phần chữ cái lớn viết HOA toàn bộ có dấu tiếng Việt như "A. HỌC THUYẾT DI TRUYỀN CỦA MENDEL",
    #    "B. MỞ RỘNG HỌC THUYẾT MENDEL", hoặc "4.1. DI TRUYỀN GIỚI TÍNH..."
    if RE_UPPER_SECTION_LESSON.match(txt) and _is_all_upper_vietnamese(txt):
        has_vn_diacritic = bool(re.search(r"[ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]", txt))
        has_inline_opt_b = bool(re.search(r"\sB\.\s", txt))
        if has_vn_diacritic and not has_inline_opt_b:
            return True

    # 3. Heading 1/2/3 viết HOA toàn bộ (như "NHIỄM SẮC THỂ...", "ĐỘT BIẾN NHIỄM SẮC THỂ", "MỐI QUAN HỆ...")
    if item["heading_level"] in (1, 2, 3) and _is_all_upper_vietnamese(txt):
        if current_mode in ("mcq", "true_false", "short_answer") or not has_lessons:
            if not txt.startswith("TÓM TẮT") and not txt.startswith("HƯỚNG DẪN"):
                return True

    return False


def _split_inline_options(raw_text: str) -> List[Tuple[str, str]]:
    """Tách trường hợp 2, 3 hoặc 4 đáp án A. ... B. ... C. ... D. ... nằm trên cùng 1 dòng (kể cả khi thiếu dấu cách sau dấu chấm, VD: A.1/16)."""
    matches = list(re.finditer(r"(?:^|[\t]| {2,})([A-D])\.\s*", raw_text))
    if len(matches) < 2:
        matches = list(re.finditer(r"(?:^|\s)([A-D])\.\s*", raw_text))
    if len(matches) < 2:
        return []
    # Lọc chỉ giữ chuỗi chữ cái tăng dần hợp lệ (A->B->C->D hoặc C->D)
    filtered = []
    seen = set()
    for m in matches:
        let = m.group(1)
        if let in seen:
            continue
        if filtered and ord(let) <= ord(filtered[-1].group(1)):
            continue
        seen.add(let)
        filtered.append(m)
    if len(filtered) < 2:
        return []
    out = []
    for i, m in enumerate(filtered):
        letter = m.group(1)
        start = m.end()
        end = filtered[i + 1].start() if i + 1 < len(filtered) else len(raw_text)
        out.append((letter, _clean(raw_text[start:end])))
    return out


def _is_blank_answer_placeholder(ans_text: str) -> bool:
    cleaned = re.sub(r"[\.\…\_\-\s]", "", ans_text or "")
    return len(cleaned) == 0


RE_HAS_VISUAL_CUE = re.compile(
    r"(hình\s*(?:bên|dưới|trên|sau|vẽ|nào|\d|\.)|trong\s*hình|trên\s*hình|quan\s*sát\s*hình|như\s*hình|sơ\s*đồ\s*(?:bên|dưới|sau|trên|nào|dưới)|bảng\s*(?:bên|dưới|sau)|đồ\s*thị|biểu\s*đồ|chú\s*thích|quá\s*trình\s*[A-D]\b|cấu\s*trúc\s*\(\d\))",
    re.IGNORECASE,
)
RE_EXPLICIT_FIG_REF = re.compile(
    r"(hình\s*(?:bên|dưới|trên|sau|vẽ|nào|\d|\.)|trong\s*hình|trên\s*hình|sơ\s*đồ\s*(?:bên|dưới|sau|trên|nào)|đồ\s*thị|biểu\s*đồ|quan\s*sát\s*hình|như\s*hình|bảng\s*(?:bên|dưới|sau))",
    re.IGNORECASE,
)


def _realign_question_images(questions: List[Dict]) -> List[Dict]:
    """
    Trong Word, hình neo (floating anchor) cho Câu X đôi khi được gắn ở cuối dòng đáp án của Câu X-1.
    - Nếu Câu X-1 không nhắc đến hình/sơ đồ/bảng nhưng có ảnh, còn Câu X nhắc rõ 'Hình bên...' mà thiếu ảnh -> chuyển sang Câu X.
    - Hoặc nếu Câu X-1 có >= 2 ảnh và Câu X nhắc rõ 'Hình bên...' mà thiếu ảnh -> chuyển ảnh cuối của Câu X-1 sang Câu X.
    """
    for i in range(len(questions) - 1):
        q_cur = questions[i]
        q_next = questions[i + 1]
        cur_imgs = q_cur.get("images") or []
        next_imgs = q_next.get("images") or []
        if not cur_imgs or next_imgs:
            continue
        cur_text = (q_cur.get("question") or q_cur.get("stem") or "")
        next_text = (q_next.get("question") or q_next.get("stem") or "")
        if RE_EXPLICIT_FIG_REF.search(next_text):
            cur_has_table_only = len(q_cur.get("tables") or []) >= 1 and not re.search(
                r"(hình\s*(?:bên|dưới|trên|sau|vẽ|nào)|sơ\s*đồ\s*(?:bên|dưới|sau|trên|nào)|đồ\s*thị|biểu\s*đồ)",
                cur_text,
                re.IGNORECASE,
            )
            if (not RE_HAS_VISUAL_CUE.search(cur_text)) or len(cur_imgs) >= 2 or cur_has_table_only:
                q_next["images"] = [cur_imgs.pop()]
                q_cur["images"] = cur_imgs
    return questions


def _parse_mcq_items(items: List[Dict], lesson_label: str, lesson_id: str, id_prefix: str) -> List[Dict]:
    questions = []
    cur = None
    pending_imgs = []

    def flush():
        nonlocal cur
        if not cur:
            return
        opts = cur["options"]
        if len(opts) >= 2:
            ordered_letters = [k for k in ("A", "B", "C", "D") if k in opts]
            ordered_vals = [opts[k] for k in ordered_letters]
            correct_idx = None
            if cur["answer_letter"] and cur["answer_letter"] in ordered_letters:
                correct_idx = ordered_letters.index(cur["answer_letter"])
            elif cur["marked_letter"] and cur["marked_letter"] in ordered_letters:
                correct_idx = ordered_letters.index(cur["marked_letter"])

            orig_num_str = str(cur["num"]).replace("l", "1").replace("I", "1")
            orig_num = int(orig_num_str) if orig_num_str.isdigit() else (len(questions) + 1)
            questions.append(
                {
                    "id": f"{id_prefix}-mcq-{len(questions) + 1}",
                    "orig_num": orig_num,
                    "lesson_id": lesson_id,
                    "lesson": lesson_label,
                    "level": cur["sub_heading"] or lesson_label,
                    "question": "\n".join(cur["stem_lines"]).strip(),
                    "images": cur["images"],
                    "tables": cur["tables"],
                    "options": ordered_vals,
                    "correct_index": correct_idx,
                    "answer_key_ready": correct_idx is not None,
                    "explanation": " ".join(cur["explain"]).strip(),
                }
            )
        cur = None

    current_sub_heading = ""
    for it in items:
        if it["type"] == "table":
            if cur:
                cur["tables"].append(it["rows"])
                for im in it["images"]:
                    if im not in cur["images"]:
                        cur["images"].append(im)
            continue

        txt = it["text"]
        raw_txt = it.get("raw_text", txt)
        imgs = it.get("images") or []
        marked = it.get("marked_letters") or []

        qm = RE_QUESTION_START.match(txt)
        if qm:
            flush()
            cur = {
                "num": qm.group(1),
                "sub_heading": current_sub_heading,
                "stem_lines": [_clean(qm.group(2))] if _clean(qm.group(2)) else [],
                "images": list(pending_imgs) + [im for im in imgs if im not in pending_imgs],
                "tables": [],
                "options": {},
                "marked_letter": None,
                "answer_letter": None,
                "explain": [],
            }
            pending_imgs = []
            continue

        if cur is None:
            if imgs:
                pending_imgs.extend(im for im in imgs if im not in pending_imgs)
            # Có thể là tiêu đề tiểu mục câu hỏi (VD: "1. Cấu trúc và chức năng của DNA")
            if txt and len(txt) < 120:
                current_sub_heading = txt
            continue

        # Nếu câu hiện tại đã đủ 4 đáp án A-D và đoạn chỉ chứa ảnh (không có chữ) -> ảnh thuộc câu kế tiếp!
        if imgs and not txt and len(cur["options"]) >= 4:
            pending_imgs.extend(im for im in imgs if im not in pending_imgs)
            continue

        # Gắn ảnh vào câu hỏi hiện tại
        for im in imgs:
            if im not in cur["images"]:
                cur["images"].append(im)

        if not txt:
            continue

        am = RE_ANSWER_LINE.match(txt)
        if am:
            ans_body = _clean(am.group(1))
            m_let = re.search(r"\b([A-D])\b", ans_body.upper())
            if m_let:
                cur["answer_letter"] = m_let.group(1)
            continue

        em = RE_EXPLAIN_LINE.match(txt)
        if em:
            cur["explain"].append(_clean(em.group(1)))
            continue

        # Nếu Word dùng đánh số tự động (w:numPr) khiến mất chữ "A. " ở đầu dòng
        if it.get("has_numpr") and not RE_OPT_LINE.match(txt):
            if re.search(r"(?:[\t]| {2,})B\.\s*", raw_txt) and "A" not in cur["options"]:
                raw_txt = "A. " + raw_txt
                txt = "A. " + txt

        # Kiểm tra nhiều đáp án trên cùng 1 dòng
        inline_opts = _split_inline_options(raw_txt)
        if len(inline_opts) >= 2:
            for letter, val in inline_opts:
                if val.startswith("*"):
                    cur["marked_letter"] = letter
                    val = _clean(val.lstrip("*"))
                cur["options"][letter] = val
            for m_let in marked:
                if m_let in ("A", "B", "C", "D"):
                    cur["marked_letter"] = m_let
            continue

        # Kiểm tra 1 đáp án trên 1 dòng
        om = RE_OPT_LINE.match(txt)
        if om:
            letter, val = om.group(1), _clean(om.group(2))
            if val.startswith("*"):
                cur["marked_letter"] = letter
                val = _clean(val.lstrip("*"))
            cur["options"][letter] = val
            if marked:
                if letter in marked or "*" in marked:
                    cur["marked_letter"] = letter
            continue

        # Trường hợp dòng đáp án đơn dùng Word auto-numbering (numPr) cho A., B., C., D.
        if it.get("has_numpr") and len(cur["options"]) < 4 and cur["stem_lines"]:
            next_letter = next((k for k in ("A", "B", "C", "D") if k not in cur["options"]), None)
            if next_letter:
                cur["options"][next_letter] = txt
                if marked:
                    cur["marked_letter"] = next_letter
                continue

        # Nếu chưa có options thì là phần tiếp theo của đề bài (VD: các phát biểu I, II, III, IV)
        if not cur["options"]:
            cur["stem_lines"].append(txt)
        elif cur["explain"]:
            cur["explain"].append(txt)
        else:
            # Nếu đã đủ 4 đáp án A,B,C,D rồi mà gặp dòng tiêu đề tiểu mục (VD: "2. Tái bản DNA")
            if len(cur["options"]) >= 4 and re.match(r"^\d+\.\s+", txt):
                flush()
                current_sub_heading = txt
            else:
                # Nối tiếp nội dung của đáp án cuối cùng
                last_key = list(cur["options"].keys())[-1]
                cur["options"][last_key] = _clean(cur["options"][last_key] + " " + txt)

    flush()
    return _realign_question_images(questions)


def _parse_tf_items(items: List[Dict], lesson_label: str, lesson_id: str, id_prefix: str) -> List[Dict]:
    questions = []
    cur = None
    pending_imgs = []

    def flush():
        nonlocal cur
        if not cur:
            return
        if cur["statements"]:
            # Nếu có answer_map từ dòng "Đáp án: a-Đ, b-S..."
            has_any_key = False
            final_stmts = []
            for st in cur["statements"][:4]:
                ans = st["answer"]
                if ans is None and st["key"] in cur["ans_map"]:
                    ans = cur["ans_map"][st["key"]]
                if ans is not None:
                    has_any_key = True
                final_stmts.append(
                    {
                        "key": st["key"],
                        "text": st["text"],
                        "answer": ans,
                        "explanation": st.get("explanation", ""),
                    }
                )
            orig_num_str = str(cur.get("num", "")).replace("l", "1").replace("I", "1")
            orig_num = int(orig_num_str) if orig_num_str.isdigit() else (len(questions) + 1)
            questions.append(
                {
                    "id": f"{id_prefix}-tf-{len(questions) + 1}",
                    "orig_num": orig_num,
                    "lesson_id": lesson_id,
                    "lesson": lesson_label,
                    "stem": "\n".join(cur["stem_lines"]).strip(),
                    "images": cur["images"],
                    "tables": cur["tables"],
                    "statements": final_stmts,
                    "answer_key_ready": has_any_key and all(s["answer"] is not None for s in final_stmts),
                }
            )
        cur = None

    for it in items:
        if it["type"] == "table":
            if cur:
                cur["tables"].append(it["rows"])
                for im in it["images"]:
                    if im not in cur["images"]:
                        cur["images"].append(im)
            continue

        txt = it["text"]
        imgs = it.get("images") or []

        qm = RE_QUESTION_START.match(txt)
        if qm:
            flush()
            cur = {
                "num": qm.group(1),
                "stem_lines": [_clean(qm.group(2))] if _clean(qm.group(2)) else [],
                "images": list(pending_imgs) + [im for im in imgs if im not in pending_imgs],
                "tables": [],
                "statements": [],
                "ans_map": {},
            }
            pending_imgs = []
            continue

        if cur is None:
            if imgs:
                pending_imgs.extend(im for im in imgs if im not in pending_imgs)
            continue

        if imgs and not txt and len(cur["statements"]) >= 4:
            pending_imgs.extend(im for im in imgs if im not in pending_imgs)
            continue

        for im in imgs:
            if im not in cur["images"]:
                cur["images"].append(im)
        if not txt:
            continue

        am = RE_ANSWER_LINE.match(txt)
        if am:
            ans_raw = _clean(am.group(1))
            if not _is_blank_answer_placeholder(ans_raw):
                pairs = re.findall(r"([a-d])\s*[:\-\s]\s*(Đúng|Sai|Đ|S)", ans_raw, re.IGNORECASE)
                if pairs:
                    for k, v in pairs:
                        cur["ans_map"][k.lower()] = v.lower() in ("đúng", "đ")
                else:
                    seq = re.findall(r"\b(Đúng|Sai|Đ|S)\b", ans_raw, re.IGNORECASE)
                    for i, v in enumerate(seq[:4]):
                        cur["ans_map"][chr(ord("a") + i)] = v.lower() in ("đúng", "đ")
            continue

        tm = RE_TF_STMT.match(txt)
        if tm and len(cur["statements"]) < 4:
            key = tm.group(1).lower()
            stmt_txt = _clean(tm.group(2))
            stmt_ans = None
            m_tail = re.search(r"[\(\[]\s*(Đúng|Sai|Đ|S|True|False)\s*[\)\]]\s*$", stmt_txt, re.IGNORECASE)
            if m_tail:
                tok = m_tail.group(1).lower()
                stmt_ans = tok in ("đúng", "đ", "true")
                stmt_txt = _clean(stmt_txt[: m_tail.start()])
            cur["statements"].append({"key": key, "text": stmt_txt, "answer": stmt_ans})
            continue

        if not cur["statements"]:
            cur["stem_lines"].append(txt)
        else:
            cur["statements"][-1]["text"] = _clean(cur["statements"][-1]["text"] + " " + txt)

    flush()
    return _realign_question_images(questions)


def _parse_sa_items(items: List[Dict], lesson_label: str, lesson_id: str, id_prefix: str) -> List[Dict]:
    questions = []
    cur = None
    pending_imgs = []

    def flush():
        nonlocal cur
        if not cur:
            return
        stem = "\n".join(cur["stem_lines"]).strip()
        if stem:
            accepted = cur["accepted"]
            orig_num_str = str(cur.get("num", "")).replace("l", "1").replace("I", "1")
            orig_num = int(orig_num_str) if orig_num_str.isdigit() else (len(questions) + 1)
            questions.append(
                {
                    "id": f"{id_prefix}-sa-{len(questions) + 1}",
                    "orig_num": orig_num,
                    "lesson_id": lesson_id,
                    "lesson": lesson_label,
                    "question": stem,
                    "images": cur["images"],
                    "tables": cur["tables"],
                    "placeholder": "Nhập kết quả của bạn...",
                    "accepted_answers": accepted,
                    "answer_key_ready": len(accepted) > 0,
                    "unit": "",
                    "explanation": " ".join(cur["explain"]).strip(),
                }
            )
        cur = None

    for it in items:
        if it["type"] == "table":
            if cur:
                cur["tables"].append(it["rows"])
                for im in it["images"]:
                    if im not in cur["images"]:
                        cur["images"].append(im)
            continue

        txt = it["text"]
        imgs = it.get("images") or []

        qm = RE_QUESTION_START.match(txt)
        if qm:
            flush()
            cur = {
                "num": qm.group(1),
                "stem_lines": [_clean(qm.group(2))] if _clean(qm.group(2)) else [],
                "images": list(pending_imgs) + [im for im in imgs if im not in pending_imgs],
                "tables": [],
                "accepted": [],
                "explain": [],
                "saw_answer": False,
            }
            pending_imgs = []
            continue

        if cur is None:
            if imgs:
                pending_imgs.extend(im for im in imgs if im not in pending_imgs)
            continue

        if imgs and (not txt and cur.get("saw_answer")):
            pending_imgs.extend(im for im in imgs if im not in pending_imgs)
            continue

        for im in imgs:
            if im not in cur["images"]:
                cur["images"].append(im)
        if not txt:
            continue

        am = RE_ANSWER_LINE.match(txt)
        if am:
            cur["saw_answer"] = True
            ans_raw = _clean(am.group(1))
            if not _is_blank_answer_placeholder(ans_raw):
                for part in re.split(r"[;|]", ans_raw):
                    p = _clean(part)
                    if p and not _is_blank_answer_placeholder(p):
                        cur["accepted"].append(p)
            continue

        em = RE_EXPLAIN_LINE.match(txt)
        if em:
            cur["explain"].append(_clean(em.group(1)))
            continue

        cur["stem_lines"].append(txt)

    flush()
    return _realign_question_images(questions)


def _build_lesson_theory(raw_items: List[Dict], lesson_meta: Dict, lesson_idx: int, topic_id: str) -> Dict:
    """Chuyển danh sách item Lý thuyết của 1 Bài thành cấu trúc chuẩn (giữ 100% text, ảnh đúng vị trí, bảng)."""
    sections = []
    cur_sec = None
    first_image = ""
    first_caption = ""
    all_points_flat = []

    def ensure_sec(heading="Kiến thức trọng tâm"):
        nonlocal cur_sec
        if cur_sec is None:
            cur_sec = {"heading": heading, "blocks": [], "points": []}
            sections.append(cur_sec)

    for it in raw_items:
        if it["type"] == "table":
            ensure_sec("Bảng tổng hợp")
            cur_sec["blocks"].append({"type": "table", "rows": it["rows"], "images": it["images"]})
            for im in it["images"]:
                if not first_image:
                    first_image = im
            continue

        txt = it["text"]
        imgs = it.get("images") or []

        # Ảnh xuất hiện trong đoạn văn
        if imgs:
            ensure_sec("Nội dung bài học")
            for im in imgs:
                if not first_image:
                    first_image = im
                cur_sec["blocks"].append({"type": "image", "src": im, "caption": ""})

        if not txt:
            continue

        # Chú thích hình ngay sau ảnh -> gán caption trực tiếp vào block ảnh trước đó!
        if RE_CAPTION.match(txt) and cur_sec and cur_sec["blocks"] and cur_sec["blocks"][-1]["type"] == "image":
            cur_sec["blocks"][-1]["caption"] = txt
            if not first_caption and cur_sec["blocks"][-1]["src"] == first_image:
                first_caption = txt
            continue

        # Tiêu đề mục lớn trong bài (1. ..., 1.1. ..., Heading 2/3/4/5)
        is_sec_head = (
            (it["heading_level"] >= 2 and len(txt) < 150)
            or (re.match(r"^(?:\d+\.\s+|\d+\.\d+\.\s+|[IVX]+\.\s+)", txt) and len(txt) < 140 and (it["is_bold"] or it["heading_level"] > 0))
            or txt.upper() in ("YÊU CẦU CẦN ĐẠT", "TÓM TẮT NỘI DUNG LÝ THUYẾT")
        )
        if is_sec_head:
            cur_sec = {"heading": txt, "blocks": [], "points": []}
            sections.append(cur_sec)
            continue

        ensure_sec("Nội dung bài học")
        cur_sec["blocks"].append({"type": "text", "text": txt, "is_bold": it["is_bold"]})
        cur_sec["points"].append(txt)
        all_points_flat.append(txt)

    # Làm gọn: bỏ các section hoàn toàn rỗng
    sections = [s for s in sections if s["blocks"]]

    summary = all_points_flat[0][:240] if all_points_flat else lesson_meta["title"]
    takeaway = all_points_flat[-1][:260] if len(all_points_flat) > 1 else summary

    # Gắn thêm mô phỏng tương tác cho Chủ đề 1
    interactive_diagram = ""
    if topic_id == "chu-de-1" and lesson_idx < len(TOPIC1_DIAGRAMS):
        interactive_diagram = TOPIC1_DIAGRAMS[lesson_idx]

    return {
        "id": lesson_meta["id"],
        "number": lesson_meta["number"],
        "title": lesson_meta["title"],
        "duration_minutes": max(20, min(45, len(all_points_flat) + 10)),
        "summary": summary,
        "image": first_image,
        "image_caption": first_caption,
        "interactive_diagram": interactive_diagram,
        "sections": sections,
        "key_takeaway": takeaway,
    }


def _build_htkt_unit(raw_items: List[Dict], lesson_meta: Dict) -> Optional[Dict]:
    """Đóng gói nguyên vẹn phần 'HỆ THỐNG KIẾN THỨC' của từng Bài (văn bản, hình ảnh, bảng biểu)."""
    if not raw_items:
        return None
    blocks = []
    for it in raw_items:
        if it["type"] == "table":
            blocks.append({"type": "table", "rows": it["rows"], "images": it["images"]})
            continue
        imgs = it.get("images") or []
        for im in imgs:
            blocks.append({"type": "image", "src": im, "caption": ""})
        txt = it["text"]
        if txt:
            if RE_CAPTION.match(txt) and blocks and blocks[-1]["type"] == "image":
                blocks[-1]["caption"] = txt
            else:
                blocks.append({"type": "text", "text": txt, "is_bold": it["is_bold"]})
    if not blocks:
        return None
    return {
        "lesson_id": lesson_meta["id"],
        "lesson_number": lesson_meta["number"],
        "lesson_title": lesson_meta["title"],
        "blocks": blocks,
    }


def parse_document_to_topic(
    file_bytes: bytes,
    filename: str,
    topic_id: str,
    existing_topic: Dict,
    title_override: str = "",
) -> Dict:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".docx":
        raw = extract_body_items_from_docx(file_bytes, topic_id)
    elif ext == ".pdf":
        raw = extract_body_items_from_pdf(file_bytes, topic_id)
    elif ext in (".txt", ".md"):
        raw = extract_body_items_from_txt(file_bytes)
    else:
        raise ValueError("Chỉ hỗ trợ file Word (.docx), PDF (.pdf) hoặc văn bản (.txt, .md).")

    items = raw["items"]
    all_images = raw["images"]

    if not items:
        raise ValueError("Không đọc được nội dung từ file.")

    # Phát hiện tiêu đề Chủ đề ở đầu file
    detected_title = title_override or existing_topic.get("title", "Chủ đề Sinh học 12")
    start_idx = 0
    if items and items[0]["type"] == "p" and RE_TOPIC_TITLE.match(items[0]["text"]):
        t0 = items[0]["text"]
        # Trường hợp "Chủ đề 2:" ở dòng 0 và tên chủ đề ở dòng 1 (Heading 1)
        if len(t0) <= 15 and len(items) > 1 and items[1]["type"] == "p" and items[1]["heading_level"] == 1:
            t0 = f"{t0} {items[1]['text']}"
            start_idx = 2
        else:
            start_idx = 1
        if not title_override:
            detected_title = t0

    # Phân nhóm toàn bộ items vào từng Bài -> 5 ngăn: theory, knowledge, mcq, true_false, short_answer
    lesson_buckets = []
    cur_bucket = None
    mode = "theory"

    def start_new_lesson(raw_title: str):
        nonlocal cur_bucket, mode
        idx = len(lesson_buckets) + 1
        m_num = re.match(r"^(BÀI\s*\d+|4\.\d+|[A-D]\.)\s*[:\.\-]?\s*(.*)$", raw_title, re.IGNORECASE)
        if m_num and m_num.group(2).strip():
            l_num = m_num.group(1).strip().rstrip(".").upper()
            if re.match(r"^[A-D]$", l_num):
                l_num = f"Phần {l_num}"
            elif re.match(r"^4\.\d+$", l_num):
                l_num = f"Mục {l_num}"
            l_title = m_num.group(2).strip()
        else:
            l_num = f"Bài {idx}"
            l_title = raw_title.strip()

        cur_bucket = {
            "meta": {
                "id": f"{topic_id}-bai-{idx}",
                "number": l_num,
                "title": l_title,
            },
            "theory": [],
            "knowledge": [],
            "mcq": [],
            "true_false": [],
            "short_answer": [],
        }
        lesson_buckets.append(cur_bucket)
        mode = "theory"

    for it in items[start_idx:]:
        if it["type"] == "p":
            txt = it["text"]
            if RE_HTKT_MARKER.match(txt):
                if cur_bucket is None:
                    start_new_lesson(detected_title)
                mode = "knowledge"
                continue
            if RE_MCQ_MARKER.match(txt):
                if cur_bucket is None:
                    start_new_lesson(detected_title)
                mode = "mcq"
                continue
            if RE_TF_MARKER.match(txt):
                if cur_bucket is None:
                    start_new_lesson(detected_title)
                mode = "true_false"
                continue
            if RE_SA_MARKER.match(txt):
                if cur_bucket is None:
                    start_new_lesson(detected_title)
                mode = "short_answer"
                continue

            if _is_new_lesson_header(it, mode, len(lesson_buckets) > 0):
                start_new_lesson(txt)
                continue

        if cur_bucket is None:
            start_new_lesson(detected_title)

        cur_bucket[mode].append(it)

    # Xây dựng dữ liệu cuối cùng cho từng thẻ
    lessons = []
    htkt_units = []
    all_mcq = []
    all_tf = []
    all_sa = []
    mindmap_branches = []
    flashcards = []
    formulas = []
    branch_colors = ["#0f766e", "#0369a1", "#b45309", "#be123c", "#6d28d9", "#15803d"]

    for i, bk in enumerate(lesson_buckets):
        meta = bk["meta"]
        label = f"{meta['number']}: {meta['title']}"
        short_label = meta["number"]

        lesson_obj = _build_lesson_theory(bk["theory"], meta, i, topic_id)
        lessons.append(lesson_obj)

        htkt_unit = _build_htkt_unit(bk["knowledge"], meta)
        if htkt_unit:
            htkt_units.append(htkt_unit)

        mcq_part = _parse_mcq_items(bk["mcq"], short_label, meta["id"], f"{topic_id}-b{i+1}")
        tf_part = _parse_tf_items(bk["true_false"], short_label, meta["id"], f"{topic_id}-b{i+1}")
        sa_part = _parse_sa_items(bk["short_answer"], short_label, meta["id"], f"{topic_id}-b{i+1}")

        all_mcq.extend(mcq_part)
        all_tf.extend(tf_part)
        all_sa.extend(sa_part)

        # Sơ đồ tư duy + Flashcards + Công thức bám sát 100% bài học
        mm_nodes = []
        for sec in lesson_obj["sections"]:
            head = sec["heading"]
            pts = sec.get("points") or []
            if pts:
                mm_nodes.append(f"{head}: {pts[0][:155]}")
                if len(flashcards) < 12 and "yêu cầu cần đạt" not in head.lower():
                    flashcards.append(
                        {
                            "front": f"[{short_label}] {head}",
                            "back": " ".join(pts[:2])[:280],
                        }
                    )
                for p_txt in pts:
                    if re.search(r"(?:N\s*=|L\s*=|H\s*=|f\s*=|2\^|2n|3,4\s*Å)", p_txt) and len(p_txt) < 170 and len(formulas) < 8:
                        formulas.append({"name": f"{short_label} • {head}", "expression": p_txt, "note": label})
            else:
                mm_nodes.append(head)

        mindmap_branches.append(
            {
                "id": f"mm-{topic_id}-{i + 1}",
                "title": label,
                "color": branch_colors[i % len(branch_colors)],
                "nodes": mm_nodes[:8] or [lesson_obj["summary"]],
            }
        )

    # Tạo phân cảnh Video tương tác thuyết minh tiếng Việt bám sát từng Bài & hình ảnh thật từ file
    scenes = []
    for i, ls in enumerate(lessons):
        pts = [p for sec in ls["sections"] for p in sec.get("points", []) if "yêu cầu cần đạt" not in sec["heading"].lower()]
        narration = " ".join(pts[:4])[:680] or ls["title"]
        # Chọn 1 câu hỏi trắc nghiệm có đáp án (nếu có) làm checkpoint của phân cảnh
        lesson_mcqs = [q for q in all_mcq if q.get("lesson_id") == ls["id"] and q.get("answer_key_ready")]
        cp_q = lesson_mcqs[0] if lesson_mcqs else None

        sc = {
            "id": f"scene-{topic_id}-{i + 1}",
            "duration": max(16, min(30, int(len(narration) / 22))),
            "title": f"{ls['number']}: {ls['title']}",
            "badge": ls["number"],
            "image": ls["image"] or (all_images[0] if all_images else "/images/dna_replication.svg"),
            "narration": narration,
            "bullets": pts[:4] or [ls["title"]],
        }
        if cp_q:
            sc["checkpoint"] = {
                "question": cp_q["question"],
                "options": cp_q["options"],
                "correct_index": cp_q["correct_index"],
                "explanation": cp_q["explanation"] or "Theo nội dung bài giảng trong tài liệu nguồn.",
            }
        scenes.append(sc)

    # Chuẩn hoá đánh số đề mục thống nhất (VD: Chủ đề 5 -> 5.1, 5.2, 5.3...) & gắn mức độ nhận thức
    order_index = int(existing_topic.get("order_index") or 0)
    if order_index <= 0:
        m_ord = re.search(r"(\d+)", topic_id)
        order_index = int(m_ord.group(1)) if m_ord else 1

    try:
        from classify_levels import classify_question as _classify_lv
    except Exception:
        _classify_lv = None

    lesson_num_map = {}
    for l_idx, ls in enumerate(lessons, 1):
        new_num = f"{order_index}.{l_idx}"
        ls["number"] = new_num
        lesson_num_map[ls["id"]] = new_num
    for u_idx, unit in enumerate(htkt_units, 1):
        unit["lesson_number"] = f"{order_index}.{u_idx}"
    for b_idx, br in enumerate(mindmap_branches, 1):
        ls_title = lessons[b_idx - 1]["title"] if b_idx <= len(lessons) else br.get("title", "")
        br["title"] = f"{order_index}.{b_idx}: {ls_title}"
    for kind_key, q_list in (("mcq", all_mcq), ("true_false", all_tf), ("short_answer", all_sa)):
        for q in q_list:
            lid = q.get("lesson_id") or ""
            if lid in lesson_num_map:
                q["lesson"] = lesson_num_map[lid]
            if _classify_lv and not q.get("cognitive_level"):
                q["cognitive_level"] = _classify_lv(q, kind_key)

    subtitle = " • ".join(f"{l['number']}: {l['title']}" for l in lessons)
    if len(subtitle) > 180:
        subtitle = " • ".join(l["title"] for l in lessons)[:180]

    knowledge_system = {
        "overview": "",
        "units": htkt_units,
        "mindmap": {
            "root": detected_title.upper(),
            "branches": mindmap_branches,
        },
        "comparison_tables": [],
        "formulas": formulas,
        "flashcards": flashcards,
    }

    youtube_videos = existing_topic.get("youtube_videos") or []

    mcq_keyed = sum(1 for q in all_mcq if q.get("answer_key_ready"))
    tf_keyed = sum(1 for q in all_tf if q.get("answer_key_ready"))
    sa_keyed = sum(1 for q in all_sa if q.get("answer_key_ready"))

    return {
        "filename": filename,
        "detected_title": detected_title,
        "stats": {
            "lessons_count": len(lessons),
            "sections_count": sum(len(l["sections"]) for l in lessons),
            "htkt_units_count": len(htkt_units),
            "images_count": len(all_images),
            "tables_count": raw["tables_count"],
            "mcq_count": len(all_mcq),
            "mcq_keyed": mcq_keyed,
            "true_false_count": len(all_tf),
            "true_false_keyed": tf_keyed,
            "short_answer_count": len(all_sa),
            "short_answer_keyed": sa_keyed,
        },
        "extracted": {
            "id": topic_id,
            "order_index": order_index,
            "title": detected_title,
            "subtitle": subtitle,
            "grade": "Sinh học 12 — Chương trình GDPT 2018",
            "status": "published",
            "source_note": "",
            "lessons": lessons,
            "knowledge_system": knowledge_system,
            "youtube_videos": youtube_videos,
            "review": {
                "mcq": all_mcq,
                "true_false": all_tf,
                "short_answer": all_sa,
            },
        },
    }


def _build_sample_docx_template_stdlib() -> bytes:
    """Tạo file Word (.docx) mẫu bằng pure-Python stdlib khi không có python-docx."""
    from xml.sax.saxutils import escape as xml_escape

    paragraphs = [
        ("CHỦ ĐỀ 1: CƠ SỞ PHÂN TỬ CỦA HIỆN TƯỢNG DI TRUYỀN VÀ BIẾN DỊ", True),
        ("BÀI 1: DNA VÀ CƠ CHẾ TÁI BẢN DNA", True),
        ("1. Cấu trúc của phân tử DNA", True),
        ("- DNA cấu tạo theo nguyên tắc đa phân, đơn phân là 4 loại nucleotide: A, T, G, C.", False),
        ("- Hai mạch polynucleotide xoắn ngược chiều nhau (5' -> 3' và 3' -> 5'), liên kết theo nguyên tắc bổ sung: A = T (2 liên kết H), G ≡ C (3 liên kết H).", False),
        ("HỆ THỐNG KIẾN THỨC", True),
        ("Câu 1: Hoàn thành bảng so sánh DNA và RNA bên dưới:", False),
        ("CÂU HỎI TRẮC NGHIỆM NHIỀU LỰA CHỌN", True),
        ("Câu 1: Đơn phân cấu tạo nên phân tử DNA là gì?", False),
        ("A. Amino acid", False),
        ("B. Nucleotide", False),
        ("C. Glucose", False),
        ("D. Acid béo", False),
        ("Đáp án: B", False),
        ("CÂU HỎI TRẮC NGHIỆM ĐÚNG SAI", True),
        ("Câu 1: Xét cấu trúc của một phân tử DNA mạch kép, các nhận định sau là Đúng hay Sai?", False),
        ("......a. A liên kết với T bằng 2 liên kết hydrogen. (Đúng)", False),
        ("......b. G liên kết với C bằng 2 liên kết hydrogen. (Sai)", False),
        ("......c. Hai mạch của DNA song song ngược chiều nhau. (Đúng)", False),
        ("......d. Trong DNA có chứa loại base Uracil (U). (Sai)", False),
        ("CÂU HỎI TRẮC NGHIỆM TRẢ LỜI NGẮN", True),
        ("Câu 1: Một đoạn DNA có A = 500 và G = 700. Tổng số liên kết hydrogen của đoạn DNA này là bao nhiêu?", False),
        ("Đáp án: 3100", False),
    ]
    body_xml = []
    for txt, bold in paragraphs:
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        body_xml.append(f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{xml_escape(txt)}</w:t></w:r></w:p>')

    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(body_xml)}<w:sectPr/></w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


def build_sample_docx_template() -> bytes:
    """Tạo file Word (.docx) mẫu chuẩn cấu trúc để Giáo viên tham khảo."""
    if docx is None:
        return _build_sample_docx_template_stdlib()
    doc = docx.Document()
    doc.add_heading("CHỦ ĐỀ 1: CƠ SỞ PHÂN TỬ CỦA HIỆN TƯỢNG DI TRUYỀN VÀ BIẾN DỊ", level=1)

    doc.add_heading("BÀI 1: DNA VÀ CƠ CHẾ TÁI BẢN DNA", level=3)
    p = doc.add_paragraph()
    p.add_run("1. Cấu trúc của phân tử DNA").bold = True
    doc.add_paragraph("- DNA cấu tạo theo nguyên tắc đa phân, đơn phân là 4 loại nucleotide: A, T, G, C.")
    doc.add_paragraph("- Hai mạch polynucleotide xoắn ngược chiều nhau (5' -> 3' và 3' -> 5'), liên kết theo nguyên tắc bổ sung: A = T (2 liên kết H), G ≡ C (3 liên kết H).")

    doc.add_paragraph("HỆ THỐNG KIẾN THỨC")
    doc.add_paragraph("Câu 1: Hoàn thành bảng so sánh DNA và RNA bên dưới:")
    tb = doc.add_table(rows=3, cols=3)
    tb.rows[0].cells[0].text = "Đặc điểm"
    tb.rows[0].cells[1].text = "DNA"
    tb.rows[0].cells[2].text = "RNA"
    tb.rows[1].cells[0].text = "Số mạch"
    tb.rows[1].cells[1].text = "2 mạch xoắn kép"
    tb.rows[1].cells[2].text = "1 mạch đơn"
    tb.rows[2].cells[0].text = "Các loại base"
    tb.rows[2].cells[1].text = "A, T, G, C"
    tb.rows[2].cells[2].text = "A, U, G, C"

    doc.add_paragraph("CÂU HỎI TRẮC NGHIỆM NHIỀU LỰA CHỌN")
    doc.add_paragraph("Câu 1: Đơn phân cấu tạo nên phân tử DNA là gì?")
    doc.add_paragraph("A. Amino acid")
    p_ans = doc.add_paragraph()
    r = p_ans.add_run("B.")
    r.underline = True
    p_ans.add_run(" Nucleotide")
    doc.add_paragraph("C. Glucose")
    doc.add_paragraph("D. Acid béo")
    doc.add_paragraph("Đáp án: B")

    doc.add_paragraph("CÂU HỎI TRẮC NGHIỆM ĐÚNG SAI")
    doc.add_paragraph("Câu 1: Xét cấu trúc của một phân tử DNA mạch kép, các nhận định sau là Đúng hay Sai?")
    doc.add_paragraph("......a. A liên kết với T bằng 2 liên kết hydrogen. (Đúng)")
    doc.add_paragraph("......b. G liên kết với C bằng 2 liên kết hydrogen. (Sai)")
    doc.add_paragraph("......c. Hai mạch của DNA song song ngược chiều nhau. (Đúng)")
    doc.add_paragraph("......d. Trong DNA có chứa loại base Uracil (U). (Sai)")

    doc.add_paragraph("CÂU HỎI TRẮC NGHIỆM TRẢ LỜI NGẮN")
    doc.add_paragraph("Câu 1: Một đoạn DNA có A = 500 và G = 700. Tổng số liên kết hydrogen của đoạn DNA này là bao nhiêu?")
    doc.add_paragraph("Đáp án: 3100")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
