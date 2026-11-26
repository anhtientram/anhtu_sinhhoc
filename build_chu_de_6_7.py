#!/usr/bin/env python3
"""
Trích xuất, chuẩn hoá và đồng bộ hoàn chỉnh CHỦ ĐỀ 6 (Tiến hóa) và CHỦ ĐỀ 7 (Sinh thái học và Môi trường)
giống 100% quy chuẩn của Chủ đề 1 -> 5:
  - Thống nhất đề mục 6.1..6.5 và 7.1..7.6
  - Bổ sung mục "Yêu cầu cần đạt" chuẩn SGK Sinh học 12 (CT GDPT 2018) cho từng bài
  - Sửa lỗi chính tả / OCR / công thức
  - Gắn ô nhập đáp án & đáp án chuẩn (đối chiếu từ Sinh học 12 - Đáp án hoàn chỉnh.pdf trang 10-30)
    cho toàn bộ Hệ thống kiến thức và Hệ thống ôn tập 3 phần
  - Gắn nhãn mức độ nhận thức (Nhận biết / Thông hiểu / Vận dụng) cho Ma trận trộn đề 3x3
  - Đồng bộ vào data/topics/chu_de_6.json, data/topics/chu_de_7.json và SQLite data/sinhhoc12.db
"""

import json
import os
import re
import shutil
import unicodedata

from classify_levels import classify_question
from database import init_db
from importer import UPLOADS_DIR, parse_document_to_topic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")
BUNDLED_VERSION = "2026.11.26-chu-de-6-7-v2"

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


# =====================================================================
# 1. YÊU CẦU CẦN ĐẠT CHUẨN SGK SINH HỌC 12 (CHỦ ĐỀ 6 & 7)
# =====================================================================
YCCD_MAP = {
    # --- CHỦ ĐỀ 6: TIẾN HOÁ ---
    "chu-de-6-bai-1": [
        "1. Trình bày được các bằng chứng tiến hoá: bằng chứng hoá thạch, bằng chứng giải phẫu so sánh, bằng chứng tế bào học và sinh học phân tử.",
        "2. Phân biệt được cơ quan tương đồng, cơ quan tương tự, cơ quan thoái hoá và hiện tượng lại tổ; lấy được ví dụ minh hoạ.",
    ],
    "chu-de-6-bai-2": [
        "1. Trình bày được quy trình nghiên cứu khoa học của Darwin và cơ chế chọn lọc tự nhiên theo quan niệm của Darwin.",
        "2. Phân biệt được chọn lọc tự nhiên và chọn lọc nhân tạo; nêu được đóng góp và hạn chế của học thuyết tiến hoá Darwin.",
    ],
    "chu-de-6-bai-3": [
        "1. Nêu được khái niệm tiến hoá nhỏ và chứng minh quần thể là đơn vị tiến hoá cơ sở.",
        "2. Trình bày được vai trò và đặc điểm tác động của các nhân tố tiến hoá: đột biến, dòng gene, phiêu bạt di truyền, giao phối không ngẫu nhiên và chọn lọc tự nhiên.",
        "3. Trình bày được quá trình hình thành đặc điểm thích nghi và giải thích tính hợp lí tương đối của các đặc điểm thích nghi.",
    ],
    "chu-de-6-bai-4": [
        "1. Phát biểu được khái niệm loài sinh học và phân biệt các cơ chế cách li sinh sản (cách li trước hợp tử và cách li sau hợp tử).",
        "2. Trình bày được các con đường hình thành loài mới (cùng khu vực địa lí và khác khu vực địa lí).",
        "3. Phân biệt được tiến hoá nhỏ và tiến hoá lớn; đọc và giải thích được sơ đồ cây phát sinh chủng loại.",
    ],
    "chu-de-6-bai-5": [
        "1. Vẽ được sơ đồ các giai đoạn chính trong quá trình phát sinh sự sống trên Trái Đất (tiến hoá hoá học, tiến hoá tiền sinh học và tiến hoá sinh học).",
        "2. Nêu được các đại địa chất và sự phát triển của sinh giới qua các đại địa chất.",
        "3. Trình bày được các giai đoạn chính trong quá trình phát sinh loài người.",
    ],
    # --- CHỦ ĐỀ 7: SINH THÁI HỌC VÀ MÔI TRƯỜNG ---
    "chu-de-7-bai-1": [
        "1. Nêu được khái niệm môi trường sống và phân biệt các nhân tố sinh thái vô sinh, hữu sinh.",
        "2. Phát biểu được khái niệm giới hạn sinh thái, khoảng thuận lợi, khoảng chống chịu và các quy luật sinh thái (tác động tổng hợp, tác động không đồng đều).",
        "3. Trình bày được nhịp sinh học, đồng hồ sinh học và sự thích nghi của sinh vật với ánh sáng, nhiệt độ.",
    ],
    "chu-de-7-bai-2": [
        "1. Phát biểu được khái niệm quần thể sinh vật và phân tích các mối quan hệ sinh thái giữa các cá thể trong quần thể (hỗ trợ và cạnh tranh cùng loài).",
        "2. Trình bày được các đặc trưng cơ bản của quần thể: kích thước, mật độ, tỉ lệ giới tính, nhóm tuổi, kiểu phân bố cá thể và kiểu tăng trưởng.",
        "3. Phân tích được nguyên nhân, cơ chế điều chỉnh mật độ và các dạng biến động số lượng cá thể của quần thể (theo chu kì và không theo chu kì).",
    ],
    "chu-de-7-bai-3": [
        "1. Phát biểu được khái niệm quần xã sinh vật và phân tích các đặc trưng cơ bản của quần xã (thành phần loài, độ đa dạng, độ phong phú, phân bố không gian).",
        "2. Phân biệt được các mối quan hệ sinh thái giữa các loài trong quần xã (hỗ trợ: cộng sinh, hợp tác, hội sinh; đối kháng: cạnh tranh, kí sinh, ức chế cảm nhiễm, sinh vật ăn sinh vật).",
        "3. Nêu được khái niệm ổ sinh thái, cạnh tranh loại trừ và ứng dụng kiến thức về ổ sinh thái trong sản xuất nông nghiệp, bảo tồn.",
    ],
    "chu-de-7-bai-4": [
        "1. Phát biểu được khái niệm hệ sinh thái, thành phần cấu trúc và các kiểu hệ sinh thái chủ yếu.",
        "2. Phân tích được quá trình trao đổi vật chất và chuyển hoá năng lượng trong hệ sinh thái: chuỗi thức ăn, lưới thức ăn, bậc dinh dưỡng, tháp sinh thái và hiệu suất sinh thái.",
        "3. Trình bày được diễn thế sinh thái (nguyên sinh, thứ sinh), nguyên nhân và tầm quan trọng của việc nghiên cứu diễn thế sinh thái.",
    ],
    "chu-de-7-bai-5": [
        "1. Phát biểu được khái niệm chu trình sinh – địa – hoá và phân tích chu trình carbon, nitrogen và nước trong tự nhiên.",
        "2. Trình bày được khái niệm sinh quyển và đặc điểm khí hậu, sinh vật của các khu sinh học (biome) chủ yếu trên Trái Đất.",
    ],
    "chu-de-7-bai-6": [
        "1. Nêu được khái niệm sinh thái học phục hồi, sinh thái học bảo tồn và các biện pháp phục hồi, bảo tồn đa dạng sinh học (bảo tồn nguyên vị, chuyển vị).",
        "2. Trình bày được khái niệm phát triển bền vững, phân loại tài nguyên thiên nhiên và các lĩnh vực trụ cột của phát triển bền vững (kinh tế, xã hội, môi trường).",
    ],
}

