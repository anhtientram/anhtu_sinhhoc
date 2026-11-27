"""
Bộ chuẩn hoá đầu vào (Input Standardizer) cho hệ thống Sinh học 12 (CT GDPT 2018):
  1. Kiểm tra & tự động chuẩn hoá chính tả tiếng Việt, dấu thanh, thuật ngữ Sinh học 12
     (DNA, RNA, gene, allele, nucleotide, amino acid, công thức DNA & kiểu gene chuẩn SGK).
  2. Tự động nhận diện và đối chiếu với nguồn tham khảo PDF "SGK_SINH HỌC" (nếu có trong thư mục dự án)
     để xây dựng từ điển thuật ngữ chuẩn và cảnh báo các từ sai chính tả / lỗi dấu nghi ngờ.
  3. Phân tích và đối chiếu file PDF "Đáp án" (tải kèm hoặc sẵn có) để tự động khớp đáp án &
     "Giải chi tiết" cho 3 phần câu hỏi (Trắc nghiệm 4 đáp án, Đúng/Sai, Trả lời ngắn).
"""

import io
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Bộ quy tắc sửa lỗi chính tả tiếng Việt & lỗi thiếu/sai dấu hay gặp trong tài liệu Sinh học 12
# (Khớp không phân biệt hoa/thường và tự bảo toàn kiểu chữ hoa/thường của từ gốc)
SPELLING_FIX_RULES: List[Tuple[str, str]] = [
    # Lỗi thiếu/sai dấu thường gặp trong tài liệu Word/PDF Sinh học 12
    (r"\bvi\s+khuân\b", "vi khuẩn"),
    (r"\bvi\s+khuan\b", "vi khuẩn"),
    (r"\bthay\s+đôi\b", "thay đổi"),
    (r"\bthay\s+doi\b", "thay đổi"),
    (r"\bbiên\s+đổi\b", "biến đổi"),
    (r"\bbiến\s+đôi\b", "biến đổi"),
    (r"\btrao\s+đôi\b", "trao đổi"),
    (r"\bdi\s+truyên\b", "di truyền"),
    (r"\bdi\s+truyen\b", "di truyền"),
    (r"\bnhiêm\s+sắc\s+thể\b", "nhiễm sắc thể"),
    (r"\bnhiễm\s+sac\s+thể\b", "nhiễm sắc thể"),
    (r"\bnhiễm\s+sắc\s+thê\b", "nhiễm sắc thể"),
    (r"\bnhiem\s+sac\s+the\b", "nhiễm sắc thể"),
    (r"\bđôt\s+biến\b", "đột biến"),
    (r"\bđột\s+biên\b", "đột biến"),
    (r"\bdot\s+bien\b", "đột biến"),
    (r"\bquân\s+thể\b", "quần thể"),
    (r"\bquần\s+thê\b", "quần thể"),
    (r"\bquân\s+xã\b", "quần xã"),
    (r"\bquần\s+xa\b", "quần xã"),
    (r"\bsinh\s+vât\b", "sinh vật"),
    (r"\bsinh\s+vat\b", "sinh vật"),
    (r"\bhê\s+sinh\s+thái\b", "hệ sinh thái"),
    (r"\bhệ\s+sinh\s+thai\b", "hệ sinh thái"),
    (r"\btiên\s+hoá\b", "tiến hoá"),
    (r"\btiên\s+hóa\b", "tiến hóa"),
    (r"\bmôi\s+trương\b", "môi trường"),
    (r"\bmoi\s+truong\b", "môi trường"),
    (r"\btê\s+bào\b", "tế bào"),
    (r"\btế\s+bao\b", "tế bào"),
    (r"\bphân\s+tư\b", "phân tử"),
    (r"\bnguyên\s+tăc\b", "nguyên tắc"),
    (r"\bliên\s+kêt\b", "liên kết"),
    (r"\blien\s+ket\b", "liên kết"),
    (r"\bhoán\s+vi\b", "hoán vị"),
    (r"\bhoan\s+vi\b", "hoán vị"),
    (r"\btương\s+tac\b", "tương tác"),
    (r"\bkêt\s+quả\b", "kết quả"),
    (r"\bkết\s+qua\b", "kết quả"),
    (r"\bquá\s+trinh\b", "quá trình"),
    (r"\bqua\s+trinh\b", "quá trình"),
    (r"\bbiêu\s+hiện\b", "biểu hiện"),
    (r"\bbiểu\s+hiên\b", "biểu hiện"),
    (r"\bcâu\s+trúc\b", "cấu trúc"),
    (r"\bcấu\s+truc\b", "cấu trúc"),
    (r"\bchưc\s+năng\b", "chức năng"),
    (r"\bchức\s+nang\b", "chức năng"),
    (r"\bđăc\s+trưng\b", "đặc trưng"),
    (r"\bđặc\s+trung\b", "đặc trưng"),
    (r"\bđăc\s+điểm\b", "đặc điểm"),
    (r"\bđặc\s+điêm\b", "đặc điểm"),
    (r"\bthưc\s+vật\b", "thực vật"),
    (r"\bđông\s+vật\b", "động vật"),
    (r"\bphát\s+triên\b", "phát triển"),
    (r"\bcơ\s+thê\b", "cơ thể"),
    (r"\bkhông\s+thê\b", "không thể"),
    (r"\bkiêu\s+hình\b", "kiểu hình"),
    (r"\bkiểu\s+hinh\b", "kiểu hình"),
    (r"\bkiêu\s+gene\b", "kiểu gene"),
    (r"\bkiêu\s+gen\b", "kiểu gene"),
    (r"\bgiao\s+tư\b", "giao tử"),
    (r"\bhơp\s+tử\b", "hợp tử"),
    (r"\bhợp\s+tư\b", "hợp tử"),
    (r"\bphiên\s+ma\b", "phiên mã"),
    (r"\bdịch\s+ma\b", "dịch mã"),
    (r"\btái\s+ban\b", "tái bản"),
    (r"\bnhân\s+đôi\b", "nhân đôi"),
    (r"\bsô\s+lượng\b", "số lượng"),
    (r"\bsố\s+lương\b", "số lượng"),
    (r"\bthành\s+phân\b", "thành phần"),
    (r"\bkích\s+thươc\b", "kích thước"),
    (r"\bnăng\s+lương\b", "năng lượng"),
    (r"\bchuyễn\s+hóa\b", "chuyển hóa"),
    (r"\bchuyễn\s+hoá\b", "chuyển hoá"),
    (r"\bchọn\s+loc\b", "chọn lọc"),
    (r"\btự\s+nhien\b", "tự nhiên"),
    (r"\bloài\s+mơi\b", "loài mới"),
    (r"\bchuôi\s+thức\s+ăn\b", "chuỗi thức ăn"),
    (r"\blươi\s+thức\s+ăn\b", "lưới thức ăn"),
    (r"\bbâc\s+dinh\s+dưỡng\b", "bậc dinh dưỡng"),
    (r"\bbậc\s+dinh\s+dương\b", "bậc dinh dưỡng"),
    (r"\bsinh\s+quyên\b", "sinh quyển"),
    (r"\bổ\s+sinh\s+thai\b", "ổ sinh thái"),
    (r"\bmât\s+độ\b", "mật độ"),
    (r"\btăng\s+trương\b", "tăng trưởng"),
    (r"\bcạnh\s+trành\b", "cạnh tranh"),
    (r"\bphân\s+giai\b", "phân giải"),
    (r"\bsản\s+xuât\b", "sản xuất"),
    (r"\btiêu\s+thu\b", "tiêu thụ"),
    (r"\bđa\s+dang\b", "đa dạng"),
    (r"\bbảo\s+tôn\b", "bảo tồn"),
    (r"\bô\s+nhiêm\b", "ô nhiễm"),
    (r"\bkhí\s+hâu\b", "khí hậu"),
    (r"\bnguyên\s+liêu\b", "nguyên liệu"),
    (r"\bnhân\s+tô\b", "nhân tố"),
    (r"\bthê\s+hệ\b", "thế hệ"),
    (r"\bthế\s+hê\b", "thế hệ"),
    (r"\btính\s+trang\b", "tính trạng"),
    (r"\btinh\s+trạng\b", "tính trạng"),
    (r"\bthụ\s+phẩn\b", "thụ phấn"),
    (r"\bthưc\s+hiện\b", "thực hiện"),
    (r"\bphương\s+phap\b", "phương pháp"),
    (r"\bứng\s+dung\b", "ứng dụng"),
    (r"\bcông\s+nghê\b", "công nghệ"),
    # Chuẩn hoá thuật ngữ GDPT 2018 (SGK Sinh học 12 mới)
    (r"\bADN\b", "DNA"),
    (r"\bARN\b", "RNA"),
    (r"\bmARN\b", "mRNA"),
    (r"\btARN\b", "tRNA"),
    (r"\brARN\b", "rRNA"),
    (r"\bnuclêôtit\b", "nucleotide"),
    (r"\bnucleotit\b", "nucleotide"),
    (r"\bpôlinuclêôtit\b", "polynucleotide"),
    (r"\bpolinucleotit\b", "polynucleotide"),
    (r"\baxit\s+amin\b", "amino acid"),
    (r"\bribôxôm\b", "ribosome"),
    (r"\benzim\b", "enzyme"),
    (r"\bprôtêin\b", "protein"),
    (r"\bhiđrô\b", "hydrogen"),
    (r"\bhiđro\b", "hydrogen"),
    (r"\bôxi\b", "oxygen"),
    (r"\balen\b", "allele"),
    (r"\bgen\b", "gene"),
]

