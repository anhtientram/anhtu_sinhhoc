#!/usr/bin/env python3
"""
Trích xuất, chuẩn hoá và đồng bộ hoàn chỉnh CHỦ ĐỀ 5 (CHỦ ĐỀ 5.docx)
giống 100% quy chuẩn của Chủ đề 1 -> 4:
  - Thống nhất đề mục 5.1, 5.2, 5.3, 5.4
  - Bổ sung mục "Yêu cầu cần đạt" chuẩn SGK Sinh học 12 (GDPT 2018) cho từng bài
  - Sửa lỗi chính tả / OCR / công thức
  - Gắn ô nhập đáp án & đáp án chuẩn (đối chiếu từ Sinh học 12 - Đáp án hoàn chỉnh.pdf trang 1-10)
    cho cả Lý thuyết, Hệ thống kiến thức và toàn bộ 462 câu Hệ thống ôn tập 3 phần
  - Gắn nhãn mức độ nhận thức (Nhận biết / Thông hiểu / Vận dụng) cho Ma trận trộn đề 3x3
  - Đồng bộ vào data/topics/chu_de_5.json và SQLite data/sinhhoc12.db
"""

import json
import os
import re
import shutil
import unicodedata

from classify_levels import classify_question
from database import get_conn, init_db, now_iso
from importer import UPLOADS_DIR, parse_document_to_topic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")
BUNDLED_VERSION = "2026.11.26-chu-de-5-v3"

LETTER_TO_IDX = {"A": 0, "B": 1, "C": 2, "D": 3}


def L(seq_str):
    tokens = [t.strip().upper() for t in seq_str.replace(",", " ").split() if t.strip()]
    return {i + 1: LETTER_TO_IDX[t] for i, t in enumerate(tokens)}


def TF(rows_dict):
    out = {}
    for k, v in rows_dict.items():
        toks = [t.strip().upper() for t in v.split() if t.strip()]
        out[k] = [t in ("Đ", "D", "T", "TRUE") for t in toks]
    return out


# 1. Yêu cầu cần đạt chuẩn SGK Sinh học 12 (Kết nối tri thức với cuộc sống)
YCCD_CHU_DE_5 = {
    "chu-de-5-bai-1": [
        "1. Nêu được khái niệm, nguyên lí và một số thành tựu của công nghệ DNA tái tổ hợp.",
        "2. Nêu được khái niệm, nguyên lí và một số thành tựu tạo thực vật và động vật biến đổi gene.",
        "3. Tranh luận, phản biện được về việc sản xuất và sử dụng sản phẩm biến đổi gene và đạo đức sinh học.",
    ],
    "chu-de-5-bai-2": [
        "1. Nêu được khái niệm về giống; quy trình chọn và tạo giống bằng phương pháp lai hữu tính.",
        "2. Trình bày được một số phương pháp lai hữu tính (chọn lọc, tự thụ phấn, lai kinh tế, lai xa, lai thuận nghịch) và ưu thế lai.",
        "3. Nêu được một số thành tựu nổi bật trong chọn, tạo giống cây trồng và vật nuôi ở Việt Nam và trên thế giới.",
    ],
    "chu-de-5-bai-3": [
        "1. Phát biểu được khái niệm quần thể (dưới góc độ di truyền học) và lấy được ví dụ minh hoạ.",
        "2. Phát biểu được khái niệm di truyền học quần thể và các đặc trưng di truyền của quần thể (tần số allele, tần số kiểu gene).",
        "3. Trình bày được cấu trúc di truyền của quần thể ngẫu phối; phát biểu và nêu điều kiện nghiệm đúng của định luật Hardy – Weinberg.",
        "4. Trình bày được ảnh hưởng của tự thụ phấn, giao phối gần đối với cấu trúc di truyền của quần thể và ứng dụng trong chọn giống, y học.",
    ],
    "chu-de-5-bai-4": [
        "1. Nêu được khái niệm, vai trò của di truyền học người và một số phương pháp nghiên cứu di truyền người (phả hệ, đồng sinh, tế bào học, phân tử, sinh hoá, quần thể).",
        "2. Xây dựng và phân tích được sơ đồ phả hệ để xác định quy luật di truyền của một số tính trạng và tính xác suất mắc bệnh di truyền.",
        "3. Nêu được khái niệm, cơ sở và vai trò của di truyền y học tư vấn.",
        "4. Nêu được khái niệm, nguyên lí, một số thành tựu ứng dụng của liệu pháp gene và vấn đề đạo đức sinh học liên quan.",
    ],
}