# =====================================================================
# 2. SỬA LỖI CHÍNH TẢ / OCR THƯỜNG GẶP TRONG CHỦ ĐỀ 6 & 7
# =====================================================================
TYPO_FIXES = [
    ("Sinh học tế bài học", "Sinh học tế bào học"),
    ("giơi đực", "giới đực"),
    ("chúc năng", "chức năng"),
    ("thực bien hiện", "thực hiện"),
    ("trinh tự nucleotide", "trình tự nucleotide"),
    ("phân từ protein", "phân tử protein"),
    ("Không xác đinh", "Không xác định"),
    ("Phiêu bạt di truyên", "Phiêu bạt di truyền"),
    ("tỉnh dung hoà", "tính dung hoà"),
    ("Trái Đát", "Trái Đất"),
    ("hydrocarbone", "hydrocarbon"),
    ("Oxygene", "Oxygen"),
    ("Tròn quá trình", "Trong quá trình"),
    ("xác địng đúng", "xác định đúng"),
    ("phất biểu", "phát biểu"),
    ("tính trặng lặn", "tính trạng lặn"),
    ("đổi với quá trình", "đối với quá trình"),
    ("Nhận xét nảo", "Nhận xét nào"),
    ("Cân 57:", "Câu 57:"),
    ("dến hầu hết", "đến hầu hết"),
    ("dộng vật", "động vật"),
    ("genebiểu hiện", "gene biểu hiện"),
    ("thùy hải sản", "thuỷ hải sản"),
    ("Khu Sinh học (biomie)", "Khu sinh học (biome)"),
    ("khoang 0°C.", "khoảng 0°C,"),
    ("rừng là rộng rụng là", "rừng lá rộng rụng lá"),
    ("thao nguyên", "thảo nguyên"),
    ("gia tang dân số", "gia tăng dân số"),
    ("biện phát quan trọng", "biện pháp quan trọng"),
    ("dẫn đền phá hủỷ", "dẫn đến phá huỷ"),
    ("mức độ phức tạo dần", "mức độ phức tạp dần"),
    ("sâu đục than", "sâu đục thân"),
    ("sau hại quả", "sâu hại quả"),
    ("liên qua trực tiếp", "liên quan trực tiếp"),
    ("lời giải", "lời giải"),
    ("\ufeff", ""),
    ("\u200b", ""),
]


def clean_str(s: str) -> str:
    if not s:
        return s
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


def normalize_2row_header(rows):
    """Đảm bảo dòng header thứ 2 (rows[1]) có đủ nhãn cột không bị rỗng do merge dọc từ Word."""
    if len(rows) < 2:
        return
    r0, r1 = rows[0], rows[1]
    if not r1[0].strip() and r0[0].strip():
        r1[0] = r0[0]
    if len(r1) > 1 and len(r0) > 1 and not r1[1].strip() and r0[1].strip():
        r1[1] = r0[1]


def build_tf_radio_from_table(table_block, tid, true_nums, header_rows=2, clear_premarked=True):
    """
    Gắn metadata check_radio (2 cột Đúng / Sai) vào bảng HTKT Đúng/Sai
    dựa theo STT số nguyên ở cột 0 (bỏ qua dòng tiêu đề phụ 1 cột).
    """
    rows = table_block["rows"]
    normalize_2row_header(rows)
    true_set = set(true_nums)
    radio_answers = {}
    seq = 0
    for ri in range(header_rows, len(rows)):
        r = rows[ri]
        if len(r) < 4:
            continue
        stt_raw = r[0].strip()
        m = re.match(r"^(\d+)", stt_raw)
        if m:
            num = int(m.group(1))
            seq = num
        else:
            if not (r[1] or "").strip():
                continue
            seq += 1
            num = seq
            r[0] = str(num)
        if clear_premarked:
            r[2] = ""
            r[3] = ""
        radio_answers[str(ri)] = 2 if num in true_set else 3

    table_block["interactive"] = {
        "id": tid,
        "mode": "check_radio",
        "header_rows": header_rows,
        "radio_cols": [2, 3],
        "col_labels": {"2": "Đúng", "3": "Sai"},
        "radio_answers": radio_answers,
    }


def ex_item(eid, group, answer, mode="input", exact=None, grade_type="compare"):
    obj = {
        "id": eid,
        "group": group,
        "mode": mode,
        "answer": answer,
        "grade_type": "exact" if (exact is not None or mode == "true_false") else grade_type,
    }
    if exact is not None:
        obj["exact"] = exact
    return obj


def cell_ans(answer, multiline=None):
    if multiline is None:
        multiline = len(answer) > 42 or "\n" in answer
    return {"answer": answer, "grade_type": "compare", "multiline": multiline}


# =====================================================================
# 3. ĐÁP ÁN ÔN TẬP 3 PHẦN — CHỦ ĐỀ 6 (PDF trang 12-18)
# =====================================================================
CD6_MCQ = {
    "chu-de-6-bai-1": L(
        "D D D D D A C B D C D D C "
        "A C B B C D D B D C D C A "
        "A A B D A A A D B D C D D"
    ),
    "chu-de-6-bai-2": L(
        "C B D B A C A A C C A A B "
        "A D B B C A C C C A C B D "
        "C B B D A C D D D C C B"
    ),
    "chu-de-6-bai-3": L(
        "B B A B C C A D C D D D B "
        "A C D A C B D B D C A D C "
        "C B A C C C B D A B D C C "
        "A D C A B A B C C A C A C "
        "D B B A C A C A A A A B C "
        "C C C B D D B B A A B C D "
        "C B D D D B A D D A C A C "
        "A B B C B A D B C B D C B "
        "D C B B D D A C B B D C B "
        "A C B B C D A B C B C B A "
        "A C"
    ),
    "chu-de-6-bai-4_p1": L(
        "A D B A A C D D A B D B B "
        "D C D B C A D C A B A D B "
        "A A A D C A B D C A D A B "
        "D A D D A B A A C A A"
    ),
    "chu-de-6-bai-4_p2": L("B A D D D A D A"),
    "chu-de-6-bai-5": L(
        "A C D B D C D C D C C B A "
        "D C A D C A A B A C D A D "
        "B D D D A A C C B D D C A "
        "B A C A B C C C C D C C C "
        "B B B A A A C D A B A A A "
        "A D"
    ),
}

