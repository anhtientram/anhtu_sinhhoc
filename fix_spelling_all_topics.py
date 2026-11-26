#!/usr/bin/env python3
"""
Rà soát và chuẩn hoá chính tả, dấu thanh tiếng Việt và lỗi OCR
trên toàn bộ 7 Chủ đề Sinh học 12 (data/topics/chu_de_1.json -> chu_de_7.json),
nâng bundled_version và đồng bộ vào SQLite data/sinhhoc12.db.
"""

import json
import os
import re
import unicodedata

from database import init_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")
BUNDLED_VERSION = "2026.11.26-spelling-clean-v6"

# Thay thế chuỗi chính xác (phân biệt hoa/thường khi cần)
EXACT_REPLACEMENTS = [
    # Ký tự lạ / BOM / OCR Latin-Cyrillic-Greek bị nhầm
    ("\ufeff", ""),
    ("trườņg", "trường"),
    ("kim loại nǎng", "kim loại nặng"),
    ("nǎng", "năng"),
    ("mǎng", "măng"),
    ("tǎng", "tăng"),
    ("bǎng", "băng"),
    ("nǎm", "năm"),
    ("ǎ", "ă"),
    ("ı", "i"),
    ("ą", "a"),
    ("ņ", "n"),
    ("ºC", "°C"),
    ("º", "°"),
    ("chuỗi B-hemoglobin", "chuỗi β-hemoglobin"),
    ("chuỗi Β-hemoglobin", "chuỗi β-hemoglobin"),
    ("Α", "A"),
    ("Β", "B"),
    ("В", "B"),
    ("І", "I"),
    ("С", "C"),
    ("А", "A"),
    ("а", "a"),

    # Dấu kép / gõ lỗi Telex-VNI / OCR
    ("hóá", "hoá"),
    ("Hóá", "Hoá"),
    ("HÓÁ", "HOÁ"),
    ("hóả", "hoá"),
    ("thủỷ", "thuỷ"),
    ("Thủỷ", "Thuỷ"),
    ("buớc", "bước"),
    ("Buớc", "Bước"),
    ("bứớc", "bước"),
    ("Bứớc", "Bước"),
    ("quy uớc", "quy ước"),
    ("Quy uớc", "Quy ước"),
    ("bàí", "bài"),
    ("kíếu", "kiểu"),
    ("kíểm", "kiểm"),
    ("gíữa", "giữa"),
    ("nàỵ", "này"),
    ("chứmg", "chứng"),
    ("Chứmg", "Chứng"),
    ("ứmg", "ứng"),
    ("Ứmg", "Ứng"),
    ("dựmg", "dựng"),
    ("rừmg", "rừng"),
    ("đnag", "đang"),
    ("mức đôh", "mức độ"),
    ("hỗổ, bào.", "hổ, báo..."),
    ("hỗổ", "hổ"),
    ("mứrc", "mức"),
    ("trựrc", "trực"),
    ("nuớc thái", "nước thải"),
    ("nước thái", "nước thải"),
    ("nuớc", "nước"),
    ("Nuớc", "Nước"),
    ("môi trưòng", "môi trường"),
    ("môi truờng", "môi trường"),
    ("TẠG", "TAG"),
    ("quy đnh", "quy định"),
    ("Đm cây", "Đem cây"),
    ("cód 2n=4", "có 2n = 4"),
    ("Vírus", "Virus"),
    ("vírus", "virus"),

    # Từ bị dính liền do OCR
    ("tốtgiúp", "tốt giúp"),
    ("tổnghợp", "tổng hợp"),
    ("phápxử", "pháp xử"),
    ("độtbiển", "đột biến"),
    ("độtbiến", "đột biến"),
    ("Tam điệpPhấn trắngJurassic", "Tam điệp – Jurassic – Phấn trắng"),
    ("Tam điệpJurassicPhấn trắng", "Tam điệp – Jurassic – Phấn trắng"),

    # Lỗi sai dấu / thiếu dấu rất rõ ràng trong Sinh học 12
    ("Diễn thể", "Diễn thế"),
    ("diễn thể", "diễn thế"),
    ("DIỄN THỂ", "DIỄN THẾ"),
    ("Ti lệ", "Tỉ lệ"),
    ("ti lệ", "tỉ lệ"),
    ("Tỉ lê", "Tỉ lệ"),
    ("tỉ lê", "tỉ lệ"),
    ("Tỷ lê", "Tỷ lệ"),
    ("tỷ lê", "tỷ lệ"),
    ("tế bảo", "tế bào"),
    ("Tế bảo", "Tế bào"),
    ("tế bài", "tế bào"),
    ("Tế bài", "Tế bào"),
    ("phân từ", "phân tử"),
    ("Phân từ", "Phân tử"),
    ("tất cà", "tất cả"),
    ("Tất cà", "Tất cả"),
    ("quản thể", "quần thể"),
    ("Quản thể", "Quần thể"),
    ("quẩn thể", "quần thể"),
    ("Quẩn thể", "Quần thể"),
    ("quần thề", "quần thể"),
    ("Quần thề", "Quần thể"),
    ("nhiễm sắc thề", "nhiễm sắc thể"),
    ("cơ thề", "cơ thể"),
    ("có thề", "có thể"),
    ("không thề", "không thể"),
    ("cầu tạo", "cấu tạo"),
    ("Cầu tạo", "Cấu tạo"),
    ("đề cầu tạo", "để cấu tạo"),
    ("tiến hoa", "tiến hoá"),
    ("Tiến hoa", "Tiến hoá"),
    ("thoái hoa", "thoái hoá"),
    ("Thoái hoa", "Thoái hoá"),
    ("đột biên", "đột biến"),
    ("Đột biên", "Đột biến"),
    ("biến di", "biến dị"),
    ("Biến di", "Biến dị"),
    ("công nghê", "công nghệ"),
    ("Công nghê", "Công nghệ"),
    ("cơ chê", "cơ chế"),
    ("Cơ chê", "Cơ chế"),
    ("nhân tô", "nhân tố"),
    ("Nhân tô", "Nhân tố"),
    ("kiêu gene", "kiểu gene"),
    ("Kiêu gene", "Kiểu gene"),
    ("kiểu hình trôi", "kiểu hình trội"),
    ("tính trang", "tính trạng"),
    ("Tính trang", "Tính trạng"),
    ("quá trinh", "quá trình"),
    ("Quá trinh", "Quá trình"),
    ("phát biêu", "phát biểu"),
    ("Phát biêu", "Phát biểu"),
    ("phát hiểu", "phát biểu"),
    ("Phát hiểu", "Phát biểu"),
    ("dầu tích", "dấu tích"),
    ("Dầu tích", "Dấu tích"),
    ("nguồn góc", "nguồn gốc"),
    ("Nguồn góc", "Nguồn gốc"),
    ("cho thầy", "cho thấy"),
    ("tinh cảm", "tình cảm"),
    ("để bài", "đề bài"),
    ("Để bài", "Đề bài"),
    ("sơ đổ", "sơ đồ"),
    ("Sơ đổ", "Sơ đồ"),
    ("thực vât", "thực vật"),
    ("Thực vât", "Thực vật"),
    ("động vât", "động vật"),
    ("Động vât", "Động vật"),
    ("sinh vât", "sinh vật"),
    ("Sinh vât", "Sinh vật"),
    ("giao phân", "giao phấn"),
    ("các loai", "các loài"),
    ("hoạt dộng", "hoạt động"),
    ("Hoạt dộng", "Hoạt động"),
    ("bảo tôn", "bảo tồn"),
    ("Bảo tôn", "Bảo tồn"),
    ("phân bô", "phân bố"),
    ("Phân bô", "Phân bố"),
    ("tối thiều", "tối thiểu"),
    ("thích nghĩ", "thích nghi"),
    ("ô nhiểm", "ô nhiễm"),
    ("Ô nhiểm", "Ô nhiễm"),
    ("dân liệu", "dẫn liệu"),
    ("Dân liệu", "Dẫn liệu"),
    ("tảng nước mặt", "tầng nước mặt"),
    ("đất hiền", "đất liền"),
    ("Chữ số mây", "Chữ số mấy"),
    ("chữ số mây", "chữ số mấy"),
    ("gây rùng", "gây rừng"),
    ("Trồng rùng", "Trồng rừng"),
    ("trồng rùng", "trồng rừng"),
    ("Trổng cây", "Trồng cây"),
    ("Trông cây họ Đậu", "Trồng cây họ Đậu"),
    ("tròng lại san hô", "trồng lại san hô"),
    ("sử dụng bèn vững", "sử dụng bền vững"),
    ("bèn vững", "bền vững"),
    ("Loại bó", "Loại bỏ"),
    ("loại bó", "loại bỏ"),
    ("Loại bổ", "Loại bỏ"),
    ("loại bổ", "loại bỏ"),
    ("rác thai nhua", "rác thải nhựa"),
    ("di truyên", "di truyền"),
    ("Di truyên", "Di truyền"),
    ("Gai xươn rồng", "Gai xương rồng"),
    ("xươn rồng", "xương rồng"),
    ("ngoai, sắn", "khoai, sắn"),
    ("Đề tạo ra", "Để tạo ra"),
    ("đề tạo ra", "để tạo ra"),
    ("Đề tạo giống", "Để tạo giống"),
    ("đề tạo giống", "để tạo giống"),
    ("Đề tạo", "Để tạo"),
    ("đề tạo", "để tạo"),
    ("xác địng", "xác định"),
    ("xác đinh", "xác định"),
    ("axit amin", "amino acid"),
    ("Axit amin", "Amino acid"),
    ("allele lăn", "allele lặn"),
    ("tính trạng lăn", "tính trạng lặn"),
    ("đột biến lăn", "đột biến lặn"),
    ("trội, lăn", "trội, lặn"),
    ("gene lăn", "gene lặn"),
    ("ngườii", "người"),
    ("Ngườii", "Người"),
    ("tiền hóa", "tiến hóa"),
    ("tiền hoá", "tiến hoá"),
    ("Tiền hóa", "Tiến hóa"),
    ("Tiền hoá", "Tiến hoá"),
    ("chúng tộc", "chủng tộc"),
    ("Chúng tộc", "Chủng tộc"),
    ("một cho một quá trình", "cho một quá trình"),
    ("chúc năng", "chức năng"),
    ("trinh tự", "trình tự"),
    ("Trái Đát", "Trái Đất"),
]