COMPILED_SPELLING_RULES = [(re.compile(pat, re.IGNORECASE), repl) for pat, repl in SPELLING_FIX_RULES]

# Cache từ điển thuật ngữ trích từ file PDF SGK_SINH HỌC (nếu có trong hệ thống)
_SGK_CACHE: Optional[Dict[str, Any]] = None


def _match_case(original: str, replacement: str) -> str:
    """Bảo toàn chữ HOA / Viết hoa đầu câu của từ gốc khi thay thế chính tả."""
    if not original:
        return replacement
    # Giữ nguyên chuẩn viết tắt khoa học (DNA, RNA, mRNA, tRNA, rRNA)
    if replacement in ("DNA", "RNA", "mRNA", "tRNA", "rRNA"):
        return replacement
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def standardize_dna_and_genotype(text: str) -> str:
    """Chuẩn hoá công thức DNA và ký hiệu kiểu gene chuẩn SGK Sinh học 12."""
    if not text:
        return ""
    s = text
    # Dấu lai × giữa 2 kiểu gene
    s = re.sub(
        r"(\b(?:[A-Za-z]{2,6}(?:/[A-Za-z]{2,6})?|[XYI]\^?[A-Za-z\{\}]{1,6}[XYI]?\^?[A-Za-z\{\}]{0,6}))\s+[xX]\s+(?=[A-Za-zXYI])",
        r"\1 × ",
        s,
    )
    # Kiểu gene liên kết/hoán vị viết sai dấu ngăn cách: AB//ab, (AB)/(ab) -> AB/ab
    s = re.sub(r"\(([A-Za-z]{2,4})\)\s*/\s*\(([A-Za-z]{2,4})\)", r"\1/\2", s)
    s = re.sub(r"\b([A-Za-z]{2,4})\s*(?://|\\)\s*([A-Za-z]{2,4})\b", r"\1/\2", s)
    # Kiểu hình viết bằng gạch dưới: A_B_, A_bb, aaB_ -> A-B-, A-bb, aaB-
    s = re.sub(r"\b([A-Z])_([A-Z])_(?![A-Za-z0-9])", r"\1-\2-", s)
    s = re.sub(r"\b([A-Z])_([a-z]{2})(?![A-Za-z0-9])", r"\1-\2", s)
    s = re.sub(r"\b([a-z]{2})([A-Z])_(?![A-Za-z0-9])", r"\1\2-", s)
    # Nhóm máu ABO / đa allele: IAIB -> I^AI^B, IAIO -> I^AI^O
    s = re.sub(r"\bI([ABO])\s*I([ABO])\b", r"I^\1I^\2", s)
    # Liên kết giới tính: XAXA -> X^AX^A, XAXa -> X^AX^a, XAY -> X^AY
    s = re.sub(r"\bX([ABDEHMRWabdehmrw])X([ABDEHMRWabdehmrw])\b", r"X^\1X^\2", s)
    s = re.sub(r"\bX([ABDEHMRWabdehmrw])Y([ABDEHMRWabdehmrw]?)\b", lambda m: f"X^{m.group(1)}Y^{m.group(2)}" if m.group(2) else f"X^{m.group(1)}Y", s)
    # Cặp base bổ sung DNA cũ G-X / G = X / G ≡ X -> G - C / G ≡ C (chỉ trong ngữ cảnh cặp base DNA)
    s = re.sub(r"\b([AT])\s*[-–]\s*([AT])\s*,\s*G\s*[-–≡=]\s*X\b", r"\1-\2, G-C", s)
    s = re.sub(r"\bG\s*≡\s*X\b", "G ≡ C", s)
    s = re.sub(r"\bX\s*≡\s*G\b", "C ≡ G", s)
    # Chiều mạch polynucleotide 5' -> 3' và 3' -> 5'
    s = re.sub(r"([35])['’]\s*->\s*([35])['’]", r"\1' → \2'", s)
    return s