CD6_TF = {
    "chu-de-6-bai-1": TF({
        1: "S Đ Đ S", 2: "Đ S Đ S", 3: "S Đ Đ Đ", 4: "Đ S Đ S",
        5: "Đ Đ S S", 6: "Đ Đ Đ S", 7: "Đ S S Đ", 8: "Đ Đ S S",
    }),
    "chu-de-6-bai-2": TF({
        1: "Đ Đ Đ S", 2: "Đ S Đ S", 3: "Đ Đ Đ S", 4: "S S S Đ",
    }),
    "chu-de-6-bai-3": TF({
        1: "Đ Đ Đ S", 2: "Đ Đ S S", 3: "S Đ S S", 4: "Đ Đ S Đ",
        5: "Đ S Đ S", 6: "Đ S Đ S", 7: "Đ S S S", 8: "Đ Đ Đ S",
        9: "Đ S Đ Đ", 10: "Đ S Đ Đ", 11: "Đ Đ S S",
    }),
    "chu-de-6-bai-4": TF({
        1: "S S Đ Đ", 2: "Đ Đ Đ S", 3: "Đ Đ Đ S",
        4: "S Đ S Đ", 5: "Đ Đ Đ Đ", 6: "S Đ Đ Đ",
    }),
    "chu-de-6-bai-5": TF({
        1: "S Đ S S", 2: "Đ Đ S S", 3: "S S S Đ", 4: "S S Đ S",
    }),
}

CD6_SA = {
    "chu-de-6-bai-1": {1: ["2"], 2: ["2"], 3: ["1"], 4: ["3,9", "3.9"], 5: ["2"], 6: ["3"]},
    "chu-de-6-bai-2": {1: ["1"], 2: ["3"], 3: ["3"], 4: ["1"], 5: ["3"]},
    "chu-de-6-bai-3": {1: ["3"], 2: ["4"], 3: ["2"], 4: ["4"], 5: ["2"], 6: ["3"], 7: ["3"], 8: ["2"], 9: ["3"], 10: ["3"]},
    "chu-de-6-bai-4": {1: ["4"], 2: ["4"], 3: ["3"], 4: ["2"], 5: ["2"], 6: ["3"], 7: ["2"], 8: ["5"], 9: ["3"], 10: ["4"], 11: ["3"], 12: ["1"]},
    "chu-de-6-bai-5": {1: ["2"], 2: ["3"], 3: ["3"], 4: ["3"], 5: ["4"], 6: ["2"], 7: ["2"]},
}


# =====================================================================
# 4. ĐÁP ÁN ÔN TẬP 3 PHẦN — CHỦ ĐỀ 7 (PDF trang 19-30)
# =====================================================================
CD7_MCQ = {
    "chu-de-7-bai-1": L(
        "D A C D B A D B A A B B D "
        "C A B B C B B B A A B A A "
        "B A C C C C D D B B A D A "
        "C D B B A D A B A A C B C "
        "B B B D A D A B A D B"
    ),
    "chu-de-7-bai-2": L(
        "C C A A D D D D C A B D B "
        "C D D C B D A C A B C A D "
        "B D D A A D B B D C D A A "
        "B D B C D C C B B B B A D "
        "A B C C D D B C D B A A D "
        "D C B D C B A C C B B C B "
        "C A D A D A B C A D A B A "
        "D D B D B C C D D C C A D "
        "C D D A C A D D D D A A B "
        "A D D B C C D B C B B A C "
        "D B A B C A D"
    ),
    "chu-de-7-bai-3": L(
        "B A C B B B C B B B B B B "
        "D B A B B B B B A D B C B "
        "C B D D C C D B B C C B C "
        "D D C C C A D B C A C A D "
        "A C C D A C D B A B B A C "
        "D D D C D A C D C A D A C "
        "B B A B C A C B A B B C D "
        "D C C C B A A B A C B A D "
        "B B C D B A C C B"
    ),
    "chu-de-7-bai-4": L(
        "D A C A D D B C B C A A C "
        "D B C C D A A C C D D A C "
        "B B D A B C B B B B C A C "
        "A A B C C A A A D D D C B "
        "D C C D B D D C D C B B "
        "C B D D A C B C C B A B A "
        "A A C B A D A A A B B B A "
        "A D A B D D D D D A C B B "
        "C C A D A A A D A D D A B "
        "A C A C C C D A C A B B B "
        "A B A C A A A C B D D B C "
        "A D B A B D C A B A B B C "
        "B D C C B A B B A B C D D "
        "D C D D B C B C A"
    ),
    "chu-de-7-bai-5": L(
        "C A A A A A A A D C C C D "
        "C D D A C A D D B A B D D "
        "C D A B B C A D D C B C A "
        "C B A B C D B C C C A B A "
        "B C B B C D D C B B A D D "
        "B A C D D B C D D B A C"
    ),
    "chu-de-7-bai-6": L(
        "D C D D A A C C B D D A D "
        "D B C B A B B C C A D D B "
        "D D A A C D C D C A D D B "
        "B B C B B A D D B"
    ),
}