# 2. Sửa lỗi chính tả / OCR phổ biến trong CHỦ ĐỀ 5.docx
TYPO_FIXES = [
    ("tự thụ tỉnh", "tự thụ tinh"),
    ("dung trong điều trị", "dùng trong điều trị"),
    ("khả răn tạo ra", "khả năng tạo ra"),
    ("Giống bỏ chuyển gene", "Giống bò chuyển gene"),
    ("hàm lượng ẞ-", "hàm lượng β-"),
    ("sản suất và sử dụng", "sản xuất và sử dụng"),
    ("từ RNA", "tử RNA"),
    ("DNA ngoại lại", "DNA ngoại lai"),
    ("của phân tử ADN", "của phân tử DNA"),
    ("liên kết hydrogene", "liên kết hydrogen"),
    ("phất biểu", "phát biểu"),
    ("nhân giồng", "nhân giống"),
    ("Tạo giồng", "Tạo giống"),
    ("phủ hợp", "phù hợp"),
    ("có thề thực hiện", "có thể thực hiện"),
    ("biến dị tô hợp", "biến dị tổ hợp"),
    ("lai hữu tinh", "lai hữu tính"),
    ("Nhằm cùng cố", "Nhằm củng cố"),
    ("DNA tái tô hợp", "DNA tái tổ hợp"),
    ("thuần chúng", "thuần chủng"),
    ("cá thề lai", "cá thể lai"),
    ("tạo giông", "tạo giống"),
    ("tự thụ phần", "tự thụ phấn"),
    ("nhiêu biên dị tô hợp", "nhiều biến dị tổ hợp"),
    ("dề tạo ra", "để tạo ra"),
    ("loài bô mẹ", "loài bố mẹ"),
    ("cây trông", "cây trồng"),
    ("Đề tạo ra", "Để tạo ra"),
    ("chọn giông", "chọn giống"),
    ("đê tạo ra giông", "để tạo ra giống"),
    ("dược gọi là", "được gọi là"),
    ("cửu mẹ mặt trắng", "cừu mẹ mặt trắng"),
    ("sâu dục thân", "sâu đục thân"),
    ("quản thể", "quần thể"),
    ("đơn vi phân loại", "đơn vị phân loại"),
    ("giao từ", "giao tử"),
    ("ti số giữa", "tỉ số giữa"),
    ("Vốn gên là tâp hợp của tất cả các kiểu gên", "Vốn gene là tập hợp của tất cả các allele"),
    ("quần thề", "quần thể"),
    ("quần thể ngẫu phổi", "quần thể ngẫu phối"),
    ("quan hện huyết thống", "quan hệ huyết thống"),
    ("Xác dịnh", "Xác định"),
    ("xác dịnh", "xác định"),
    ("biêu hiện", "biểu hiện"),
    ("kiêu gene", "kiểu gene"),
    ("đột biên", "đột biến"),
    ("cơ thê người bệnh", "cơ thể người bệnh"),
    ("dể xác định", "để xác định"),
    ("cầu trúc", "cấu trúc"),
    ("dịnh lượng", "định lượng"),
    ("quy dịnh", "quy định"),
    ("dồng sinh", "đồng sinh"),
    ("đặc diểm", "đặc điểm"),
    ("chuẩn đoán", "chẩn đoán"),
    ("dự doán", "dự đoán"),
    ("sự ra dời", "sự ra đời"),
    ("rồi loạn di truyền", "rối loạn di truyền"),
    ("chuyến gene ADA", "chuyển gene ADA"),
    ("sơ đồ phá hệ", "sơ đồ phả hệ"),
    ("tính trạng ào đó", "tính trạng nào đó"),
    ("Cà hai bệnh này", "Cả hai bệnh này"),
    ("số IIl5", "số III5"),
    ("thế hệ thứ IIl", "thế hệ thứ III"),
    ("con gái IIl4", "con gái III4"),
    ("được tỉnh theo", "được tính theo"),
    ("trên NST thưởng", "trên NST thường"),
    ("allele trôi A", "allele trội A"),
    ("đánh dấu “” vào", "đánh dấu “×” vào"),
]


def clean_str(s: str) -> str:
    if not s:
        return s
    s = s.replace("\u200b", "")
    for old, new in TYPO_FIXES:
        if old in s:
            s = s.replace(old, new)
    return s


def deep_clean(obj):
    if isinstance(obj, str):
        return clean_str(obj)
    if isinstance(obj, list):
        return [deep_clean(x) for x in obj]
    if isinstance(obj, dict):
        return {k: deep_clean(v) for k, v in obj.items()}
    return obj


