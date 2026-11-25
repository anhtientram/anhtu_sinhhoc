#!/usr/bin/env python3
"""
Phân loại mức độ nhận thức (Nhận biết / Thông hiểu / Vận dụng) cho toàn bộ
ngân hàng 1.211 câu hỏi trong 4 Chủ đề (dựa theo đặc trưng chuẩn đề Sinh học 12 GDPT 2018).
Quản trị viên vẫn có thể chỉnh sửa lại mức độ từng câu trực tiếp trên giao diện.
"""
import json
import os
import re

from database import get_conn, now_iso

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")

RE_VD = re.compile(
    r"(phần bài tập|bài tập|tính số|tính tỉ lệ|chiếm tỉ lệ|bao nhiêu\s*(?:%|phần trăm|loại kiểu|phân tử|nucleotide|cặp|liên kết|cá thể|tế bào|giao tử|phép lai|trường hợp|amino acid|bộ ba|cây|con)|"
    r"dài\s*\d|chiều dài|\d+\s*(?:Å|nm|µm|%)|phép lai|cho\s*\(?P\)?|F1|F2|hoán vị.*%|tần số hoán vị|xác suất|xác định kiểu gene|kiểu hình\s*\d\s*:|\d\s*:\s*\d)",
    re.IGNORECASE,
)

RE_TH = re.compile(
    r"(hình\s*(?:bên|dưới|sau|vẽ|nào)|sơ\s*đồ|bảng\s*(?:bên|dưới|sau)|đồ\s*thị|biểu\s*đồ|"
    r"có bao nhiêu phát biểu|có bao nhiêu nhận định|nhận định nào|phát biểu nào.*đúng|phát biểu nào.*không đúng|"
    r"giải thích|vì sao|tại sao|điều nào sau đây|kết luận nào|so sánh|khác nhau|giống nhau|nguyên nhân nào|"
    r"\bI\.\s+.+\bII\.\s+)",
    re.IGNORECASE | re.DOTALL,
)


def classify_question(q: dict, kind: str, force: bool = False) -> str:
    # Giữ nguyên nếu đã có cognitive_level hợp lệ (trừ khi force=True)
    existing = q.get("cognitive_level")
    if not force and existing in ("nhan_biet", "thong_hieu", "van_dung"):
        return existing

    text = (q.get("question") or q.get("stem") or "") + " " + (q.get("level") or "")
    has_media = bool(q.get("images") or q.get("tables"))

    if kind == "short_answer":
        if RE_VD.search(text):
            return "van_dung"
        if has_media or RE_TH.search(text):
            return "thong_hieu"
        return "nhan_biet"

    if kind == "true_false":
        stmts_text = " ".join(s.get("text", "") for s in (q.get("statements") or []))
        combined = text + " " + stmts_text
        if RE_VD.search(combined):
            return "van_dung"
        if has_media or re.search(
            r"(thí nghiệm|giải thích|vì sao|tại sao|so sánh|đồ thị|bảng số liệu|sơ đồ|khi xử lí|đột biến|tác động)",
            combined,
            re.IGNORECASE,
        ):
            return "thong_hieu"
        return "nhan_biet"

    # MCQ
    if RE_VD.search(text):
        return "van_dung"
    if has_media or RE_TH.search(text):
        return "thong_hieu"
    return "nhan_biet"


def main():
    import sys
    force = "--force" in sys.argv
    conn = get_conn()
    ts = now_iso()

    for idx in range(1, 5):
        jpath = os.path.join(TOPICS_DIR, f"chu_de_{idx}.json")
        if not os.path.exists(jpath):
            continue
        with open(jpath, "r", encoding="utf-8") as f:
            topic = json.load(f)

        stats = {}
        for kind in ("mcq", "true_false", "short_answer"):
            c = {"nhan_biet": 0, "thong_hieu": 0, "van_dung": 0}
            for q in topic.get("review", {}).get(kind, []):
                lv = classify_question(q, kind, force=force)
                q["cognitive_level"] = lv
                c[lv] += 1
            stats[kind] = c

        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(topic, f, ensure_ascii=False, indent=2)

        # Cập nhật vào DB (giữ youtube_videos nếu có)
        row = conn.execute("SELECT content_json FROM topics WHERE id = ?", (topic["id"],)).fetchone()
        if row:
            old = json.loads(row["content_json"])
            if old.get("youtube_videos"):
                topic["youtube_videos"] = old["youtube_videos"]
        conn.execute(
            "UPDATE topics SET content_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(topic, ensure_ascii=False), ts, topic["id"]),
        )
        print(f"Chủ đề {idx}: {stats}")

    conn.commit()
    conn.close()
    print("DONE tagging cognitive levels!")


if __name__ == "__main__":
    main()