CD7_TF = {
    "chu-de-7-bai-1": TF({
        1: "Đ S Đ S", 2: "Đ Đ S Đ", 3: "S Đ Đ S", 4: "Đ S Đ S",
        5: "Đ Đ S Đ", 6: "S Đ Đ S", 7: "Đ S Đ S", 8: "Đ S Đ S",
        9: "Đ S S S", 10: "Đ Đ S Đ", 11: "Đ S S S", 12: "Đ S Đ S",
        13: "Đ S S Đ",
    }),
    "chu-de-7-bai-3": TF({
        1: "Đ Đ Đ S", 2: "S Đ S Đ", 3: "S Đ Đ Đ", 4: "S Đ S S",
        5: "Đ Đ Đ S", 6: "Đ S Đ Đ", 7: "S S S Đ", 8: "Đ S S Đ",
        9: "Đ S S Đ", 10: "Đ Đ S Đ", 11: "Đ S S Đ", 12: "Đ Đ Đ Đ",
        13: "S Đ S Đ", 14: "Đ Đ S S", 15: "Đ Đ Đ S", 16: "S S Đ S",
        17: "Đ Đ Đ S",
    }),
    "chu-de-7-bai-4": TF({
        1: "Đ S Đ Đ", 2: "S S S Đ", 3: "Đ S S Đ", 4: "S S Đ S",
        5: "Đ Đ S Đ", 6: "Đ Đ Đ Đ", 7: "S Đ Đ Đ", 8: "S S Đ Đ",
        9: "Đ S S S", 10: "Đ Đ Đ S", 11: "Đ Đ Đ Đ", 12: "S S S Đ",
        13: "S S S Đ", 14: "Đ S Đ Đ", 15: "S Đ Đ S", 16: "Đ Đ S Đ",
        17: "Đ S Đ Đ", 18: "S Đ Đ S", 19: "Đ Đ S S", 20: "S Đ S S",
    }),
    "chu-de-7-bai-5": TF({
        1: "Đ S S Đ", 2: "Đ Đ Đ S", 3: "Đ Đ Đ S", 4: "S S Đ Đ",
        5: "Đ S S Đ", 6: "Đ S S Đ", 7: "S S Đ Đ",
    }),
    "chu-de-7-bai-6": TF({
        1: "Đ Đ Đ S", 2: "Đ S Đ S", 3: "Đ S Đ S", 4: "S Đ S S",
        5: "S Đ Đ Đ", 6: "Đ S Đ S", 7: "S S Đ Đ",
    }),
}

CD7_SA = {
    "chu-de-7-bai-1": {1: ["2"], 2: ["4"], 3: ["2"], 4: ["2"], 5: ["2"], 6: ["4"], 7: ["1"], 8: ["3"]},
    "chu-de-7-bai-3": {
        1: ["1"], 2: ["3"], 3: ["1"], 4: ["4"], 5: ["3"], 6: ["2"], 7: ["2"], 8: ["0,2", "0.2"],
        9: ["2"], 10: ["4"], 11: ["2"], 12: ["1"], 13: ["4"], 14: ["4"], 15: ["4"], 16: ["2"], 17: ["3"],
    },
    # Lưu ý 7.4 có 2 câu số 14 (14a = 0,01; 14b = 2) trên cả file Word lẫn PDF trang 27
    "chu-de-7-bai-4": {
        1: ["4"], 2: ["2"], 3: ["4"], 4: ["4"], 5: ["4"], 6: ["4"], 7: ["7"], 8: ["6"], 9: ["2"], 10: ["4"],
        11: ["1"], 12: ["12"], 13: ["2"], "14a": ["0,01", "0.01"], "14b": ["2"],
        15: ["3"], 16: ["7"], 17: ["2"], 18: ["3"], 19: ["5"], 20: ["3"],
    },
    "chu-de-7-bai-5": {
        1: ["4"], 2: ["1"], 3: ["4"], 4: ["1"], 5: ["1"], 6: ["16"],
        7: ["4"], 8: ["3"], 9: ["1"], 10: ["1"], 11: ["2"], 12: ["2"],
    },
    "chu-de-7-bai-6": {
        1: ["4"], 2: ["4"], 3: ["4"], 4: ["3"], 5: ["4"],
        6: ["2"], 7: ["2"], 8: ["1"], 9: ["2"], 10: ["3"],
    },
}