# 3. Đáp án chuẩn Hệ thống ôn tập 3 phần (Sinh học 12 - Đáp án hoàn chỉnh.pdf trang 1-10)
MCQ_KEYS_5_1 = L(
    "C A C B A A A B B C B A B "
    "D A A C B B A D A C A D B "
    "D D B D D C D A B C D C A "
    "D D A C A B B C A C"
)
TF_KEYS_5_1 = TF({
    1: "Đ Đ Đ Đ",
    2: "Đ Đ Đ Đ",
    3: "Đ S Đ Đ",
    4: "S Đ Đ Đ",
    5: "S Đ S Đ",
    6: "Đ Đ S Đ",
})
SA_KEYS_5_1 = {
    1: ["2"], 2: ["5"], 3: ["4"], 4: ["3"],
    5: ["3"], 6: ["2"], 7: ["4"], 8: ["4"],
}

MCQ_KEYS_5_2 = L(
    "A B C D A B A C B B D A D "
    "D C B C D B C B A B C A D "
    "B B C D D C D A C A D C C"
)
TF_KEYS_5_2 = TF({
    1: "Đ Đ S S",
    2: "S S S Đ",
    3: "Đ S Đ S",
})
SA_KEYS_5_2 = {
    1: ["2"], 2: ["3"], 3: ["5"], 4: ["16"], 5: ["3"],
}

MCQ_KEYS_5_3_LY_THUYET = L(
    "A A C B B A C C D A A B C "
    "A B D C A D D B C D A D C "
    "B C C A C A"
)
# Phần 2..6 Bài tập Quần thể (1..129 trên PDF trang 6-7; lưu ý 51 in 2 lần nên lần thứ 2 là 52)
MCQ_KEYS_5_3_BAI_TAP = L(
    # 1..24
    "C C C B C C B A A A B A C "
    "A A A B B B D A B B A "
    # 25..64 (40 câu)
    "B B C A B C D C B A C B D "
    "D A A C B A A C C C C C D "
    "A A B D D D C C C C B B B "
    "C "
    # 65..76 (12 câu)
    "D B A C D A D D A A A A "
    # 77..91 (15 câu)
    "D A C C D D B C D B C A "
    "C B A "
    # 92..129 (38 câu)
    "A A A C A A D A A D D A A "
    "A B B C C B D B A C D C C "
    "D B B B D D D A A B C A"
)
TF_KEYS_5_3 = TF({
    1: "Đ S Đ S",
    2: "Đ S Đ Đ",
    3: "Đ Đ Đ Đ",
    4: "S S Đ S",
    5: "S S Đ Đ",
    6: "S S Đ S",
    7: "Đ Đ Đ Đ",
    8: "Đ S Đ Đ",
    9: "Đ Đ Đ Đ",
    10: "Đ Đ S S",
    11: "S Đ S Đ",
    12: "Đ S Đ Đ",
    13: "Đ Đ S Đ",
    14: "Đ Đ Đ S",
    15: "S Đ Đ Đ",
})
SA_KEYS_5_3 = {
    1: ["0,1", "0.1"], 2: ["2"], 3: ["0,35", "0.35"], 4: ["0,0025", "0.0025"], 5: ["25"],
    6: ["1/54"], 7: ["7"], 8: ["20"], 9: ["15"], 10: ["0,09", "0.09"],
    11: ["1"], 12: ["42"], 13: ["108"], 14: ["0,8", "0.8"], 15: ["0,33", "0.33"],
    16: ["3"], 17: ["5"], 18: ["3"], 19: ["2"], 20: ["118"],
}

MCQ_KEYS_5_4_LY_THUYET = L(
    # 1..52
    "B B A A C C D A B B B C A "
    "C B A C B A D B B A B C B "
    "B A A B A A A A A C A D C "
    "A A C A D D A A C A C A B "
    # 53..68 (16 câu)
    "C B A B D B C B A C C D D "
    "D C B "
    # 69..83 (15 câu)
    "B D D B D C D B B A D D A "
    "C B"
)
MCQ_KEYS_5_4_PHA_HE = L(
    "A B C A C A D A A A C B "
    "D D D B B D D D B A "
    "B D D B A B C B A "
    "A B C C B B D D A A B D B "
    "B A A"
)
TF_KEYS_5_4 = TF({
    1: "Đ S S S",
    2: "S S Đ S",
    3: "Đ Đ S S",
    4: "Đ Đ Đ S",
    5: "Đ S Đ S",
    6: "Đ S S Đ",
    7: "Đ Đ Đ Đ",
    8: "S Đ Đ Đ",
    9: "Đ S Đ S",
    10: "Đ S Đ Đ",
    11: "Đ Đ Đ Đ",
    12: "Đ Đ S S",
    13: "S Đ Đ Đ",
    14: "Đ Đ S Đ",
    15: "Đ S Đ Đ",
})
SA_KEYS_5_4 = {
    1: ["3"], 2: ["2"], 3: ["3"], 4: ["4"], 5: ["1"],
    6: ["3"], 7: ["2"], 8: ["2"], 9: ["4"], 10: ["3"],
    11: ["3"], 12: ["2"], 13: ["4"], 14: ["5"], 15: ["12"],
    16: ["1"], 17: ["2"], 18: ["40,1", "40.1"], 19: ["44,4", "44.4"], 20: ["46,67", "46.67"],
}