def standardize_bio_text(text: str, location: str = "", fixes_log: Optional[List[Dict[str, str]]] = None) -> Tuple[str, int]:
    """
    Chuẩn hoá NFC + chính tả tiếng Việt + thuật ngữ/kiểu gene Sinh học 12 cho một chuỗi văn bản.
    Trả về: (văn bản đã chuẩn hoá, số lỗi đã tự động sửa).
    """
    if not text or not isinstance(text, str):
        return text or "", 0

    s = unicodedata.normalize("NFC", text)
    # Chuẩn hoá khoảng trắng & dấu câu cơ bản
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+([,.;:?!])", r"\1", s)
    s = re.sub(r"[ \t]{2,}", " ", s)

    fix_count = 0
    for rx, repl in COMPILED_SPELLING_RULES:
        def _sub_fn(m):
            nonlocal fix_count
            orig = m.group(0)
            target = _match_case(orig, repl)
            if orig == target:
                return orig
            fix_count += 1
            if fixes_log is not None and len(fixes_log) < 35:
                fixes_log.append({
                    "original": orig,
                    "fixed": target,
                    "location": location or "Nội dung",
                })
            return target
        s = rx.sub(_sub_fn, s)

    s2 = standardize_dna_and_genotype(s)
    if s2 != s:
        fix_count += 1
        if fixes_log is not None and len(fixes_log) < 35:
            fixes_log.append({
                "original": s[:60],
                "fixed": s2[:60],
                "location": f"{location} (Công thức/Kiểu gene)" if location else "Công thức/Kiểu gene",
            })
        s = s2

    return s, fix_count