# =====================================================================
# 5. GẮN BÀI TẬP TƯƠNG TÁC HỆ THỐNG KIẾN THỨC — CHỦ ĐỀ 6 (PDF trang 11-17)
# =====================================================================
def enrich_interactive_cd6(d):
    units = d["knowledge_system"]["units"]

    # --- 6.1 (Bài 17) ---
    u0 = units[0]["blocks"]
    # Câu 1 (B1): 26 ví dụ chọn 1 trong 4 cột (col 2: Giải phẫu so sánh, col 3: Sinh học tế bào học, col 4: Sinh học phân tử, col 5: Hóa thạch)
    normalize_2row_header(u0[1]["rows"])
    if len(u0[1]["rows"][1]) >= 6 and not u0[1]["rows"][1][5].strip():
        u0[1]["rows"][1][5] = "Hóa thạch (trực tiếp)"
    c1_61 = {
        1: 5, 2: 2, 3: 5, 4: 2, 5: 5, 6: 3, 7: 5, 8: 4, 9: 3, 10: 2,
        11: 4, 12: 4, 13: 2, 14: 2, 15: 2, 16: 5, 17: 2, 18: 3, 19: 4, 20: 2,
        21: 5, 22: 2, 23: 2, 24: 4, 25: 4, 26: 2,
    }
    u0[1]["interactive"] = {
        "id": "cd6-ks-6.1-c1",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3, 4, 5],
        "col_labels": {"2": "Giải phẫu so sánh", "3": "Sinh học tế bào học", "4": "Sinh học phân tử", "5": "Hóa thạch (trực tiếp)"},
        "radio_answers": {str(i + 1): col for i, col in c1_61.items()},
    }
    # Câu 2 (B3): 13 ví dụ chọn 1 trong 4 cột (col 2: Tương đồng, col 3: Tương tự, col 4: Thoái hóa, col 5: Lại tổ)
    c2_61 = {1: 4, 2: 4, 3: 5, 4: 4, 5: 4, 6: 5, 7: 2, 8: 2, 9: 2, 10: 3, 11: 4, 12: 3, 13: 3}
    u0[3]["interactive"] = {
        "id": "cd6-ks-6.1-c2",
        "mode": "check_radio",
        "header_rows": 1,
        "radio_cols": [2, 3, 4, 5],
        "col_labels": {"2": "Cơ quan tương đồng", "3": "Cơ quan tương tự", "4": "Cơ quan thoái hóa", "5": "Hiện tượng lại tổ"},
        "radio_answers": {str(i): col for i, col in c2_61.items()},
    }
    # Câu 3 (B5): 27 phát biểu Đúng/Sai (PDF p.12 Câu 4)
    build_tf_radio_from_table(u0[5], "cd6-ks-6.1-c3", [1, 2, 7, 8, 9, 10, 11, 13, 18, 21, 24, 25, 26, 27])

    # --- 6.2 (Bài 18) ---
    u1 = units[1]["blocks"]
    build_tf_radio_from_table(u1[1], "cd6-ks-6.2-c1", [2, 6, 8, 9, 10, 12, 13, 14, 17, 18, 19, 22, 24, 25, 27, 28, 30, 33])

    # --- 6.3 (Bài 19) ---
    u2 = units[2]["blocks"]
    # Câu 1 (B1): 5 nhân tố tiến hóa (check_multi cols 2..9 — PDF p.15 Câu 2)
    normalize_2row_header(u2[1]["rows"])
    u2[1]["interactive"] = {
        "id": "cd6-ks-6.3-c1",
        "mode": "check_multi",
        "header_rows": 2,
        "check_cols": [2, 3, 4, 5, 6, 7, 8, 9],
        "col_labels": {
            "2": "Tần số allele", "3": "Tần số kiểu gene", "4": "Giàu vốn gene", "5": "Nghèo vốn gene",
            "6": "Tốc độ nhanh", "7": "Tốc độ chậm", "8": "Có hướng xác định", "9": "Không xác định",
        },
        "row_answers": {
            "2": {"cols": [2, 3, 4, 7, 9]},
            "3": {"cols": [2, 3, 4, 5, 6, 9], "note": "Giàu khi nhập cư, nghèo khi di cư"},
            "4": {"cols": [3, 5, 7, 8]},
            "5": {"cols": [2, 3, 5, 6, 7, 8], "note": "Nhanh với allele trội, chậm với allele lặn"},
            "6": {"cols": [2, 3, 5, 6, 9]},
        },
    }
    # Câu 2 (B3): 78 phát biểu Đúng/Sai (PDF p.15 Câu 3)
    build_tf_radio_from_table(
        u2[3], "cd6-ks-6.3-c2",
        [1, 2, 5, 6, 7, 9, 10, 12, 14, 16, 19, 22, 23, 24, 27, 28, 29, 31, 32, 34, 36, 37, 40,
         41, 44, 45, 47, 48, 50, 52, 53, 56, 58, 59, 61, 63, 64, 65, 66, 67, 70, 72, 74, 75, 76, 78]
    )

    # --- 6.4 (Bài 20) ---
    u3 = units[3]["blocks"]
    # Câu 1 (B1): Bảng phân biệt Tiến hóa nhỏ & Tiến hóa lớn (PDF p.17 Câu 2)
    u3[1]["interactive"] = {
        "id": "cd6-ks-6.4-c1",
        "mode": "fill",
        "answers": {
            "1:2": cell_ans("Là quá trình thay đổi tần số allele và tần số kiểu gene qua các thế hệ của quần thể"),
            "1:3": cell_ans("Quá trình biến đổi xảy ra ở phạm vi loài và các đơn vị phân loại trên loài, hình thành loài mới và các bậc phân loại cao hơn, bao gồm cả sự tuyệt chủng"),
            "2:2": cell_ans("Nhỏ (phạm vi quần thể)", multiline=False),
            "2:3": cell_ans("Lớn (phạm vi loài và trên loài)", multiline=False),
            "3:2": cell_ans("Ngắn", multiline=False),
            "3:3": cell_ans("Dài (hàng triệu năm)", multiline=False),
            "4:2": cell_ans("Nghiên cứu thực nghiệm và nghiên cứu thông qua bằng chứng tiến hóa"),
            "4:3": cell_ans("Nghiên cứu thông qua các bằng chứng tiến hóa"),
        },
    }
    # Câu 2 (B3): 43 phát biểu Đúng/Sai (PDF p.17 Câu 3)
    build_tf_radio_from_table(
        u3[3], "cd6-ks-6.4-c2",
        [1, 2, 3, 6, 8, 10, 11, 15, 18, 21, 22, 23, 25, 26, 27, 28, 29, 30, 33, 34, 36, 37, 38, 40, 42]
    )

    # --- 6.5 (Bài 21) ---
    u4 = units[4]["blocks"]
    # Gộp 2 bảng tách nửa của Câu 1 (1..18 ở B1 và 19..38 ở B2) thành 1 bảng liền mạch!
    if len(u4) >= 3 and u4[1].get("type") == "table" and u4[2].get("type") == "table":
        r_extra = u4[2]["rows"]
        for r in r_extra:
            if len(r) == 2 and not r[1].strip():
                u4[1]["rows"].append([r[0]])
            else:
                u4[1]["rows"].append(r)
        u4.pop(2)
    build_tf_radio_from_table(
        u4[1], "cd6-ks-6.5-c1",
        [2, 3, 6, 10, 11, 12, 15, 16, 20, 21, 22, 24, 25, 28, 29, 30, 31, 33, 34, 35, 36, 38]
    )


