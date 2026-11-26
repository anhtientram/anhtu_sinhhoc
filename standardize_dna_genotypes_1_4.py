#!/usr/bin/env python3
"""
Chuẩn hoá công thức DNA và cách viết kiểu gene chuẩn SGK Sinh học 12 (CT GDPT 2018)
trên toàn bộ 4 Chủ đề (Chủ đề 1 -> Chủ đề 4): Lý thuyết, Hệ thống kiến thức, Mindmap và Hệ thống ôn tập.
"""
import json
import os
import re

from database import init_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")
BUNDLED_VERSION = "2026.11.26-dna-geno-v4"

# Bảng chuẩn hoá ký hiệu DNA, đồng vị, kiểu gene và thuật ngữ SGK 2018
REGEX_FIXES = [
    # 1. Đồng vị phóng xạ & thuật ngữ DNA/RNA/gene/allele
    (re.compile(r"\bN14\b"), "14N"),
    (re.compile(r"\bN15\b"), "15N"),
    (re.compile(r"\bADN\b"), "DNA"),
    (re.compile(r"\bARN\b"), "RNA"),
    (re.compile(r"\bmARN\b"), "mRNA"),
    (re.compile(r"\btARN\b"), "tRNA"),
    (re.compile(r"\brARN\b"), "rRNA"),
    (re.compile(r"\bgen\b(?!\s*e)"), "gene"),
    (re.compile(r"\bGen\b(?!\s*e)"), "Gene"),
    (re.compile(r"\balen\b"), "allele"),
    (re.compile(r"\bAlen\b"), "Allele"),

    # 2. Kiểu hình khuyết dấu gạch ngang chuẩn SGK (tránh A_B_ bị hiểu nhầm chỉ số dưới)
    (re.compile(r"\bA_B_D_\b"), "A-B-D-"),
    (re.compile(r"\bA_B_\b"), "A-B-"),
    (re.compile(r"\bA_bb\b"), "A-bb"),
    (re.compile(r"\baaB_\b"), "aaB-"),
    (re.compile(r"\bA-\s+B-\s+D-"), "A-B-D-"),
    (re.compile(r"\bA-\s+B-"), "A-B-"),

    # 3. Kiểu gene liên kết thiếu khoảng trắng quanh dấu × hoặc /
    (re.compile(r"\b([A-Za-z]{2,4}/[A-Za-z]{2,4})×"), r"\1 ×"),
    (re.compile(r"×([A-Za-z]{2,4}/[A-Za-z]{2,4})\b"), r"× \1"),
    (re.compile(r"\b([A-Za-z]{2,4})\s+/\s*([A-Za-z]{2,4})\b"), r"\1/\2"),
    (re.compile(r"\b([A-Za-z]{2,4})/\s+([A-Za-z]{2,4})\b"), r"\1/\2"),

    # 4. Kiểu gene nhóm máu ABO có khoảng trắng thừa giữa 2 allele
    (re.compile(r"\bIA\s+IA\b"), "I^AI^A"),
    (re.compile(r"\bIA\s+IO\b"), "I^AI^O"),
    (re.compile(r"\bIA\s+IB\b"), "I^AI^B"),
    (re.compile(r"\bIB\s+IB\b"), "I^BI^B"),
    (re.compile(r"\bIB\s+IO\b"), "I^BI^O"),
    (re.compile(r"\bIO\s+IO\b"), "I^OI^O"),
    (re.compile(r"\bIAIA\b"), "I^AI^A"),
    (re.compile(r"\bIAIO\b"), "I^AI^O"),
    (re.compile(r"\bIAIB\b"), "I^AI^B"),
    (re.compile(r"\bIBIB\b"), "I^BI^B"),
    (re.compile(r"\bIBIO\b"), "I^BI^O"),
    (re.compile(r"\bIOIO\b"), "I^OI^O"),

    # 5. Kiểu gene liên kết NST giới tính viết liền thiếu mũ (chuẩn hoá sang dạng X^A X^a / X^A Y / X^A X^a X^a)
    (re.compile(r"\bX([ABDEHMRWabdehmrw])X([ABDEHMRWabdehmrw])X([ABDEHMRWabdehmrw])\b"), r"X^\1X^\2X^\3"),
    (re.compile(r"\bX([ABDEHMRWabdehmrw])X([ABDEHMRWabdehmrw])\b"), r"X^\1X^\2"),
    (re.compile(r"\bX([ABDEHMRWabdehmrw])Y([ABDEHMRWabdehmrw])\b"), r"X^\1Y^\2"),
    (re.compile(r"\bX([ABDEHMRWabdehmrw])Y\b"), r"X^\1Y"),
    (re.compile(r"\bXY([ABDEHMRWabdehmrw])\b"), r"XY^\1"),
    (re.compile(r"\b([A-Za-z]{2})X([ABDEHMRWabdehmrw])X([ABDEHMRWabdehmrw])\b"), r"\1X^\2X^\3"),
    (re.compile(r"\b([A-Za-z]{2})X([ABDEHMRWabdehmrw])Y\b"), r"\1X^\2Y"),

    # 6. Lỗi khoảng trắng cặp base DNA: G- C -> G - C
    (re.compile(r"\b([ATGC])\s*-\s*([ATGC])\b"), r"\1 – \2"),
    # 7. Lỗi gõ chữ l thay số 1 trước kiểu gene hoặc tính trạng
    (re.compile(r"\bl\s+aabb\b"), "1 aabb"),
    (re.compile(r"\b1nm\s*="), "1 nm ="),
]

