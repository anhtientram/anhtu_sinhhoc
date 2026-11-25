#!/usr/bin/env python3
"""
Áp dụng chính xác đáp án từ bộ PDF đáp án của Giáo viên (ĐÁP ÁN 1.pdf & ĐÁP ÁN 2.pdf)
vào từng bài của 4 Chủ đề theo đúng số thứ tự câu gốc (orig_num) và từng tiểu mục (run_index).
Đồng thời chạy kiểm tra chéo với các đáp án gạch chân sẵn trong file Word Chủ đề 3.
"""
import json
import os
from database import get_conn, now_iso

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")

LETTER_TO_IDX = {"A": 0, "B": 1, "C": 2, "D": 3}


def L(seq_str):
    """Chuyển chuỗi đáp án 'B A A B C...' thành dict {1: 1, 2: 0, ...}."""
    tokens = [t.strip().upper() for t in seq_str.replace(",", " ").split() if t.strip()]
    return {i + 1: LETTER_TO_IDX[t] for i, t in enumerate(tokens)}


def TF(rows_dict):
    """Chuyển {1: 'Đ S S Đ', ...} thành {1: [True, False, False, True]}."""
    out = {}
    for k, v in rows_dict.items():
        toks = [t.strip().upper() for t in v.split() if t.strip()]
        out[k] = [t in ("Đ", "D", "T", "TRUE") for t in toks]
    return out