# =====================================================================
# 6. GẮN BÀI TẬP TƯƠNG TÁC HỆ THỐNG KIẾN THỨC — CHỦ ĐỀ 7 (PDF trang 19-29)
# =====================================================================
def enrich_interactive_cd7(d):
    units = d["knowledge_system"]["units"]

    # --- 7.1 (Bài 22) ---
    u0 = units[0]["blocks"]
    # Câu 1 (B1): 11 ví dụ Quy luật sinh thái (PDF p.19 Câu 2)
    normalize_2row_header(u0[1]["rows"])
    c1_71 = {1: 2, 2: 3, 3: 3, 4: 4, 5: 2, 6: 3, 7: 4, 8: 4, 9: 2, 10: 4, 11: 4}
    u0[1]["interactive"] = {
        "id": "cd7-ks-7.1-c1",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3, 4],
        "col_labels": {"2": "Giới hạn sinh thái", "3": "Tác động tổng hợp", "4": "Tác động không đồng đều"},
        "radio_answers": {str(i + 1): col for i, col in c1_71.items()},
    }
    # Câu 2 (B3): 20 ví dụ Đúng/Sai (PDF p.19 Câu 3)
    build_tf_radio_from_table(u0[3], "cd7-ks-7.1-c2", [1, 2, 4, 6, 7, 11, 13, 14, 16, 18, 20])
    # Câu 3 (B5 + B6 gộp thành 1 bảng 44 phát biểu — PDF p.19 Câu 4)
    if len(u0) >= 7 and u0[5].get("type") == "table" and u0[6].get("type") == "table":
        u0[5]["rows"].extend(u0[6]["rows"])
        u0.pop(6)
    build_tf_radio_from_table(
        u0[5], "cd7-ks-7.1-c3",
        [1, 3, 5, 6, 8, 10, 12, 15, 17, 19, 21, 23, 24, 25, 26, 29, 30, 32, 34, 36, 37, 38, 40, 41, 43, 44]
    )

    # --- 7.2 (Bài 23) ---
    u1 = units[1]["blocks"]
    # Câu 1 (B1): 14 tổ chức có phải quần thể không (PDF p.20 Câu 2)
    build_tf_radio_from_table(u1[1], "cd7-ks-7.2-c1", [1, 2, 4, 5, 7, 9, 10, 13, 14])
    # Câu 2 (B3): 10 mối quan hệ Hỗ trợ (2) / Cạnh tranh (3) (PDF p.21 Câu 3)
    normalize_2row_header(u1[3]["rows"])
    c2_72 = {1: 3, 2: 3, 3: 2, 4: 3, 5: 2, 6: 3, 7: 2, 8: 2, 9: 3, 10: 2}
    for ri in range(2, len(u1[3]["rows"])):
        u1[3]["rows"][ri][2] = ""
        u1[3]["rows"][ri][3] = ""
    u1[3]["interactive"] = {
        "id": "cd7-ks-7.2-c2",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3],
        "col_labels": {"2": "Hỗ trợ", "3": "Cạnh tranh"},
        "radio_answers": {str(i + 1): col for i, col in c2_72.items()},
    }
    # Câu 3 (B5): 12 ví dụ Biến động theo chu kỳ (2) / không theo chu kỳ (3) (PDF p.21 Câu 4)
    normalize_2row_header(u1[5]["rows"])
    c3_72 = {1: 2, 2: 3, 3: 2, 4: 3, 5: 2, 6: 2, 7: 3, 8: 2, 9: 2, 10: 2, 11: 3, 12: 3}
    for ri in range(2, len(u1[5]["rows"])):
        u1[5]["rows"][ri][2] = ""
        u1[5]["rows"][ri][3] = ""
    u1[5]["interactive"] = {
        "id": "cd7-ks-7.2-c3",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3],
        "col_labels": {"2": "Theo chu kỳ", "3": "Không theo chu kỳ"},
        "radio_answers": {str(i + 1): col for i, col in c3_72.items()},
    }
    # Câu 4 (B7): Bảng 3 kiểu phân bố (PDF p.22 Câu 5)
    u1[7]["interactive"] = {
        "id": "cd7-ks-7.2-c4",
        "mode": "fill",
        "answers": {
            "1:1": cell_ans("Đồng nhất", multiline=False),
            "1:2": cell_ans("Các cá thể cạnh tranh gay gắt về không gian sống"),
            "1:3": cell_ans("Giảm sự cạnh tranh giữa các cá thể", multiline=False),
            "2:1": cell_ans("Đồng nhất", multiline=False),
            "2:2": cell_ans("Các cá thể không có tính lãnh thổ và không có xu hướng tụ họp"),
            "2:3": cell_ans("Khai thác nguồn sống tiềm tàng trong môi trường"),
            "3:1": cell_ans("Không đồng nhất", multiline=False),
            "3:2": cell_ans("Các cá thể trong quần thể có xu hướng tập trung thành từng nhóm"),
            "3:3": cell_ans("Hỗ trợ nhau chống lại các điều kiện bất lợi của môi trường"),
        },
    }
    # Câu 5 (B9): 81 phát biểu Đúng/Sai (PDF p.22 Câu 6)
    build_tf_radio_from_table(
        u1[9], "cd7-ks-7.2-c5",
        [1, 4, 5, 6, 7, 9, 10, 12, 15, 16, 18, 19, 24, 26, 28, 32, 35, 38, 40, 42, 43, 44, 48,
         52, 53, 55, 57, 58, 60, 62, 63, 64, 67, 68, 69, 71, 72, 75, 76, 77, 78, 80, 81]
    )

    # --- 7.3 (Bài 24) ---
    u2 = units[2]["blocks"]
    # Câu 1 (B1): 15 mối quan hệ trong quần xã (col 2..7 — PDF p.24 Câu 3)
    normalize_2row_header(u2[1]["rows"])
    if not u2[1]["rows"][2][1].strip():
        u2[1]["rows"][2][1] = "Tảo giáp nở hoa gây độc cho cá, tôm sống chung."
    c1_73 = {1: 5, 2: 7, 3: 2, 4: 4, 5: 7, 6: 5, 7: 4, 8: 6, 9: 2, 10: 3, 11: 4, 12: 5, 13: 3, 14: 2, 15: 7}
    # Lưu ý câu 2 & 5 trong PDF p.24 ghi "Vật chủ - vật kí sinh" (thuộc nhóm Đối kháng) -> thêm cột nhãn rõ ràng
    u2[1]["interactive"] = {
        "id": "cd7-ks-7.3-c1",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3, 4, 5, 6, 7],
        "col_labels": {
            "2": "Hội sinh", "3": "Hợp tác", "4": "Cộng sinh",
            "5": "Ức chế cảm nhiễm", "6": "Cạnh tranh", "7": "Sinh vật ăn sinh vật / Kí sinh",
        },
        "radio_answers": {str(i + 1): col for i, col in c1_73.items()},
    }
    # Câu 2 (B3): 9 hoạt động Đúng/Sai (PDF p.24 Câu 4)
    build_tf_radio_from_table(u2[3], "cd7-ks-7.3-c2", [1, 2, 6, 8, 9])
    # Câu 3 (B5): 50 phát biểu Đúng/Sai (PDF p.24 Câu 5)
    build_tf_radio_from_table(
        u2[5], "cd7-ks-7.3-c3",
        [2, 4, 5, 6, 7, 9, 11, 12, 14, 16, 17, 19, 20, 21, 24, 25, 27, 30, 31, 32, 34, 36, 38, 41, 42, 44, 45, 46, 47, 49, 50]
    )

    # --- 7.4 (Bài 25) ---
    u3 = units[3]["blocks"]
    # Xoá các dòng gạch chân dài ________ (B8..B15) để giao diện sạch đẹp
    u3[:] = [b for b in u3 if not (b.get("type") == "paragraph" and re.match(r"^[_\s]+$", b.get("text", "")))]
    for b in u3:
        txt = b.get("text", "")
        if txt.startswith("1. Lưới thức ăn này có tối đa bao nhiêu chuỗi"):
            b["exercise"] = ex_item("cd7-ks-7.4-vd1-1", "cd7-ks-7.4-vd1", "Có 6 chuỗi thức ăn", mode="input", exact=["6", "6 chuoi", "co 6 chuoi"])
        elif txt.startswith("2. Có bao nhiêu loài tham gia vào tất cả"):
            b["exercise"] = ex_item("cd7-ks-7.4-vd1-2", "cd7-ks-7.4-vd1", "Có 2 loài tham gia vào tất cả các chuỗi thức ăn: A và E", mode="input")
        elif txt.startswith("3. Chuỗi thức ăn dài nhất và ngắn nhất"):
            b["exercise"] = ex_item(
                "cd7-ks-7.4-vd1-3", "cd7-ks-7.4-vd1",
                "- Chuỗi thức ăn dài nhất có 5 bậc dinh dưỡng; chuỗi ngắn nhất có 3 bậc dinh dưỡng.\n- Loài E có thể thuộc nhiều bậc dinh dưỡng khác nhau nhất.\n- Có 2 loài chỉ thuộc 2 bậc dinh dưỡng khác nhau: loài D và F.",
                mode="textarea"
            )
        elif txt.startswith("4. Sự thay đổi số lượng cá thể của loài H"):
            b["exercise"] = ex_item(
                "cd7-ks-7.4-vd1-4", "cd7-ks-7.4-vd1",
                "Liên quan trực tiếp đến loài G và loài I. Vì H vừa là mắt xích trực tiếp tiêu thụ G, vừa là mắt xích trực tiếp bị I tiêu thụ.",
                mode="textarea"
            )
        elif txt.startswith("5. Giả sử các loài trên thuộc hệ sinh thái dưới nước"):
            b["exercise"] = ex_item(
                "cd7-ks-7.4-vd1-5", "cd7-ks-7.4-vd1",
                "Loài E. Vì thuỷ ngân là kim loại nặng, không bị phân giải trong cơ thể; theo hiện tượng khuếch đại sinh học, loài nằm cuối cùng trong chuỗi thức ăn dài nhất tích luỹ chất độc nhiều nhất.",
                mode="textarea"
            )
        elif re.match(r"^[…\.\s]*a\.", txt):
            b["text"] = re.sub(r"^[…\.\s]+", "", txt)
            b["exercise"] = ex_item("cd7-ks-7.4-vd2-a", "cd7-ks-7.4-vd2", "Sai", mode="true_false")
        elif re.match(r"^[…\.\s]*b\.", txt):
            b["text"] = re.sub(r"^[…\.\s]+", "", txt)
            b["exercise"] = ex_item("cd7-ks-7.4-vd2-b", "cd7-ks-7.4-vd2", "Sai", mode="true_false")
        elif re.match(r"^[…\.\s]*c\.", txt):
            b["text"] = re.sub(r"^[…\.\s]+", "", txt)
            b["exercise"] = ex_item("cd7-ks-7.4-vd2-c", "cd7-ks-7.4-vd2", "Đúng", mode="true_false")
        elif re.match(r"^[…\.\s]*d\.", txt):
            b["text"] = re.sub(r"^[…\.\s]+", "", txt)
            b["exercise"] = ex_item("cd7-ks-7.4-vd2-d", "cd7-ks-7.4-vd2", "Sai", mode="true_false")
    # Bảng 61 phát biểu Đúng/Sai cuối U3 (PDF p.26 Câu 3)
    tbl_74 = next(b for b in u3 if b.get("type") == "table")
    build_tf_radio_from_table(
        tbl_74, "cd7-ks-7.4-c2",
        [1, 3, 4, 7, 9, 11, 13, 15, 16, 20, 21, 22, 24, 25, 27, 28, 29, 30, 32, 34, 35, 36,
         38, 40, 42, 43, 47, 49, 51, 53, 55, 56, 57, 58, 60, 61]
    )

    # --- 7.5 (Bài 26) ---
    u4 = units[4]["blocks"]
    # Câu 1 (B1): 12 đặc điểm Khu sinh học (biome) — row 4 có 2 dấu × (Rừng lá kim phương Bắc + Đồng rêu) nên dùng check_multi! (PDF p.27-28)
    normalize_2row_header(u4[1]["rows"])
    u4[1]["interactive"] = {
        "id": "cd7-ks-7.5-c1",
        "mode": "check_multi",
        "header_rows": 2,
        "check_cols": [2, 3, 4, 5, 6, 7],
        "col_labels": {
            "2": "Rừng mưa nhiệt đới", "3": "Savanna", "4": "Sa mạc",
            "5": "Rừng lá rộng ôn đới", "6": "Rừng lá kim phương Bắc", "7": "Đồng rêu",
        },
        "row_answers": {
            "2": [5], "3": [4], "4": [3], "5": [6, 7], "6": [2], "7": [6],
            "8": [7], "9": [2], "10": [4], "11": [7], "12": [3], "13": [5],
        },
    }
    # Câu 2 (B3): 42 phát biểu Đúng/Sai (PDF p.28 Câu 2)
    build_tf_radio_from_table(
        u4[3], "cd7-ks-7.5-c2",
        [2, 4, 6, 9, 10, 12, 15, 16, 18, 21, 25, 27, 28, 31, 33, 35, 36, 37, 39, 40, 42]
    )

    # --- 7.6 (Bài 27) ---
    u5 = units[5]["blocks"]
    # Câu 1 (B1): 11 đặc điểm Phát triển bền vững (col 2: Kinh tế, col 3: Xã hội, col 4: Môi trường — PDF p.29 Câu 2)
    normalize_2row_header(u5[1]["rows"])
    c1_76 = {1: 4, 2: 2, 3: 3, 4: 2, 5: 4, 6: 3, 7: 3, 8: 3, 9: 2, 10: 3, 11: 4}
    u5[1]["interactive"] = {
        "id": "cd7-ks-7.6-c1",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3, 4],
        "col_labels": {"2": "Kinh tế", "3": "Xã hội", "4": "Môi trường"},
        "radio_answers": {str(i + 1): col for i, col in c1_76.items()},
    }
    # Câu 2 (B3): 41 phát biểu Đúng/Sai (PDF p.29 Câu 3)
    build_tf_radio_from_table(
        u5[3], "cd7-ks-7.6-c2",
        [1, 2, 4, 5, 7, 9, 12, 13, 15, 17, 18, 20, 23, 25, 27, 29, 31, 33, 35, 36, 38, 40, 41]
    )


