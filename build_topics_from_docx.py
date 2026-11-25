#!/usr/bin/env python3
"""
Trích xuất toàn bộ 4 file Word (CHỦ ĐỀ 1.docx -> CHỦ ĐỀ 4.docx) vào data/topics/
và cập nhật trực tiếp vào cơ sở dữ liệu SQLite data/sinhhoc12.db.
"""
import json
import os
import shutil
import unicodedata

from database import get_conn, init_db, now_iso
from importer import UPLOADS_DIR, parse_document_to_topic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")

TOPIC_SPECS = [
    {
        "num": 1,
        "id": "chu-de-1",
        "json_file": "chu_de_1.json",
        "title_override": "Chủ đề 1. Cơ sở phân tử của hiện tượng di truyền và biến dị",
    },
    {
        "num": 2,
        "id": "chu-de-2",
        "json_file": "chu_de_2.json",
        "title_override": "Chủ đề 2. Cơ sở tế bào của hiện tượng di truyền và biến dị",
    },
    {
        "num": 3,
        "id": "chu-de-3",
        "json_file": "chu_de_3.json",
        "title_override": "Chủ đề 3. Học thuyết di truyền của Mendel và Mở rộng học thuyết Mendel",
    },
    {
        "num": 4,
        "id": "chu-de-4",
        "json_file": "chu_de_4.json",
        "title_override": "Chủ đề 4. Morgan – Di truyền ngoài nhân & Tương tác Kiểu gene – Môi trường",
    },
]


def find_docx_for_num(num: int):
    for fname in os.listdir(BASE_DIR):
        if not fname.lower().endswith(".docx") or fname.startswith("~$"):
            continue
        norm = unicodedata.normalize("NFC", fname).upper()
        if f"CHỦ ĐỀ {num}" in norm or f"CHU DE {num}" in norm:
            return os.path.join(BASE_DIR, fname), unicodedata.normalize("NFC", fname)
    return None, None


def main():
    os.makedirs(TOPICS_DIR, exist_ok=True)
    init_db()
    conn = get_conn()
    ts = now_iso()

    for spec in TOPIC_SPECS:
        fpath, clean_name = find_docx_for_num(spec["num"])
        if not fpath:
            print(f"[SKIP] Không tìm thấy file Word cho Chủ đề {spec['num']}")
            continue

        # Dọn ảnh cũ của chủ đề trước khi trích xuất mới để tránh rác trùng lặp
        topic_upload_dir = os.path.join(UPLOADS_DIR, spec["id"])
        if os.path.exists(topic_upload_dir):
            shutil.rmtree(topic_upload_dir)

        with open(fpath, "rb") as f:
            file_bytes = f.read()

        base_meta = {"id": spec["id"], "order_index": spec["num"], "title": spec["title_override"]}
        parsed = parse_document_to_topic(
            file_bytes,
            clean_name,
            spec["id"],
            base_meta,
            title_override=spec["title_override"],
        )
        topic_data = parsed["extracted"]
        st = parsed["stats"]

        json_path = os.path.join(TOPICS_DIR, spec["json_file"])
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(topic_data, jf, ensure_ascii=False, indent=2)

        conn.execute(
            """
            INSERT OR REPLACE INTO topics (id, order_index, title, subtitle, status, content_json, updated_at)
            VALUES (?, ?, ?, ?, 'published', ?, ?)
            """,
            (
                topic_data["id"],
                spec["num"],
                topic_data["title"],
                topic_data["subtitle"],
                json.dumps(topic_data, ensure_ascii=False),
                ts,
            ),
        )
        print(
            f"[OK] {topic_data['title']}\n"
            f"     Bài học: {st['lessons_count']} | Mục lý thuyết: {st['sections_count']} | "
            f"Hệ thống KT: {st['htkt_units_count']} bài | Ảnh gốc: {st['images_count']} | Bảng: {st['tables_count']}\n"
            f"     Ôn tập -> 3.1 (4 đáp án): {st['mcq_count']} (có đáp án sẵn: {st['mcq_keyed']}) | "
            f"3.2 (Đúng/Sai): {st['true_false_count']} (sẵn: {st['true_false_keyed']}) | "
            f"3.3 (Trả lời ngắn): {st['short_answer_count']} (sẵn: {st['short_answer_keyed']})"
        )
        for ls in topic_data["lessons"]:
            print(f"       • {ls['number']}: {ls['title']} ({len(ls['sections'])} mục)")

    conn.commit()
    conn.close()
    print("\n=== HOÀN TẤT NẠP 4 CHỦ ĐỀ VÀO CƠ SỞ DỮ LIỆU! ===")


if __name__ == "__main__":
    main()