# Bảng công thức DNA chuẩn hoá trình bày gọn đẹp trong Bài 1.1 Lý thuyết
CLEAN_DNA_FORMULA_TABLE = [
    ["Đại lượng / Công thức DNA (Gene)", "Biểu thức chuẩn"],
    ["Quy ước các đại lượng", "N: tổng số nucleotide của phân tử DNA (gene); A = T và G = C là số nucleotide từng loại; A1, T1, G1, C1 và A2, T2, G2, C2 lần lượt là số nucleotide từng loại trên mạch 1 và mạch 2."],
    ["Đơn vị kích thước", "1 mm = 10^3 µm = 10^6 nm = 10^7 Å  (1 nm = 10 Å; 1 µm = 10^4 Å)"],
    ["Chiều dài phân tử DNA (gene)", "L = (N/2) × 3,4 Å  ⇒  N = (2 × L) / 3,4"],
    ["Số chu kì xoắn", "CK = N / 20  (mỗi chu kì xoắn gồm 10 cặp nucleotide = 20 nucleotide, dài 34 Å)"],
    ["Khối lượng phân tử DNA", "M = N × 300 đvC (amu)"],
    ["Số liên kết hydrogen", "H = 2A + 3G = N + G"],
    ["Số liên kết phosphodiester", "Giữa các nucleotide trên 2 mạch: N − 2;  Tổng số liên kết phosphodiester trong DNA: 2N − 2"],
    ["Số nucleotide từng loại", "A = T = A1 + T1 = A1 + A2 = %A × N;\nG = C = G1 + C1 = G1 + G2 = %G × N;\nA + G = T + C = N/2"],
    ["Tỉ lệ phần trăm (%) từng loại", "%A = %T = (%A1 + %T1)/2 = (%A1 + %A2)/2;\n%G = %C = (%G1 + %C1)/2 = (%G1 + %C2)/2;\n%A + %G = 50%"],
]

CLEAN_DNA_FORMULAS_KS = [
    {"name": "Chiều dài phân tử DNA (L)", "expression": "L = (N/2) × 3,4 Å  (1 µm = 10^4 Å = 10^3 nm)"},
    {"name": "Số chu kì xoắn (CK)", "expression": "CK = N / 20"},
    {"name": "Khối lượng phân tử DNA (M)", "expression": "M = N × 300 đvC"},
    {"name": "Số liên kết hydrogen (H)", "expression": "H = 2A + 3G = N + G"},
    {"name": "Nguyên tắc bổ sung (NTBS)", "expression": "A = T = A1 + T1 = A1 + A2;  G = C = G1 + C1 = G1 + G2;  A + G = N/2;  %A + %G = 50%"},
    {"name": "Tái bản DNA (k lần từ a phân tử)", "expression": "Số DNA con = a × 2^k;  Số DNA hoàn toàn mới = a × (2^k − 2);  Số mạch mới = a × 2 × (2^k − 1)"},
]


def normalize_text(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    out = s
    for pat, rep in REGEX_FIXES:
        out = pat.sub(rep, out)
    # Tránh nhân đôi ký hiệu mũ X^^A
    out = out.replace("X^^", "X^").replace("Y^^", "Y^").replace("I^^", "I^")
    return out


def deep_normalize(obj, key_name=""):
    # Không biến đổi các khóa ID/URL/exact tokens vốn đã là lowercase không dấu
    if key_name in ("id", "lesson_id", "src", "exact", "accepted", "bundled_version", "status", "type", "mode", "grade_type", "group"):
        return obj
    if isinstance(obj, str):
        return normalize_text(obj)
    if isinstance(obj, list):
        return [deep_normalize(x, key_name) for x in obj]
    if isinstance(obj, dict):
        return {k: deep_normalize(v, k) for k, v in obj.items()}
    return obj


def main():
    for idx in range(1, 5):
        path = os.path.join(TOPICS_DIR, f"chu_de_{idx}.json")
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)

        d = deep_normalize(d)

        # Riêng Chủ đề 1: thay bảng công thức DNA bị dính thành 1 ô dài bằng bảng công thức 2 cột rõ ràng, dễ tra cứu
        if idx == 1:
            sec3_blocks = d["lessons"][0]["sections"][3]["blocks"]
            if sec3_blocks and sec3_blocks[0].get("type") == "table":
                sec3_blocks[0]["rows"] = CLEAN_DNA_FORMULA_TABLE
            if "knowledge_system" in d:
                d["knowledge_system"]["formulas"] = CLEAN_DNA_FORMULAS_KS

        d["bundled_version"] = BUNDLED_VERSION
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        print(f"Standardized chu_de_{idx}.json -> bundled_version={BUNDLED_VERSION}")

    init_db()
    print("Synced standardized Chủ đề 1-4 into SQLite DB!")


if __name__ == "__main__":
    main()