# =====================================================================
# 7. GẮN ĐÁP ÁN ÔN TẬP 3 PHẦN & PHÂN LOẠI MỨC ĐỘ NB / TH / VD
# =====================================================================
def apply_review_keys_cd6(d):
    rev = d["review"]
    # Loại bỏ câu 35 trùng lặp từ 6.2 ("Theo quan điểm của Darwin...") bị lạc vào đầu phần MCQ 6.3 trong file Word
    rev["mcq"] = [
        q for q in rev.get("mcq", [])
        if not (
            q.get("lesson_id") == "chu-de-6-bai-3"
            and int(q.get("orig_num") or 0) == 35
            and "darwin" in (q.get("question") or "").lower()
        )
    ]
    mcq_ok = tf_ok = sa_ok = 0
    seen_64_p1 = 0
    for q in rev.get("mcq", []):
        lid = q.get("lesson_id")
        on = int(q.get("orig_num") or 0)
        ans = None
        if lid == "chu-de-6-bai-4":
            if seen_64_p1 < 50:
                ans = CD6_MCQ["chu-de-6-bai-4_p1"].get(on)
                seen_64_p1 += 1
            else:
                ans = CD6_MCQ["chu-de-6-bai-4_p2"].get(on)
        else:
            ans = CD6_MCQ.get(lid, {}).get(on)
        if ans is not None:
            q["correct_index"] = ans
            q["answer"] = ans
            q["answer_key_ready"] = True
            mcq_ok += 1
        q["cognitive_level"] = classify_question(q, "mcq", force=True)

    for q in rev.get("true_false", []):
        lid = q.get("lesson_id")
        on = int(q.get("orig_num") or 0)
        vals = CD6_TF.get(lid, {}).get(on)
        if vals:
            for i, st in enumerate(q.get("statements", [])):
                if i < len(vals):
                    st["answer"] = vals[i]
            q["answer_key_ready"] = True
            tf_ok += 1
        q["cognitive_level"] = classify_question(q, "true_false", force=True)

    for q in rev.get("short_answer", []):
        lid = q.get("lesson_id")
        on = int(q.get("orig_num") or 0)
        acc = CD6_SA.get(lid, {}).get(on)
        if acc:
            q["accepted"] = acc
            q["accepted_answers"] = acc
            q["answer_key_ready"] = True
            sa_ok += 1
        q["cognitive_level"] = classify_question(q, "short_answer", force=True)

    print(f"  [CD6] Review keys -> MCQ: {mcq_ok}/{len(rev.get('mcq', []))}, TF: {tf_ok}/{len(rev.get('true_false', []))}, SA: {sa_ok}/{len(rev.get('short_answer', []))}")