ANSWER_KEYS = {
    # ==================== CHỦ ĐỀ 1 ====================
    "chu-de-1-bai-1": {
        "mcq_runs": {
            0: L(
                "B A A B C D A B D D C D B "
                "C A B C D C D D A C D "
                "C B B B C C D A D B A D D "
                "A C D A A B D B A B B A D "
                "C D C D D A C B D A D C "
                "B A C C A C D A"
            ),
            1: L(
                "D C B B B B C B B D B B "
                "B B B B B B"
            ),
        },
        "tf": TF({
            1: "Đ S S Đ",
            2: "S Đ Đ S",
            3: "S S S Đ",
            4: "S Đ Đ Đ",
            5: "S Đ S Đ",
        }),
        "sa": {
            1: ["86"], 2: ["64"], 3: ["900"], 4: ["4"], 5: ["4"],
            6: ["3"], 7: ["2"], 8: ["0,22", "0.22"], 9: ["4"], 10: ["4"],
        },
    },
    "chu-de-1-bai-2": {
        "mcq_runs": {
            0: L(
                "B D A C C D D A A B D C B "
                "B B C A D C B C D D C D "
                "D B C A A A D A D B A A C "
                "A B C C C C C D B C D C A "
                "B B B C C A A B A D B B "
                "D A B B B C C D A D D A "
                "A C B B D D A D B B C D C "
                "B A A D A C B C A C D D "
                "D C B C B A A D B D"
            ),
        },
        "tf": TF({
            1: "Đ Đ S Đ",
            2: "Đ S Đ S",
            3: "S Đ S S",
            4: "S S Đ Đ",
            5: "S S Đ S",
            6: "S Đ S Đ",
            7: "Đ Đ S Đ",
        }),
        "sa": {
            1: ["26"], 2: ["1"], 3: ["8"], 4: ["2"], 5: ["1"],
            6: ["1"], 7: ["5"], 8: ["4"], 9: ["2"], 10: ["1"],
        },
    },
    "chu-de-1-bai-3": {
        "mcq_runs": {
            0: L(
                "B B A C C A D C B B B C B "
                "D A A B C B A B A B C C D "
                "C D D D D B C D A D C C "
                "B C"
            ),
        },
        "tf": TF({
            1: "Đ S Đ Đ",
            2: "S S S Đ",
            3: "Đ S Đ S",
            4: "Đ S Đ S",
            5: "S Đ Đ Đ",
            6: "Đ S Đ S",
        }),
        "sa": {
            1: ["5"], 2: ["2"], 3: ["3"], 4: ["4"], 5: ["3"],
            6: ["1"], 7: ["3"], 8: ["3"], 9: ["1"],
        },
    },
    "chu-de-1-bai-4": {
        "mcq_runs": {
            0: L(
                "A B C B A A A D A C A C B "
                "A A D A C A D C D B A D B "
                "C A D C B C D A D B C A D "
                "D A A D A D B B B C A C B A"
            ),
            # Run 1 là 44 câu Công nghệ gene (bộ đề khác với Bài 13 PDF nên giữ chờ GV cài)
            2: L("A D A D C D A B D B B A B"),
        },
        "tf": TF({
            1: "S Đ Đ Đ",
            2: "S S S Đ",
            3: "Đ Đ S Đ",
            4: "Đ S Đ Đ",
            5: "Đ Đ S S",
            6: "S Đ Đ Đ",
            7: "S S Đ S",
            8: "Đ S S Đ",
            9: "Đ S S Đ",
        }),
        "sa": {},
    },

    # ==================== CHỦ ĐỀ 2 ====================
    "chu-de-2-bai-1": {
        "mcq_runs": {
            0: L(
                "C C B B D C D A A B C D A "
                "A D B B D B D D A B B B A "
                "B D A A D A B C D C A B A "
                "C B D A A B C C B A C B "
                "A B A A D A D D B D A B B "
                "C D B D C C B B D B A A B "
                "B D C C B A C D D"
            ),
        },
        "tf": TF({
            1: "Đ Đ S Đ",
            2: "Đ Đ S S",
            3: "Đ Đ S S",
            4: "Đ S S S",
            5: "S S S Đ",
            6: "S S Đ Đ",
            7: "Đ Đ S Đ",
            8: "Đ Đ Đ S",
            9: "S Đ Đ S",
            10: "S Đ Đ S",
        }),
        "sa": {
            1: ["8"], 2: ["4"], 3: ["1"], 4: ["37,5", "37.5"], 5: ["4"],
            6: ["3"], 7: ["2"], 8: ["6"], 9: ["31,25", "31.25"], 10: ["5"],
        },
    },
    "chu-de-2-bai-2": {
        "mcq_runs": {
            0: L(
                "D D A B A C A A A A B A D "
                "D C D C A C B D D A C C B "
                "C A C D B C D A D B A B B "
                "A D C A B D B D B"
            ),
            1: L(
                "D D D B A A A D D A C A B "
                "C C B A B D A B A A D A A "
                "B D A B D B D A C C "
                "C B A A D D C A A A A A D "
                "B C B C A D A A A C C B "
                "B A B C A A C "
                "A D A A D D A C D B"
            ),
            2: L(
                "D B A B D D D B A C C "
                "D D C D D C D C B D B A B "
                "A A B A A A D B C D C D B "
                "C B B A D B B A A A D C D "
                "A D D B C"
            ),
        },
        "tf": TF({
            1: "S Đ S Đ",
            2: "Đ Đ S Đ",
            3: "S Đ Đ S",
            4: "Đ S S Đ",
            5: "S Đ S Đ",
            6: "S Đ S S",
            7: "S Đ Đ Đ",
            8: "S S Đ Đ",
            9: "Đ Đ S S",
            10: "Đ S Đ S",
        }),
        "sa": {
            1: ["0,5", "0.5"], 2: ["4"], 3: ["1,25", "1.25"], 4: ["1"], 5: ["6"],
            6: ["1/12"], 7: ["5"], 8: ["2"], 9: ["1"], 10: ["3"],
        },
    },
    "chu-de-2-bai-3": {
        "mcq_runs": {
            0: L(
                "B C B C C A B C C B C D D "
                "B D D B A D C B C D C A C "
                "A B C C B D A"
            ),
        },
        "tf": {},
        "sa": {},
    },

    # ==================== CHỦ ĐỀ 3 ====================
    "chu-de-3-bai-1": {
        "mcq_runs": {
            0: L(
                "D B D C C C D D A C A A A "
                "A C B C B D B C C B A B C"
            ),
            1: L(
                "C C A D C B A C C D B B B "
                "B D A A A B A D B D A A B "
                "D C C A D C A B D C D C "
                "D A B C C B C A C D A B B A"
            ),
        },
        "tf": TF({
            1: "S Đ S Đ",
            2: "Đ Đ S S",
            3: "Đ Đ S S",
            4: "S S S Đ",
            5: "Đ S Đ Đ",
            6: "S Đ Đ Đ",
            7: "Đ Đ Đ S",
            8: "Đ S S Đ",
            9: "S Đ Đ Đ",
            10: "S Đ S S",
        }),
        "sa": {
            1: ["3; 6; 4", "3, 6, 4"], 2: ["3"], 3: ["137"], 4: ["2"],
            5: ["1/9"], 6: ["60"], 7: ["8/9"], 8: ["5"],
            9: ["1/3"], 10: ["27"], 11: ["3"], 12: ["3"],
        },
    },
    "chu-de-3-bai-2": {
        "mcq_runs": {
            0: L(
                "C B D C C B B D A A D D B "
                "B A C A B C D"
            ),
            1: L(
                "D B B D D A D C B B C C B "
                "B B B C B A B C B B C B D "
                "D D B A B C D D A D"
            ),
        },
        "tf": TF({
            1: "Đ Đ Đ S",
            2: "Đ Đ Đ Đ",
            3: "S S Đ Đ",
            4: "Đ Đ S Đ",
            5: "Đ Đ Đ S",
            6: "S Đ Đ Đ",
            7: "Đ Đ S S",
            8: "Đ Đ Đ Đ",
            9: "Đ S Đ Đ",
            10: "Đ S S S",
            11: "Đ Đ Đ Đ",
            12: "Đ Đ S Đ",
            13: "Đ Đ Đ Đ",
            14: "Đ S Đ Đ",
            15: "S S S Đ",
        }),
        "sa": {
            1: ["2"], 2: ["1/4; 1/2", "0,25; 0,5"], 3: ["3"], 4: ["2"],
            5: ["27; 18; 1/4; 1/32; 1/16"], 6: ["6"], 7: ["1/2", "0,5", "0.5"],
        },
    },

    # ==================== CHỦ ĐỀ 4 ====================
    "chu-de-4-bai-1": {
        "mcq_runs": {
            0: L("A A D A D A B C C B C C D B A B"),
            1: L(
                "A D C B D A D C A D B C A "
                "B C B C C B B C A C B C D "
                "C B C A B B D"
            ),
        },
        "tf": TF({
            1: "Đ Đ S S",
            2: "Đ Đ S S",
            3: "Đ Đ Đ S",
            4: "Đ Đ Đ Đ",
            5: "S S S Đ",
            6: "Đ Đ Đ Đ",
        }),
        "sa": {
            1: ["1/3"], 2: ["1/8", "0,125", "0.125"], 3: ["50"], 4: ["25"],
            5: ["31,25", "31.25"], 6: ["25"], 7: ["4/15"], 8: ["3"], 9: ["4"], 10: ["25"],
        },
    },
    "chu-de-4-bai-2": {
        "mcq_runs": {
            0: L("D D C D B A B B C"),
            1: L("D B B B B A B B A D C C D C A"),
            2: L(
                "B A D A B C B A C A B D B "
                "B D C A B A D B A A D D B C C"
            ),
            3: L(
                "B C A D B A C B D B A D C "
                "B D D D C C B B C D D B D "
                "D D A C C C C B B A A D A A"
            ),
            4: L("B C A B C A D B A B A"),
            5: L("A B B A C C D B A C A"),
        },
        "tf": TF({
            1: "Đ S Đ Đ",
            2: "S Đ S Đ",
            3: "Đ Đ Đ S",
            4: "S Đ S Đ",
            5: "Đ S S S",
            6: "S Đ Đ Đ",
            7: "S Đ Đ Đ",
            8: "Đ Đ Đ S",
            9: "S Đ S Đ",
            10: "Đ Đ S Đ",
            11: "Đ S Đ S",
        }),
        "sa": {
            1: ["17,5", "17.5"], 2: ["2"], 3: ["50"], 4: ["4"], 5: ["15"],
            6: ["18,75", "18.75"], 7: ["27,95", "27.95"], 8: ["50"], 9: ["5"],
            10: ["25"], 11: ["2160"], 12: ["4"], 13: ["7"], 14: ["16,5", "16.5"],
        },
    },
    "chu-de-4-bai-3": {
        "mcq_runs": {
            0: L(
                "B C A D A B B D C A D D A "
                "A B D B D C B C D C B B C "
                "D A D B"
            ),
        },
        "tf": TF({
            1: "Đ S Đ Đ",
            2: "S Đ S S",
            3: "S S Đ S",
            4: "S S S Đ",
            5: "S S S Đ",
            6: "S S Đ S",
        }),
        "sa": {
            1: ["4"], 2: ["3"], 3: ["2"], 4: ["4"], 5: ["100"],
        },
    },
    "chu-de-4-bai-4": {
        "mcq_runs": {
            0: L(
                "C C A D A A B A D C B A C "
                "D B A B B D A C D B B C B "
                "B A A A"
            ),
        },
        "tf": TF({
            1: "Đ Đ Đ S",
            2: "Đ Đ S Đ",
        }),
        "sa": {
            1: ["1"], 2: ["75"], 3: ["50"], 4: ["37,5", "37.5"],
        },
    },
}


