"""
Xuất file Excel mẫu (.xlsx) và đọc danh sách học sinh từ file Excel (.xlsx) / CSV (.csv)
không cần thư viện ngoài (pure Python zipfile + ElementTree).
"""
import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List, Tuple
from xml.sax.saxutils import escape as xml_escape

from database import DEFAULT_USER_PASSWORD

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,40}$")


def validate_username(raw: str) -> Tuple[str, str]:
    """Kiểm tra tên đăng nhập viết liền không dấu, 3-40 ký tự."""
    u = (raw or "").strip().lower()
    if not u:
        return "", "Tên đăng nhập không được để trống."
    if " " in u:
        return "", f"Tên đăng nhập '{raw}' không được chứa khoảng trắng (phải viết liền không dấu)."
    if not USERNAME_RE.match(u):
        return "", f"Tên đăng nhập '{raw}' chỉ gồm chữ cái không dấu (a-z), chữ số (0-9), dấu chấm, gạch dưới hoặc gạch ngang (3–40 ký tự)."
    return u, ""


def _col_letter(idx_1based: int) -> str:
    res = ""
    n = idx_1based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        res = chr(65 + rem) + res
    return res


def _build_sheet_xml(rows: List[List[str]], widths: List[int] = None) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
    ]
    if widths:
        lines.append("<cols>")
        for i, w in enumerate(widths, 1):
            lines.append(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>')
        lines.append("</cols>")
    lines.append("<sheetData>")
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


def build_student_import_template_xlsx() -> bytes:
    """Tạo file Excel mẫu (.xlsx) nhập danh sách học sinh cho Quản trị viên & Giáo viên."""
    sheet1_rows = [
        ["Ten dang nhap", "Mat khau mac dinh"],
        ["nguyenvanan", DEFAULT_USER_PASSWORD],
        ["tranthibinh", DEFAULT_USER_PASSWORD],
        ["leminhcuong", DEFAULT_USER_PASSWORD],
    ]
    sheet2_rows = [
        ["Huong dan nhap danh sach hoc sinh"],
        ["1. Cot A (Ten dang nhap): nhap ten dang nhap viet lien khong dau, khong khoang trang (VD: nguyenvanan, hs12a1_01)."],
        [f"2. Cot B (Mat khau mac dinh): de mac dinh la {DEFAULT_USER_PASSWORD} (hoac de trong he thong tu gan {DEFAULT_USER_PASSWORD})."],
        ["3. Xoa 3 dong vi du mau truoc khi nhap danh sach hoc sinh thuc te."],
        ["4. Sau khi hoc sinh dang nhap lan dau, he thong se yeu cau cap nhat Ho ten, Lop, Truong, SDT va Mat khau moi."],
    ]

    sheets = [
        ("Danh sach hoc sinh", sheet1_rows, [32, 24]),
        ("Huong dan", sheet2_rows, [95]),
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

    wb_sheets = "".join(
        f'<sheet name="{xml_escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        for i, (name, _, _) in enumerate(sheets, 1)
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{wb_sheets}</sheets></workbook>"
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
        for i, (_, rows, widths) in enumerate(sheets, 1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", _build_sheet_xml(rows, widths))
    return buf.getvalue()


def _col_ref_to_idx(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return max(0, idx - 1)


def _read_xlsx_rows(file_bytes: bytes) -> List[List[str]]:
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        names = set(zf.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("s:si", ns):
                txt = "".join(t.text or "" for t in si.findall(".//s:t", ns))
                shared.append(txt)

        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in names:
            candidates = sorted(n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            if not candidates:
                raise ValueError("File Excel không có trang tính (worksheet) hợp lệ.")
            sheet_name = candidates[0]

        sroot = ET.fromstring(zf.read(sheet_name))
        rows = []
        for row_el in sroot.findall(".//s:sheetData/s:row", ns):
            cells = {}
            for c in row_el.findall("s:c", ns):
                ref = c.attrib.get("r", "")
                ctype = c.attrib.get("t", "")
                cidx = _col_ref_to_idx(ref) if ref else len(cells)
                val = ""
                if ctype == "inlineStr":
                    val = "".join(t.text or "" for t in c.findall(".//s:t", ns))
                elif ctype == "s":
                    v_el = c.find("s:v", ns)
                    if v_el is not None and (v_el.text or "").isdigit():
                        si_idx = int(v_el.text)
                        val = shared[si_idx] if si_idx < len(shared) else ""
                else:
                    v_el = c.find("s:v", ns)
                    val = v_el.text if v_el is not None and v_el.text is not None else ""
                cells[cidx] = val.strip()
            if cells:
                max_c = max(cells.keys())
                row_list = [cells.get(i, "") for i in range(max_c + 1)]
                if any(x for x in row_list):
                    rows.append(row_list)
        return rows


def _read_csv_rows(file_bytes: bytes) -> List[List[str]]:
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            text = file_bytes.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        raise ValueError("Không thể giải mã nội dung file CSV.")
    sample = text[:2048]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    return [[c.strip() for c in r] for r in reader if any(c.strip() for c in r)]


def parse_students_from_file(file_bytes: bytes, filename: str) -> List[Dict]:
    """Đọc danh sách (username, password) từ file Excel .xlsx hoặc .csv."""
    lower = (filename or "").lower()
    if lower.endswith(".xlsx"):
        raw_rows = _read_xlsx_rows(file_bytes)
    elif lower.endswith(".csv") or lower.endswith(".txt"):
        raw_rows = _read_csv_rows(file_bytes)
    else:
        raise ValueError("Chỉ hỗ trợ định dạng file Excel (.xlsx) hoặc CSV (.csv).")

    if not raw_rows:
        raise ValueError("File không có dữ liệu.")

    results = []
    # Phát hiện nếu cột A là STT và cột B là Tên đăng nhập
    header0 = [c.lower() for c in raw_rows[0]]
    use_col_offset = 0
    if header0 and header0[0] in ("stt", "tt", "so thu tu", "số thứ tự") and len(header0) >= 2:
        use_col_offset = 1

    header_keywords = (
        "ten dang nhap",
        "tên đăng nhập",
        "username",
        "tai khoan",
        "tài khoản",
        "stt",
    )

    for r_num, row in enumerate(raw_rows, 1):
        c0 = row[use_col_offset].strip() if len(row) > use_col_offset else ""
        c1 = row[use_col_offset + 1].strip() if len(row) > use_col_offset + 1 else ""
        if not c0:
            continue
        if r_num == 1 and any(kw in c0.lower() for kw in header_keywords):
            continue
        results.append(
            {
                "row_num": r_num,
                "username": c0,
                "password": c1 or DEFAULT_USER_PASSWORD,
            }
        )
    return results
