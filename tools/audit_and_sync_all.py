#!/usr/bin/env python3
"""
Công cụ kiểm tra & chuẩn hoá đồng bộ cho Web App Sinh học 12:
  1. Xoay đúng chiều (180°) ảnh img_217a1f6879.png vừa trích xuất từ .emf và tối ưu dung lượng 3 ảnh Chủ đề 7.
  2. Chuẩn hoá 100% đáp án & giải thích ngắn của Chủ đề 7 (Bài 7.1..7.6 = Bài 22..27) đối chiếu trực tiếp
     với nguồn 'ĐÁP ÁN/Sinh học 12 - Đáp án hoàn chỉnh.pdf' (trang 18..30), báo cáo mọi sai lệch trước/sau.
  3. Kiểm thử bộ đọc đáp án PDF mới (gồm 2 cột Đ/S, ghi chú ngoặc, phân số, Đọc hiểu & OCR tự động trên macOS).
"""
import io
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from content_standardizer import (
    LETTER_TO_IDX,
    parse_answer_pdf_keys,
    standardize_topic_content,
)

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None


# ================== BẢNG ĐÁP ÁN GỐC ĐỐI CHIẾU TRỰC TIẾP TỪ ==================
# ĐÁP ÁN/Sinh học 12 - Đáp án hoàn chỉnh.pdf (Hoàng Long Education, trang 18–30)
# Ánh xạ 1-1: 7.1 = Bài 22 | 7.2 = Bài 23 | 7.3 = Bài 24 | 7.4 = Bài 25 | 7.5 = Bài 26 | 7.6 = Bài 27