def split_mcq_into_runs(mcqs):
    runs = []
    for q in mcqs:
        n = q.get("orig_num", 1)
        if not runs or n <= runs[-1][-1].get("orig_num", 0):
            runs.append([q])
        else:
            runs[-1].append(q)
    return runs


def main():
    conn = get_conn()
    ts = now_iso()

    total_mcq = total_mcq_keyed = 0
    total_tf = total_tf_keyed = 0
    total_sa = total_sa_keyed = 0
    cross_match = cross_total = 0

    for idx in range(1, 5):
        jpath = os.path.join(TOPICS_DIR, f"chu_de_{idx}.json")
        with open(jpath, "r", encoding="utf-8") as f:
            topic = json.load(f)

        # Đảm bảo bỏ hoàn toàn source_note và interactive_video cũ, giữ youtube_videos
        topic["source_note"] = ""
        topic.pop("interactive_video", None)
        topic.setdefault("youtube_videos", [])
        if "knowledge_system" in topic:
            topic["knowledge_system"]["overview"] = ""

        # Giữ nguyên youtube_videos nếu giáo viên đã thêm trên DB
        db_row = conn.execute("SELECT content_json FROM topics WHERE id = ?", (topic["id"],)).fetchone()
        if db_row:
            old_db = json.loads(db_row["content_json"])
            if old_db.get("youtube_videos"):
                topic["youtube_videos"] = old_db["youtube_videos"]

        for ls in topic["lessons"]:
            lid = ls["id"]
            key_spec = ANSWER_KEYS.get(lid)
            if not key_spec:
                continue

            # 1. MCQ matching by (run_idx, orig_num)
            l_mcqs = [q for q in topic["review"]["mcq"] if q["lesson_id"] == lid]
            runs = split_mcq_into_runs(l_mcqs)
            for r_idx, run_qs in enumerate(runs):
                run_map = key_spec["mcq_runs"].get(r_idx)
                if not run_map:
                    continue
                for q in run_qs:
                    n = q.get("orig_num")
                    if n in run_map:
                        pdf_ans = run_map[n]
                        # Cross-check against underlined answers in Chủ đề 3
                        if q.get("answer_key_ready") and q.get("correct_index") is not None:
                            cross_total += 1
                            if q["correct_index"] == pdf_ans:
                                cross_match += 1
                        if pdf_ans < len(q.get("options") or []):
                            q["correct_index"] = pdf_ans
                            q["answer_key_ready"] = True

            # 2. True/False matching by orig_num
            l_tfs = [q for q in topic["review"]["true_false"] if q["lesson_id"] == lid]
            tf_map = key_spec.get("tf") or {}
            for q in l_tfs:
                n = q.get("orig_num")
                if n in tf_map:
                    ans_arr = tf_map[n]
                    stmts = q.get("statements") or []
                    if len(stmts) == len(ans_arr):
                        for st, val in zip(stmts, ans_arr):
                            st["answer"] = val
                        q["answer_key_ready"] = True

            # 3. Short Answer matching by orig_num
            l_sas = [q for q in topic["review"]["short_answer"] if q["lesson_id"] == lid]
            sa_map = key_spec.get("sa") or {}
            for q in l_sas:
                n = q.get("orig_num")
                if n in sa_map:
                    q["accepted_answers"] = sa_map[n]
                    q["answer_key_ready"] = True

        # Chỉnh vị trí chính xác cho 2 cụm hình neo lệch trong Chủ đề 2 Bài 1 & gắn 2 hình vẽ lại rõ nét
        if topic["id"] == "chu-de-2":
            tf_by_id = {q["id"]: q for q in topic["review"]["true_false"]}
            if "chu-de-2-b1-tf-5" in tf_by_id and "chu-de-2-b1-tf-6" in tf_by_id:
                tf5 = tf_by_id["chu-de-2-b1-tf-5"]
                tf6 = tf_by_id["chu-de-2-b1-tf-6"]
                if tf5.get("images") and not tf6.get("images"):
                    tf6["images"] = tf5["images"]
                    tf5["images"] = ["/images/redrawn/cd2_b1_tf5.svg"]
            sa_by_id = {q["id"]: q for q in topic["review"]["short_answer"]}
            if "chu-de-2-b1-sa-2" in sa_by_id and not sa_by_id["chu-de-2-b1-sa-2"].get("images"):
                sa_by_id["chu-de-2-b1-sa-2"]["images"] = ["/images/redrawn/cd2_b1_sa2.svg"]
            if all(k in sa_by_id for k in ("chu-de-2-b1-sa-4", "chu-de-2-b1-sa-5", "chu-de-2-b1-sa-6")):
                sa4, sa5, sa6 = sa_by_id["chu-de-2-b1-sa-4"], sa_by_id["chu-de-2-b1-sa-5"], sa_by_id["chu-de-2-b1-sa-6"]
                if sa4.get("images") and sa5.get("images") and not sa6.get("images"):
                    sa6["images"] = sa5["images"]
                    sa5["images"] = sa4["images"]
                    sa4["images"] = []

        # Thống kê từng chủ đề
        m_all = len(topic["review"]["mcq"])
        m_key = sum(1 for q in topic["review"]["mcq"] if q.get("answer_key_ready"))
        t_all = len(topic["review"]["true_false"])
        t_key = sum(1 for q in topic["review"]["true_false"] if q.get("answer_key_ready"))
        s_all = len(topic["review"]["short_answer"])
        s_key = sum(1 for q in topic["review"]["short_answer"] if q.get("answer_key_ready"))

        total_mcq += m_all; total_mcq_keyed += m_key
        total_tf += t_all; total_tf_keyed += t_key
        total_sa += s_all; total_sa_keyed += s_key

        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(topic, f, ensure_ascii=False, indent=2)

        conn.execute(
            "UPDATE topics SET title = ?, subtitle = ?, content_json = ?, updated_at = ? WHERE id = ?",
            (topic["title"], topic.get("subtitle", ""), json.dumps(topic, ensure_ascii=False), ts, topic["id"]),
        )
        print(
            f"[OK] {topic['title']}\n"
            f"     3.1 MCQ: {m_key}/{m_all} có đáp án | 3.2 Đúng/Sai: {t_key}/{t_all} có đáp án | 3.3 Trả lời ngắn: {s_key}/{s_all} có đáp án"
        )

    conn.commit()
    conn.close()
    print("-" * 72)
    print(f"TỔNG CỘNG: MCQ {total_mcq_keyed}/{total_mcq} | Đúng/Sai {total_tf_keyed}/{total_tf} | Trả lời ngắn {total_sa_keyed}/{total_sa}")
    if cross_total:
        print(f"KIỂM TRA CHÉO VỚI ĐÁP ÁN GẠCH CHÂN TRONG WORD (CHỦ ĐỀ 3): khớp {cross_match}/{cross_total} ({cross_match/cross_total*100:.1f}%)")


if __name__ == "__main__":
    main()