def apply_review_keys_cd7(d):
    rev = d["review"]
    mcq_ok = tf_ok = sa_ok = 0
    for q in rev.get("mcq", []):
        lid = q.get("lesson_id")
        on = int(q.get("orig_num") or 0)
        ans = CD7_MCQ.get(lid, {}).get(on)
        if ans is not None:
            q["correct_index"] = ans
            q["answer"] = ans
            q["answer_key_ready"] = True
            mcq_ok += 1
        q["cognitive_level"] = classify_question(q, "mcq", force=True)

    for q in rev.get("true_false", []):
        lid = q.get("lesson_id")
        on = int(q.get("orig_num") or 0)
        vals = CD7_TF.get(lid, {}).get(on)
        if vals:
            for i, st in enumerate(q.get("statements", [])):
                if i < len(vals):
                    st["answer"] = vals[i]
            q["answer_key_ready"] = True
            tf_ok += 1
        q["cognitive_level"] = classify_question(q, "true_false", force=True)

    seen_74_14 = 0
    for q in rev.get("short_answer", []):
        lid = q.get("lesson_id")
        on = int(q.get("orig_num") or 0)
        if lid == "chu-de-7-bai-4" and on == 14:
            seen_74_14 += 1
            acc = CD7_SA[lid].get("14a" if seen_74_14 == 1 else "14b")
        else:
            acc = CD7_SA.get(lid, {}).get(on)
        if acc:
            q["accepted"] = acc
            q["accepted_answers"] = acc
            q["answer_key_ready"] = True
            sa_ok += 1
        q["cognitive_level"] = classify_question(q, "short_answer", force=True)

    print(f"  [CD7] Review keys -> MCQ: {mcq_ok}/{len(rev.get('mcq', []))}, TF: {tf_ok}/{len(rev.get('true_false', []))}, SA: {sa_ok}/{len(rev.get('short_answer', []))}")


def build_topic(num: int, title_override: str, enrich_fn, keys_fn):
    matches = [
        f for f in os.listdir(BASE_DIR)
        if f.lower().endswith(".docx") and not f.startswith("~$") and str(num) in unicodedata.normalize("NFC", f)
    ]
    if not matches:
        raise FileNotFoundError(f"Không tìm thấy CHỦ ĐỀ {num}.docx")
    docx_path = os.path.join(BASE_DIR, matches[0])
    clean_name = unicodedata.normalize("NFC", matches[0])
    tid = f"chu-de-{num}"

    up_dir = os.path.join(UPLOADS_DIR, tid)
    if os.path.exists(up_dir):
        shutil.rmtree(up_dir)

    with open(docx_path, "rb") as f:
        raw_bytes = f.read()

    parsed = parse_document_to_topic(
        raw_bytes, clean_name, tid,
        {"id": tid, "order_index": num, "title": title_override},
        title_override=title_override,
    )
    d = deep_clean(parsed["extracted"])
    d["id"] = tid
    d["order_index"] = num
    d["title"] = title_override
    d["status"] = "published"
    d["bundled_version"] = BUNDLED_VERSION

    # Chuẩn hoá đề mục 6.1..6.5 / 7.1..7.6 + chèn Yêu cầu cần đạt chuẩn SGK
    for idx, lesson in enumerate(d.get("lessons", []), start=1):
        code = f"{num}.{idx}"
        lesson["number"] = code
        lid = lesson["id"]
        yccd = YCCD_MAP.get(lid, [])
        if yccd:
            has_yccd = any("yêu cầu cần đạt" in (s.get("heading") or "").lower() for s in lesson.get("sections", []))
            if not has_yccd:
                lesson["sections"].insert(
                    0,
                    {
                        "heading": "Yêu cầu cần đạt",
                        "points": yccd,
                        "blocks": [{"type": "paragraph", "text": pt, "is_bold": False} for pt in yccd],
                    },
                )
        if len(lesson["sections"]) > 1 and lesson["sections"][1].get("heading") == "Nội dung bài học":
            b0 = lesson["sections"][1].get("blocks", [])
            if len(b0) == 1 and len(b0[0].get("text", "")) < 45:
                lesson["sections"].pop(1)

    for idx, u in enumerate(d.get("knowledge_system", {}).get("units", []), start=1):
        u["lesson_number"] = f"{num}.{idx}"
    for idx, br in enumerate(d.get("knowledge_system", {}).get("mindmap", {}).get("branches", []), start=1):
        br["title"] = re.sub(r"^(?:Bài\s*\d+|\d+\.\d+)\s*[:.]?\s*", f"{num}.{idx}: ", br.get("title", ""), flags=re.IGNORECASE)

    enrich_fn(d)
    keys_fn(d)

    os.makedirs(TOPICS_DIR, exist_ok=True)
    out_path = os.path.join(TOPICS_DIR, f"chu_de_{num}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"Saved {out_path} ({os.path.getsize(out_path)/1024:.1f} KB) | lessons={len(d['lessons'])} | uploads={len(os.listdir(up_dir))}")


def main():
    build_topic(6, "Chủ đề 6. Tiến hóa", enrich_interactive_cd6, apply_review_keys_cd6)
    build_topic(7, "Chủ đề 7. Sinh thái học và Môi trường", enrich_interactive_cd7, apply_review_keys_cd7)
    init_db()
    print("ALL DONE! Synced Chủ đề 6 & 7 into SQLite DB!")


if __name__ == "__main__":
    main()
