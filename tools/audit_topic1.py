#!/usr/bin/env python3
"""Kiểm kê chi tiết 100% câu hỏi Chủ đề 1 (414 câu), liệt kê toàn bộ các câu thiếu đáp án và quét mọi nguồn đáp án trong dự án."""
import json
import os
import unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
t1_path = os.path.join(BASE_DIR, "data", "topics", "chu_de_1.json")

with open(t1_path, "r", encoding="utf-8") as f:
    t1 = json.load(f)

print(f"Title: {t1.get('title')} | bundled_version: {t1.get('bundled_version')}")
rev = t1.get("review") or {}
total = 0
ready = 0
for part in ("mcq", "true_false", "short_answer"):
    qs = rev.get(part) or []
    r = sum(1 for q in qs if q.get("answer_key_ready"))
    total += len(qs)
    ready += r
    print(f"\n=== PART: {part} ({r}/{len(qs)} có đáp án, thiếu {len(qs) - r}) ===")
    by_lesson = {}
    for idx, q in enumerate(qs):
        lid = q.get("lesson_id") or "(none)"
        by_lesson.setdefault(lid, []).append((idx, q))
    for lid, items in by_lesson.items():
        r_l = sum(1 for _, q in items if q.get("answer_key_ready"))
        print(f"  Lesson {lid}: {r_l}/{len(items)} ready")
        # Nhóm theo level
        by_lvl = {}
        for _, q in items:
            lvl = q.get("level") or "(none)"
            by_lvl.setdefault(lvl, []).append(q)
        for lvl, lqs in by_lvl.items():
            lr = sum(1 for q in lqs if q.get("answer_key_ready"))
            nums = [q.get("orig_num") for q in lqs]
            print(f"    level={lvl!r}: {lr}/{len(lqs)} ready | orig_nums={nums[:6]}..{nums[-4:]}")
        missing = [q for _, q in items if not q.get("answer_key_ready")]
        if missing:
            print(f"    -> Danh sách thiếu ({len(missing)} câu): {[ (q.get('id'), q.get('orig_num'), q.get('level')) for q in missing[:10] ]} ... cuối: {(missing[-1].get('id'), missing[-1].get('orig_num'), missing[-1].get('level'))}")

print(f"\n==> TỔNG CỘNG: {ready}/{total} câu có đáp án (thiếu {total - ready} câu).")

print("\n=== QUÉT TOÀN BỘ FILE .PDF / .DOCX / .PY ĐÁP ÁN TRONG DỰ ÁN ===")
for root, dirs, files in os.walk(BASE_DIR):
    dirs[:] = [d for d in sorted(dirs) if not d.startswith(".") and d not in ("static", "__pycache__", "node_modules", ".git")]
    for fn in sorted(files):
        if fn.startswith("."):
            continue
        low = unicodedata.normalize("NFC", fn).lower()
        if low.endswith((".pdf", ".docx")) or "answer" in low or "dap" in low or "key" in low:
            print("  •", unicodedata.normalize("NFC", os.path.relpath(os.path.join(root, fn), BASE_DIR)))
