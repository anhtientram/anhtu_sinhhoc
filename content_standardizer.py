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
    # Chuẩn hoá thuật ngữ GDPT 2018 (SGK Sinh học 10–12 mới)
    (r"\bADN\b", "DNA"),
    (r"\bARN\b", "RNA"),
    (r"\bmARN\b", "mRNA"),
    (r"\btARN\b", "tRNA"),
    (r"\brARN\b", "rRNA"),
    (r"\bnuclêôtit\b", "nucleotide"),
    (r"\bnucleotit\b", "nucleotide"),
    (r"\bpôlinuclêôtit\b", "polynucleotide"),
    (r"\bpolinucleotit\b", "polynucleotide"),
    (r"\bpôlipeptit\b", "polypeptide"),
    (r"\bpolipeptit\b", "polypeptide"),
    (r"\baxit\s+amin\b", "amino acid"),
    (r"\baxit\s+nuclêic\b", "nucleic acid"),
    (r"\baxit\s+nucleic\b", "nucleic acid"),
    (r"\baxit\s+piruvic\b", "pyruvic acid"),
    (r"\baxit\s+pyruvic\b", "pyruvic acid"),
    (r"\baxit\s+lactic\b", "lactic acid"),
    (r"\bribôxôm\b", "ribosome"),
    (r"\bribôxom\b", "ribosome"),
    (r"\benzim\b", "enzyme"),
    (r"\bprôtêin\b", "protein"),
    (r"\bhoocmôn\b", "hormone"),
    (r"\bhoocmon\b", "hormone"),
    (r"\bcôđon\b", "codon"),
    (r"\bcôđôn\b", "codon"),
    (r"\banticôđon\b", "anticodon"),
    (r"\banticôđôn\b", "anticodon"),
    (r"\bôpêron\b", "operon"),
    (r"\bopêron\b", "operon"),
    (r"\bOpreron\b", "Operon"),
    (r"\bprômôtơ\b", "promoter"),
    (r"\btilacôit\b", "thylakoid"),
    (r"\btilacoit\b", "thylakoid"),
    (r"\bclorôphin\b", "chlorophyll"),
    (r"\bclorophin\b", "chlorophyll"),
    (r"\bcarôtenôit\b", "carotenoid"),
    (r"\bcarotenoit\b", "carotenoid"),
    (r"\bglucôzơ\b", "glucose"),
    (r"\bglucozơ\b", "glucose"),
    (r"\bfructôzơ\b", "fructose"),
    (r"\bsaccarôzơ\b", "saccharose"),
    (r"\blactôzơ\b", "lactose"),
    (r"\bcacbohiđrat\b", "carbohydrate"),
    (r"\bcacbohydrat\b", "carbohydrate"),
    (r"\blipit\b", "lipid"),
    (r"\bhiđrô\b", "hydrogen"),
    (r"\bhiđro\b", "hydrogen"),
    (r"\bôxi\b(?!\s*h[oóò]a)", "oxygen"),
    (r"\bnitơ\b", "nitrogen"),
    (r"\bcacbon\b", "carbon"),
    (r"\bphôtpho\b", "phosphorus"),
    (r"\balen\b", "allele"),
    (r"\bgen\b", "gene"),
    (r"\bthành\s+dảy\b", "thành dày"),
    (r"\bcường\s+độ\s+anh\s+sáng\b", "cường độ ánh sáng"),
    (r"\bthoát\s+rA\b", "thoát ra"),
    (r"\bgầu\s+hết\b", "hầu hết"),
    (r"\bquá\s+tình\b", "quá trình"),
    (r"\bvới\s+nahu\b", "với nhau"),
    (r"\bquấn\s+xã\b", "quần xã"),
    (r"\bhình\s+thúc\b", "hình thức"),
    (r"\bhiệu\s+úng\b", "hiệu ứng"),
    (r"\btiêu\s+diệ\b", "tiêu diệt"),
    (r"\bđuợc\b", "được"),
    (r"\btỏng\s+gan\b", "trong gan"),
    (r"\btáo\s+giáp\b", "tảo giáp"),
    (r"\bđộ\s+đang\s+dạng\b", "độ đa dạng"),
    (r"\bđộ\s+phóng\s+phú\b", "độ phong phú"),
    (r"\bdữtrong\b", "dữ trong"),
    (r"\bCóbao\b", "Có bao"),
    (r"\bnề\s+nông\s+nghiệp\b", "nền nông nghiệp"),
    (r"\bnghiện\s+cứu\b", "nghiên cứu"),
    (r"\bhộ\s+trợ\b", "hỗ trợ"),
    (r"\bbiển\s+đông\s+về\s+mực\s+nước\b", "biến động về mực nước"),
    (r"\btát\s+cả\b", "tất cả"),
    (r"\bsố\s+tàng\b", "số tầng"),
    (r"\btrung\s+binh\b", "trung bình"),
    (r"\bđiều\s+chính\s+kích\s+thước\b", "điều chỉnh kích thước"),
    (r"\bsố\s+lượng\s+cả\s+thể\b", "số lượng cá thể"),
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
    # Dấu lai × giữa 2 kiểu gene (chỉ áp dụng khi cả 2 vế thực sự có ký hiệu kiểu gene)
    s = re.sub(
        r"(\b(?:[A-H][a-h](?:[A-H][a-h]){0,3}|[A-H]{2}(?:[A-H]{2})?|[a-h]{2}(?:[a-h]{2})?|[A-Za-z]{2,4}/[A-Za-z]{2,4}|[XYI]\^?[A-Za-z]{1,4}[XYI]?\^?[A-Za-z]{0,4}))\s+[xX]\s+(?=(?:[A-H][a-h]|[A-H]{2}|[a-h]{2}|[A-Za-z]{2,4}/|[XYI]\^))",
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


def _ascii_lower_norm(s: str) -> str:
    n = unicodedata.normalize("NFC", s or "").lower().replace("đ", "d")
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", n).strip()


def discover_reference_pdfs() -> Dict[str, Any]:
    """
    Tự động tìm các file PDF tham khảo 'SGK_SINH HỌC' và các file trong thư mục 'ĐÁP ÁN'
    (gồm thư mục gốc, ĐÁP ÁN/, data/, data/ĐÁP ÁN/, data/references/, data/sources/).
    """
    search_dirs = [
        BASE_DIR,
        os.path.join(BASE_DIR, "data"),
        os.path.join(BASE_DIR, "data", "references"),
        os.path.join(BASE_DIR, "data", "sources"),
        os.path.join(BASE_DIR, "references"),
    ]
    # Tự động quét thêm thư mục tên "ĐÁP ÁN" / "DAP AN" / "SGK..." (hỗ trợ cả Unicode NFC/NFD trên macOS)
    for root in (BASE_DIR, os.path.join(BASE_DIR, "data")):
        if not os.path.isdir(root):
            continue
        try:
            for entry in sorted(os.listdir(root)):
                full_d = os.path.join(root, entry)
                if os.path.isdir(full_d):
                    an = _ascii_lower_norm(entry)
                    if "dap an" in an or "dapan" in an or "sgk" in an:
                        search_dirs.append(full_d)
        except Exception:
            continue

    sgk_pdfs: List[str] = []
    answer_pdfs: List[str] = []
    seen: Set[str] = set()

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        dir_is_answer = "dap an" in _ascii_lower_norm(os.path.basename(d)) or "dapan" in _ascii_lower_norm(os.path.basename(d))
        try:
            walker = os.walk(d) if dir_is_answer else [(d, [], sorted(os.listdir(d)))]
        except Exception:
            continue
        for cur_d, dirnames, entries in walker:
            if dir_is_answer:
                dirnames[:] = sorted(x for x in dirnames if not x.startswith("."))
            for fn in sorted(entries):
                if fn.startswith(".") or not fn.lower().endswith(".pdf"):
                    continue
                full = os.path.abspath(os.path.join(cur_d, fn))
                if full in seen or not os.path.isfile(full):
                    continue
                seen.add(full)
                norm = _ascii_lower_norm(fn)
                if "sgk" in norm and ("sinh" in norm or "12" in norm):
                    sgk_pdfs.append(full)
                elif dir_is_answer or "dap an" in norm or "dapan" in norm or "hdg" in norm:
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

    def fix_stem_blocks(q_obj: Dict[str, Any], tag: str):
        for blk in q_obj.get("stem_blocks") or []:
            if blk.get("type") == "text" and isinstance(blk.get("text"), str):
                blk["text"] = fix_field(blk["text"], tag)
            elif blk.get("type") == "table" and isinstance(blk.get("rows"), list):
                blk["rows"] = [[fix_field(c, f"{tag} - Bảng") for c in row] for row in blk["rows"]]
        if isinstance(q_obj.get("tables"), list):
            q_obj["tables"] = [
                [[fix_field(c, f"{tag} - Bảng") for c in row] for row in tbl]
                for tbl in q_obj["tables"]
            ]

    for i, q in enumerate(content.get("mcq") or [], 1):
        tag = f"Phần I - Câu {i}"
        q["question"] = fix_field(q.get("question", ""), tag)
        fix_stem_blocks(q, tag)
        if isinstance(q.get("options"), list):
            q["options"] = [fix_field(o, tag) for o in q["options"]]
        if q.get("explanation"):
            q["explanation"] = fix_field(q["explanation"], f"{tag} - Giải chi tiết")

    for i, q in enumerate(content.get("true_false") or [], 1):
        tag = f"Phần II - Câu {i}"
        key_name = "stem" if "stem" in q else "question"
        q[key_name] = fix_field(q.get(key_name, ""), tag)
        fix_stem_blocks(q, tag)
        for st in q.get("statements") or []:
            st["text"] = fix_field(st.get("text", ""), tag)
        if q.get("explanation"):
            q["explanation"] = fix_field(q["explanation"], f"{tag} - Giải chi tiết")

    for i, q in enumerate(content.get("short_answer") or [], 1):
        tag = f"Phần III - Câu {i}"
        q["question"] = fix_field(q.get("question", ""), tag)
        fix_stem_blocks(q, tag)
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
    for m in re.finditer(r"([a-d])\s*[\)\.\-–:\s]?\s*(Đúng|Sai|Đ|S|True|False|T|F)\b", s, re.IGNORECASE):
        k = m.group(1).lower()
        v = m.group(2).strip().upper()
        res[k] = v in ("ĐÚNG", "Đ", "TRUE", "T")
    if len(res) >= 2:
        return [res.get(k) for k in ("a", "b", "c", "d")]
    # Dạng viết liền 4 chữ: ĐSĐS, DSSD, Đ-S-Đ-Đ
    stripped_seq = re.sub(r"[\s,;|\-–/]+", "", s).upper()
    if re.fullmatch(r"[ĐSDTF]{4}", stripped_seq):
        return [ch in ("Đ", "D", "T") for ch in stripped_seq]
    words = re.findall(r"(?:^|[\s,;|\-–/])(Đúng|Sai|Đ|S)(?=$|[\s,;|\-–/\.])", s, re.IGNORECASE)
    if len(words) == 4:
        return [w.strip().upper() in ("ĐÚNG", "Đ") for w in words]
    return None


def _normalize_sa_pair(raw: str) -> List[str]:
    v = re.sub(r"\s*\([^\)]+\)", "", (raw or "").strip()).strip()
    v = v.strip(" .;:–-")
    if not v or re.match(r"^[…\.\-_]+$", v):
        return []
    acc = [v]
    if "," in v:
        acc.append(v.replace(",", "."))
    elif "." in v:
        acc.append(v.replace(".", ","))
    return acc


def _extract_table_number_row(ln: str) -> Optional[List[int]]:
    """Nhận diện dòng tiêu đề số câu trong bảng đáp án 2 hàng (VD: 'Câu 1 2 3 4 5 6 7 8 9 10' hoặc '1 2 3 4 5')."""
    s = re.sub(r"^(?:Câu(?:\s*hỏi)?|STT|Bài)\s*[:\.\-–]?\s*", "", ln.strip(), flags=re.IGNORECASE)
    toks = re.split(r"[\s|,\t]+", s.strip())
    toks = [t for t in toks if t]
    if len(toks) < 2:
        return None
    if all(re.fullmatch(r"\d{1,3}", t) for t in toks):
        nums = [int(t) for t in toks]
        # Kiểm tra dãy số hợp lý (tăng dần hoặc nằm trong khoảng 1..200)
        if all(1 <= n <= 250 for n in nums):
            return nums
    return None


def _extract_table_letter_row(ln: str) -> Optional[List[str]]:
    """Nhận diện dòng chữ cái đáp án trong bảng 2 hàng (VD: 'Đáp án A B C D A B C D' hoặc 'A B C D')."""
    s = re.sub(r"^(?:Đáp\s*án|Chọn|Key|ĐA)\s*[:\.\-–]?\s*", "", ln.strip(), flags=re.IGNORECASE)
    toks = re.split(r"[\s|,\t]+", s.strip())
    toks = [t.upper() for t in toks if t]
    if len(toks) < 2:
        return None
    if all(t in ("A", "B", "C", "D") for t in toks):
        return toks
    return None


def _extract_table_sa_row(ln: str) -> Optional[List[str]]:
    """Nhận diện dòng giá trị số trong bảng đáp án Trả lời ngắn 2 hàng (VD: 'Đáp án 4 2 0,25 3')."""
    s = re.sub(r"^(?:Đáp\s*án|Đáp\s*số|Kết\s*quả|Key|ĐA)\s*[:\.\-–]?\s*", "", ln.strip(), flags=re.IGNORECASE)
    toks = re.split(r"[\s|\t]+", s.strip())
    toks = [t.strip(";") for t in toks if t.strip(";")]
    if len(toks) < 2:
        return None
    if all(re.fullmatch(r"[-+]?\d+(?:[,\.]\d+)?%?", t) for t in toks):
        return toks
    return None


def _new_answer_bucket(title: str = "", lesson_num: int = 0) -> Dict[str, Any]:
    return {
        "title": title,
        "lesson_num": lesson_num,
        "mcq": {},
        "tf": {},
        "sa": {},
        "reading": {},
        "exp": {},
    }


def _ocr_scanned_pdf_lines(pdf_bytes: bytes, max_pages: int = 40) -> List[str]:
    """
    Tự động OCR tiếng Việt cho file PDF dạng ảnh chụp/scan (không có lớp văn bản):
    - Trên macOS: dùng JXA (`osascript -l JavaScript`) gọi trực tiếp Apple Vision + PDFKit
      (tích hợp sẵn trên mọi máy Mac, khởi chạy tức thì, không cần Xcode/Swift compiler).
    - Trên Linux: thử pdftoppm + tesseract (nếu có sẵn).
    """
    import shutil
    import subprocess
    import sys
    import tempfile

    lines_out: List[str] = []
    if sys.platform == "darwin" and shutil.which("osascript"):
        jxa_code = r'''
ObjC.import("Foundation");
ObjC.import("PDFKit");
ObjC.import("Vision");
ObjC.import("AppKit");

function run(argv) {
  if (!argv || argv.length < 1) return "";
  var pdfPath = argv[0];
  var maxPages = argv.length >= 2 ? parseInt(argv[1], 10) : 40;
  if (isNaN(maxPages) || maxPages <= 0) maxPages = 40;
  var url = $.NSURL.fileURLWithPath(pdfPath);
  var doc = $.PDFDocument.alloc.initWithURL(url);
  if (!doc || doc.isNil()) return "";
  var total = Math.min(doc.pageCount, maxPages);
  var outLines = [];

  for (var i = 0; i < total; i++) {
    var page = doc.pageAtIndex(i);
    if (!page || page.isNil()) continue;
    var bounds = page.boundsForBox($.kPDFDisplayBoxMediaBox);
    var scale = 2.0;
    var w = Math.max(1, Math.round(bounds.size.width * scale));
    var h = Math.max(1, Math.round(bounds.size.height * scale));
    var rep = $.NSBitmapImageRep.alloc.initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(
      null, w, h, 8, 4, true, false, $.NSCalibratedRGBColorSpace, 0, 0
    );
    var ctx = $.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep);
    $.NSGraphicsContext.saveGraphicsState;
    $.NSGraphicsContext.setCurrentContext(ctx);
    var cg = ctx.CGContext;
    $.NSColor.whiteColor.setFill;
    $.NSRectFill($.NSMakeRect(0, 0, w, h));
    var t = $.NSAffineTransform.transform;
    t.scaleBy(scale);
    t.concat;
    page.drawWithBoxToContext($.kPDFDisplayBoxMediaBox, cg);
    $.NSGraphicsContext.restoreGraphicsState;

    var cgImg = rep.CGImage;
    var req = $.VNRecognizeTextRequest.alloc.init;
    req.setRecognitionLevel($.VNRequestTextRecognitionLevelAccurate);
    req.setUsesLanguageCorrection(true);
    req.setRecognitionLanguages($(["vi-VN", "en-US"]));
    var handler = $.VNImageRequestHandler.alloc.initWithCGImageOptions(cgImg, $({}));
    var err = Ref();
    handler.performRequestsError($([req]), err);
    var results = req.results;
    if (!results || results.isNil()) continue;
    var cnt = results.count;
    var items = [];
    for (var j = 0; j < cnt; j++) {
      var obs = results.objectAtIndex(j);
      var cands = obs.topCandidates(1);
      if (!cands || cands.count === 0) continue;
      var txt = ObjC.unwrap(cands.objectAtIndex(0).string);
      var bb = obs.boundingBox;
      items.push({ y: bb.origin.y + bb.size.height / 2, x: bb.origin.x, text: txt });
    }
    items.sort(function(a, b) {
      if (Math.abs(a.y - b.y) > 0.012) return b.y - a.y;
      return a.x - b.x;
    });
    var rows = [];
    for (var k = 0; k < items.length; k++) {
      var it = items[k];
      if (rows.length && Math.abs(it.y - rows[rows.length - 1][0].y) <= 0.012) {
        rows[rows.length - 1].push(it);
      } else {
        rows.push([it]);
      }
    }
    for (var r = 0; r < rows.length; r++) {
      rows[r].sort(function(a, b) { return a.x - b.x; });
      outLines.push(rows[r].map(function(z) { return z.text; }).join("  "));
    }
  }
  return outLines.join("\n");
}
'''
        with tempfile.TemporaryDirectory(prefix="pdfocr_") as tmp:
            pdf_file = os.path.join(tmp, "in.pdf")
            js_file = os.path.join(tmp, "ocr.js")
            with open(pdf_file, "wb") as f:
                f.write(pdf_bytes)
            with open(js_file, "w", encoding="utf-8") as f:
                f.write(jxa_code)
            try:
                proc = subprocess.run(
                    ["osascript", "-l", "JavaScript", js_file, pdf_file, str(max_pages)],
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                if proc.returncode == 0 and proc.stdout:
                    for ln in unicodedata.normalize("NFC", proc.stdout).splitlines():
                        cl = re.sub(r"[ \t]+", " ", ln.replace("\u00a0", " ")).strip()
                        if cl:
                            lines_out.append(cl)
            except Exception:
                pass
    elif shutil.which("pdftoppm") and shutil.which("tesseract"):
        with tempfile.TemporaryDirectory(prefix="pdfocr_") as tmp:
            pdf_file = os.path.join(tmp, "in.pdf")
            with open(pdf_file, "wb") as f:
                f.write(pdf_bytes)
            try:
                subprocess.run(
                    ["pdftoppm", "-png", "-r", "200", "-l", str(max_pages), pdf_file, os.path.join(tmp, "p")],
                    check=False,
                    timeout=90,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                pngs = sorted(fn for fn in os.listdir(tmp) if fn.endswith(".png"))
                for png in pngs:
                    pr = subprocess.run(
                        ["tesseract", os.path.join(tmp, png), "stdout", "-l", "vie+eng"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if pr.stdout:
                        for ln in unicodedata.normalize("NFC", pr.stdout).splitlines():
                            cl = re.sub(r"[ \t]+", " ", ln.replace("\u00a0", " ")).strip()
                            if cl:
                                lines_out.append(cl)
            except Exception:
                pass
    return lines_out


def _slice_pdf_lines_for_topic(
    lines: List[str],
    topic_order_index: Optional[int] = None,
    topic_title: str = "",
) -> List[str]:
    """
    Nếu file PDF Đáp án chứa nhiều Chủ đề (VD: 'Sinh học 12 - Đáp án hoàn chỉnh.pdf' gồm Chủ đề 1..7),
    tự động tách đúng đoạn thuộc Chủ đề mục tiêu để không bị trộn lẫn đáp án giữa các Chủ đề.
    """
    if not lines or not topic_order_index:
        return lines

    re_topic_hdr = re.compile(r"^(?:PHẦN\s+[A-Z0-9]+\s*[\.\:\-]\s*)?(?:CHỦ\s*ĐỀ|CHƯƠNG)\s*(\d+)\b", re.IGNORECASE)
    spans: List[Tuple[int, int, str]] = []  # (line_idx, topic_num, line_text)
    for idx, ln in enumerate(lines):
        if len(ln) > 160:
            continue
        m = re_topic_hdr.match(ln)
        if m:
            spans.append((idx, int(m.group(1)), ln))

    # Chỉ cắt đoạn nếu PDF thực sự có từ 2 Chủ đề khác nhau trở lên
    distinct_nums = {num for _, num, _ in spans}
    if len(distinct_nums) < 2:
        return lines

    selected_chunks: List[str] = []
    target_num = int(topic_order_index)
    target_kw = set(re.findall(r"[a-z]{3,}", _ascii_lower_norm(topic_title)))
    target_kw -= {"chu", "sinh", "hoc", "lop", "bai", "cua", "cac", "hien", "tuong"}

    for si, (start_i, tnum, hdr_txt) in enumerate(spans):
        end_i = spans[si + 1][0] if si + 1 < len(spans) else len(lines)
        hdr_kw = set(re.findall(r"[a-z]{3,}", _ascii_lower_norm(hdr_txt)))
        match_by_num = (tnum == target_num)
        match_by_kw = bool(target_kw and len(target_kw & hdr_kw) >= 2)
        if match_by_num or match_by_kw:
            selected_chunks.extend(lines[start_i:end_i])

    return selected_chunks if selected_chunks else lines


def parse_answer_pdf_keys(
    pdf_bytes: bytes,
    topic_order_index: Optional[int] = None,
    topic_title: str = "",
) -> Dict[str, Any]:
    """
    Trích xuất TOÀN DIỆN bảng đáp án & giải chi tiết từ file PDF 'Đáp án':
      - Tự động tách đúng phân đoạn Chủ đề N nếu file PDF chứa nhiều Chủ đề
      - Hỗ trợ phân theo từng Bài (Bài 1..6, Bài 20..25, 7.1..7.6, A./B. tiêu đề) lẫn toàn Chủ đề
      - Hỗ trợ bảng đáp án ngang 2 hàng (hàng Câu 1..10 + hàng Đáp án A..D hoặc số)
      - Hỗ trợ bảng đáp án Đúng/Sai nhiều dòng (Câu 1 rồi a) Đúng, b) Sai...) và ma trận cột (a) Đ S Đ Đ)
      - Hỗ trợ cặp inline (1.A 2.B, 1A 2B, Câu 1: Chọn A, Câu 1: Đáp án 12,5, A. 4)
    """
    if PdfReader is None:
        raise RuntimeError("Thiếu thư viện pypdf trên máy chủ để đọc file PDF Đáp án.")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    lines: List[str] = []
    for page in reader.pages:
        try:
            # Thử trích xuất layout trước để giữ nguyên hàng bảng nếu pypdf hỗ trợ, fallback về mặc định
            try:
                raw = page.extract_text(extraction_mode="layout") or page.extract_text() or ""
            except TypeError:
                raw = page.extract_text() or ""
            raw = unicodedata.normalize("NFC", raw)
            for ln in raw.splitlines():
                cl = re.sub(r"[ \t]+", " ", ln.replace("\u00a0", " ")).strip()
                if cl:
                    lines.append(cl)
        except Exception:
            continue

    total_chars = sum(len(x) for x in lines)
    is_scanned_pdf = len(reader.pages) > 0 and total_chars < max(30, len(reader.pages) * 15)
    ocr_used = False
    if is_scanned_pdf:
        ocr_lines = _ocr_scanned_pdf_lines(pdf_bytes, max_pages=min(45, len(reader.pages)))
        if ocr_lines:
            lines = ocr_lines
            ocr_used = True

    lines = _slice_pdf_lines_for_topic(lines, topic_order_index=topic_order_index, topic_title=topic_title)

    by_lesson: Dict[int, Dict[str, Any]] = {}
    seq_lessons: List[Dict[str, Any]] = []
    global_bucket: Dict[str, Any] = _new_answer_bucket("Global", 0)

    def ensure_lesson_bucket(l_num: int, title: str = "") -> Dict[str, Any]:
        if l_num <= 0:
            return global_bucket
        if l_num not in by_lesson:
            bk_new = _new_answer_bucket(title, l_num)
            by_lesson[l_num] = bk_new
            seq_lessons.append(bk_new)
        elif title and not by_lesson[l_num].get("title"):
            by_lesson[l_num]["title"] = title
        return by_lesson[l_num]

    cur_lesson = 0
    cur_part = "mcq"
    cur_exp_target: Optional[Tuple[int, str, int]] = None
    cur_tf_qnum: Optional[int] = None
    cur_tf_partial: Dict[str, bool] = {}
    pending_table_nums: Optional[List[int]] = None

    def flush_tf_partial():
        nonlocal cur_tf_qnum, cur_tf_partial
        if cur_tf_qnum is not None and cur_tf_partial:
            bk_cur = ensure_lesson_bucket(cur_lesson)
            existing = bk_cur["tf"].get(cur_tf_qnum) or [None, None, None, None]
            merged = [
                cur_tf_partial.get(k) if cur_tf_partial.get(k) is not None else existing[idx]
                for idx, k in enumerate(("a", "b", "c", "d"))
            ]
            bk_cur["tf"][cur_tf_qnum] = merged
            global_bucket["tf"].setdefault(cur_tf_qnum, merged)
        cur_tf_qnum = None
        cur_tf_partial = {}

    re_lesson = re.compile(
        r"^(?:BÀI\s*(\d+)(?:\s*[:\.\-–]\s*(.*))?|[1-9]\.(\d+)\s*[:\.\-–\s]\s*(.*))$",
        re.IGNORECASE,
    )
    re_htkt = re.compile(
        r"^(?:PHẦN\s+)?(?:HỆ\s+THỐNG\s+KIẾN\s+THỨC|HƯỚNG\s+DẪN\s+(?:CÁC\s+DẠNG\s+)?BÀI\s+TẬP)",
        re.IGNORECASE,
    )
    re_p1 = re.compile(
        r"(?:PHẦN\s*(?:I\b|1\b)|I\s*[\.\:\-]\s*TRẮC|TRẮC\s+NGHIỆM\s+(?:NHIỀU|4\s+ĐÁP|KHÁCH|LỰA\s*CHỌN)|CÂU\s+HỎI\s+TRẮC\s+NGHIỆM\s+NHIỀU)",
        re.IGNORECASE,
    )
    re_p2 = re.compile(
        r"(?:PHẦN\s*(?:II\b|2\b)|II\s*[\.\:\-]\s*.*ĐÚNG|TRẮC\s+NGHIỆM\s+ĐÚNG\s*[/\-–]?\s*SAI|CÂU\s+HỎI\s+(?:TRẮC\s+NGHIỆM\s+)?ĐÚNG\s*[/\-–]?\s*SAI)",
        re.IGNORECASE,
    )
    re_p3 = re.compile(
        r"(?:PHẦN\s*(?:III\b|3\b)|III\s*[\.\:\-]\s*.*TRẢ\s*LỜI|TRẢ\s+LỜI\s+NGẮN)",
        re.IGNORECASE,
    )
    re_reading = re.compile(
        r"(?:CÂU\s+HỎI\s+)?PHẦN\s+ĐỌC\s+HIỂU",
        re.IGNORECASE,
    )

    for ln in lines:
        # 1. Tiêu đề Bài học mới (Bài 1, Bài 22..27, 7.1..7.6, ...)
        ml = re_lesson.match(ln)
        if ml and len(ln) < 150 and not re.match(r"^Câu\s*\d+", ln, re.IGNORECASE):
            lnum = int(ml.group(1) or ml.group(3) or 0)
            ltitle = (ml.group(2) or ml.group(4) or "").strip()
            if ml.group(1) or (ltitle and any(ch.isalpha() for ch in ltitle)):
                flush_tf_partial()
                cur_lesson = lnum
                ensure_lesson_bucket(cur_lesson, ltitle)
                cur_part = "intro"
                cur_exp_target = None
                pending_table_nums = None
                continue

        # 2. Chuyển mục Hệ thống kiến thức / Phần Đọc hiểu / Phần I / II / III
        if re_htkt.search(ln) and len(ln) < 120:
            flush_tf_partial()
            cur_part = "intro"
            cur_exp_target = None
            pending_table_nums = None
            continue
        if re_reading.search(ln) and len(ln) < 120:
            flush_tf_partial()
            cur_part = "reading"
            cur_exp_target = None
            pending_table_nums = None
            continue
        if re_p3.search(ln) and len(ln) < 140 and not re.match(r"^Câu\s*\d+", ln, re.IGNORECASE):
            flush_tf_partial()
            cur_part = "short_answer"
            cur_exp_target = None
            pending_table_nums = None
            continue
        if re_p2.search(ln) and len(ln) < 140 and not re.match(r"^Câu\s*\d+", ln, re.IGNORECASE):
            flush_tf_partial()
            cur_part = "true_false"
            cur_exp_target = None
            pending_table_nums = None
            continue
        if re_p1.search(ln) and len(ln) < 140 and not re.match(r"^Câu\s*\d+", ln, re.IGNORECASE):
            flush_tf_partial()
            cur_part = "mcq"
            cur_exp_target = None
            pending_table_nums = None
            continue

        bk = ensure_lesson_bucket(cur_lesson)

        # Nếu đang ở phần intro (HTKT/Hướng dẫn), chỉ tự kích hoạt sang mcq khi gặp dòng bảng đáp án rõ ràng ("1.A  2.B  3.C")
        if cur_part == "intro":
            probe_mcq = re.findall(r"(?:^|[\s|;,])(\d{1,3})\s*[\.\:\-–\)]\s*([A-D])(?=$|[\s|;,\.\(])", ln)
            if len(probe_mcq) >= 3:
                cur_part = "mcq"
            else:
                continue

        # 3. Xử lý bảng ngang 2 hàng (Hàng 1: dãy số câu -> Hàng 2: dãy đáp án A/B/C/D hoặc số hoặc a) Đ S Đ S)
        if pending_table_nums is not None:
            if cur_part in ("mcq", "reading"):
                let_row = _extract_table_letter_row(ln)
                if let_row and len(let_row) == len(pending_table_nums):
                    target_dict = bk["reading"] if cur_part == "reading" else bk["mcq"]
                    for qn, lt in zip(pending_table_nums, let_row):
                        idx_val = LETTER_TO_IDX[lt]
                        target_dict[qn] = idx_val
                        if cur_part == "mcq":
                            global_bucket["mcq"].setdefault(qn, idx_val)
                    pending_table_nums = None
                    cur_exp_target = None
                    continue
            elif cur_part == "short_answer":
                sa_row = _extract_table_sa_row(ln)
                if sa_row and len(sa_row) == len(pending_table_nums):
                    for qn, sval in zip(pending_table_nums, sa_row):
                        acc = _normalize_sa_pair(sval)
                        if acc:
                            bk["sa"][qn] = acc
                            global_bucket["sa"].setdefault(qn, acc)
                    pending_table_nums = None
                    cur_exp_target = None
                    continue
            elif cur_part == "true_false":
                # Bảng Đúng/Sai dạng ma trận theo hàng a), b), c), d)
                m_row_tf = re.match(r"^(?:Ý\s*)?([a-d])\s*[\)\.\-–:]?\s+(.+)$", ln, re.IGNORECASE)
                if m_row_tf:
                    rk = m_row_tf.group(1).lower()
                    rtoks = re.findall(r"\b(Đúng|Sai|Đ|S|T|F)\b", m_row_tf.group(2), re.IGNORECASE)
                    if len(rtoks) == len(pending_table_nums):
                        ridx = "abcd".index(rk)
                        for qn, rval in zip(pending_table_nums, rtoks):
                            arr = bk["tf"].get(qn) or [None, None, None, None]
                            arr[ridx] = rval.strip().upper() in ("ĐÚNG", "Đ", "T")
                            bk["tf"][qn] = arr
                            global_bucket["tf"].setdefault(qn, arr)
                        continue
                # Bảng Đúng/Sai dạng 1 hàng chữ ghép (ĐSĐĐ  SĐĐS ...)
                compact_toks = [t.upper() for t in re.split(r"[\s|]+", re.sub(r"^(?:Đáp\s*án|ĐA)\s*[:\.\-–]?\s*", "", ln, flags=re.IGNORECASE).strip()) if t]
                if len(compact_toks) == len(pending_table_nums) and all(re.fullmatch(r"[ĐSDTF]{4}", t) for t in compact_toks):
                    for qn, t4 in zip(pending_table_nums, compact_toks):
                        vals4 = [ch in ("Đ", "D", "T") for ch in t4]
                        bk["tf"][qn] = vals4
                        global_bucket["tf"].setdefault(qn, vals4)
                    pending_table_nums = None
                    continue

        num_row = _extract_table_number_row(ln)
        if num_row is not None and not re.match(r"^\s*Câu\s*\d+\s*[:\.\-–]\s*[A-D]\b", ln, re.IGNORECASE):
            pending_table_nums = num_row
            continue
        elif cur_part != "true_false":
            pending_table_nums = None

        # 4. Phân tích theo từng Phần
        if cur_part in ("mcq", "reading"):
            target_dict = bk["reading"] if cur_part == "reading" else bk["mcq"]
            # Hỗ trợ đầy đủ "1.A  2.B  63.B (III)  106.B(I, III, IV)" và "1A 2B"
            pairs_with_note = re.findall(
                r"(?:^|[\s|;,])(?:Câu\s*)?(\d{1,3})\s*[\.\:\-–\)]\s*([A-D])(?:\s*\(([^\)]*)\))?(?=$|[\s|;,\.])",
                ln,
                re.IGNORECASE,
            )
            if not pairs_with_note:
                pairs_raw = re.findall(r"(?:^|[\s|;,])(\d{1,3})\s+([A-D])(?=$|[\s|;,\(])", ln)
                if not pairs_raw:
                    pairs_raw = re.findall(r"\b(\d{1,3})([A-D])\b", ln)
                pairs_with_note = [(a, b, "") for a, b in pairs_raw]

            stripped_notes_len = len(re.sub(r"\([^\)]*\)", "", ln).strip())
            if pairs_with_note and (len(pairs_with_note) >= 2 or (len(pairs_with_note) == 1 and stripped_notes_len <= 24)):
                for num_s, let, note in pairs_with_note:
                    qn = int(num_s)
                    if 1 <= qn <= 300:
                        idx_val = LETTER_TO_IDX[let.upper()]
                        target_dict[qn] = idx_val
                        if cur_part == "mcq":
                            global_bucket["mcq"].setdefault(qn, idx_val)
                            if note and note.strip():
                                bk["exp"].setdefault(("mcq", qn), f"Các ý đúng: {note.strip()}")
                cur_exp_target = None
                continue

            if cur_part == "mcq":
                m_q = re.match(r"^\s*Câu\s*(\d+)\s*(?:\(([A-D])\))?\s*[:\.\-–]?\s*(.*)$", ln, re.IGNORECASE)
                if m_q:
                    qn = int(m_q.group(1))
                    rest = m_q.group(3).strip()
                    picked_let = None
                    if m_q.group(2):
                        picked_let = m_q.group(2).upper()
                    else:
                        m_lead = re.match(r"^([A-D])(?=$|[\s\.\,\-\–\(:])", rest)
                        if m_lead:
                            picked_let = m_lead.group(1).upper()
                        else:
                            mp = re.search(r"(?:Chọn|Đáp\s*án(?:\s*đúng)?|=>|→)\s*[:\.\-–]?\s*([A-D])\b", rest, re.IGNORECASE)
                            if mp:
                                picked_let = mp.group(1).upper()
                    if picked_let and picked_let in LETTER_TO_IDX:
                        bk["mcq"][qn] = LETTER_TO_IDX[picked_let]
                        global_bucket["mcq"].setdefault(qn, LETTER_TO_IDX[picked_let])
                    if rest and len(rest) > 3:
                        bk["exp"][("mcq", qn)] = (bk["exp"].get(("mcq", qn), "") + "\n" + rest).strip()
                    cur_exp_target = (cur_lesson, "mcq", qn)
                    continue

        elif cur_part == "true_false":
            # Hỗ trợ bố cục 2 cột / nhiều câu trên CÙNG 1 dòng:
            # VD: "1: a. Đúng, b. Sai, c. Đúng, d. Sai;    2: a. Đúng, b. Đúng, c. Sai, d. Đúng;"
            multi_col_tf = re.findall(
                r"(?:^|[\s;])(?:Câu\s*)?(\d{1,3})\s*[:\.\-–]\s*(a\s*[\.\)\-–:\s]\s*(?:Đúng|Sai|Đ|S|True|False).*?)(?=(?:[\s;]+(?:Câu\s*)?\d{1,3}\s*[:\.\-–]\s*a\s*[\.\)\-–:\s])|$)",
                ln,
                re.IGNORECASE,
            )
            if multi_col_tf:
                parsed_any = False
                for num_s, seg in multi_col_tf:
                    vals = _parse_tf_vals(seg)
                    if vals:
                        flush_tf_partial()
                        qn = int(num_s)
                        bk["tf"][qn] = vals
                        global_bucket["tf"].setdefault(qn, vals)
                        parsed_any = True
                if parsed_any:
                    cur_exp_target = None
                    continue

            # Hỗ trợ nhiều câu ngắn trên 1 dòng: "Câu 1: ĐSĐS   Câu 2: SĐĐS"
            multi_tf = re.findall(r"(?:Câu\s*)?(\d{1,2})\s*[:\.\-–]\s*([ĐSDTFđsdtf]{4})\b", ln, re.IGNORECASE)
            if len(multi_tf) >= 2:
                flush_tf_partial()
                for num_s, seq4 in multi_tf:
                    qn = int(num_s)
                    vals4 = [ch in ("Đ", "D", "T") for ch in seq4.upper()]
                    bk["tf"][qn] = vals4
                    global_bucket["tf"].setdefault(qn, vals4)
                cur_exp_target = None
                continue

            m_tf = re.match(r"^\s*(?:Câu\s*)?(\d{1,3})\s*[:\.\-–]\s*(.*)$", ln, re.IGNORECASE)
            if m_tf:
                flush_tf_partial()
                qn = int(m_tf.group(1))
                rest = m_tf.group(2).strip()
                parsed = _parse_tf_vals(rest)
                if parsed:
                    bk["tf"][qn] = parsed
                    global_bucket["tf"].setdefault(qn, parsed)
                else:
                    cur_tf_qnum = qn
                    cur_tf_partial = {}
                    for mk in re.finditer(r"([a-d])\s*[\)\.\-–:]?\s*(Đúng|Sai|Đ|S|True|False)\b", rest, re.IGNORECASE):
                        cur_tf_partial[mk.group(1).lower()] = mk.group(2).strip().upper() in ("ĐÚNG", "Đ", "TRUE")
                if rest and (not parsed or len(rest) > 45):
                    bk["exp"][("true_false", qn)] = (bk["exp"].get(("true_false", qn), "") + "\n" + rest).strip()
                cur_exp_target = (cur_lesson, "true_false", qn)
                continue

            # Dòng phát biểu ý a) Đúng / b) Sai nằm riêng từng dòng dưới Câu N
            if cur_tf_qnum is not None:
                m_st_ln = re.match(r"^\s*(?:Ý\s*)?([a-d])\s*[\)\.\-–:]\s*(.*)$", ln, re.IGNORECASE)
                if m_st_ln:
                    sk = m_st_ln.group(1).lower()
                    srest = m_st_ln.group(2).strip()
                    m_val = re.match(r"^(Đúng|Sai|Đ|S|True|False)\b", srest, re.IGNORECASE) or re.search(
                        r"(?:[:\-–→=>]\s*|\(\s*)(Đúng|Sai|Đ|S)\s*\)?(?:\.|$)", srest, re.IGNORECASE
                    )
                    if m_val:
                        cur_tf_partial[sk] = m_val.group(1).strip().upper() in ("ĐÚNG", "Đ", "TRUE")
                    bk["exp"][("true_false", cur_tf_qnum)] = (bk["exp"].get(("true_false", cur_tf_qnum), "") + "\n" + ln).strip()
                    if len(cur_tf_partial) >= 4:
                        flush_tf_partial()
                    continue

        elif cur_part == "short_answer":
            # Hỗ trợ nhiều câu trên 1 dòng kể cả phân số (1/54), thập phân (0,01), ghi chú ngoặc:
            # VD: "1. 2   2. 4   3. 2 (1, 3)   4. 2 (2, 3)   8. 3 (1, 2, 3)"
            sa_pairs = re.findall(
                r"(?:^|[\s|;,])(?:Câu\s*)?(\d{1,3})\s*[:\.\-–\)]\s*([-+]?\d+(?:[,\./]\d+)?)(?:\s*\(([^\)]*)\))?(?=$|[\s|;,])",
                ln,
                re.IGNORECASE,
            )
            stripped_sa_len = len(re.sub(r"\([^\)]*\)", "", ln).strip())
            if sa_pairs and (len(sa_pairs) >= 2 or (len(sa_pairs) == 1 and stripped_sa_len <= 24)):
                for num_s, val, note in sa_pairs:
                    qn = int(num_s)
                    acc = _normalize_sa_pair(val)
                    if acc:
                        bk["sa"][qn] = acc
                        global_bucket["sa"].setdefault(qn, acc)
                        if note and note.strip():
                            nt = note.strip()
                            exp_txt = f"Các ý đúng: ({nt})" if re.fullmatch(r"[\d,\s;]+", nt) else nt
                            bk["exp"].setdefault(("short_answer", qn), exp_txt)
                cur_exp_target = None
                continue

            m_sa = re.match(r"^\s*(?:Câu\s*)?(\d{1,3})\s*[:\.\-–]?\s*(.*)$", ln, re.IGNORECASE)
            if m_sa:
                qn = int(m_sa.group(1))
                rest = m_sa.group(2).strip()
                m_a = re.match(
                    r"^(?:A\s*[\.\:\)]\s*|(?:Đáp\s*án|Đáp\s*số|Trả\s*lời|Kết\s*quả)\s*[:\.\-–]?\s*)?([-+]?\d+(?:[,\./]\d+)?)(?:\s*\(([^\)]*)\))?(?=$|[\s\.\,\;\(\%])",
                    rest,
                    re.IGNORECASE,
                )
                if not m_a:
                    m_a = re.search(
                        r"(?:Đáp\s*án|Đáp\s*số|Trả\s*lời|Kết\s*quả|Chọn|=>|→)\s*[:\.\-–]?\s*([-+]?\d+(?:[,\./]\d+)?)",
                        rest,
                        re.IGNORECASE,
                    )
                if m_a:
                    acc = _normalize_sa_pair(m_a.group(1))
                    if acc:
                        bk["sa"][qn] = acc
                        global_bucket["sa"].setdefault(qn, acc)
                    if m_a.lastindex and m_a.lastindex >= 2 and m_a.group(2):
                        nt = m_a.group(2).strip()
                        exp_txt = f"Các ý đúng: ({nt})" if re.fullmatch(r"[\d,\s;]+", nt) else nt
                        bk["exp"].setdefault(("short_answer", qn), exp_txt)
                if len(rest) > 10:
                    bk["exp"][("short_answer", qn)] = (bk["exp"].get(("short_answer", qn), "") + "\n" + rest).strip()
                cur_exp_target = (cur_lesson, "short_answer", qn)
                continue

        # 5. Dòng tiếp theo của lời giải chi tiết (bắt thêm đáp án nằm cuối lời giải)
        if cur_exp_target:
            cl, cp, cq = cur_exp_target
            tbk = ensure_lesson_bucket(cl)
            if cp == "mcq" and cq not in tbk["mcq"]:
                mp2 = re.search(r"(?:Chọn|Đáp\s*án(?:\s*đúng)?|=>|→)\s*[:\.\-–]?\s*([A-D])\b", ln, re.IGNORECASE)
                if mp2:
                    tbk["mcq"][cq] = LETTER_TO_IDX[mp2.group(1).upper()]
                    global_bucket["mcq"].setdefault(cq, LETTER_TO_IDX[mp2.group(1).upper()])
            elif cp == "short_answer" and cq not in tbk["sa"]:
                m_sa_a = re.match(
                    r"^\s*(?:A\s*[\.\:\)]|(?:Đáp\s*án|Đáp\s*số|Trả\s*lời|Kết\s*quả)\s*[:\.\-–]?)\s*([-+]?\d+(?:[,\./]\d+)?)",
                    ln,
                    re.IGNORECASE,
                ) or re.fullmatch(r"\s*([-+]?\d+(?:[,\./]\d+)?)\s*", ln)
                if m_sa_a:
                    acc = _normalize_sa_pair(m_sa_a.group(1))
                    if acc:
                        tbk["sa"][cq] = acc
                        global_bucket["sa"].setdefault(cq, acc)
            tbk["exp"][(cp, cq)] = (tbk["exp"].get((cp, cq), "") + "\n" + ln).strip()

    flush_tf_partial()
    return {
        "by_lesson": by_lesson,
        "seq_lessons": seq_lessons,
        "global": global_bucket,
        "is_scanned_pdf": is_scanned_pdf,
        "ocr_used": ocr_used,
    }


def _match_pdf_buckets_to_topic_lessons(
    lessons: List[Dict[str, Any]],
    by_lesson: Dict[int, Dict[str, Any]],
    seq_lessons: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """
    Ánh xạ thông minh các ngăn bài học trong PDF Đáp án vào đúng thứ tự 1..N bài của Chủ đề:
    - Ưu tiên khớp theo độ tương đồng từ khoá tiêu đề bài học (VD: Bài 22..27 -> 7.1..7.6)
    - Khi đã có bài neo (VD: 7.1 khớp Bài 22), tự động neo tuần tự các bài tiếp theo (7.2 -> Bài 23, ...)
      để không bao giờ khớp nhầm sang bài của chủ đề trước trong file PDF gộp nhiều chương!
    """
    mapped: Dict[int, Dict[str, Any]] = {}
    if not lessons or not seq_lessons:
        return mapped

    used_buckets: Set[int] = set()
    anchor_offsets: List[int] = []  # j - (idx - 1)

    # 1. Ưu tiên khớp theo độ tương đồng từ khoá tiêu đề bài học
    for idx, ls in enumerate(lessons, 1):
        ls_words = set(re.findall(r"[a-z0-9]{2,}", _ascii_lower_norm(ls.get("title", ""))))
        ls_words -= {"va", "cac", "cua", "bai", "chu", "de", "hoc", "sinh", "vat"}
        best_j = -1
        best_score = 0.0
        for j, bk in enumerate(seq_lessons):
            if j in used_buckets:
                continue
            bk_words = set(re.findall(r"[a-z0-9]{2,}", _ascii_lower_norm(bk.get("title", ""))))
            bk_words -= {"va", "cac", "cua", "bai", "chu", "de", "hoc", "sinh", "vat"}
            if not ls_words or not bk_words:
                continue
            inter = len(ls_words & bk_words)
            score = inter / max(1, min(len(ls_words), len(bk_words)))
            if inter >= 2 and score > best_score:
                best_score = score
                best_j = j
        if best_j >= 0 and best_score >= 0.45:
            mapped[idx] = seq_lessons[best_j]
            used_buckets.add(best_j)
            anchor_offsets.append(best_j - (idx - 1))

    # 2. Dùng độ lệch neo phổ biến nhất (VD: Bài 22..27 -> offset = j_start) cho các bài còn thiếu
    if anchor_offsets:
        from collections import Counter
        best_off = Counter(anchor_offsets).most_common(1)[0][0]
        for idx in range(1, len(lessons) + 1):
            if idx in mapped:
                continue
            cand_j = best_off + (idx - 1)
            if 0 <= cand_j < len(seq_lessons) and cand_j not in used_buckets:
                mapped[idx] = seq_lessons[cand_j]
                used_buckets.add(cand_j)

    # 3. Nếu PDF chỉ chứa đúng 1 chủ đề (số bài <= số bài chủ đề + 2), mới khớp trực tiếp theo STT 1..N hoặc tuần tự
    if len(seq_lessons) <= len(lessons) + 2:
        for idx in range(1, len(lessons) + 1):
            if idx in mapped:
                continue
            if idx in by_lesson:
                j = seq_lessons.index(by_lesson[idx])
                if j not in used_buckets:
                    mapped[idx] = by_lesson[idx]
                    used_buckets.add(j)

        rem_buckets = [bk for j, bk in enumerate(seq_lessons) if j not in used_buckets]
        rem_iter = iter(rem_buckets)
        for idx in range(1, len(lessons) + 1):
            if idx in mapped:
                continue
            nxt = next(rem_iter, None)
            if nxt is not None:
                mapped[idx] = nxt

    return mapped


def apply_answer_pdf_to_topic(
    topic_obj: Dict[str, Any],
    pdf_bytes: bytes,
    filename: str = "",
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Khớp đáp án & giải chi tiết từ file PDF 'Đáp án' vào toàn bộ câu hỏi của Chủ đề."""
    parsed = parse_answer_pdf_keys(
        pdf_bytes,
        topic_order_index=topic_obj.get("order_index"),
        topic_title=topic_obj.get("title", ""),
    )
    by_lesson = parsed["by_lesson"]
    seq_lessons = parsed.get("seq_lessons") or []
    gl = parsed["global"]

    lessons = topic_obj.get("lessons") or []
    lesson_id_to_idx = {ls.get("id"): idx for idx, ls in enumerate(lessons, 1)}
    matched_buckets = _match_pdf_buckets_to_topic_lessons(lessons, by_lesson, seq_lessons)

    rev = topic_obj.get("review") or {}
    matched_mcq = 0
    matched_tf = 0
    matched_sa = 0

    for i, q in enumerate(rev.get("mcq") or [], 1):
        l_idx = lesson_id_to_idx.get(q.get("lesson_id"), 0)
        qn = int(q.get("orig_num") or i)
        bk = matched_buckets.get(l_idx) or by_lesson.get(l_idx) or {}
        key_val = (bk.get("mcq") or {}).get(qn)
        if key_val is None and not matched_buckets:
            key_val = (gl.get("mcq") or {}).get(qn)
            if key_val is None:
                key_val = (gl.get("mcq") or {}).get(i)
        if key_val is not None and (overwrite or not q.get("answer_key_ready")):
            q["correct_index"] = key_val
            q["answer_key_ready"] = True
            matched_mcq += 1
        exp = (bk.get("exp") or {}).get(("mcq", qn)) or ((gl.get("exp") or {}).get(("mcq", qn)) if not matched_buckets else "")
        if exp and (overwrite or not q.get("explanation")):
            q["explanation"], _ = standardize_bio_text(exp)

    for i, q in enumerate(rev.get("true_false") or [], 1):
        l_idx = lesson_id_to_idx.get(q.get("lesson_id"), 0)
        qn = int(q.get("orig_num") or i)
        bk = matched_buckets.get(l_idx) or by_lesson.get(l_idx) or {}
        vals = (bk.get("tf") or {}).get(qn)
        if vals is None and not matched_buckets:
            vals = (gl.get("tf") or {}).get(qn) or (gl.get("tf") or {}).get(i)
        if vals and (overwrite or not q.get("answer_key_ready")):
            stmts = q.get("statements") or []
            ok_any = False
            for si, st in enumerate(stmts):
                sk = str(st.get("key") or "").strip().lower()
                val_idx = "abcd".index(sk) if sk in ("a", "b", "c", "d") else si
                if val_idx < len(vals) and vals[val_idx] is not None and (overwrite or st.get("answer") is None):
                    st["answer"] = vals[val_idx]
                    ok_any = True
            if ok_any and stmts and all(st.get("answer") is not None for st in stmts):
                q["answer_key_ready"] = True
                matched_tf += 1
        exp = (bk.get("exp") or {}).get(("true_false", qn)) or ((gl.get("exp") or {}).get(("true_false", qn)) if not matched_buckets else "")
        if exp and (overwrite or not q.get("explanation")):
            q["explanation"], _ = standardize_bio_text(exp)

    for i, q in enumerate(rev.get("short_answer") or [], 1):
        l_idx = lesson_id_to_idx.get(q.get("lesson_id"), 0)
        qn = int(q.get("orig_num") or i)
        bk = matched_buckets.get(l_idx) or by_lesson.get(l_idx) or {}
        acc = (bk.get("sa") or {}).get(qn)
        if acc is None and not matched_buckets:
            acc = (gl.get("sa") or {}).get(qn) or (gl.get("sa") or {}).get(i)
        if acc and (overwrite or not q.get("answer_key_ready")):
            q["accepted_answers"] = acc
            q["accepted"] = acc
            q["answer_key_ready"] = True
            matched_sa += 1
        exp = (bk.get("exp") or {}).get(("short_answer", qn)) or ((gl.get("exp") or {}).get(("short_answer", qn)) if not matched_buckets else "")
        if exp and (overwrite or not q.get("explanation")):
            q["explanation"], _ = standardize_bio_text(exp)

    return {
        "source_name": filename or "PDF Đáp án",
        "matched_mcq": matched_mcq,
        "matched_tf": matched_tf,
        "matched_sa": matched_sa,
        "total_matched": matched_mcq + matched_tf + matched_sa,
        "pdf_lessons_detected": len(seq_lessons),
        "is_scanned_pdf": bool(parsed.get("is_scanned_pdf")),
        "ocr_used": bool(parsed.get("ocr_used")),
    }