def discover_reference_pdfs() -> Dict[str, Any]:
    """
    Tự động tìm các file PDF tham khảo 'SGK_SINH HỌC' và 'Đáp án' trong thư mục dự án
    (gồm thư mục gốc, data/, data/references/, data/sources/).
    """
    search_dirs = [
        BASE_DIR,
        os.path.join(BASE_DIR, "data"),
        os.path.join(BASE_DIR, "data", "references"),
        os.path.join(BASE_DIR, "data", "sources"),
        os.path.join(BASE_DIR, "references"),
    ]
    sgk_pdfs: List[str] = []
    answer_pdfs: List[str] = []
    seen: Set[str] = set()

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        try:
            entries = sorted(os.listdir(d))
        except Exception:
            continue
        for fn in entries:
            if not fn.lower().endswith(".pdf"):
                continue
            full = os.path.abspath(os.path.join(d, fn))
            if full in seen or not os.path.isfile(full):
                continue
            seen.add(full)
            norm = unicodedata.normalize("NFC", fn).lower()
            if "sgk" in norm and ("sinh" in norm or "12" in norm):
                sgk_pdfs.append(full)
            elif "đáp án" in norm or "dap an" in norm or "dapan" in norm:
                answer_pdfs.append(full)

    return {
        "sgk_pdfs": sgk_pdfs,
        "answer_pdfs": answer_pdfs,
    }


def _load_sgk_lexicon() -> Dict[str, Any]:
    """Đọc và cache danh mục từ vựng tiếng Việt + thuật ngữ từ PDF 'SGK_SINH HỌC' (nếu có)."""
    global _SGK_CACHE
    if _SGK_CACHE is not None:
        return _SGK_CACHE

    refs = discover_reference_pdfs()
    sgk_paths = refs["sgk_pdfs"]
    vocab: Set[str] = set()
    pages_read = 0
    source_name = ""

    if sgk_paths and PdfReader is not None:
        source_name = os.path.basename(sgk_paths[0])
        try:
            reader = PdfReader(sgk_paths[0])
            pages_read = len(reader.pages)
            for page in reader.pages:
                try:
                    txt = unicodedata.normalize("NFC", page.extract_text() or "")
                    for w in re.findall(r"[A-Za-zÀ-ỹĐđ]{2,}", txt):
                        vocab.add(w.lower())
                except Exception:
                    continue
        except Exception:
            pass

    _SGK_CACHE = {
        "available": bool(source_name and vocab),
        "source_name": source_name,
        "pages_read": pages_read,
        "vocab_size": len(vocab),
        "vocab": vocab,
        "answer_pdfs": [os.path.basename(p) for p in refs["answer_pdfs"]],
    }
    return _SGK_CACHE


def _find_suspect_spelling_words(texts: List[str], sgk_vocab: Set[str]) -> List[str]:
    """
    Phát hiện các từ nghi ngờ lỗi chính tả / lỗi font / ghép dấu sai (VD: 2 thanh điệu, phụ âm lạ,
    lỗi tách chữ OCR) và đối chiếu loại trừ với từ điển SGK_SINH HỌC.
    """
    suspects: List[str] = []
    seen: Set[str] = set()
    # Các mẫu chữ tiếng Việt bất thường thường do gõ nhầm Telex/VNI hoặc OCR PDF
    re_broken = re.compile(
        r"\b(?:[a-zà-ỹđ]*[ăâêôơư]{2,}[a-zà-ỹđ]*|[a-zà-ỹđ]*(?:aa|ee|oo|uw|ow|aw|dd)[a-zà-ỹđ]*|[bcdfghjklmnpqrstvwxz]{4,})\b",
        re.IGNORECASE,
    )
    allow_sci = {
        "aabb", "aabbdd", "aabbcc", "aabbccdd", "allele", "alleles", "amino", "chromosome",
        "codon", "darwin", "dna", "ecoli", "enzyme", "gene", "genes", "mendel", "morgan",
        "mrna", "nucleotide", "operon", "phenotype", "polypeptide", "polynucleotide",
        "protein", "ribosome", "rna", "rrna", "trna", "transposon", "uracil", "thymine",
        "adenine", "guanine", "cytosine", "lactose", "promoter", "operator", "intron", "exon",
        "crossing", "feedback", "biomass", "ecosystem", "biosphere", "species", "http", "https",
    }
    for t in texts:
        for m in re_broken.finditer(t or ""):
            w = m.group(0)
            wl = w.lower()
            if wl in seen or wl in allow_sci or wl in sgk_vocab:
                continue
            # Bỏ qua kiểu gene thuần (chỉ gồm A-H, a-h, X, Y, I, O)
            if re.match(r"^[A-Ha-hXYIO]{2,10}$", w):
                continue
            seen.add(wl)
            suspects.append(w)
            if len(suspects) >= 20:
                return suspects
    return suspects