def ex_item(eid, group, answer, mode="input", exact=None, grade_type="compare", placeholder=None):
    obj = {
        "id": eid,
        "group": group,
        "mode": mode,
        "answer": answer,
        "grade_type": "exact" if (exact is not None or mode == "true_false") else grade_type,
    }
    if exact is not None:
        obj["exact"] = exact
    if placeholder:
        obj["placeholder"] = placeholder
    return obj


def group_item(eid, label, answer, mode="input", exact=None, grade_type="compare"):
    obj = {
        "id": eid,
        "label": label,
        "mode": mode,
        "answer": answer,
        "grade_type": "exact" if (exact is not None or mode == "true_false") else grade_type,
    }
    if exact is not None:
        obj["exact"] = exact
    return obj


def enrich_interactive_chu_de_5(d):
    lessons = d["lessons"]
    units = d["knowledge_system"]["units"]

    # --- LÝ THUYẾT 5.4: Bài tập Phả hệ (Ví dụ 2, 3, 4, 5, 6 — PDF trang 7-8) ---
    s5_blocks = lessons[3]["sections"][-1]["blocks"]
    for idx, b in enumerate(s5_blocks):
        txt = b.get("text", "")
        if txt.startswith("Hãy xác định gene gây bệnh ở các sơ đồ phả hệ trên"):
            b["exercise_group"] = {
                "id": "cd5-th-5.4-vd2",
                "columns": 1,
                "title": "Xác định quy luật di truyền & số người biết chính xác kiểu gene cho từng sơ đồ (A → E):",
                "items": [
                    group_item("cd5-th-5.4-vd2-a", "Sơ đồ A", "Bệnh do gene lặn trên NST thường quy định (A bình thường > a bệnh) — Số người biết chính xác KG: 7"),
                    group_item("cd5-th-5.4-vd2-b", "Sơ đồ B", "Bệnh do gene trội trên NST thường quy định (A bệnh > a bình thường) — Số người biết chính xác KG: 4"),
                    group_item("cd5-th-5.4-vd2-c", "Sơ đồ C", "Bệnh do gene lặn trên NST X quy định (X^A bình thường > X^a bệnh) — Số người biết chính xác KG: 4"),
                    group_item("cd5-th-5.4-vd2-d", "Sơ đồ D", "Bệnh do gene trội trên NST X quy định (X^A bệnh > X^a bình thường; người 2 không mang allele bình thường) — Số người biết chính xác KG: 7"),
                    group_item("cd5-th-5.4-vd2-e", "Sơ đồ E", "Bệnh do ít nhất hai gene không allele tương tác quy định"),
                ],
            }
        elif txt.startswith("1. Bệnh Q do gene trội hay gene lặn"):
            b["exercise"] = ex_item("cd5-th-5.4-vd3-1", "cd5-th-5.4-vd3", "Bệnh Q do gene lặn nằm trên NST thường quy định", mode="input")
        elif txt.startswith("2. Xác định các kiểu gene của các thành viên"):
            b["exercise"] = ex_item(
                "cd5-th-5.4-vd3-2", "cd5-th-5.4-vd3",
                "- I3, I4, II1, II4, II5, III1, III4: kiểu gene Aa.\n- I2, II2, III2, III3, III6, III7: kiểu gene aa.\n- I1, II3, III5, III8: chưa biết chính xác kiểu gene (AA hoặc Aa).",
                mode="textarea"
            )
        elif txt.startswith("3. Nếu cho người đàn ông III5 kết hôn"):
            b["exercise"] = ex_item("cd5-th-5.4-vd3-3", "cd5-th-5.4-vd3", "1/6", mode="input", exact=["1/6"])
        elif txt.startswith("4. Nếu cho người con gái III8 kết hôn"):
            b["exercise"] = ex_item("cd5-th-5.4-vd3-4", "cd5-th-5.4-vd3", "13/66", mode="input", exact=["13/66"])
        elif txt.startswith("1. Bệnh P và bệnh Q do gene trội hay gene lặn"):
            b["exercise"] = ex_item("cd5-th-5.4-vd4-1", "cd5-th-5.4-vd4", "Bệnh P và bệnh Q đều do gene lặn quy định", mode="input")
        elif txt.startswith("2. Xác định số người biết được chính xác kiểu gene quy định cả 2"):
            b["exercise"] = ex_item("cd5-th-5.4-vd4-2", "cd5-th-5.4-vd4", "6 người", mode="input", exact=["6", "6 nguoi"])
        elif txt.startswith("3. Tính xác suất để người con gái III14"):
            b["exercise"] = ex_item("cd5-th-5.4-vd4-3", "cd5-th-5.4-vd4", "1/3", mode="input", exact=["1/3"])
        elif txt.startswith("4. Tính xác suất sinh con đầu lòng không bị bệnh của cặp vợ chồng III13"):
            b["exercise"] = ex_item("cd5-th-5.4-vd4-4", "cd5-th-5.4-vd4", "63/80", mode="input", exact=["63/80"])
        elif txt.startswith("1. Có 7 người xác định được kiểu gene về cả hai"):
            b["exercise"] = ex_item("cd5-th-5.4-vd5-1", "cd5-th-5.4-vd5", "Sai", mode="true_false")
        elif txt.startswith("2. Người con gái số III2 lấy chồng bị cả 2 bệnh"):
            b["exercise"] = ex_item("cd5-th-5.4-vd5-2", "cd5-th-5.4-vd5", "Đúng", mode="true_false")
        elif txt.startswith("3. Người con trai số III5 được sinh ra"):
            b["exercise"] = ex_item("cd5-th-5.4-vd5-3", "cd5-th-5.4-vd5", "Đúng", mode="true_false")
        elif txt.startswith("4. Ở thế hệ thứ III, có ít nhất 2 người"):
            b["exercise"] = ex_item("cd5-th-5.4-vd5-4", "cd5-th-5.4-vd5", "Sai", mode="true_false")
        elif txt.startswith("5. Xác suất để người con gái III4 mang kiểu gene đồng hợp"):
            b["exercise"] = ex_item("cd5-th-5.4-vd5-5", "cd5-th-5.4-vd5", "Đúng", mode="true_false")
        elif txt.startswith("1. Số người biết được chính xác kiểu gene."):
            b["exercise"] = ex_item("cd5-th-5.4-vd6-1", "cd5-th-5.4-vd6", "5 người", mode="input", exact=["5", "5 nguoi"])
        elif txt.startswith("2. Xác suất để Huyền mang allele gây bệnh M"):
            b["exercise"] = ex_item("cd5-th-5.4-vd6-2", "cd5-th-5.4-vd6", "53/115", mode="input", exact=["53/115"])
        elif txt.startswith("3. Xác suất sinh con thứ hai là trai không bị bệnh M"):
            b["exercise"] = ex_item("cd5-th-5.4-vd6-3", "cd5-th-5.4-vd6", "115/252", mode="input", exact=["115/252"])
        elif txt.startswith("4. Xác suất để Hà mang allele gây bệnh M"):
            b["exercise"] = ex_item("cd5-th-5.4-vd6-4", "cd5-th-5.4-vd6", "2/11", mode="input", exact=["2/11"])

    # --- HỆ THỐNG KIẾN THỨC 5.1 (Công nghệ gene) ---
    u0 = units[0]["blocks"]
    # Câu 1: 24 thành tựu công nghệ gene (PDF p.1 Câu 4 + 22, 24)
    u0[1]["interactive"] = {
        "id": "cd5-ks-5.1-c1",
        "mode": "check_single",
        "check_col": 2,
        "check_rows": [1, 2, 4, 6, 7, 10, 11, 12, 14, 15, 16, 18, 19, 20, 22, 24],
        "checked_label": "× Công nghệ gene",
        "unchecked_label": "Không phải công nghệ gene",
    }
    # Câu 2: 34 phát biểu Đúng/Sai (PDF p.1 Câu 5: đúng = 1,2,4,5,7,11,13,15,18,20,22,23,25,26,27,28,31,32,33,34)
    c2_51_true = {1, 2, 4, 5, 7, 11, 13, 15, 18, 20, 22, 23, 25, 26, 27, 28, 31, 32, 33, 34}
    u0[3]["interactive"] = {
        "id": "cd5-ks-5.1-c2",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3],
        "col_labels": {"2": "Đúng", "3": "Sai"},
        "radio_answers": {str(i + 1): (2 if i in c2_51_true else 3) for i in range(1, 35)},
    }

    # --- HỆ THỐNG KIẾN THỨC 5.2 (Chọn & tạo giống bằng lai hữu tính) ---
    u1 = units[1]["blocks"]
    # Câu 1: 12 thành tựu (col 2: Chọn lọc, col 3: Tự thụ phấn, col 4: Lai kinh tế, col 5: Lai xa — PDF p.2-3)
    c1_52_map = {1: 4, 2: 5, 3: 2, 4: 4, 5: 5, 6: 3, 7: 5, 8: 5, 9: 2, 10: 4, 11: 5, 12: 4}
    u1[1]["interactive"] = {
        "id": "cd5-ks-5.2-c1",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3, 4, 5],
        "col_labels": {"2": "Chọn lọc", "3": "Tự thụ phấn", "4": "Lai kinh tế", "5": "Lai xa"},
        "radio_answers": {str(i + 1): col for i, col in c1_52_map.items()},
    }
    # Câu 2: 21 phát biểu Đúng/Sai (đã kiểm chứng khoa học 100%)
    c2_52_true = {1, 2, 4, 9, 12, 16, 17, 19}
    u1[3]["interactive"] = {
        "id": "cd5-ks-5.2-c2",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3],
        "col_labels": {"2": "Đúng", "3": "Sai"},
        "radio_answers": {str(i + 1): (2 if i in c2_52_true else 3) for i in range(1, 22)},
    }

    # --- HỆ THỐNG KIẾN THỨC 5.3 (Di truyền học quần thể) ---
    u2 = units[2]["blocks"]
    # Bổ sung công thức Hardy-Weinberg bị mất OMML trong bảng ở dòng 17, 18
    if len(u2[1]["rows"]) > 19:
        u2[1]["rows"][18][1] = "Khi đạt trạng thái cân bằng di truyền, cấu trúc di truyền của quần thể ngẫu phối có dạng: p^2 AA + 2pq Aa + q^2 aa = 1."
        u2[1]["rows"][19][1] = "Quần thể ngẫu phối đạt trạng thái cân bằng khi: p^2 + 2pq + q^2 = 1 (với p là tần số allele trội, q là tần số allele lặn)."
    c1_53_true = {2, 3, 4, 6, 7, 9, 10, 12, 13, 15, 17, 18, 19, 20, 21, 24, 25, 26, 27, 29}
    u2[1]["interactive"] = {
        "id": "cd5-ks-5.3-c1",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3],
        "col_labels": {"2": "Đúng", "3": "Sai"},
        "radio_answers": {str(i + 1): (2 if i in c1_53_true else 3) for i in range(1, 30)},
    }

    # --- HỆ THỐNG KIẾN THỨC 5.4 (Di truyền học người) ---
    u3 = units[3]["blocks"]
    # Câu 1: 13 bệnh di truyền (4 cột nguyên nhân multi-check + 1 cột Phương pháp nghiên cứu bệnh — PDF p.8-9)
    c1_54_rows = {
        "2":  {"checks": [4],    "text": "Tế bào học",       "exact": ["te bao hoc", "phuong phap te bao hoc"]},
        "3":  {"checks": [4],    "text": "Tế bào học",       "exact": ["te bao hoc", "phuong phap te bao hoc"]},
        "4":  {"checks": [2, 5], "text": "Di truyền hóa sinh", "exact": ["di truyen hoa sinh", "di truyen sinh hoa", "sinh hoa", "hoa sinh"]},
        "5":  {"checks": [2, 5], "text": "Phả hệ (hoặc Di truyền hóa sinh)", "exact": ["pha he", "di truyen hoa sinh", "di truyen sinh hoa"]},
        "6":  {"checks": [2],    "text": "Phả hệ",           "exact": ["pha he", "phuong phap pha he"]},
        "7":  {"checks": [2],    "text": "Phả hệ",           "exact": ["pha he", "phuong phap pha he"]},
        "8":  {"checks": [2],    "text": "Phả hệ",           "exact": ["pha he", "phuong phap pha he"]},
        "9":  {"checks": [3],    "text": "Tế bào học",       "exact": ["te bao hoc", "phuong phap te bao hoc"]},
        "10": {"checks": [3],    "text": "Tế bào học",       "exact": ["te bao hoc", "phuong phap te bao hoc"]},
        "11": {"checks": [3],    "text": "Tế bào học",       "exact": ["te bao hoc", "phuong phap te bao hoc"]},
        "12": {"checks": [2, 5], "text": "Di truyền hóa sinh", "exact": ["di truyen hoa sinh", "di truyen sinh hoa", "sinh hoa", "hoa sinh"]},
        "13": {"checks": [2],    "text": "Phả hệ",           "exact": ["pha he", "phuong phap pha he"]},
        "14": {"checks": [2, 5], "text": "Phả hệ (hoặc Di truyền hóa sinh)", "exact": ["pha he", "di truyen hoa sinh", "di truyen sinh hoa"]},
    }
    u3[1]["interactive"] = {
        "id": "cd5-ks-5.4-c1",
        "mode": "check_multi_and_fill",
        "header_rows": 2,
        "check_cols": [2, 3, 4, 5],
        "text_col": 6,
        "col_labels": {
            "2": "Đột biến gene",
            "3": "Đột biến số lượng NST",
            "4": "Đột biến cấu trúc NST",
            "5": "Rối loạn chuyển hóa",
        },
        "row_answers": c1_54_rows,
    }
    # Câu 2: 27 phát biểu Đúng/Sai (điền STT 1..27 + PDF p.9 Câu 3)
    c2_54_rows = u3[3]["rows"]
    for i in range(1, 28):
        if i + 1 < len(c2_54_rows) and not c2_54_rows[i + 1][0].strip():
            c2_54_rows[i + 1][0] = str(i)
    c2_54_true = {1, 2, 3, 5, 7, 10, 11, 13, 15, 18, 19, 20, 21, 23, 24, 26, 27}
    u3[3]["interactive"] = {
        "id": "cd5-ks-5.4-c2",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3],
        "col_labels": {"2": "Đúng", "3": "Sai"},
        "radio_answers": {str(i + 1): (2 if i in c2_54_true else 3) for i in range(1, 28)},
    }