# Regex biên từ cho các lỗi không thể thay trực tiếp bằng substring
REGEX_REPLACEMENTS = [
    (re.compile(r"\bngườ\b"), "người"),
    (re.compile(r"\bNgườ\b"), "Người"),
    # Fix khoảng trắng sau dấu chấm phẩy bị dính (VD: ";(2)." -> "; (2).")
    (re.compile(r";\((\d+)\)\."), r"; (\1)."),
    (re.compile(r"\.\s*Có bao nhiêu"), ". Có bao nhiêu"),
]

SKIP_KEYS = {
    "id", "lesson_id", "image", "images", "url", "embed_url",
    "bundled_version", "cognitive_level", "mode", "type", "grade_type", "group",
}

changes_by_topic = {}


def clean_text(s: str, tid: str) -> str:
    if not s or s.startswith("/uploads/") or s.startswith("http") or s.startswith("data:"):
        return s
    orig = s
    s = unicodedata.normalize("NFC", s)
    for old, new in EXACT_REPLACEMENTS:
        if old in s:
            s = s.replace(old, new)
    for rx, rep in REGEX_REPLACEMENTS:
        s = rx.sub(rep, s)
    if s != orig:
        changes_by_topic[tid] = changes_by_topic.get(tid, 0) + 1
    return s


def walk_clean(obj, tid: str):
    if isinstance(obj, str):
        return clean_text(obj, tid)
    if isinstance(obj, list):
        return [walk_clean(x, tid) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in SKIP_KEYS:
                out[k] = v
            else:
                out[k] = walk_clean(v, tid)
        return out
    return obj


def main():
    for n in range(1, 8):
        path = os.path.join(TOPICS_DIR, f"chu_de_{n}.json")
        tid = f"chu-de-{n}"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        cleaned = walk_clean(data, tid)
        cleaned["bundled_version"] = BUNDLED_VERSION
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        print(f"  {tid}: fixed {changes_by_topic.get(tid, 0)} strings -> version {BUNDLED_VERSION}")

    init_db()
    print("Synced all 7 cleaned topics into SQLite DB!")


if __name__ == "__main__":
    main()