TOPIC7_AUTHORITATIVE_PDF_KEYS = {
    # 7.1 — BÀI 22: MÔI TRƯỜNG VÀ CÁC NHÂN TỐ SINH THÁI (trang 19–20)
    "chu-de-7-bai-1": {
        "mcq": (
            "1.D 2.A 3.C 4.D 5.B 6.A 7.D 8.B 9.A 10.B 11.A 12.B 13.D "
            "14.C 15.A 16.B 17.B 18.C 19.B 20.B 21.B 22.A 23.B 24.A 25.A 26.A "
            "27.B 28.A 29.C 30.C 31.C 32.C 33.D 34.D 35.B 36.B 37.A 38.D 39.A "
            "40.C 41.D 42.B 43.B 44.A 45.D 46.A 47.B 48.A 49.A 50.C 51.B 52.C "
            "53.B 54.B 55.B 56.D 57.A 58.D 59.A 60.B 61.A 62.D 63.B"
        ),
        "tf": {
            1: "ĐSĐS", 2: "ĐĐSĐ", 3: "SĐĐS", 4: "ĐSĐS", 5: "ĐĐSĐ", 6: "SĐĐS",
            7: "ĐSĐS", 8: "ĐSĐS", 9: "ĐSSS", 10: "ĐĐSĐ", 11: "ĐSSS", 12: "ĐSĐS", 13: "ĐĐSĐ",
        },
        "sa": {
            1: ("2", ""),
            2: ("4", ""),
            3: ("2", "Các ý đúng: (1, 3)"),
            4: ("2", "Các ý đúng: (2, 3)"),
            5: ("2", ""),
            6: ("4", ""),
            7: ("1", ""),
            8: ("3", "Các ý đúng: (1, 2, 3)"),
        },
    },
    # 7.2 — BÀI 23: SINH THÁI HỌC QUẦN THỂ (trang 22)
    "chu-de-7-bai-2": {
        "mcq": (
            "1.C 2.C 3.A 4.A 5.D 6.D 7.D 8.D 9.C 10.A 11.B 12.D 13.B "
            "14.C 15.D 16.D 17.C 18.B 19.D 20.A 21.C 22.A 23.B 24.C 25.A 26.D "
            "27.B 28.D 29.D 30.A 31.A 32.D 33.B 34.B 35.D 36.C 37.D 38.A 39.A "
            "40.B 41.D 42.B 43.C 44.D 45.C 46.C 47.B 48.B 49.B 50.B 51.A 52.D "
            "53.A 54.B 55.C 56.C 57.D 58.D 59.B 60.C 61.D 62.B 63.A 64.A 65.D "
            "66.D 67.C 68.B 69.D 70.C 71.B 72.A 73.C 74.C 75.B 76.B 77.C 78.B "
            "79.C 80.A 81.D 82.A 83.D 84.A 85.B 86.C 87.A 88.D 89.A 90.B 91.A "
            "92.D 93.D 94.B 95.D 96.B 97.C 98.C 99.D 100.D 101.C 102.C 103.A 104.D "
            "105.C 106.D 107.D 108.A 109.C 110.A 111.D 112.D 113.D 114.D 115.A 116.A 117.B "
            "118.A 119.D 120.D 121.B 122.C 123.C 124.D 125.B 126.C 127.B 128.B 129.A 130.C "
            "131.D 132.B 133.A 134.B 135.C 136.A 137.D"
        ),
        "tf": {
            1: "SĐĐS", 2: "SĐĐĐ", 3: "SSĐĐ", 4: "ĐĐĐĐ", 5: "SĐĐS",
            6: "ĐSĐĐ", 7: "ĐĐĐS", 8: "ĐSSS", 9: "ĐSSĐ", 10: "SĐSS",
            11: "SSĐS", 12: "SSSĐ", 13: "ĐSSS", 14: "ĐĐSS", 15: "ĐSĐS",
            16: "ĐĐĐĐ", 17: "ĐĐĐS", 18: "SSSĐ", 19: "SĐĐS", 20: "ĐĐSĐ",
        },
        "sa": {
            1: ("3", "Các ý đúng: (2, 3, 5)"),
            2: ("2132", ""),
            3: ("30", ""),
            4: ("15750", ""),
            5: ("4", ""),
            6: ("4", ""),
            7: ("3", ""),
            8: ("3", "Các ý đúng: (1, 3, 4)"),
            9: ("5", ""),
            10: ("4", ""),
            11: ("10", ""),
            12: ("4", ""),
            13: ("3", ""),
            14: ("4", ""),
            15: ("2", "Các ý đúng: (1, 2)"),
            16: ("3", "Các ý đúng: (1, 2, 3)"),
            17: ("3", ""),
            18: ("5", "Các ý đúng: (1, 2, 4, 5, 8)"),
        },
    },
    # 7.3 — BÀI 24: QUẦN XÃ SINH VẬT (trang 24–25)
    "chu-de-7-bai-3": {
        "mcq": (
            "1.B 2.A 3.C 4.B 5.B 6.B 7.C 8.B 9.B 10.B 11.B 12.B 13.B "
            "14.D 15.B 16.A 17.B 18.B 19.B 20.B 21.B 22.A 23.D 24.B 25.C 26.B "
            "27.C 28.B 29.D 30.D 31.C 32.C 33.D 34.B 35.B 36.C 37.C 38.B 39.C "
            "40.D 41.D 42.C 43.C 44.C 45.A 46.D 47.B 48.C 49.A 50.C 51.A 52.D "
            "53.A 54.C 55.C 56.D 57.A 58.C 59.D 60.B 61.A 62.B 63.B 64.A 65.C "
            "66.D 67.D 68.D 69.C 70.D 71.A 72.C 73.D 74.C 75.A 76.D 77.A 78.C "
            "79.B 80.B 81.A 82.B 83.C 84.A 85.C 86.B 87.A 88.B 89.B 90.C 91.D "
            "92.D 93.C 94.C 95.C 96.B 97.A 98.A 99.B 100.A 101.C 102.B 103.A 104.D "
            "105.B 106.B 107.C 108.D 109.B 110.A 111.C 112.C 113.B"
        ),
        "mcq_notes": {106: "Các ý đúng: I, III, IV", 113: "Các ý đúng: I, III"},
        "tf": {
            1: "ĐĐĐS", 2: "SĐSĐ", 3: "SĐĐĐ", 4: "SĐĐS", 5: "ĐĐĐS",
            6: "ĐSĐĐ", 7: "SSSĐ", 8: "ĐSSĐ", 9: "ĐSSĐ", 10: "ĐĐSĐ",
            11: "ĐSSĐ", 12: "ĐĐĐĐ", 13: "SĐSĐ", 14: "ĐĐSS", 15: "ĐĐĐS",
            16: "SSĐS", 17: "ĐĐĐS",
        },
        "sa": {
            1: ("1", "Thí nghiệm 1"),
            2: ("3", "Các ý đúng: (1, 2, 3)"),
            3: ("1", ""),
            4: ("4", "Các ý đúng: (1, 2, 3, 5)"),
            5: ("3", ""),
            6: ("2", "Các ý đúng: (2, 4)"),
            7: ("2", ""),
            8: ("0,2", ""),
            9: ("2", "Các ý đúng: (1, 3)"),
            10: ("4", ""),
            11: ("2", "Các ý đúng: (1, 2)"),
            12: ("1", ""),
            13: ("4", ""),
            14: ("4", ""),
            15: ("4", ""),
            16: ("2", "Các ý đúng: (2, 4)"),
            17: ("3", ""),
        },
    },
    # 7.4 — BÀI 25: HỆ SINH THÁI (trang 26–27)
    "chu-de-7-bai-4": {
        "mcq": (
            "1.D 2.A 3.C 4.A 5.D 6.D 7.B 8.C 9.B 10.C 11.A 12.A 13.C "
            "14.D 15.B 16.C 17.C 18.D 19.A 20.A 21.C 22.C 23.D 24.D 25.A 26.C "
            "27.B 28.B 29.D 30.A 31.B 32.C 33.B 34.B 35.B 36.B 37.C 38.A 39.C "
            "40.A 41.A 42.B 43.C 44.C 45.A 46.A 47.A 48.D 49.D 50.D 51.C 52.B "
            "53.D 54.C 55.C 56.D 57.B 58.D 59.D 60.C 61.D 62.C 63.B 64.B "
            "65.C 66.B 67.D 68.D 69.A 70.C 71.B 72.C 73.C 74.B 75.A 76.B 77.A "
            "78.A 79.A 80.C 81.B 82.A 83.D 84.A 85.A 86.A 87.B 88.B 89.B 90.A "
            "91.A 92.D 93.A 94.B 95.D 96.D 97.D 98.D 99.D 100.A 101.C 102.B 103.B "
            "104.C 105.C 106.A 107.D 108.A 109.A 110.A 111.D 112.A 113.D 114.D 115.A 116.B "
            "117.A 118.C 119.A 120.C 121.C 122.C 123.D 124.A 125.C 126.A 127.B 128.B 129.B "
            "130.A 131.B 132.A 133.C 134.A 135.A 136.A 137.C 138.B 139.D 140.D 141.B 142.C "
            "143.A 144.D 145.B 146.A 147.B 148.D 149.C 150.A 151.B 152.A 153.B 154.B 155.C "
            "156.B 157.D 158.C 159.C 160.B 161.A 162.B 163.B 164.A 165.B 166.C 167.D 168.D "
            "169.D 170.C 171.D 172.D 173.B 174.C 175.B 176.C 177.A"
        ),
        "mcq_notes": {63: "Ý đúng: III"},
        "tf": {
            1: "ĐSĐĐ", 2: "SSSĐ", 3: "ĐSSĐ", 4: "SSĐS", 5: "ĐĐSĐ",
            6: "ĐĐĐĐ", 7: "SĐĐĐ", 8: "SSĐĐ", 9: "ĐSSS", 10: "ĐĐĐS",
            11: "ĐĐĐĐ", 12: "SSSĐ", 13: "SSSĐ", 14: "ĐSĐĐ", 15: "SĐĐS",
            16: "ĐĐSĐ", 17: "ĐSĐĐ", 18: "SĐĐS", 19: "ĐĐSS", 20: "SĐSS",
        },
        "sa": {
            1: ("4", "Các ý đúng: (3, 5, 6, 7)"),
            2: ("2", ""),
            3: ("4", "Các ý đúng: (2, 3, 4, 5)"),
            4: ("4", ""),
            5: ("4", ""),
            6: ("4", ""),
            7: ("7", ""),
            8: ("6", ""),
            9: ("2", "Các ý đúng: (4, 5)"),
            10: ("4", "Các ý đúng: (1, 3, 5, 7)"),
            11: ("1", ""),
            12: ("12", ""),
            13: ("2", ""),
            14: ("0,01", ""),
            15: ("3", "Các ý đúng: (1, 2, 4)"),
            16: ("7", "Các ý đúng: (1, 4)"),
            17: ("2", ""),
            18: ("3", ""),
            19: ("5", ""),
            20: ("3", ""),
        },
    },
    # 7.5 — BÀI 26: CHU TRÌNH SINH – ĐỊA – HÓA VÀ SINH QUYỂN (trang 28)
    "chu-de-7-bai-5": {
        "mcq": (
            "1.C 2.A 3.A 4.A 5.A 6.A 7.A 8.A 9.D 10.C 11.C 12.C 13.D "
            "14.C 15.D 16.D 17.A 18.C 19.A 20.D 21.D 22.B 23.A 24.D 25.D 26.D "
            "27.C 28.D 29.A 30.A 31.B 32.C 33.A 34.D 35.D 36.C 37.B 38.C 39.A "
            "40.C 41.B 42.A 43.B 44.C 45.D 46.B 47.C 48.C 49.C 50.A 51.B 52.A "
            "53.B 54.C 55.B 56.B 57.C 58.D 59.D 60.C 61.B 62.B 63.A 64.D 65.D "
            "66.B 67.A 68.C 69.D 70.D 71.B 72.C 73.D 74.D 75.B 76.A 77.C"
        ),
        "tf": {
            1: "ĐSSĐ", 2: "ĐĐĐS", 3: "ĐĐĐS", 4: "SSĐĐ", 5: "ĐSSĐ", 6: "ĐSĐĐ", 7: "SSĐĐ",
        },
        "sa": {
            1: ("4", ""),
            2: ("1", "Ý đúng: (3)"),
            3: ("4", ""),
            4: ("1", ""),
            5: ("1", ""),
            6: ("16", ""),
            7: ("4", ""),
            8: ("3", ""),
            9: ("1", ""),
            10: ("1", ""),
            11: ("2", ""),
            12: ("2", "Các ý đúng: (1, 3)"),
        },
    },
    # 7.6 — BÀI 27: SINH THÁI HỌC PHỤC HỒI – BẢO TỒN ĐA DẠNG SINH HỌC VÀ PHÁT TRIỂN BỀN VỮNG (trang 29–30)
    "chu-de-7-bai-6": {
        "mcq": (
            "1.D 2.C 3.D 4.D 5.A 6.A 7.C 8.C 9.B 10.D 11.D 12.A 13.D "
            "14.D 15.B 16.C 17.B 18.A 19.B 20.B 21.C 22.C 23.A 24.D 25.D 26.B "
            "27.D 28.D 29.A 30.A 31.C 32.D 33.C 34.D 35.C 36.A 37.D 38.D 39.B "
            "40.B 41.B 42.C 43.B 44.B 45.A 46.D 47.D 48.B"
        ),
        "tf": {
            1: "ĐĐĐS", 2: "ĐSĐS", 3: "ĐSĐS", 4: "SĐSS", 5: "SĐĐĐ", 6: "ĐSĐS", 7: "SSĐĐ",
        },
        "sa": {
            1: ("4", "Các ý đúng: (1, 3, 4, 5)"),
            2: ("4", "Các ý đúng: (1, 2, 3, 4)"),
            3: ("4", ""),
            4: ("3", "Các ý đúng: (1, 3, 4)"),
            5: ("4", "Các ý đúng: (1, 2, 3, 4)"),
            6: ("2", "Các ý đúng: (1, 2)"),
            7: ("2", "Các ý đúng: (1, 2)"),
            8: ("1", ""),
            9: ("2", "Các ý đúng: (1, 2)"),
            10: ("3", "Các ý đúng: (1, 2, 4)"),
        },
    },
}