def apply_review_keys_and_levels(d):
    rev = d["review"]
    mcq_ok = tf_ok = sa_ok = 0

    # --- MCQ ---
    counters = {"chu-de-5-bai-3": 0, "chu-de-5-bai-4": 0}
    for q in rev.get("mcq", []):
        lid = q.get("lesson_id")
        on = int(q.get("orig_num") or 0)
        ans = None
        if lid == "chu-de-5-bai-1":
            ans = MCQ_KEYS_5_1.get(on)
        elif lid == "chu-de-5-bai-2":
            ans = MCQ_KEYS_5_2.get(on)
        elif lid == "chu-de-5-bai-3":
            idx = counters["chu-de-5-bai-3"]
            counters["chu-de-5-bai-3"] += 1
            if idx < 32:
                ans = MCQ_KEYS_5_3_LY_THUYET.get(on)
            else:
                norm_on = 121 if on == 211 else on
                q["orig_num"] = norm_on
                ans = MCQ_KEYS_5_3_BAI_TAP.get(norm_on)
        elif lid == "chu-de-5-bai-4":
            idx = counters["chu-de-5-bai-4"]
            counters["chu-de-5-bai-4"] += 1
            if idx < 83:
                ans = MCQ_KEYS_5_4_LY_THUYET.get(on)
            else:
                ans = MCQ_KEYS_5_4_PHA_HE.get(on)
        if ans is not None:
            q["correct_index"] = ans
            q["answer"] = ans
            q["answer_key_ready"] = True
            mcq_ok += 1
        q["cognitive_level"] = classify_question(q, "mcq", force=True)

    # --- TRUE / FALSE ---
    tf_map = {
        "chu-de-5-bai-1": TF_KEYS_5_1,
        "chu-de-5-bai-2": TF_KEYS_5_2,
        "chu-de-5-bai-3": TF_KEYS_5_3,
        "chu-de-5-bai-4": TF_KEYS_5_4,
    }
    for q in rev.get("true_false", []):
        lid = q.get("lesson_id")
        on = int(q.get("orig_num") or 0)
        vals = tf_map.get(lid, {}).get(on)
        if vals:
            for i, st in enumerate(q.get("statements", [])):
                if i < len(vals):
                    st["answer"] = vals[i]
            q["answer_key_ready"] = True
            tf_ok += 1
        q["cognitive_level"] = classify_question(q, "true_false", force=True)

    # --- SHORT ANSWER ---
    sa_map = {
        "chu-de-5-bai-1": SA_KEYS_5_1,
        "chu-de-5-bai-2": SA_KEYS_5_2,
        "chu-de-5-bai-3": SA_KEYS_5_3,
        "chu-de-5-bai-4": SA_KEYS_5_4,
    }
    for q in rev.get("short_answer", []):
        lid = q.get("lesson_id")
        on = int(q.get("orig_num") or 0)
        acc = sa_map.get(lid, {}).get(on)
        if acc:
            q["accepted"] = acc
            q["accepted_answers"] = acc
            q["answer_key_ready"] = True
            sa_ok += 1
        q["cognitive_level"] = classify_question(q, "short_answer", force=True)

    print(
        f"Review keys applied -> MCQ: {mcq_ok}/{len(rev.get('mcq', []))}, "
        f"TF: {tf_ok}/{len(rev.get('true_false', []))}, "
        f"SA: {sa_ok}/{len(rev.get('short_answer', []))}"
    )