def standardize_topic_content(topic_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chuẩn hoá toàn bộ một đối tượng Chủ đề (Lý thuyết, Hệ thống kiến thức, Câu hỏi ôn tập 3 phần):
    - Chuẩn hoá chính tả tiếng Việt & thuật ngữ Sinh học 12 chuẩn SGK
    - Chuẩn hoá công thức DNA & kiểu gene
    - Đối chiếu với nguồn tham khảo PDF SGK_SINH HỌC (nếu có)
    Trả về báo cáo spelling_report để hiển thị ngay ở màn hình Xem trước Chủ đề mới.
    """
    fixes_log: List[Dict[str, str]] = []
    total_fixes = 0
    all_texts: List[str] = []

    def fix_field(val: Any, loc: str) -> str:
        nonlocal total_fixes
        if not isinstance(val, str) or not val:
            return val if isinstance(val, str) else ""
        cleaned, cnt = standardize_bio_text(val, loc, fixes_log)
        total_fixes += cnt
        all_texts.append(cleaned)
        return cleaned

    topic_obj["title"] = fix_field(topic_obj.get("title", ""), "Tên Chủ đề")
    topic_obj["subtitle"] = fix_field(topic_obj.get("subtitle", ""), "Mô tả Chủ đề")

    for ls in topic_obj.get("lessons") or []:
        ls_tag = ls.get("number") or "Bài học"
        ls["title"] = fix_field(ls.get("title", ""), f"{ls_tag} - Tiêu đề")
        ls["summary"] = fix_field(ls.get("summary", ""), f"{ls_tag} - Tóm tắt")
        ls["key_takeaway"] = fix_field(ls.get("key_takeaway", ""), f"{ls_tag} - Ghi nhớ")
        for sec in ls.get("sections") or []:
            sec["heading"] = fix_field(sec.get("heading", ""), f"{ls_tag} - Mục")
            if isinstance(sec.get("points"), list):
                sec["points"] = [fix_field(p, f"{ls_tag} - Lý thuyết") for p in sec["points"]]
            for blk in sec.get("blocks") or []:
                if blk.get("type") == "text" or "text" in blk:
                    blk["text"] = fix_field(blk.get("text", ""), f"{ls_tag} - Lý thuyết")
                elif blk.get("type") == "image" and blk.get("caption"):
                    blk["caption"] = fix_field(blk.get("caption", ""), f"{ls_tag} - Chú thích ảnh")
                elif blk.get("type") == "table" and isinstance(blk.get("rows"), list):
                    blk["rows"] = [
                        [fix_field(c, f"{ls_tag} - Bảng") for c in row]
                        for row in blk["rows"]
                    ]

    ks = topic_obj.get("knowledge_system") or {}
    for unit in ks.get("units") or []:
        utag = f"HTKT {unit.get('lesson_number', '')}".strip()
        unit["lesson_title"] = fix_field(unit.get("lesson_title", ""), utag)
        for blk in unit.get("blocks") or []:
            if "text" in blk:
                blk["text"] = fix_field(blk.get("text", ""), utag)
            elif blk.get("type") == "table" and isinstance(blk.get("rows"), list):
                blk["rows"] = [[fix_field(c, utag) for c in row] for row in blk["rows"]]
    for br in (ks.get("mindmap") or {}).get("branches") or []:
        br["title"] = fix_field(br.get("title", ""), "Sơ đồ tư duy")
        if isinstance(br.get("nodes"), list):
            br["nodes"] = [fix_field(n, "Sơ đồ tư duy") for n in br["nodes"]]
    for fc in ks.get("flashcards") or []:
        fc["front"] = fix_field(fc.get("front", ""), "Thẻ ghi nhớ")
        fc["back"] = fix_field(fc.get("back", ""), "Thẻ ghi nhớ")

    rev = topic_obj.get("review") or {}
    for q in rev.get("mcq") or []:
        qtag = f"TN {q.get('lesson', '')} Câu {q.get('orig_num', '')}".strip()
        q["question"] = fix_field(q.get("question", ""), qtag)
        if isinstance(q.get("options"), list):
            q["options"] = [fix_field(o, qtag) for o in q["options"]]
        if q.get("explanation"):
            q["explanation"] = fix_field(q["explanation"], f"{qtag} - Giải chi tiết")
    for q in rev.get("true_false") or []:
        qtag = f"Đ/S {q.get('lesson', '')} Câu {q.get('orig_num', '')}".strip()
        q["stem"] = fix_field(q.get("stem", ""), qtag)
        for st in q.get("statements") or []:
            st["text"] = fix_field(st.get("text", ""), qtag)
            if st.get("explanation"):
                st["explanation"] = fix_field(st["explanation"], f"{qtag} - Giải chi tiết")
        if q.get("explanation"):
            q["explanation"] = fix_field(q["explanation"], f"{qtag} - Giải chi tiết")
    for q in rev.get("short_answer") or []:
        qtag = f"TLN {q.get('lesson', '')} Câu {q.get('orig_num', '')}".strip()
        q["question"] = fix_field(q.get("question", ""), qtag)
        if q.get("explanation"):
            q["explanation"] = fix_field(q["explanation"], f"{qtag} - Giải chi tiết")

    sgk_info = _load_sgk_lexicon()
    suspects = _find_suspect_spelling_words(all_texts, sgk_info.get("vocab") or set())

    return {
        "auto_fixed_count": total_fixes,
        "fixes_examples": fixes_log[:25],
        "suspect_words": suspects,
        "sgk_reference": {
            "available": sgk_info["available"],
            "source_name": sgk_info["source_name"],
            "pages_read": sgk_info["pages_read"],
            "vocab_size": sgk_info["vocab_size"],
            "answer_pdfs_found": sgk_info["answer_pdfs"],
        },
    }


def standardize_exam_content(content: Dict[str, Any]) -> Dict[str, Any]:
    """Chuẩn hoá chính tả & kiểu gene cho đề thi thử / đề trộn từ file Word."""
    fixes_log: List[Dict[str, str]] = []
    total_fixes = 0
    all_texts: List[str] = []

    def fix_field(val: Any, loc: str) -> str:
        nonlocal total_fixes
        if not isinstance(val, str) or not val:
            return val if isinstance(val, str) else ""
        cleaned, cnt = standardize_bio_text(val, loc, fixes_log)
        total_fixes += cnt
        all_texts.append(cleaned)
        return cleaned

    for i, q in enumerate(content.get("mcq") or [], 1):
        tag = f"Phần I - Câu {i}"
        q["question"] = fix_field(q.get("question", ""), tag)
        if isinstance(q.get("options"), list):
            q["options"] = [fix_field(o, tag) for o in q["options"]]
        if q.get("explanation"):
            q["explanation"] = fix_field(q["explanation"], f"{tag} - Giải chi tiết")

    for i, q in enumerate(content.get("true_false") or [], 1):
        tag = f"Phần II - Câu {i}"
        key_name = "stem" if "stem" in q else "question"
        q[key_name] = fix_field(q.get(key_name, ""), tag)
        for st in q.get("statements") or []:
            st["text"] = fix_field(st.get("text", ""), tag)
        if q.get("explanation"):
            q["explanation"] = fix_field(q["explanation"], f"{tag} - Giải chi tiết")

    for i, q in enumerate(content.get("short_answer") or [], 1):
        tag = f"Phần III - Câu {i}"
        q["question"] = fix_field(q.get("question", ""), tag)
        if q.get("explanation"):
            q["explanation"] = fix_field(q["explanation"], f"{tag} - Giải chi tiết")

    sgk_info = _load_sgk_lexicon()
    suspects = _find_suspect_spelling_words(all_texts, sgk_info.get("vocab") or set())
    return {
        "auto_fixed_count": total_fixes,
        "fixes_examples": fixes_log[:20],
        "suspect_words": suspects,
        "sgk_reference": {
            "available": sgk_info["available"],
            "source_name": sgk_info["source_name"],
        },
    }


# ================== ĐỐI CHIẾU & KHỚP ĐÁP ÁN TỪ FILE PDF "ĐÁP ÁN" ==================

LETTER_TO_IDX = {"A": 0, "B": 1, "C": 2, "D": 3}


def _parse_tf_vals(raw: str) -> Optional[List[Optional[bool]]]:
    s = (raw or "").strip()
    if not s:
        return None
    res: Dict[str, bool] = {}
    for m in re.finditer(r"([a-d])\s*[\)\.\-–:]?\s*(Đúng|Sai|Đ|S|True|False|T|F)\b", s, re.IGNORECASE):
        k = m.group(1).lower()
        v = m.group(2).strip().upper()
        res[k] = v in ("ĐÚNG", "Đ", "TRUE", "T")
    if len(res) >= 2:
        return [res.get(k) for k in ("a", "b", "c", "d")]
    compact = re.sub(r"[^ĐSDTFđsdtf]", "", s).upper()
    if len(compact) == 4:
        return [ch in ("Đ", "D", "T") for ch in compact]
    words = re.findall(r"\b(Đúng|Sai|Đ|S)\b", s, re.IGNORECASE)
    if len(words) == 4:
        return [w.strip().upper() in ("ĐÚNG", "Đ") for w in words]
    return None


def _normalize_sa_pair(raw: str) -> List[str]:
    v = re.sub(r"\s*\([^\)]+\)", "", (raw or "").strip()).strip()
    if not v or re.match(r"^[…\.\-_]+$", v):
        return []
    acc = [v]
    if "," in v:
        acc.append(v.replace(",", "."))
    elif "." in v:
        acc.append(v.replace(".", ","))
    return acc


def parse_answer_pdf_keys(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Trích xuất bảng đáp án & giải chi tiết từ file PDF 'Đáp án' (hỗ trợ cả phân theo từng Bài lẫn toàn Chủ đề).
    Trả về:
      {
        "by_lesson": { lesson_idx_1based: {"mcq": {qnum: idx}, "tf": {qnum: [bool..]}, "sa": {qnum: [str..]}, "exp": {(part, qnum): str}} },
        "global": {"mcq": {}, "tf": {}, "sa": {}, "exp": {}},
      }
    """
    if PdfReader is None:
        raise RuntimeError("Thiếu thư viện pypdf trên máy chủ để đọc file PDF Đáp án.")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    lines: List[str] = []
    for page in reader.pages:
        try:
            raw = unicodedata.normalize("NFC", page.extract_text() or "")
            for ln in raw.splitlines():
                cl = re.sub(r"[ \t]+", " ", ln.replace("\u00a0", " ")).strip()
                if cl:
                    lines.append(cl)
        except Exception:
            continue

    by_lesson: Dict[int, Dict[str, Any]] = {}
    global_bucket: Dict[str, Any] = {"mcq": {}, "tf": {}, "sa": {}, "exp": {}}

    def get_bucket(l_idx: int) -> Dict[str, Any]:
        if l_idx <= 0:
            return global_bucket
        if l_idx not in by_lesson:
            by_lesson[l_idx] = {"mcq": {}, "tf": {}, "sa": {}, "exp": {}}
        return by_lesson[l_idx]

    cur_lesson = 0
    cur_part = "mcq"
    cur_exp_target: Optional[Tuple[int, str, int]] = None

    re_lesson = re.compile(r"^(?:BÀI\s*(\d+)|[1-9]\.(\d+)[\.\:\s])", re.IGNORECASE)
    re_p1 = re.compile(r"PHẦN\s*(?:I\b|1\b)|TRẮC\s+NGHIỆM\s+(?:NHIỀU|4\s+ĐÁP|KHÁCH)", re.IGNORECASE)
    re_p2 = re.compile(r"PHẦN\s*(?:II\b|2\b)|ĐÚNG\s*[/\-–]?\s*SAI", re.IGNORECASE)
    re_p3 = re.compile(r"PHẦN\s*(?:III\b|3\b)|TRẢ\s+LỜI\s+NGẮN", re.IGNORECASE)

    for ln in lines:
        ml = re_lesson.match(ln)
        if ml and len(ln) < 120 and not re.match(r"^Câu\s*\d+", ln, re.IGNORECASE):
            cur_lesson = int(ml.group(1) or ml.group(2) or 0)
            cur_exp_target = None
            continue
        if re_p1.search(ln) and len(ln) < 120:
            cur_part = "mcq"
            cur_exp_target = None
            continue
        if re_p2.search(ln) and len(ln) < 120:
            cur_part = "true_false"
            cur_exp_target = None
            continue
        if re_p3.search(ln) and len(ln) < 120:
            cur_part = "short_answer"
            cur_exp_target = None
            continue

        bk = get_bucket(cur_lesson)
        if cur_part == "mcq":
            pairs = re.findall(r"(?:Câu\s*)?(\d+)\s*[\.\:\-–\s]\s*([A-D])(?![a-zA-ZÀ-ỹ])", ln, re.IGNORECASE)
            if not pairs:
                pairs = re.findall(r"\b(\d{1,3})([A-D])\b", ln)
            if pairs and len(ln) < 300 and not re.search(r"giải\s*chi\s*tiết|vì\s", ln, re.IGNORECASE):
                for num_s, let in pairs:
                    qn = int(num_s)
                    idx_val = LETTER_TO_IDX[let.upper()]
                    bk["mcq"][qn] = idx_val
                    global_bucket["mcq"].setdefault(qn, idx_val)
                cur_exp_target = None
                continue
            m_q = re.match(r"^\s*Câu\s*(\d+)\s*(?:\(([A-D])\))?\s*[:\.\-–]\s*(.*)$", ln, re.IGNORECASE)
            if m_q:
                qn = int(m_q.group(1))
                rest = m_q.group(3).strip()
                if m_q.group(2):
                    bk["mcq"][qn] = LETTER_TO_IDX[m_q.group(2).upper()]
                else:
                    mp = re.search(r"(?:Chọn|Đáp\s*án)\s*[:\s]*([A-D])\b", rest, re.IGNORECASE)
                    if mp:
                        bk["mcq"][qn] = LETTER_TO_IDX[mp.group(1).upper()]
                if rest:
                    bk["exp"][("mcq", qn)] = (bk["exp"].get(("mcq", qn), "") + "\n" + rest).strip()
                cur_exp_target = (cur_lesson, "mcq", qn)
                continue

        elif cur_part == "true_false":
            m_tf = re.match(r"^\s*(?:Câu\s*)?(\d+)\s*[:\.\-–]\s*(.*)$", ln, re.IGNORECASE)
            if m_tf:
                qn = int(m_tf.group(1))
                rest = m_tf.group(2).strip()
                parsed = _parse_tf_vals(rest)
                if parsed:
                    bk["tf"][qn] = parsed
                    global_bucket["tf"].setdefault(qn, parsed)
                if rest and (not parsed or len(rest) > 22):
                    bk["exp"][("true_false", qn)] = (bk["exp"].get(("true_false", qn), "") + "\n" + rest).strip()
                cur_exp_target = (cur_lesson, "true_false", qn)
                continue

        else:  # short_answer
            sa_pairs = re.findall(r"(?:Câu\s*)?(\d+)\s*[:\.\-–]\s*([-+]?\d+(?:[,\.]\d+)?)", ln, re.IGNORECASE)
            if sa_pairs and len(sa_pairs) >= 2:
                for num_s, val in sa_pairs:
                    qn = int(num_s)
                    acc = _normalize_sa_pair(val)
                    if acc:
                        bk["sa"][qn] = acc
                        global_bucket["sa"].setdefault(qn, acc)
                cur_exp_target = None
                continue
            m_sa = re.match(r"^\s*(?:Câu\s*)?(\d+)\s*[:\.\-–]\s*(.*)$", ln, re.IGNORECASE)
            if m_sa:
                qn = int(m_sa.group(1))
                rest = m_sa.group(2).strip()
                # Hỗ trợ cả "A. 12,5" lẫn "12,5"
                m_a = re.match(r"^(?:A\s*[\.\:\)]\s*|(?:Đáp\s*án|Đáp\s*số)\s*[:\.\-–]?\s*)?([-+]?\d+(?:[,\.]\d+)?)", rest, re.IGNORECASE)
                if m_a:
                    acc = _normalize_sa_pair(m_a.group(1))
                    if acc:
                        bk["sa"][qn] = acc
                        global_bucket["sa"].setdefault(qn, acc)
                if len(rest) > 10:
                    bk["exp"][("short_answer", qn)] = (bk["exp"].get(("short_answer", qn), "") + "\n" + rest).strip()
                cur_exp_target = (cur_lesson, "short_answer", qn)
                continue

        # Dòng tiếp theo của lời giải chi tiết hoặc "A. <giá trị>" cho trả lời ngắn
        if cur_exp_target:
            cl, cp, cq = cur_exp_target
            tbk = get_bucket(cl)
            if cp == "short_answer" and cq not in tbk["sa"]:
                m_sa_a = re.match(r"^\s*A\s*[\.\:\)]\s*([-+]?\d+(?:[,\.]\d+)?)", ln)
                if m_sa_a:
                    acc = _normalize_sa_pair(m_sa_a.group(1))
                    if acc:
                        tbk["sa"][cq] = acc
            tbk["exp"][(cp, cq)] = (tbk["exp"].get((cp, cq), "") + "\n" + ln).strip()

    return {"by_lesson": by_lesson, "global": global_bucket}


def apply_answer_pdf_to_topic(topic_obj: Dict[str, Any], pdf_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """Khớp đáp án & giải chi tiết từ file PDF 'Đáp án' vào toàn bộ câu hỏi của Chủ đề."""
    parsed = parse_answer_pdf_keys(pdf_bytes)
    by_lesson = parsed["by_lesson"]
    gl = parsed["global"]

    lessons = topic_obj.get("lessons") or []
    lesson_id_to_idx = {ls.get("id"): idx for idx, ls in enumerate(lessons, 1)}

    rev = topic_obj.get("review") or {}
    matched_mcq = 0
    matched_tf = 0
    matched_sa = 0

    for i, q in enumerate(rev.get("mcq") or [], 1):
        l_idx = lesson_id_to_idx.get(q.get("lesson_id"), 0)
        qn = int(q.get("orig_num") or i)
        bk = by_lesson.get(l_idx) or {}
        key_val = (bk.get("mcq") or {}).get(qn)
        if key_val is None:
            key_val = (gl.get("mcq") or {}).get(qn) or (gl.get("mcq") or {}).get(i)
        if key_val is not None and not q.get("answer_key_ready"):
            q["correct_index"] = key_val
            q["answer_key_ready"] = True
            matched_mcq += 1
        exp = (bk.get("exp") or {}).get(("mcq", qn)) or (gl.get("exp") or {}).get(("mcq", qn))
        if exp and not q.get("explanation"):
            q["explanation"], _ = standardize_bio_text(exp)

    for i, q in enumerate(rev.get("true_false") or [], 1):
        l_idx = lesson_id_to_idx.get(q.get("lesson_id"), 0)
        qn = int(q.get("orig_num") or i)
        bk = by_lesson.get(l_idx) or {}
        vals = (bk.get("tf") or {}).get(qn) or (gl.get("tf") or {}).get(qn) or (gl.get("tf") or {}).get(i)
        if vals and not q.get("answer_key_ready"):
            stmts = q.get("statements") or []
            ok_any = False
            for si, st in enumerate(stmts):
                if si < len(vals) and vals[si] is not None and st.get("answer") is None:
                    st["answer"] = vals[si]
                    ok_any = True
            if ok_any and stmts and all(st.get("answer") is not None for st in stmts):
                q["answer_key_ready"] = True
                matched_tf += 1
        exp = (bk.get("exp") or {}).get(("true_false", qn)) or (gl.get("exp") or {}).get(("true_false", qn))
        if exp and not q.get("explanation"):
            q["explanation"], _ = standardize_bio_text(exp)

    for i, q in enumerate(rev.get("short_answer") or [], 1):
        l_idx = lesson_id_to_idx.get(q.get("lesson_id"), 0)
        qn = int(q.get("orig_num") or i)
        bk = by_lesson.get(l_idx) or {}
        acc = (bk.get("sa") or {}).get(qn) or (gl.get("sa") or {}).get(qn) or (gl.get("sa") or {}).get(i)
        if acc and not q.get("answer_key_ready"):
            q["accepted_answers"] = acc
            q["answer_key_ready"] = True
            matched_sa += 1
        exp = (bk.get("exp") or {}).get(("short_answer", qn)) or (gl.get("exp") or {}).get(("short_answer", qn))
        if exp and not q.get("explanation"):
            q["explanation"], _ = standardize_bio_text(exp)

    return {
        "source_name": filename or "PDF Đáp án",
        "matched_mcq": matched_mcq,
        "matched_tf": matched_tf,
        "matched_sa": matched_sa,
        "total_matched": matched_mcq + matched_tf + matched_sa,
    }