def _parse_mcq_str(s: str):
    out = {}
    for m in re.finditer(r"(\d+)\.([A-D])", s):
        out[int(m.group(1))] = LETTER_TO_IDX[m.group(2)]
    return out


def _tf_str_to_bools(s: str):
    return [ch == "Đ" for ch in s]


def fix_rotated_and_heavy_topic7_images():
    print("=== 1. XOAY ĐÚNG CHIỀU & TỐI ƯU 3 ẢNH VỪA CHUYỂN TỪ .EMF (CHỦ ĐỀ 7) ===")
    if PILImage is None:
        print("  [CẢNH BÁO] Chưa có Pillow — thử dùng sips trên macOS.")
    targets = [
        ("static/uploads/chu-de-7/img_217a1f6879.png", 180),  # Đang bị lộn ngược 180°
        ("static/uploads/chu-de-7/img_23d8b77a68.png", 0),
        ("static/uploads/chu-de-7/img_bedc9ea121.png", 0),
    ]
    import subprocess, shutil
    for rel, deg in targets:
        p = os.path.join(BASE_DIR, rel)
        if not os.path.isfile(p):
            continue
        before_sz = os.path.getsize(p)
        if PILImage is not None:
            im = PILImage.open(p)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            if deg:
                im = im.rotate(deg, expand=True)
            if im.width > 1280:
                nh = max(1, int(im.height * 1280 / im.width))
                im = im.resize((1280, nh), PILImage.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=88, optimize=True)
            with open(p, "wb") as wf:
                wf.write(buf.getvalue())
            print(f"  [OK Pillow] {rel}: xoay {deg}°, {before_sz//1024}KB -> {len(buf.getvalue())//1024}KB ({im.width}x{im.height})")
        elif shutil.which("sips"):
            if deg:
                subprocess.run(["sips", "-r", str(deg), p], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["sips", "-Z", "1280", "-s", "format", "jpeg", "-s", "formatOptions", "88", p, "--out", p], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            after_sz = os.path.getsize(p)
            print(f"  [OK sips] {rel}: xoay {deg}°, {before_sz//1024}KB -> {after_sz//1024}KB")
    print()


def sync_topic7_with_authoritative_pdf():
    print("=== 2. CHUẨN HOÁ 100% CHỦ ĐỀ 7 TỪ 'ĐÁP ÁN/Sinh học 12 - Đáp án hoàn chỉnh.pdf' ===")
    t7_path = os.path.join(BASE_DIR, "data", "topics", "chu_de_7.json")
    with open(t7_path, "r", encoding="utf-8") as f:
        t7 = json.load(f)

    rev = t7.get("review") or {}
    idx_to_let = ["A", "B", "C", "D"]
    mcq_fixed = []
    tf_fixed = []
    sa_fixed = []
    exp_added = 0

    for q in rev.get("mcq") or []:
        lid = q.get("lesson_id")
        qn = int(q.get("orig_num") or 0)
        spec = TOPIC7_AUTHORITATIVE_PDF_KEYS.get(lid)
        if not spec:
            continue
        m_map = _parse_mcq_str(spec["mcq"])
        if qn in m_map:
            new_idx = m_map[qn]
            old_idx = q.get("correct_index")
            if old_idx != new_idx or not q.get("answer_key_ready"):
                mcq_fixed.append((q["id"], idx_to_let[old_idx] if isinstance(old_idx, int) and 0 <= old_idx < 4 else str(old_idx), idx_to_let[new_idx]))
                q["correct_index"] = new_idx
                q["answer_key_ready"] = True
            note = (spec.get("mcq_notes") or {}).get(qn)
            if note and not q.get("explanation"):
                q["explanation"] = note
                exp_added += 1

    for q in rev.get("true_false") or []:
        lid = q.get("lesson_id")
        qn = int(q.get("orig_num") or 0)
        spec = TOPIC7_AUTHORITATIVE_PDF_KEYS.get(lid)
        if not spec:
            continue
        tf_str = spec["tf"].get(qn)
        if tf_str:
            target_bools = _tf_str_to_bools(tf_str)
            stmts = q.get("statements") or []
            old_str = "".join("Đ" if st.get("answer") else "S" for st in stmts[:4])
            if old_str != tf_str or not q.get("answer_key_ready"):
                tf_fixed.append((q["id"], old_str, tf_str))
                for si, st in enumerate(stmts[:4]):
                    st["answer"] = target_bools[si]
                q["answer_key_ready"] = True

    for q in rev.get("short_answer") or []:
        lid = q.get("lesson_id")
        qn = int(q.get("orig_num") or 0)
        spec = TOPIC7_AUTHORITATIVE_PDF_KEYS.get(lid)
        if not spec:
            continue
        sa_entry = spec["sa"].get(qn)
        if lid == "chu-de-7-bai-4" and q.get("id") == "chu-de-7-b4-sa-15":
            sa_entry = ("2", "")
        if sa_entry:
            val_str, note = sa_entry
            # Riêng Bài 25 (7.4) trong PDF có in trùng số "14. 0,01" và "14. 2" — kiểm tra câu hỏi có nhắc 0,01 / hiệu suất / phần trăm không
            if lid == "chu-de-7-bai-4" and qn == 14:
                qtxt = (q.get("question") or "").lower()
                if "thập phân" not in qtxt and "hiệu suất" not in qtxt and "%" not in qtxt and "0,01" not in (q.get("accepted_answers") or []):
                    print(f"  [KIỂM TRA 7.4 Câu 14 TLN] Nội dung: {q.get('question', '')[:120]} | ĐA cũ: {q.get('accepted_answers')}")
            acc = [val_str]
            if "," in val_str:
                acc.append(val_str.replace(",", "."))
            elif "." in val_str:
                acc.append(val_str.replace(".", ","))
            old_acc = list(q.get("accepted_answers") or [])
            if old_acc != acc or not q.get("answer_key_ready"):
                sa_fixed.append((q["id"], old_acc, acc))
                q["accepted_answers"] = acc
                q["accepted"] = acc
                q["answer_key_ready"] = True
            if note and not q.get("explanation"):
                q["explanation"] = note
                exp_added += 1

    print(f"  • Trắc nghiệm (TN): hiệu chỉnh {len(mcq_fixed)} câu / {len(rev.get('mcq') or [])} câu")
    for item in mcq_fixed[:20]:
        print(f"      {item[0]}: {item[1]} -> {item[2]}")
    if len(mcq_fixed) > 20:
        print(f"      ... (+{len(mcq_fixed) - 20} câu khác)")
    print(f"  • Đúng / Sai (Đ/S): hiệu chỉnh {len(tf_fixed)} câu / {len(rev.get('true_false') or [])} câu")
    for item in tf_fixed[:20]:
        print(f"      {item[0]}: {item[1]} -> {item[2]}")
    print(f"  • Trả lời ngắn (TLN): hiệu chỉnh {len(sa_fixed)} câu / {len(rev.get('short_answer') or [])} câu")
    for item in sa_fixed[:20]:
        print(f"      {item[0]}: {item[1]} -> {item[2]}")
    print(f"  • Đã bổ sung giải thích ngắn (các ý đúng từ PDF): {exp_added} câu")

    rep = standardize_topic_content(t7)
    print(f"  • Chuẩn hoá chính tả & thuật ngữ thêm: {rep['auto_fixed_count']} vị trí")

    # Thống kê từng bài 7.1..7.6
    for ls in t7.get("lessons") or []:
        lid = ls["id"]
        lm = [q for q in rev.get("mcq") or [] if q.get("lesson_id") == lid]
        lt = [q for q in rev.get("true_false") or [] if q.get("lesson_id") == lid]
        ls_a = [q for q in rev.get("short_answer") or [] if q.get("lesson_id") == lid]
        print(f"    - {ls['number']} ({ls['title'][:36]}): TN {len(lm)} | Đ/S {len(lt)} | TLN {len(ls_a)}")

    t7["bundled_version"] = "2026.11.28-topic7-dapan-v9"
    with open(t7_path, "w", encoding="utf-8") as f:
        json.dump(t7, f, ensure_ascii=False, indent=2)
    print("  => Đã lưu data/topics/chu_de_7.json (bundled_version = 2026.11.28-topic7-dapan-v9).\n")


def test_pdf_ocr_on_dapan2():
    print("=== 3. KIỂM THỬ BỘ ĐỌC PDF ĐÁP ÁN MỚI (TỰ ĐỘNG OCR BẢN SCAN 'ĐÁP ÁN 2.pdf') ===")
    # Tìm file ĐÁP ÁN 2.pdf (NFC/NFD an toàn)
    pdf_path = None
    for entry in os.listdir(BASE_DIR):
        p_dir = os.path.join(BASE_DIR, entry)
        if os.path.isdir(p_dir):
            for fn in os.listdir(p_dir):
                if fn.lower().endswith(".pdf") and "2" in fn and ("dap" in fn.lower() or "đáp" in fn.lower() or "án" in fn.lower()):
                    pdf_path = os.path.join(p_dir, fn)
                    break
        if pdf_path:
            break
    if not pdf_path:
        print("  (Bỏ qua: không tìm thấy ĐÁP ÁN 2.pdf)")
        return
    with open(pdf_path, "rb") as f:
        data = f.read()
    res = parse_answer_pdf_keys(data)
    gl = res["global"]
    print(f"  File: {os.path.relpath(pdf_path, BASE_DIR)}")
    print(f"  is_scanned_pdf={res['is_scanned_pdf']} | ocr_used={res['ocr_used']}")
    print(f"  Kết quả đọc được: TN={len(gl['mcq'])} (kỳ vọng 30), Đ/S={len(gl['tf'])} (kỳ vọng 2), TLN={len(gl['sa'])} (kỳ vọng 4)")
    print(f"  Mẫu Đ/S: {gl['tf']}")
    print(f"  Mẫu TLN: {gl['sa']}")


if __name__ == "__main__":
    # Đã xoay đúng chiều img_217a1f6879.png (63KB); chỉ chạy kiểm thử bộ đọc PDF OCR & đồng bộ
    test_pdf_ocr_on_dapan2()