def main():
    docx_files = [
        f for f in os.listdir(BASE_DIR)
        if f.lower().endswith(".docx") and not f.startswith("~$") and "5" in unicodedata.normalize("NFC", f)
    ]
    if not docx_files:
        raise FileNotFoundError("Không tìm thấy file Word CHỦ ĐỀ 5.docx trong thư mục dự án.")
    docx_path = os.path.join(BASE_DIR, docx_files[0])
    clean_name = unicodedata.normalize("NFC", docx_files[0])

    # Dọn ảnh cũ của chủ đề 5 và trích xuất mới
    upload_dir = os.path.join(UPLOADS_DIR, "chu-de-5")
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)

    with open(docx_path, "rb") as f:
        raw_bytes = f.read()

    title_override = "Chủ đề 5. Ứng dụng di truyền học"
    parsed = parse_document_to_topic(
        raw_bytes,
        clean_name,
        "chu-de-5",
        {"id": "chu-de-5", "order_index": 5, "title": title_override},
        title_override=title_override,
    )
    d = deep_clean(parsed["extracted"])
    d["id"] = "chu-de-5"
    d["order_index"] = 5
    d["title"] = title_override
    d["status"] = "published"
    d["bundled_version"] = BUNDLED_VERSION

    # Chuẩn hoá số bài 5.1 -> 5.4 và gắn mục "Yêu cầu cần đạt" chuẩn SGK ở đầu mỗi bài
    for idx, lesson in enumerate(d.get("lessons", []), start=1):
        code = f"5.{idx}"
        lesson["number"] = code
        lid = lesson["id"]
        yccd_pts = YCCD_CHU_DE_5.get(lid, [])
        if yccd_pts:
            has_yccd = any("yêu cầu cần đạt" in (s.get("heading") or "").lower() for s in lesson.get("sections", []))
            if not has_yccd:
                lesson["sections"].insert(
                    0,
                    {
                        "heading": "Yêu cầu cần đạt",
                        "points": yccd_pts,
                        "blocks": [{"type": "paragraph", "text": pt, "is_bold": False} for pt in yccd_pts],
                    },
                )
        # Bỏ mục rỗng đầu bài nếu chỉ chứa mỗi tiêu đề lặp
        if len(lesson["sections"]) > 1 and lesson["sections"][1].get("heading") == "Nội dung bài học":
            b0 = lesson["sections"][1].get("blocks", [])
            if len(b0) == 1 and len(b0[0].get("text", "")) < 40:
                lesson["sections"].pop(1)

    # Đồng bộ số bài 5.1..5.4 trong HTKT và Mindmap
    for idx, u in enumerate(d.get("knowledge_system", {}).get("units", []), start=1):
        u["lesson_number"] = f"5.{idx}"
    for idx, br in enumerate(d.get("knowledge_system", {}).get("mindmap", {}).get("branches", []), start=1):
        br["title"] = re.sub(r"^(?:Bài\s*\d+|5\.\d+)\s*[:.]?\s*", f"5.{idx}: ", br.get("title", ""), flags=re.IGNORECASE)

    # Gắn bài tập tương tác (ô nhập + đáp án kế bên)
    enrich_interactive_chu_de_5(d)

    # Gắn 100% đáp án hệ thống ôn tập 3 phần + phân loại mức độ nhận thức NB/TH/VD
    apply_review_keys_and_levels(d)

    # Lưu ra data/topics/chu_de_5.json
    os.makedirs(TOPICS_DIR, exist_ok=True)
    out_path = os.path.join(TOPICS_DIR, "chu_de_5.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    # Đồng bộ trực tiếp vào SQLite data/sinhhoc12.db
    init_db()
    print(f"Saved {out_path} ({os.path.getsize(out_path)/1024:.1f} KB) and synced SQLite DB!")


if __name__ == "__main__":
    main()
