#!/usr/bin/env python3
"""
Gắn hệ thống ô nhập đáp án và đáp án chuẩn (đối chiếu từ ĐÁP ÁN 1.pdf, ĐÁP ÁN 2.pdf,
Sinh học 12 - Đáp án hoàn chỉnh.pdf và SGK Sinh học 12 GDPT 2018) cho tất cả bài tập
vận dụng và bảng phiếu trong hai mục:
  1. Lý thuyết
  2. Hệ thống kiến thức
của các Chủ đề 1 -> 4, đồng thời tăng bundled_version để đồng bộ tự động vào SQLite.
"""

import json
import os
import re

BUNDLED_VERSION = "2026.11.26-exercises-v3"
TOPICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "topics")


def load_topic(filename):
    path = os.path.join(TOPICS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f), path


def save_topic(data, path):
    data["bundled_version"] = BUNDLED_VERSION
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cell_ans(answer, exact=None, grade_type="compare", multiline=None):
    if multiline is None:
        multiline = len(answer) > 48 or "\n" in answer
    obj = {
        "answer": answer,
        "grade_type": grade_type if exact is None else "exact",
        "multiline": multiline,
    }
    if exact is not None:
        obj["exact"] = exact
    return obj


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


def group_item(eid, label, answer, mode="input", exact=None, grade_type="compare", placeholder=None):
    obj = {
        "id": eid,
        "label": label,
        "mode": mode,
        "answer": answer,
        "grade_type": "exact" if (exact is not None or mode == "true_false") else grade_type,
    }
    if exact is not None:
        obj["exact"] = exact
    if placeholder:
        obj["placeholder"] = placeholder
    return obj


def clean_old_interactive(data):
    """Xóa metadata interactive/exercise cũ để script chạy idempotent."""
    for lesson in data.get("lessons", []):
        for sec in lesson.get("sections", []):
            for b in sec.get("blocks", []):
                b.pop("interactive", None)
                b.pop("exercise", None)
                b.pop("exercise_group", None)
                b.pop("hidden_by_group", None)
    for unit in data.get("knowledge_system", {}).get("units", []):
        for b in unit.get("blocks", []):
            b.pop("interactive", None)
            b.pop("exercise", None)
            b.pop("exercise_group", None)
            b.pop("hidden_by_group", None)


# =====================================================================
# CHỦ ĐỀ 1
# =====================================================================
def enrich_chu_de_1():
    data, path = load_topic("chu_de_1.json")
    clean_old_interactive(data)

    lessons = data["lessons"]
    units = data["knowledge_system"]["units"]

    # ---------- LÝ THUYẾT 1.1 ----------
    s4 = lessons[0]["sections"][4]["blocks"]
    s4[3]["text"] = "1. Tổng số phân tử DNA được tạo ra."
    s4[3]["exercise"] = ex_item(
        "cd1-th-1.1-vd1-1", "cd1-th-1.1-vd1",
        "64 phân tử DNA con (vì 2 giờ = 120 phút → số lần tái bản k = 120/20 = 6 → 2^6 = 64)",
        mode="input", exact=["64", "64 phan tu dna", "64 phan tu dna con", "64 dna"]
    )
    s4[4]["text"] = "2. Tổng số phân tử DNA con hoàn toàn chứa 14N phóng xạ."
    s4[4]["exercise"] = ex_item(
        "cd1-th-1.1-vd1-2", "cd1-th-1.1-vd1",
        "62 phân tử DNA hoàn toàn chứa 14N (2^6 − 2 = 62)",
        mode="input", exact=["62", "62 phan tu dna", "62 phan tu dna con", "62 dna"]
    )
    s4[5]["exercise"] = ex_item(
        "cd1-th-1.1-vd1-3", "cd1-th-1.1-vd1",
        "126 mạch đơn hoàn toàn mới (2 × (2^6 − 1) = 126)",
        mode="input", exact=["126", "126 mach", "126 mach don", "126 mach don hoan toan moi"]
    )
    s4[6]["exercise"] = ex_item(
        "cd1-th-1.1-vd1-4", "cd1-th-1.1-vd1",
        "2 mạch chứa 15N",
        mode="input", exact=["2", "2 mach", "2 mach chua 15n"]
    )
    s4[7]["exercise"] = ex_item(
        "cd1-th-1.1-vd1-5", "cd1-th-1.1-vd1",
        "2 phân tử DNA con có chứa 15N",
        mode="input", exact=["2", "2 phan tu", "2 phan tu dna", "2 phan tu dna con"]
    )
    # Ví dụ 2 (Đúng/Sai 4 ý a..d — theo ĐÁP ÁN 1.pdf trang 285)
    s4[9]["interactive"] = {
        "id": "cd1-th-1.1-vd2",
        "mode": "tf_rows",
        "has_header": False,
        "tf_answers": {
            "0": "Đúng",
            "1": "Đúng",
            "2": "Sai",
            "3": "Đúng",
        },
    }

    # ---------- LÝ THUYẾT 1.2 ----------
    s10 = lessons[1]["sections"][10]["blocks"]
    s10[10]["rows"][2][1] = "5'GCTTCGCGATCG3'"
    s10[10]["interactive"] = {
        "id": "cd1-th-1.2-vd",
        "mode": "fill",
        "answers": {
            "1:1": cell_ans("5'CGA TCG CGA AGC3'", exact=["5'cgatcgcgaagc3'", "cgatcgcgaagc"], multiline=False),
            "2:2": cell_ans("3'CGA AGC GCT AGC5'", exact=["3'cgaagcgctagc5'", "cgaagcgctagc"], multiline=False),
            "3:1": cell_ans("5'CGA UCG CGA AGC3'", exact=["5'cgaucgcgaagc3'", "cgaucgcgaagc"], multiline=False),
            "3:2": cell_ans("5'GCU UCG CGA UCG3'", exact=["5'gcuucgcgaucg3'", "gcuucgcgaucg"], multiline=False),
            "4:1": cell_ans("/3'GCU5'/3'AGC5'/3'GCU5'/3'UCG5'/", exact=["/3'gcu5'/3'agc5'/3'gcu5'/3'ucg5'/", "gcu agc gcu ucg", "3'gcu5'3'agc5'3'gcu5'3'ucg5'"], multiline=False),
            "4:2": cell_ans("/3'CGA5'/3'AGC5'/3'GCU5'/3'AGC5'/", exact=["/3'cga5'/3'agc5'/3'gcu5'/3'agc5'/", "cga agc gcu agc", "3'cga5'3'agc5'3'gcu5'3'agc5'"], multiline=False),
            "5:1": cell_ans("Arginine – Serine – Arginine – Serine", exact=["arginine-serine-arginine-serine", "arg-ser-arg-ser"], multiline=False),
            "5:2": cell_ans("Alanine – Serine – Arginine – Serine", exact=["alanine-serine-arginine-serine", "ala-ser-arg-ser"], multiline=False),
        },
    }

    # ---------- LÝ THUYẾT 1.4 ----------
    s11 = lessons[3]["sections"][11]["blocks"]
    s11[9]["exercise"] = ex_item(
        "cd1-th-1.4-bt1-1", "cd1-th-1.4-bt1",
        "Gene trước đột biến: A = T = 600, G = C = 1200.\nDạng đột biến: Thay 1 cặp A = T bằng 1 cặp G ≡ C.\nGene sau đột biến: A = T = 599, G = C = 1201.",
        mode="textarea"
    )
    s11[10]["exercise"] = ex_item(
        "cd1-th-1.4-bt1-2", "cd1-th-1.4-bt1",
        "Gene trước đột biến: A = T = 480, G = C = 720.\nDạng đột biến:\n+ Nếu mất 1 cặp A = T → Gene sau đột biến: A = T = 479, G = C = 720.\n+ Nếu thay 2 cặp G ≡ C bằng 2 cặp A = T → Gene sau đột biến: A = T = 482, G = C = 718.",
        mode="textarea"
    )
    s11[11]["exercise"] = ex_item(
        "cd1-th-1.4-bt1-3", "cd1-th-1.4-bt1",
        "Gene trước đột biến: A = T = 230, G = C = 460.\nDạng đột biến:\n+ Nếu mất 1 cặp A = T → Gene sau đột biến: A = T = 229, G = C = 460.\n+ Nếu thay 2 cặp G ≡ C bằng 2 cặp A = T → Gene sau đột biến: A = T = 232, G = C = 458.",
        mode="textarea"
    )

    s12 = lessons[3]["sections"][12]["blocks"]
    s12[6]["exercise"] = ex_item(
        "cd1-th-1.4-bt2-a", "cd1-th-1.4-bt2-vd1",
        "- Allele D1: thay thế 1 cặp A–T bằng 1 cặp G–C ở vị trí nucleotide số 9 (đột biến đồng nghĩa).\n- Allele D2: thay thế 1 cặp A–T bằng 1 cặp G–C ở vị trí nucleotide số 6 (đột biến đồng nghĩa).\n- Allele D3: thay thế 1 cặp A–T bằng 1 cặp G–C ở vị trí nucleotide số 10 (đột biến sai nghĩa).",
        mode="textarea"
    )
    s12[7]["exercise"] = ex_item(
        "cd1-th-1.4-bt2-b", "cd1-th-1.4-bt2-vd1",
        "- Allele D (mRNA: 5'AUG GAU CAU UAC AGU UAG3'): Methionine – Aspartate – Histidine – Tyrosine – Serine.\n- Allele D1 (mRNA: 5'AUG GAU CAC UAC AGU UAG3'): Methionine – Aspartate – Histidine – Tyrosine – Serine (không đổi).\n- Allele D2 (mRNA: 5'AUG GAC CAU UAC AGU UAG3'): Methionine – Aspartate – Histidine – Tyrosine – Serine (không đổi).\n- Allele D3 (mRNA: 5'AUG GAU CAU CAC AGU UAG3'): Methionine – Aspartate – Histidine – Histidine – Serine (thay Tyrosine bằng Histidine).",
        mode="textarea"
    )
    # Làm sạch dấu chấm ....... trước a, b, c, d ở Ví dụ 2 và gắn Đúng/Sai (ĐÁP ÁN 1.pdf trang 289)
    vd2_tf = [("a.", "Đúng"), ("b.", "Đúng"), ("c.", "Sai"), ("d.", "Đúng")]
    for idx_off, (prefix, tf_val) in enumerate(vd2_tf):
        blk = s12[12 + idx_off]
        blk["text"] = re.sub(r"^\.+\s*", "", blk["text"])
        blk["exercise"] = ex_item(
            f"cd1-th-1.4-vd2-{prefix[0]}", "cd1-th-1.4-vd2",
            tf_val, mode="true_false"
        )

    # ---------- HỆ THỐNG KIẾN THỨC 1.1 ----------
    u0 = units[0]["blocks"]
    c1_rows = u0[1]["rows"]
    c1_ans_1_1 = [
        "Thuộc giới khởi sinh, tế bào chưa có màng nhân và các bào quan có màng",
        "Thuộc giới nguyên sinh, thực vật, nấm, động vật; tế bào có màng nhân và các bào quan có màng",
        "Các phân tử tham gia lưu trữ và truyền đạt thông tin di truyền gồm DNA, RNA và Protein",
        "Là quá trình tạo ra 2 phân tử DNA mới giống hệt nhau từ 1 phân tử DNA ban đầu",
        "Đơn phân cấu tạo nên phân tử DNA (gồm đường deoxyribose C5H10O4, nhóm phosphate và 1 trong 4 loại base A, T, G, C)",
        "Liên kết cộng hoá trị bền vững nối các nucleotide kế tiếp nhau trên cùng một mạch đơn polynucleotide",
        "Liên kết yếu hình thành giữa các cặp base bổ sung của hai mạch đơn DNA (A = T bằng 2 liên kết, G ≡ C bằng 3 liên kết)",
        "Nguyên tắc bắt cặp đặc hiệu giữa các nitrogenous base: A liên kết với T, G liên kết với C (hoặc A–U trong phiên mã)",
        "Trong mỗi phân tử DNA con được tạo ra có một mạch cũ của DNA mẹ và một mạch mới tổng hợp từ môi trường",
        "Enzyme xúc tác tổng hợp đoạn mồi RNA (primase) hoặc tổng hợp phân tử RNA trong quá trình phiên mã",
        "Enzyme lắp ráp các nucleotide tự do theo nguyên tắc bổ sung để tổng hợp mạch DNA mới theo chiều 5' → 3'",
        "Enzyme nối các đoạn Okazaki trên mạch tổng hợp gián đoạn tạo thành mạch polynucleotide hoàn chỉnh",
        "Là những biến đổi trong cấu trúc của gene liên quan đến 1 hoặc 1 số cặp nucleotide",
        "Là hiện tượng con sinh ra có kiểu hình khác với bố mẹ",
    ]
    ans_map = {}
    for i, text_ans in enumerate(c1_ans_1_1, start=1):
        if i < len(c1_rows):
            if not c1_rows[i][0].strip():
                c1_rows[i][0] = str(i)
            ans_map[f"{i}:2"] = cell_ans(text_ans)
    u0[1]["interactive"] = {"id": "cd1-ks-1.1-c1", "mode": "fill", "answers": ans_map}

    u0[3]["exercise"] = ex_item(
        "cd1-ks-1.1-c2-1", "cd1-ks-1.1-c2-1",
        "Liên kết phosphodiester bền → đảm bảo duy trì được sự ổn định của thông tin di truyền. Liên kết hydrogen kém bền → DNA có thể tách mạch làm khuôn giúp truyền đạt thông tin di truyền.",
        mode="textarea"
    )
    u0[5]["exercise_group"] = {
        "id": "cd1-ks-1.1-c2-2",
        "columns": 2,
        "items": [
            group_item("cd1-ks-1.1-c2-2-1", "Số 1", "Nucleotide", exact=["nucleotide", "nu"]),
            group_item("cd1-ks-1.1-c2-2-2", "Số 2", "Thymine", exact=["thymine", "t", "timin"]),
            group_item("cd1-ks-1.1-c2-2-3", "Số 3", "Liên kết phosphodiester", exact=["lien ket phosphodiester", "phosphodiester"]),
            group_item("cd1-ks-1.1-c2-2-4", "Số 4", "Nhóm phosphate", exact=["nhom phosphate", "phosphate", "photphat", "nhom photphat"]),
            group_item("cd1-ks-1.1-c2-2-5", "Số 5", "Đường deoxyribose (C5H10O4)", exact=["duong deoxyribose", "deoxyribose", "duong deoxyribose (c5h10o4)", "c5h10o4"]),
            group_item("cd1-ks-1.1-c2-2-6", "Số 6", "Liên kết hydrogen", exact=["lien ket hydrogen", "hydrogen", "lien ket hidro", "hidro"]),
            group_item("cd1-ks-1.1-c2-2-7", "Số 7", "Cytosine", exact=["cytosine", "c", "xitozin"]),
        ],
    }

    # ---------- HỆ THỐNG KIẾN THỨC 1.2 ----------
    u1 = units[1]["blocks"]
    u1[0]["text"] = u1[0]["text"].replace("bản bên dưới", "bảng bên dưới")
    c1_ans_1_2 = [
        "Là một đoạn của phân tử DNA mang thông tin quy định trình tự amino acid của chuỗi polypeptide hoặc trình tự nucleotide của RNA",
        "Là tập hợp đầy đủ các trình tự DNA có trong tế bào của một loài sinh vật",
        "Là gene chứa các đoạn exon (mã hóa amino acid) xen kẽ với các đoạn intron (không mã hóa amino acid)",
        "Là gene chỉ chứa các đoạn exon (mã hóa amino acid)",
        "Là gene tạo ra sản phẩm tham gia cấu tạo tế bào hoặc thực hiện chức năng",
        "Là gene tạo ra sản phẩm tham gia điều hòa biểu hiện của gene khác",
        "Là mạch có chiều 3' → 5' của gene dùng làm khuôn cho quá trình phiên mã",
        "Là mạch có chiều 5' → 3' bổ sung với mạch gốc của gene",
        "Là quá trình tổng hợp RNA dựa trên mạch khuôn của gene",
        "Là quá trình tổng hợp DNA bổ sung (cDNA) dựa trên khuôn RNA",
        "Là trình tự nucleotide được mã hoá ở dạng mã bộ ba (codon) trên mRNA quy định trình tự amino acid trong một chuỗi polypeptide",
        "Là quá trình tổng hợp protein (chuỗi polypeptide) dựa trên khuôn mRNA",
        "Là nhiều ribosome tham gia dịch mã cùng lúc trên một phân tử mRNA giúp tăng hiệu suất tổng hợp protein",
        "Enzyme trượt dọc trên mạch khuôn 3' → 5' của gene để tổng hợp phân tử RNA theo chiều 5' → 3'",
        "Gồm 3 bộ ba 5'UAA3', 5'UAG3', 5'UGA3' trên mRNA, không mã hoá amino acid, quy định tín hiệu kết thúc dịch mã",
        "Bộ ba 5'AUG3' trên mRNA, quy định tín hiệu mở đầu dịch mã và mã hoá Methionine (sinh vật nhân thực) hoặc fMet (nhân sơ)",
        "Bộ ba nucleotide kế tiếp nhau trên mạch gốc của DNA (chiều 3' → 5')",
        "Bộ ba nucleotide kế tiếp nhau trên phân tử mRNA (chiều 5' → 3')",
        "Bộ ba đối mã trên phân tử tRNA khớp bổ sung với codon tương ứng trên mRNA",
        "Tất cả các loài sinh vật đều dùng chung một bộ mã di truyền (trừ một vài ngoại lệ)",
        "Một bộ ba chỉ mã hoá cho một loại amino acid duy nhất",
        "Nhiều bộ ba khác nhau có thể cùng mã hoá cho một loại amino acid (trừ AUG và UGG)",
        "Liên kết cộng hoá trị nối các amino acid kế tiếp nhau trong chuỗi polypeptide",
    ]
    ans_map = {}
    for i, text_ans in enumerate(c1_ans_1_2, start=1):
        if i < len(u1[1]["rows"]):
            if not u1[1]["rows"][i][0].strip():
                u1[1]["rows"][i][0] = str(i)
            ans_map[f"{i}:2"] = cell_ans(text_ans)
    u1[1]["interactive"] = {"id": "cd1-ks-1.2-c1", "mode": "fill", "answers": ans_map}

    # Câu 2: Phân biệt DNA và mRNA (ĐÁP ÁN 1.pdf trang 287)
    u1[3]["interactive"] = {
        "id": "cd1-ks-1.2-c2",
        "mode": "fill",
        "answers": {
            "1:2": cell_ans("Deoxyribose (C5H10O4)", exact=["deoxyribose", "deoxyribose (c5h10o4)", "c5h10o4"], multiline=False),
            "1:3": cell_ans("Ribose (C5H10O5)", exact=["ribose", "ribose (c5h10o5)", "c5h10o5"], multiline=False),
            "2:2": cell_ans("A, T, G, C", exact=["a,t,g,c", "atgc", "a t g c"], multiline=False),
            "2:3": cell_ans("A, U, G, C", exact=["a,u,g,c", "augc", "a u g c"], multiline=False),
            "3:2": cell_ans("Gồm 2 mạch song song và ngược chiều nhau"),
            "3:3": cell_ans("Gồm 1 mạch có chiều 5' → 3'"),
            "4:2": cell_ans("Lưu trữ, bảo quản, truyền đạt, biểu hiện thông tin di truyền và tạo biến dị"),
            "4:3": cell_ans("mRNA: làm khuôn để tổng hợp protein (tRNA: vận chuyển amino acid; rRNA: kết hợp với protein tạo ribosome – nơi dịch mã)"),
        },
    }
    # Câu 3: Điền 17 số (ĐÁP ÁN 1.pdf trang 287)
    c3_1_2_items = [
        ("1", "Phiên mã", ["phien ma"]),
        ("2", "mRNA", ["mrna"]),
        ("3", "RNA polymerase", ["rna polymerase"]),
        ("4", "Mạch khuôn", ["mach khuon"]),
        ("5", "Mạch bổ sung", ["mach bo sung"]),
        ("6", "Uracil", ["uracil", "u"]),
        ("7", "Nhân", ["nhan"]),
        ("8", "Dịch mã", ["dich ma"]),
        ("9", "Màng nhân", ["mang nhan"]),
        ("10", "Ribosome", ["ribosome", "riboxom"]),
        ("11", "mRNA", ["mrna"]),
        ("12", "Codon", ["codon"]),
        ("13", "Anticodon", ["anticodon"]),
        ("14", "Amino acid", ["amino acid", "axit amin"]),
        ("15", "Chuỗi polypeptide", ["chuoi polypeptide", "polypeptide"]),
        ("16", "tRNA", ["trna"]),
        ("17", "Tế bào chất", ["te bao chat"]),
    ]
    u1[6]["exercise_group"] = {
        "id": "cd1-ks-1.2-c3",
        "columns": 3,
        "title": "Điền chú thích tương ứng với các số trên hình (1 → 17):",
        "items": [group_item(f"cd1-ks-1.2-c3-{n}", f"Số {n}", a, exact=ex) for n, a, ex in c3_1_2_items],
    }

    # ---------- HỆ THỐNG KIẾN THỨC 1.3 ----------
    u2 = units[2]["blocks"]
    c1_1_3_items = [
        ("1", "Operator", ["operator", "vung o", "vung van hanh"]),
        ("2", "Promoter", ["promoter", "promotor", "vung p", "vung khoi dong"]),
        ("3", "Phiên mã", ["phien ma"]),
        ("4", "mRNA", ["mrna"]),
        ("5", "Dịch mã", ["dich ma"]),
        ("6", "Lactose", ["lactose", "allolactose"]),
        ("7", "Protein ức chế bị bất hoạt", ["protein uc che bi bat hoat"]),
        ("8", "Các enzyme chuyển hóa lactose", ["cac enzyme chuyen hoa lactose", "enzyme chuyen hoa lactose"]),
        ("9", "RNA polymerase", ["rna polymerase"]),
        ("10", "Phiên mã", ["phien ma"]),
        ("11", "Dịch mã", ["dich ma"]),
        ("12", "mRNA", ["mrna"]),
        ("13", "Protein ức chế", ["protein uc che"]),
    ]
    u2[1]["exercise_group"] = {
        "id": "cd1-ks-1.3-c1",
        "columns": 2,
        "title": "Điền chú thích tương ứng với các số trên 2 hình (1 → 13):",
        "items": [group_item(f"cd1-ks-1.3-c1-{n}", f"Số {n}", a, exact=ex) for n, a, ex in c1_1_3_items],
    }
    c2_ans_1_3 = [
        "Quy định protein ức chế lacI",
        "Là nơi enzyme RNA polymerase liên kết để khởi đầu quá trình phiên mã",
        "Là nơi protein ức chế liên kết để ngăn cản quá trình phiên mã",
        "Quy định enzyme β-galactosidase (phân giải lactose)",
        "Quy định enzyme permease (vận chuyển lactose vào tế bào)",
        "Quy định enzyme transacetylase (khử các chất độc)",
        "Liên kết với vùng O (operator) → cản trở quá trình phiên mã của nhóm gene cấu trúc",
        "Liên kết với protein ức chế → biến đổi cấu hình của protein ức chế → giải phóng vùng O của Operon Lac",
        "Lắp ráp các nucleotide tự do để tổng hợp mRNA có chiều 5' → 3'",
    ]
    u2[3]["interactive"] = {
        "id": "cd1-ks-1.3-c2",
        "mode": "fill",
        "answers": {f"{i}:2": cell_ans(v) for i, v in enumerate(c2_ans_1_3, start=1)},
    }

    # ---------- HỆ THỐNG KIẾN THỨC 1.4 ----------
    u3 = units[3]["blocks"]
    c1_ans_1_4 = [
        "Là những biến đổi trong cấu trúc của gene liên quan đến 1 hoặc 1 số cặp nucleotide",
        "Là đột biến gene liên quan đến 1 cặp nucleotide",
        "Là cơ thể chứa đột biến gene đã biểu hiện thành kiểu hình đột biến",
        "Là cơ thể chứa đột biến gene chỉ biểu hiện ở 1 phần trên cơ thể",
        "Là đột biến xảy ra trong quá trình giảm phân tạo giao tử",
        "Là đột biến xảy ra ở tế bào soma (tế bào sinh dưỡng)",
        "Là đột biến mới chỉ xảy ra trên một mạch nào đó của gene",
        "Là allele quy định kiểu hình trội và được biểu hiện ở kiểu gene đồng hợp hoặc dị hợp",
        "Là allele quy định kiểu hình lặn và chỉ được biểu hiện ở kiểu gene đồng hợp lặn",
        "Là kiểu gene chứa các allele có trạng thái giống nhau của cùng một gene (VD: AA, aa)",
        "Là kiểu gene chứa các allele có trạng thái khác nhau của cùng một gene (VD: Aa)",
        "Là đột biến gene làm cho bộ ba này trở thành một bộ ba khác nhưng mã hoá cùng một loại amino acid (đột biến câm)",
        "Là đột biến gene làm cho bộ ba mã hoá amino acid trở thành bộ ba kết thúc",
        "Là đột biến gene làm cho bộ ba mã hoá amino acid này trở thành bộ ba mã hoá cho amino acid khác",
        "Là đột biến gene dạng mất hoặc thêm cặp nucleotide dẫn đến làm lệch khung các bộ ba từ vị trí xảy ra đột biến trở về cuối gene",
        "Là các quy trình kĩ thuật áp dụng trên đối tượng là gene, DNA, RNA từ đó tạo ra các sản phẩm phục vụ con người như tế bào, sinh vật biến đổi gene",
        "Là phân tử DNA được hình thành từ sự kết hợp giữa các đoạn DNA khác nguồn gốc (gồm gene cần chuyển và vector chuyển gene)",
        "Là enzyme restrictase, có khả năng nhận biết và cắt đứt DNA ở những điểm xác định để tạo ra đầu dính phù hợp",
        "Là enzyme ligase, có khả năng nối đoạn DNA (gene cần chuyển) vào phân tử DNA của thể truyền (plasmid) tạo DNA tái tổ hợp",
        "Là những sinh vật được nhận gene ngoại lai (hoặc có hệ gene đã được biến đổi phù hợp với mục đích sử dụng của con người)",
        "Là kĩ thuật chuyển đoạn DNA chứa gene cần chuyển từ tế bào cho sang tế bào nhận nhờ thể truyền (vector)",
    ]
    u3[1]["interactive"] = {
        "id": "cd1-ks-1.4-c1",
        "mode": "fill",
        "answers": {f"{i}:2": cell_ans(v) for i, v in enumerate(c1_ans_1_4, start=1)},
    }
    # Câu 2: Đánh chéo vào ví dụ là đột biến (ĐÁP ÁN 1.pdf trang 289: 2, 3, 5, 7, 8, 10, 11, 13, 14, 16, 17, 18)
    u3[3]["interactive"] = {
        "id": "cd1-ks-1.4-c2",
        "mode": "check_single",
        "check_col": 2,
        "check_rows": [2, 3, 5, 7, 8, 10, 11, 13, 14, 16, 17, 18],
        "checked_label": "× Đột biến",
        "unchecked_label": "Không phải đột biến",
    }

    save_topic(data, path)
    print("Updated chu_de_1.json")


# =====================================================================
# CHỦ ĐỀ 2
# =====================================================================
def enrich_chu_de_2():
    data, path = load_topic("chu_de_2.json")
    clean_old_interactive(data)

    lessons = data["lessons"]
    units = data["knowledge_system"]["units"]

    # ---------- LÝ THUYẾT 2.3 ----------
    s1 = lessons[2]["sections"][1]["blocks"]
    s1[7]["hidden_by_group"] = True
    s1[8]["hidden_by_group"] = True
    s1[9]["hidden_by_group"] = True
    s1[6]["exercise_group"] = {
        "id": "cd2-th-2.3-vd",
        "columns": 2,
        "items": [
            group_item("cd2-th-2.3-vd-1", "1. aaBb", "1 aB : 1 ab", exact=["1ab:1ab", "ab,ab", "1ab:1ab"]),
            group_item("cd2-th-2.3-vd-2", "2. AaBb", "1 AB : 1 Ab : 1 aB : 1 ab"),
            group_item("cd2-th-2.3-vd-3", "3. X^AX^a", "1 X^A : 1 X^a"),
            group_item("cd2-th-2.3-vd-4", "4. DdX^HY", "1 DX^H : 1 DY : 1 dX^H : 1 dY"),
            group_item("cd2-th-2.3-vd-5", "5. Ab/aB", "1 Ab : 1 aB"),
            group_item("cd2-th-2.3-vd-6", "6. ABd/abD", "1 ABd : 1 abD"),
            group_item("cd2-th-2.3-vd-7", "7. Aa Bd/bD", "1 ABd : 1 AbD : 1 aBd : 1 abD"),
            group_item("cd2-th-2.3-vd-8", "8. AB/ab De/dE", "1 AB De : 1 AB dE : 1 ab De : 1 ab dE"),
            group_item("cd2-th-2.3-vd-9", "9. Ab/aB (f = 0,4)", "AB = ab = 0,2 và Ab = aB = 0,3"),
            group_item("cd2-th-2.3-vd-10", "10. Ab/aB Dd (f = 0,2)", "AbD = Abd = aBD = aBd = 0,2 và ABD = ABd = abD = abd = 0,05"),
            group_item("cd2-th-2.3-vd-11", "11. Aa X^{DE}X^{de} (f = 0,2)", "AX^{DE} = AX^{de} = aX^{DE} = aX^{de} = 0,2 và AX^{De} = AX^{dE} = aX^{De} = aX^{dE} = 0,05"),
            group_item("cd2-th-2.3-vd-12", "12. AB/aB De/dE (f giữa D và E = 0,4)", "AB De = AB dE = aB De = aB dE = 0,15 và AB DE = AB de = aB DE = aB de = 0,1"),
        ],
    }
    # Dùng grade_type compare cho 12 câu viết giao tử (vì học sinh viết nhiều cách 1/2, 50%, 1:1...)
    for it in s1[6]["exercise_group"]["items"]:
        it["grade_type"] = "compare"
        it.pop("exact", None)

    s2 = lessons[2]["sections"][2]["blocks"]
    s2[5]["interactive"] = {
        "id": "cd2-th-2.3-vd1",
        "mode": "fill",
        "header_rows": 2,
        "answers": {
            "2:2": cell_ans("2 loại (1A : 1a)", multiline=False),
            "2:3": cell_ans("2 loại (1A : 1a)", multiline=False),
            "3:2": cell_ans("2 loại (1AB : 1ab hoặc 1Ab : 1aB)", multiline=False),
            "3:3": cell_ans("4 loại (1AB : 1Ab : 1aB : 1ab)", multiline=False),
            "4:2": cell_ans("2 loại (1 AB : 1 ab)", multiline=False),
            "4:3": cell_ans("2 loại (1 AB : 1 ab)", multiline=False),
            "5:2": cell_ans("4 loại (1 AB : 1 ab : 1 Ab : 1 aB)", multiline=False),
            "5:3": cell_ans("4 loại (AB = ab = x; Ab = aB = y), x và y phụ thuộc vào tần số hoán vị f"),
        },
    }
    s2[6]["exercise"] = ex_item(
        "cd2-th-2.3-why", "cd2-th-2.3-why",
        "- Ở mức độ cơ thể: một số tế bào sinh tinh giảm phân có xảy ra hoán vị, một số tế bào khác giảm phân không xảy ra hoán vị → số giao tử liên kết > số giao tử hoán vị → tỉ lệ các loại giao tử phụ thuộc vào f.\n- Ở mức độ 1 tế bào: một tế bào sinh tinh giảm phân chỉ cho 4 tinh trùng nên khi xảy ra hoán vị chỉ cho tối đa 4 loại giao tử (2 loại giao tử liên kết và 2 loại giao tử hoán vị) tương ứng với 4 tinh trùng → tỉ lệ các loại giao tử là 1 : 1 : 1 : 1, không phụ thuộc vào f.",
        mode="textarea"
    )
    vd2_nums = ["2", "4", "8", "6", "6", "6", "6"]
    s2[14]["interactive"] = {
        "id": "cd2-th-2.3-vd2",
        "mode": "fill",
        "answers": {
            f"{i}:2": cell_ans(f"{n} loại", exact=[n, f"{n} loai", f"{n} giao tu"], multiline=False)
            for i, n in enumerate(vd2_nums, start=1)
        },
    }

    # ---------- HỆ THỐNG KIẾN THỨC 2.1 ----------
    u0 = units[0]["blocks"]
    c1_ans_2_1 = [
        "Là bộ NST mà trong tế bào NST tồn tại thành từng cặp tương đồng (giống nhau về hình thái và cấu trúc nhưng khác nhau về nguồn gốc)",
        "Là bộ NST mà trong tế bào NST tồn tại thành từng chiếc",
        "Là NST chỉ chứa các gene quy định tính trạng thường",
        "Là NST chứa gene quy định giới tính, ngoài ra còn chứa các gene quy định tính trạng thường",
        "Là 1 đoạn DNA chứa 147 cặp nucleotide quấn 1,7 vòng quanh 8 phân tử protein histone",
        "Là vị trí trên NST liên kết với tơ vô sắc để được rút về 2 cực của tế bào trong quá trình phân bào",
        "Là vùng đầu mút của NST, mang các trình tự lặp lại có vai trò bảo vệ NST khỏi bị phân huỷ bởi các enzyme, ngăn các NST dính vào nhau trong phân bào và có liên quan đến sự già hoá của tế bào",
        "Là NST (nhiễm sắc tử chị em) đang ở trạng thái đóng xoắn cực đại",
        "Là vị trí định vị của gene trên NST",
    ]
    u0[1]["interactive"] = {
        "id": "cd2-ks-2.1-c1",
        "mode": "fill",
        "answers": {f"{i}:2": cell_ans(v) for i, v in enumerate(c1_ans_2_1, start=1)},
    }
    u0[4]["exercise_group"] = {
        "id": "cd2-ks-2.1-c2a",
        "columns": 3,
        "title": "Điền chú thích cho hình A — Nguyên phân (1 → 9):",
        "items": [
            group_item("cd2-ks-2.1-c2a-1", "Số 1", "Kì trung gian", exact=["ki trung gian", "ky trung gian"]),
            group_item("cd2-ks-2.1-c2a-2", "Số 2", "Kì đầu", exact=["ki dau", "ky dau"]),
            group_item("cd2-ks-2.1-c2a-3", "Số 3", "Kì giữa", exact=["ki giua", "ky giua"]),
            group_item("cd2-ks-2.1-c2a-4", "Số 4", "Kì sau", exact=["ki sau", "ky sau"]),
            group_item("cd2-ks-2.1-c2a-5", "Số 5", "Kì cuối", exact=["ki cuoi", "ky cuoi"]),
            group_item("cd2-ks-2.1-c2a-6", "Số 6", "Nhiễm sắc thể", exact=["nhiem sac the", "nst"]),
            group_item("cd2-ks-2.1-c2a-7", "Số 7", "Tơ phân bào", exact=["to phan bao", "thoi phan bao", "to vo sac"]),
            group_item("cd2-ks-2.1-c2a-8", "Số 8", "Tâm động", exact=["tam dong"]),
            group_item("cd2-ks-2.1-c2a-9", "Số 9", "Trung tử", exact=["trung tu", "trung the"]),
        ],
    }
    u0[6]["exercise_group"] = {
        "id": "cd2-ks-2.1-c2b",
        "columns": 3,
        "title": "Điền chú thích cho hình B — Giảm phân (1 → 7):",
        "items": [
            group_item("cd2-ks-2.1-c2b-1", "Số 1", "Kì sau II", exact=["ki sau ii", "ky sau ii", "ki sau 2", "ky sau 2"]),
            group_item("cd2-ks-2.1-c2b-2", "Số 2", "Kì đầu I", exact=["ki dau i", "ky dau i", "ki dau 1", "ky dau 1"]),
            group_item("cd2-ks-2.1-c2b-3", "Số 3", "Kì cuối II", exact=["ki cuoi ii", "ky cuoi ii", "ki cuoi 2", "ky cuoi 2"]),
            group_item("cd2-ks-2.1-c2b-4", "Số 4", "Kì giữa II", exact=["ki giua ii", "ky giua ii", "ki giua 2", "ky giua 2"]),
            group_item("cd2-ks-2.1-c2b-5", "Số 5", "Kì sau I", exact=["ki sau i", "ky sau i", "ki sau 1", "ky sau 1"]),
            group_item("cd2-ks-2.1-c2b-6", "Số 6", "Kì giữa I", exact=["ki giua i", "ky giua i", "ki giua 1", "ky giua 1"]),
            group_item("cd2-ks-2.1-c2b-7", "Số 7", "Kì cuối I", exact=["ki cuoi i", "ky cuoi i", "ki cuoi 1", "ky cuoi 1"]),
        ],
    }
    u0[8]["exercise"] = ex_item(
        "cd2-ks-2.1-c2c", "cd2-ks-2.1-c2c",
        "- Nguyên phân: 1 lần nhân đôi, 1 lần phân bào → từ 1 tế bào 2n (Aa) tạo 2 tế bào con 2n (Aa) giống hệt tế bào mẹ.\n- Giảm phân: 1 lần nhân đôi, 2 lần phân bào liên tiếp (kì đầu I có tiếp hợp/trao đổi chéo; kì giữa I xếp 2 hàng; kì sau I phân li cặp NST tương đồng) → từ 1 tế bào 2n (Aa) tạo 4 tế bào con đơn bội n (2 A : 2 a) có bộ NST giảm đi một nửa.",
        mode="textarea",
        placeholder="Ghi kết luận điểm khác biệt giữa nguyên phân và giảm phân..."
    )
    u0[10]["exercise_group"] = {
        "id": "cd2-ks-2.1-c3",
        "columns": 2,
        "title": "Điền chú thích cho hình Câu 3 — Cặp NST tương đồng (1 → 7):",
        "items": [
            group_item("cd2-ks-2.1-c3-1", "Số 1", "Telomere", exact=["telomere", "vung dau mut"]),
            group_item("cd2-ks-2.1-c3-2", "Số 2", "Allele", exact=["allele", "alen"]),
            group_item("cd2-ks-2.1-c3-3", "Số 3", "Locus", exact=["locus", "locut"]),
            group_item("cd2-ks-2.1-c3-4", "Số 4", "Tâm động", exact=["tam dong"]),
            group_item("cd2-ks-2.1-c3-5", "Số 5", "Kiểu gene đồng hợp", exact=["kieu gene dong hop", "kieu gen dong hop", "dong hop"]),
            group_item("cd2-ks-2.1-c3-6", "Số 6", "Kiểu gene dị hợp", exact=["kieu gene di hop", "kieu gen di hop", "di hop"]),
            group_item("cd2-ks-2.1-c3-7", "Số 7", "Cặp NST tương đồng", exact=["cap nst tuong dong", "cap nhiem sac the tuong dong"]),
        ],
    }
    u0[14]["interactive"] = {
        "id": "cd2-ks-2.1-bt1",
        "mode": "fill",
        "answers": {
            "2:2": cell_ans("AA → 1A; Aa → 1A : 1a; aa → 1a"),
            "3:2": cell_ans("X^AX^A → 1X^A; X^AX^a → 1X^A : 1X^a; X^aX^a → 1X^a; X^AY → 1X^A : 1Y; X^aY → 1X^a : 1Y"),
            "4:2": cell_ans("XX → X; XY^A → 1X : 1Y^A; XY^a → 1X : 1Y^a"),
            "5:2": cell_ans("X^AX^A → 1X^A; X^AX^a → 1X^A : 1X^a; X^aX^a → 1X^a; X^AY^A → 1X^A : 1Y^A; X^AY^a → 1X^A : 1Y^a; X^aY^A → 1X^a : 1Y^A; X^aY^a → 1X^a : 1Y^a"),
            "7:2": cell_ans("AB/AB → 1AB; ab/ab → 1ab; Ab/Ab → 1Ab; aB/aB → 1aB; AB/Ab → 1AB : 1Ab; AB/aB → 1AB : 1aB; Ab/ab → 1Ab : 1ab; aB/ab → 1aB : 1ab; AB/ab → 1AB : 1ab; Ab/aB → 1Ab : 1aB"),
            "8:2": cell_ans("AABB → 1AB; aabb → 1ab; AAbb → 1Ab; aaBB → 1aB; AABb → 1AB : 1Ab; AaBB → 1AB : 1aB; Aabb → 1Ab : 1ab; aaBb → 1aB : 1ab; AaBb → 1AB : 1Ab : 1aB : 1ab"),
        },
    }

    # ---------- HỆ THỐNG KIẾN THỨC 2.2 ----------
    u1 = units[1]["blocks"]
    c1_ans_2_2 = [
        "Là những biến đổi trong cấu trúc của gene liên quan đến 1 hoặc 1 số cặp nucleotide",
        "Những biến đổi trong cấu trúc NST, làm thay đổi số lượng, thành phần gene hay trình tự sắp xếp của các gene trên NST",
        "Những biến đổi dẫn đến làm thay đổi số lượng NST trong tế bào",
        "Những biến đổi làm tăng hay giảm số lượng của 1 hoặc 1 vài chiếc NST",
        "Tế bào mang bộ NST của 1 loài, có thể là 3n (tam bội), 4n (tứ bội), 5n (ngũ bội)...",
        "Tế bào mang bộ NST của ít nhất 2 loài khác nhau",
        "Là những biến đổi liên quan đến vật chất di truyền, xảy ra ở gene (cấp độ phân tử) hoặc nhiễm sắc thể (cấp độ tế bào)",
        "Là loại biến dị phát sinh do sự tổ hợp lại vật chất di truyền của bố và mẹ",
        "Là các biến dị phát sinh do quá trình đột biến",
        "Là các biến dị tổ hợp phát sinh do sự tổ hợp lại vật chất di truyền của bố và mẹ trong quá trình giao phối",
        "Chọn lọc được những giống vật nuôi, cây trồng phù hợp với nhu cầu của con người",
        "Chọn lọc các sinh vật thích nghi với môi trường sống",
        "Là lai giữa hai loài khác nhau",
        "Là trường hợp số lượng NST trong tế bào tăng gấp đôi so với bình thường (ví dụ: giao tử n → giao tử 2n, tế bào 2n → tế bào 4n)",
    ]
    u1[1]["interactive"] = {
        "id": "cd2-ks-2.2-c1",
        "mode": "fill",
        "answers": {f"{i}:2": cell_ans(v) for i, v in enumerate(c1_ans_2_2, start=1)},
    }
    u1[3]["exercise_group"] = {
        "id": "cd2-ks-2.2-c2",
        "columns": 2,
        "title": "Xác định tên 7 dạng đột biến cấu trúc tương ứng với hình (1 → 7):",
        "items": [
            group_item("cd2-ks-2.2-c2-1", "Hình 1", "Đảo đoạn không chứa tâm động", exact=["dao doan khong chua tam dong"]),
            group_item("cd2-ks-2.2-c2-2", "Hình 2", "Chuyển đoạn trên 1 NST", exact=["chuyen doan tren 1 nst", "chuyen doan tren mot nst"]),
            group_item("cd2-ks-2.2-c2-3", "Hình 3", "Đảo đoạn chứa tâm động", exact=["dao doan chua tam dong"]),
            group_item("cd2-ks-2.2-c2-4", "Hình 4", "Mất đoạn", exact=["mat doan"]),
            group_item("cd2-ks-2.2-c2-5", "Hình 5", "Lặp đoạn", exact=["lap doan"]),
            group_item("cd2-ks-2.2-c2-6", "Hình 6", "Chuyển đoạn không tương hỗ", exact=["chuyen doan khong tuong ho"]),
            group_item("cd2-ks-2.2-c2-7", "Hình 7", "Chuyển đoạn tương hỗ", exact=["chuyen doan tuong ho"]),
        ],
    }
    u1[5]["exercise_group"] = {
        "id": "cd2-ks-2.2-c3",
        "columns": 2,
        "title": "Xác định tên 6 thể đột biến số lượng NST tương ứng với hình (1 → 6):",
        "items": [
            group_item("cd2-ks-2.2-c3-1", "Hình 1", "Thể tam bội (3n)", exact=["the tam boi", "the tam boi (3n)", "tam boi", "3n"]),
            group_item("cd2-ks-2.2-c3-2", "Hình 2", "Thể tứ bội (4n)", exact=["the tu boi", "the tu boi (4n)", "tu boi", "4n"]),
            group_item("cd2-ks-2.2-c3-3", "Hình 3", "Thể ba nhiễm (2n + 1)", exact=["the ba nhiem", "the ba", "the ba nhiem (2n+1)", "2n+1"]),
            group_item("cd2-ks-2.2-c3-4", "Hình 4", "Thể một nhiễm (2n − 1)", exact=["the mot nhiem", "the mot", "the mot nhiem (2n-1)", "2n-1"]),
            group_item("cd2-ks-2.2-c3-5", "Hình 5", "Thể bốn (2n + 2)", exact=["the bon", "the bon nhiem", "the bon (2n+2)", "2n+2"]),
            group_item("cd2-ks-2.2-c3-6", "Hình 6", "Thể không (2n − 2)", exact=["the khong", "the khong nhiem", "the khong (2n-2)", "2n-2"]),
        ],
    }
    c4_ans_2_2 = {
        "2:2": cell_ans("Chuyển vai dài của NST số 21 sang NST số 14"),
        "3:2": cell_ans("Mất đoạn vai ngắn NST số 5"),
        "4:2": cell_ans("Thể ba nhiễm 2n + 1: XXX", multiline=False),
        "5:2": cell_ans("Thể một nhiễm 2n − 1: OX (XO)", multiline=False),
        "6:2": cell_ans("Mất đoạn NST số 21", multiline=False),
        "7:2": cell_ans("Lặp đoạn trên cánh dài NST số 4"),
        "8:2": cell_ans("Thể ba nhiễm 2n + 1: thừa 1 chiếc NST số 13", multiline=False),
        "9:2": cell_ans("Thể ba nhiễm 2n + 1: XXY", multiline=False),
        "10:2": cell_ans("Mất đoạn dài NST số 11", multiline=False),
        "11:2": cell_ans("Thể ba nhiễm 2n + 1: XYY", multiline=False),
        "12:2": cell_ans("Lặp đoạn trên cánh ngắn của NST số 17"),
        "13:2": cell_ans("Thể ba nhiễm 2n + 1: thừa 1 chiếc NST số 18", multiline=False),
    }
    u1[7]["interactive"] = {"id": "cd2-ks-2.2-c4", "mode": "fill", "answers": c4_ans_2_2}

    u1[14]["interactive"] = {
        "id": "cd2-ks-2.2-vd1",
        "mode": "fill",
        "answers": {
            "1:2": cell_ans("AAaBbDd, AaaBbDd", multiline=False),
            "2:2": cell_ans("AaBBbDd, AaBbbDd", multiline=False),
            "3:2": cell_ans("AaBbDDDd, AaBbDDdd, AaBbDddd", multiline=False),
            "4:2": cell_ans("AAAaBbDd, AAaaBbDd, AaaaBbDd", multiline=False),
            "1:5": cell_ans("ABbDd, aBbDd", multiline=False),
            "2:5": cell_ans("AaBDd, AabDd", multiline=False),
            "3:5": cell_ans("AaBb", exact=["aabb"], multiline=False),
            "4:5": cell_ans("AaDd", exact=["aadd"], multiline=False),
        },
    }
    u1[18]["interactive"] = {
        "id": "cd2-ks-2.2-vd2",
        "mode": "fill",
        "answers": {
            "1:2": cell_ans("A", exact=["a"], multiline=False),
            "1:3": cell_ans("AA, O", exact=["aa,o", "aa,0", "aa va o"], multiline=False),
            "1:4": cell_ans("AA, A, O", exact=["aa,a,o", "aa,a,0"], multiline=False),
            "2:2": cell_ans("a", exact=["a"], multiline=False),
            "2:3": cell_ans("aa, O", exact=["aa,o", "aa,0"], multiline=False),
            "2:4": cell_ans("aa, a, O", exact=["aa,a,o", "aa,a,0"], multiline=False),
            "3:2": cell_ans("X^a", exact=["xa", "x^a"], multiline=False),
            "3:3": cell_ans("X^aX^a, O", exact=["xaxa,o", "x^ax^a,o"], multiline=False),
            "3:4": cell_ans("X^aX^a, X^a, O", exact=["xaxa,xa,o", "x^ax^a,x^a,o"], multiline=False),
            "4:2": cell_ans("X, Y", exact=["x,y"], multiline=False),
            "4:3": cell_ans("XY, O", exact=["xy,o", "xy,0"], multiline=False),
            "4:4": cell_ans("XX, YY, X, Y, O", exact=["xx,yy,x,y,o"], multiline=False),
            "5:2": cell_ans("AB, Ab, aB, ab", exact=["ab,ab,ab,ab"], multiline=False),
            "5:3": cell_ans("AaB, Aab, OB, Ob", multiline=False),
            "5:4": cell_ans("AAB, AAb, aaB, aab, AB, Ab, aB, ab, OB, Ob"),
        },
    }
    u1[23]["exercise"] = ex_item(
        "cd2-ks-2.2-bt2-vd1", "cd2-ks-2.2-bt2-vd1",
        "- Số kiểu gene của hợp tử lưỡng bội là 9 (3 × 3).\n- Số kiểu gene của hợp tử lệch bội là 12 (giao tử đực lệch bội AaB, Aab, OB, Ob × giao tử cái AB, Ab, aB, ab → 4 loại về cặp A [AAa, Aaa, A, a] × 3 loại về cặp B [BB, Bb, bb] = 12).",
        mode="textarea"
    )
    u1[24]["exercise"] = ex_item(
        "cd2-ks-2.2-bt2-vd2", "cd2-ks-2.2-bt2-vd2",
        "- Trong giảm phân II ở mẹ (X^AX^a), NST giới tính không phân li tạo giao tử X^AX^A, X^aX^a và O.\n- Bố (X^AY) giảm phân bình thường tạo giao tử X^A và Y.\n- Sự thụ tinh giữa giao tử X^A của bố với giao tử X^aX^a của mẹ tạo hợp tử con gái có kiểu gene X^AX^aX^a.",
        mode="textarea"
    )
    u1[30]["rows"][1][2] = ""  # Để học sinh tự điền đủ cả dòng 1 (hoặc điền đầy đủ AA, Aa, aa)
    u1[30]["interactive"] = {
        "id": "cd2-ks-2.2-bt3-vd",
        "mode": "fill",
        "answers": {
            "1:2": cell_ans("AA → A; Aa → 1A : 1a; aa → a", multiline=False),
            "2:2": cell_ans("AA → AA; Aa → Aa; aa → aa", multiline=False),
            "3:2": cell_ans("AAA, AAa, Aaa, aaa → không tạo giao tử bình thường", multiline=False),
            "4:2": cell_ans("AAAA → AA\nAAAa → 1AA : 1Aa\nAAaa → 1AA : 4Aa : 1aa\nAaaa → 1Aa : 1aa\naaaa → aa"),
        },
    }
    u1[33]["text"] = u1[33]["text"].replace("thụ tình", "thụ tinh")
    u1[34]["text"] = "(I) AAaa × Aaaa    (II) Aaaa × Aaaa    (III) AAaa × Aa    (IV) Aaaa × Aa"
    u1[35]["exercise_group"] = {
        "id": "cd2-ks-2.2-bt4-vd1",
        "columns": 1,
        "items": [
            group_item("cd2-ks-2.2-bt4-vd1-1", "(I) AAaa × Aaaa", "TLKG: 1 AAAa : 5 AAaa : 5 Aaaa : 1 aaaa — TLKH: 11 đỏ : 1 vàng"),
            group_item("cd2-ks-2.2-bt4-vd1-2", "(II) Aaaa × Aaaa", "TLKG: 1 AAaa : 2 Aaaa : 1 aaaa — TLKH: 3 đỏ : 1 vàng"),
            group_item("cd2-ks-2.2-bt4-vd1-3", "(III) AAaa × Aa", "TLKG: 1 AAA : 5 AAa : 5 Aaa : 1 aaa — TLKH: 11 đỏ : 1 vàng"),
            group_item("cd2-ks-2.2-bt4-vd1-4", "(IV) Aaaa × Aa", "TLKG: 1 AAa : 2 Aaa : 1 aaa — TLKH: 3 đỏ : 1 vàng"),
        ],
    }
    u1[36]["exercise"] = ex_item(
        "cd2-ks-2.2-bt4-vd2", "cd2-ks-2.2-bt4-vd2",
        "F2 có tỉ lệ 1190 đỏ : 108 vàng ≈ 11 đỏ : 1 vàng → P(F1): AAaa × Aa (tứ bội lai lưỡng bội).\n- Tỉ lệ kiểu gene F2: 1 AAA : 5 AAa : 5 Aaa : 1 aaa.\n- Tỉ lệ kiểu hình F2: 11 quả đỏ : 1 quả vàng.",
        mode="textarea"
    )

    save_topic(data, path)
    print("Updated chu_de_2.json")


# =====================================================================
# CHỦ ĐỀ 3
# =====================================================================
def enrich_chu_de_3():
    data, path = load_topic("chu_de_3.json")
    clean_old_interactive(data)

    units = data["knowledge_system"]["units"]

    # ---------- HỆ THỐNG KIẾN THỨC 3.1 ----------
    u0 = units[0]["blocks"]
    u0[0]["text"] = u0[0]["text"].replace("Đề nắm", "Để nắm").replace("nội dùng", "nội dung")
    c1_3_1 = [
        ("Là 1 đoạn của phân tử DNA mang thông tin quy định trình tự amino acid của chuỗi polypeptide hoặc trình tự nucleotide của RNA", "Gene quy định màu sắc hoa"),
        ("Các trạng thái khác nhau của cùng một gene", "Allele A quy định hoa đỏ, allele a quy định hoa trắng"),
        ("Là tổ hợp tất cả các gene trong tế bào của cơ thể sinh vật", "AA, Aa, aa"),
        ("Là kiểu gene chứa các allele có trạng thái giống nhau của cùng một gene", "AA, aa"),
        ("Là kiểu gene đồng hợp về tất cả các gene", "AA, aa"),
        ("Là kiểu gene chứa các allele có trạng thái khác nhau của cùng một gene", "Aa"),
        ("Là những đặc điểm về hình thái, cấu tạo và sinh lý riêng biệt của cơ thể sinh vật", "Màu sắc hoa, hình dạng quả, màu sắc hạt..."),
        ("Là kiểu hình do allele trội quy định và luôn được biểu hiện thành kiểu hình", "A quy định hoa đỏ → kiểu gene AA, Aa → hoa đỏ"),
        ("Là kiểu hình do allele lặn quy định và chỉ được biểu hiện ở cơ thể có kiểu gene đồng hợp lặn", "Kiểu gene aa → hoa trắng"),
        ("Là hiện tượng hạt phấn thụ phấn cho nhụy của cùng một hoa hoặc cho nhụy của các hoa khác cùng cây", "Ở đậu Hà Lan, hạt phấn chỉ thụ phấn cho nhụy của cùng một hoa"),
        ("Là hiện tượng hạt phấn của hoa này thụ phấn cho hoa ở cây khác", "Hạt phấn của cây A thụ phấn cho cây B"),
        ("Giao phối giữa các cá thể có cùng huyết thống hoặc có họ hàng gần nhau", "Những con gà cùng bố mẹ giao phối với nhau"),
        ("Là phép lai đổi vai trò của bố và mẹ", "Lai thuận: ♀AA × ♂aa; Lai nghịch: ♀aa × ♂AA"),
        ("Lai giữa cá thể có kiểu hình trội (chưa biết kiểu gene) với cá thể đồng hợp lặn", "AA × aa hoặc Aa × aa"),
    ]
    ans_map = {}
    for i, (meaning, eg) in enumerate(c1_3_1, start=1):
        ans_map[f"{i}:2"] = cell_ans(meaning)
        ans_map[f"{i}:3"] = cell_ans(eg, multiline=len(eg) > 36)
    u0[1]["interactive"] = {"id": "cd3-ks-3.1-c1", "mode": "fill", "answers": ans_map}

    # Câu 2: Giao tử (ĐÁP ÁN 1.pdf trang 293)
    u0[3]["interactive"] = {
        "id": "cd3-ks-3.1-c2-tbl",
        "mode": "fill",
        "answers": {
            "1:2": cell_ans("A", exact=["a"], multiline=False),
            "2:2": cell_ans("a", exact=["a"], multiline=False),
            "3:2": cell_ans("A, a", exact=["a,a", "1a:1a"], multiline=False),
            "4:2": cell_ans("AB", exact=["ab"], multiline=False),
            "5:2": cell_ans("Ab", exact=["ab"], multiline=False),
            "6:2": cell_ans("aB", exact=["ab"], multiline=False),
            "1:5": cell_ans("ab", exact=["ab"], multiline=False),
            "2:5": cell_ans("Ab, ab", exact=["ab,ab", "1ab:1ab"], multiline=False),
            "3:5": cell_ans("aB, ab", exact=["ab,ab", "1ab:1ab"], multiline=False),
            "4:5": cell_ans("AB, aB", exact=["ab,ab", "1ab:1ab"], multiline=False),
            "5:5": cell_ans("AB, Ab", exact=["ab,ab", "1ab:1ab"], multiline=False),
            "6:5": cell_ans("AB, Ab, aB, ab", multiline=False),
        },
    }
    # Lưu ý: giữ case-sensitive phân biệt A/a ở đây → dùng compare cho bảng giao tử chữ hoa/thường để không chấm nhầm Ab vs aB
    for k, v in u0[3]["interactive"]["answers"].items():
        v["grade_type"] = "compare"
        v.pop("exact", None)

    u0[4]["text"] = u0[4]["text"].replace("cá kiểu gene", "các kiểu gene")
    u0[5]["exercise"] = ex_item("cd3-ks-3.1-c2-dh", "cd3-ks-3.1-c2-list", "AA, aa, AABB, AAbb, aaBB, aabb", mode="input")
    u0[6]["exercise"] = ex_item("cd3-ks-3.1-c2-dh1", "cd3-ks-3.1-c2-list", "Aa, Aabb, aaBb, AaBB, AABb", mode="input")
    u0[7]["exercise"] = ex_item("cd3-ks-3.1-c2-dh2", "cd3-ks-3.1-c2-list", "AaBb", mode="input", exact=["aabb"])

    # Câu 3: Bảng 1 cặp tính trạng (ĐÁP ÁN 1.pdf trang 294)
    u0[8]["text"] = u0[8]["text"].replace("sờ đồ lai", "sơ đồ lai")
    u0[14]["text"] = u0[14]["text"].replace("dể xác định", "để xác định")
    # Gộp dòng trùng số 10 ở bảng 1 cặp tính trạng (r4 và r5 giống nhau cột bên phải)
    if len(u0[15]["rows"]) == 7 and u0[15]["rows"][5][3] == "10":
        u0[15]["rows"][5][3] = ""
        u0[15]["rows"][5][4] = ""
        u0[15]["rows"][5][5] = ""
    u0[15]["interactive"] = {
        "id": "cd3-ks-3.1-c3-1",
        "mode": "fill",
        "answers": {
            "1:2": cell_ans("4", exact=["4"], multiline=False),
            "2:2": cell_ans("2", exact=["2"], multiline=False),
            "3:2": cell_ans("3 : 1", exact=["3:1"], multiline=False),
            "4:2": cell_ans("3/4", exact=["3/4", "75%", "0,75", "0.75"], multiline=False),
            "5:2": cell_ans("1/4", exact=["1/4", "25%", "0,25", "0.25"], multiline=False),
            "6:2": cell_ans("3", exact=["3"], multiline=False),
            "1:5": cell_ans("1 : 2 : 1", exact=["1:2:1"], multiline=False),
            "2:5": cell_ans("1/2", exact=["1/2", "50%", "0,5", "0.5"], multiline=False),
            "3:5": cell_ans("1/2", exact=["1/2", "50%", "0,5", "0.5"], multiline=False),
            "4:5": cell_ans("1/3", exact=["1/3"], multiline=False),
            "6:5": cell_ans("3/4", exact=["3/4", "75%", "0,75", "0.75"], multiline=False),
        },
    }

    # Câu 3: Bảng 2 cặp tính trạng (ĐÁP ÁN 1.pdf trang 294)
    c3_2_rows = [
        ("16", ["16"], "4 × 4"),
        ("4", ["4"], "2 × 2"),
        ("9 : 3 : 3 : 1", ["9:3:3:1"], "(3 : 1) × (3 : 1)"),
        ("9/16", ["9/16", "56,25%", "0,5625"], "TT = 3/4 × 3/4 = 9/16"),
        ("3/8", ["3/8", "6/16", "37,5%", "0,375"], "TL + LT = (3/4 × 1/4) + (1/4 × 3/4) = 3/8"),
        ("1/16", ["1/16", "6,25%", "0,0625"], "LL = 1/4 × 1/4 = 1/16"),
        ("7/16", ["7/16", "43,75%", "0,4375"], "1 − TT = 1 − 9/16 = 7/16"),
        ("9", ["9"], "3 × 3 = 9"),
        ("4 : 2 : 2 : 2 : 2 : 1 : 1 : 1 : 1", ["4:2:2:2:2:1:1:1:1", "1:2:1:2:4:2:1:2:1"], "(1 : 2 : 1) × (1 : 2 : 1)"),
        ("1/4", ["1/4", "25%", "0,25", "0.25"], "1/2 × 1/2 = 1/4"),
        ("3/4", ["3/4", "75%", "0,75", "0.75"], "1 − ĐH = 1 − 1/4 = 3/4"),
        ("1/2", ["1/2", "50%", "0,5", "0.5"], "ĐH, DH + DH, ĐH = (1/2 × 1/2) + (1/2 × 1/2) = 1/2"),
        ("1/4", ["1/4", "25%", "0,25", "0.25"], "DH, DH = 1/2 × 1/2 = 1/4"),
        ("3/8", ["3/8", "6/16", "37,5%", "0,375"], "C(4, 2) / 2^4 = 6/16 = 3/8"),
    ]
    ans_map = {}
    for i, (res, ex, method) in enumerate(c3_2_rows, start=1):
        ans_map[f"{i}:2"] = cell_ans(res, exact=ex, multiline=False)
        ans_map[f"{i}:3"] = cell_ans(method, multiline=False)
    u0[26]["interactive"] = {"id": "cd3-ks-3.1-c3-2", "mode": "fill", "answers": ans_map}

    # 1. Bài tập quy luật phân li — Ví dụ 1..4 (ĐÁP ÁN 1.pdf trang 294)
    u0[36]["exercise"] = ex_item("cd3-ks-3.1-pl-vd1-1", "cd3-ks-3.1-pl-vd1", "Tỉ lệ kiểu gene: 1 AA : 2 Aa : 1 aa (1 : 2 : 1); Tỉ lệ kiểu hình: 3 quả đỏ : 1 quả vàng (3 : 1)", mode="input")
    u0[37]["exercise"] = ex_item("cd3-ks-3.1-pl-vd1-2", "cd3-ks-3.1-pl-vd1", "1/2 (50%)", mode="input", exact=["1/2", "50%", "0,5", "0.5"])
    u0[38]["exercise"] = ex_item("cd3-ks-3.1-pl-vd1-3", "cd3-ks-3.1-pl-vd1", "1/3", mode="input", exact=["1/3"])
    u0[39]["exercise"] = ex_item("cd3-ks-3.1-pl-vd1-4", "cd3-ks-3.1-pl-vd1", "- TH1: AA × aa → Fb: 100% Aa (100% quả đỏ).\n- TH2: Aa × aa → Fb: 1 Aa : 1 aa (1 quả đỏ : 1 quả vàng).", mode="textarea")

    u0[49]["exercise"] = ex_item("cd3-ks-3.1-pl-vd2-1", "cd3-ks-3.1-pl-vd2", "Aa × Aa", mode="input")
    u0[50]["exercise"] = ex_item("cd3-ks-3.1-pl-vd2-2", "cd3-ks-3.1-pl-vd2", "Aa × Aa hoặc Aa × aa", mode="input")
    u0[51]["exercise"] = ex_item("cd3-ks-3.1-pl-vd2-3", "cd3-ks-3.1-pl-vd2", "AA × AA, AA × Aa, AA × aa (đồng loạt hoa đỏ) hoặc aa × aa (đồng loạt hoa trắng)", mode="input")

    u0[57]["exercise"] = ex_item("cd3-ks-3.1-pl-vd3-1", "cd3-ks-3.1-pl-vd3", "3/4", mode="input", exact=["3/4", "75%", "0,75", "0.75"])
    u0[58]["exercise"] = ex_item("cd3-ks-3.1-pl-vd3-2", "cd3-ks-3.1-pl-vd3", "3/8", mode="input", exact=["3/8", "37,5%", "0,375", "0.375"])
    u0[59]["exercise"] = ex_item("cd3-ks-3.1-pl-vd3-3", "cd3-ks-3.1-pl-vd3", "9/64", mode="input", exact=["9/64"])
    u0[60]["exercise"] = ex_item("cd3-ks-3.1-pl-vd3-4", "cd3-ks-3.1-pl-vd3", "3/32", mode="input", exact=["3/32"])
    u0[61]["exercise"] = ex_item("cd3-ks-3.1-pl-vd3-5", "cd3-ks-3.1-pl-vd3", "3/32", mode="input", exact=["3/32"])

    u0[68]["text"] = u0[68]["text"].replace("tóc trẳng", "tóc thẳng").replace("tốc xoăn", "tóc xoăn").replace("bồ mẹ", "bố mẹ").replace("bồ tóc xoăn", "bố tóc xoăn")
    u0[68]["exercise"] = ex_item("cd3-ks-3.1-pl-vd4", "cd3-ks-3.1-pl-vd4", "5/12 (Chồng 2/3 Aa, vợ 100% Aa → xác suất sinh con gái tóc xoăn = 1/2 × (1 − 2/3 × 1/4) = 5/12)", mode="input", exact=["5/12"])

    # 2. Bài tập quy luật phân li độc lập — Ví dụ 1, 2, 3
    u0[72]["text"] = u0[72]["text"].replace("quả bầu dụC", "quả bầu dục").replace("kiểu hinh", "kiểu hình")
    u0[73]["hidden_by_group"] = True
    u0[74]["hidden_by_group"] = True
    u0[72]["exercise_group"] = {
        "id": "cd3-ks-3.1-pldl-vd1",
        "columns": 2,
        "items": [
            group_item("cd3-ks-3.1-pldl-vd1-1", "1. AABB × aabb", "TLKG: 100% AaBb — TLKH: 100% đỏ, tròn"),
            group_item("cd3-ks-3.1-pldl-vd1-2", "2. AABB × aaBb", "TLKG: 1 AaBB : 1 AaBb — TLKH: 100% đỏ, tròn"),
            group_item("cd3-ks-3.1-pldl-vd1-3", "3. AABB × AaBb", "TLKG: 1 AABB : 1 AABb : 1 AaBB : 1 AaBb — TLKH: 100% đỏ, tròn"),
            group_item("cd3-ks-3.1-pldl-vd1-4", "4. AaBB × AaBB", "TLKG: 1 AABB : 2 AaBB : 1 aaBB — TLKH: 3 đỏ, tròn : 1 vàng, tròn"),
            group_item("cd3-ks-3.1-pldl-vd1-5", "5. AABb × AaBb", "TLKG: 1 AABB : 2 AABb : 1 AAbb : 1 AaBB : 2 AaBb : 1 Aabb — TLKH: 3 đỏ, tròn : 1 đỏ, bầu dục"),
            group_item("cd3-ks-3.1-pldl-vd1-6", "6. AaBb × AaBb", "TLKG: (1:2:1)(1:2:1) = 4:2:2:2:2:1:1:1:1 — TLKH: 9 đỏ, tròn : 3 đỏ, bầu dục : 3 vàng, tròn : 1 vàng, bầu dục"),
        ],
    }

    # Ví dụ 2 (21 ý từ ĐÁP ÁN 1.pdf trang 294–295)
    u0[83]["text"] = u0[83]["text"].replace("hoa dỏ", "hoa đỏ").replace("quy dịnh", "quy định").replace("quy dinh", "quy định").replace("Biết răng", "Biết rằng")
    u0[91]["text"] = u0[91]["text"].replace("2,6.", "2.6.")
    u0[96]["text"] = u0[96]["text"].replace("mang l allele", "mang 1 allele").rstrip(".")
    u0[103]["text"] = u0[103]["text"].replace("có l cặp", "có 1 cặp")
    vd2_pldl = [
        (84, "1", "16", ["16"]),
        (86, "2-1", "12", ["12"]),
        (87, "2-2", "2 : 2 : 2 : 2 : 1 : 1 : 1 : 1 : 1 : 1 : 1 : 1", ["2:2:2:2:1:1:1:1:1:1:1:1"]),
        (88, "2-3", "1/8", ["1/8", "12,5%", "0,125", "0.125"]),
        (89, "2-4", "0", ["0", "0%"]),
        (90, "2-5", "0", ["0", "0%"]),
        (91, "2-6", "7/8", ["7/8", "87,5%", "0,875", "0.875"]),
        (92, "2-7", "3/8", ["3/8", "37,5%", "0,375", "0.375"]),
        (93, "2-8", "3/8", ["3/8", "37,5%", "0,375", "0.375"]),
        (94, "2-9", "1/8", ["1/8", "12,5%", "0,125", "0.125"]),
        (95, "2-10", "3/8", ["3/8", "37,5%", "0,375", "0.375"]),
        (96, "2-11", "1/16", ["1/16", "6,25%", "0,0625", "0.0625"]),
        (97, "2-12", "1/8", ["1/8", "12,5%", "0,125", "0.125"]),
        (99, "3-1", "4", ["4"]),
        (100, "3-2", "3 : 3 : 1 : 1", ["3:3:1:1"]),
        (101, "3-3", "3/8", ["3/8", "37,5%", "0,375", "0.375"]),
        (102, "3-4", "0", ["0", "0%"]),
        (103, "3-5", "1/2", ["1/2", "50%", "0,5", "0.5"]),
        (104, "3-6", "1/8", ["1/8", "12,5%", "0,125", "0.125"]),
        (105, "3-7", "3/8", ["3/8", "37,5%", "0,375", "0.375"]),
        (106, "3-8", "1/8", ["1/8", "12,5%", "0,125", "0.125"]),
    ]
    for bidx, code, ans, ex in vd2_pldl:
        u0[bidx]["exercise"] = ex_item(f"cd3-ks-3.1-pldl-vd2-{code}", "cd3-ks-3.1-pldl-vd2", ans, mode="input", exact=ex)

    # Ví dụ 3 (3 trường hợp)
    u0[112]["text"] = u0[112]["text"].replace("quả bầu dụC", "quả bầu dục").replace("chưa ro", "chưa rõ")
    u0[113]["text"] = "1. Trường hợp 1: F1 thu được 3 đỏ, tròn : 3 đỏ, bầu dục : 1 vàng, tròn : 1 vàng, bầu dục"
    u0[114]["text"] = "2. Trường hợp 2: F1 thu được 1 đỏ, tròn : 1 đỏ, bầu dục : 1 vàng, tròn : 1 vàng, bầu dục"
    u0[115]["text"] = "3. Trường hợp 3: F1 thu được 9 đỏ, tròn : 3 đỏ, bầu dục : 3 vàng, tròn : 1 vàng, bầu dục"
    u0[113]["exercise"] = ex_item("cd3-ks-3.1-pldl-vd3-1", "cd3-ks-3.1-pldl-vd3", "P: AaBb (đỏ, tròn) × Aabb (đỏ, bầu dục)", mode="input")
    u0[114]["exercise"] = ex_item("cd3-ks-3.1-pldl-vd3-2", "cd3-ks-3.1-pldl-vd3", "P: AaBb (đỏ, tròn) × aabb (vàng, bầu dục) hoặc Aabb (đỏ, bầu dục) × aaBb (vàng, tròn)", mode="input")
    u0[115]["exercise"] = ex_item("cd3-ks-3.1-pldl-vd3-3", "cd3-ks-3.1-pldl-vd3", "P: AaBb (đỏ, tròn) × AaBb (đỏ, tròn)", mode="input")

    # ---------- HỆ THỐNG KIẾN THỨC 3.2 ----------
    u1 = units[1]["blocks"]
    c1_ans_3_2 = [
        "Là hiện tượng allele trội át chế hoàn toàn sự biểu hiện của allele lặn khi cả hai allele cùng xuất hiện trong một kiểu gene",
        "Là hiện tượng tương tác giữa các allele của cùng một gene, trong đó một allele trội không át chế hoàn toàn sự biểu hiện của allele lặn → thể dị hợp biểu hiện thành kiểu hình trung gian giữa trội và lặn",
        "Là hiện tượng cả 2 allele khác nhau của cùng một gene cùng biểu hiện thành kiểu hình trên cơ thể",
        "Là một gene có nhiều hơn 2 allele",
        "Là gene chi phối nhiều tính trạng",
        "Là sự tác động qua lại giữa các sản phẩm của các gene allele để hình thành 1 tính trạng",
        "Là sự tác động qua lại giữa các sản phẩm của các gene không allele để hình thành 1 tính trạng",
        "Là hiện tượng các gene trội không allele cùng tác động quy định kiểu hình mới",
        "Là hiện tượng 1 gene sẽ kìm hãm sự biểu hiện của gene không allele khác",
        "Là trường hợp mỗi gene trội hoặc lặn của các gene không allele đều đóng góp một phần như nhau vào sự biểu hiện tính trạng",
        "Còn được gọi là tính trạng đa gene và chịu ảnh hưởng nhiều bởi sự tác động của môi trường",
        "Là tính trạng do 1 hoặc vài gene quy định và ít chịu ảnh hưởng bởi sự tác động của môi trường",
    ]
    u1[1]["interactive"] = {
        "id": "cd3-ks-3.2-c1",
        "mode": "fill",
        "answers": {f"{i}:2": cell_ans(v) for i, v in enumerate(c1_ans_3_2, start=1)},
    }

    # Câu 2.1: Bảng tương tác gene không allele (ĐÁP ÁN 1.pdf trang 296–297)
    u1[4]["rows"][1][3] = "AaBb × AaBb"  # sửa lỗi chính tả AaBbb
    c21_data = [
        (3, "Át chế trội", "12 trắng : 3 hồng : 1 vàng", "2 trắng : 1 hồng : 1 vàng", "4 trắng : 3 hồng : 1 vàng"),
        (4, "Cộng gộp", "15 đỏ : 1 trắng", "3 đỏ : 1 trắng", "7 đỏ : 1 trắng"),
        (5, "Bổ trợ", "9 đỏ : 7 trắng", "1 đỏ : 3 trắng", "3 đỏ : 5 trắng"),
        (6, "Át chế lặn", "9 đỏ : 3 hồng : 4 trắng", "1 đỏ : 1 hồng : 2 trắng", "3 đỏ : 1 hồng : 4 trắng"),
        (7, "Át chế trội", "13 trắng : 3 vàng", "3 trắng : 1 vàng", "5 trắng : 3 vàng"),
        (8, "Bổ trợ", "9 đỏ : 6 vàng : 1 trắng", "1 đỏ : 2 vàng : 1 trắng", "3 đỏ : 4 vàng : 1 trắng"),
        (9, "Cộng gộp", "1: 140 cm; 4: 130 cm; 6: 120 cm; 4: 110 cm; 1: 100 cm", "1: 120 cm; 2: 110 cm; 1: 100 cm", "1: 130 cm; 3: 120 cm; 3: 110 cm; 1: 100 cm"),
    ]
    ans_map = {}
    for r, kind, p1, p2, p3 in c21_data:
        ans_map[f"{r}:2"] = cell_ans(kind, multiline=False)
        ans_map[f"{r}:3"] = cell_ans(p1, multiline=(r == 9))
        ans_map[f"{r}:4"] = cell_ans(p2, multiline=(r == 9))
        ans_map[f"{r}:5"] = cell_ans(p3, multiline=(r == 9))
    u1[4]["interactive"] = {"id": "cd3-ks-3.2-c2-1", "mode": "fill", "header_rows": 2, "answers": ans_map}

    # Câu 2.2: Tỉ lệ mở rộng từ AaBb × AaBb (ĐÁP ÁN 1.pdf trang 297)
    u1[6]["exercise_group"] = {
        "id": "cd3-ks-3.2-c2-2",
        "columns": 2,
        "title": "Điền 5 cột tỉ lệ mở rộng và loại tương tác tương ứng trên hình:",
        "items": [
            group_item("cd3-ks-3.2-c2-2-1", "Cột 1", "9/16 : 3/16 : 4/16 — Át chế lặn"),
            group_item("cd3-ks-3.2-c2-2-2", "Cột 2", "12/16 : 3/16 : 1/16 — Át chế trội"),
            group_item("cd3-ks-3.2-c2-2-3", "Cột 3", "9/16 : 7/16 — Bổ trợ"),
            group_item("cd3-ks-3.2-c2-2-4", "Cột 4", "9/16 : 6/16 : 1/16 — Bổ trợ"),
            group_item("cd3-ks-3.2-c2-2-5", "Cột 5", "15/16 : 1/16 — Cộng gộp"),
        ],
    }

    # 1. Trội không hoàn toàn (ĐÁP ÁN 1.pdf trang 298)
    u1[10]["text"] = u1[10]["text"].replace("hoàn tòan", "hoàn toàn")
    u1[10]["exercise"] = ex_item(
        "cd3-ks-3.2-tkht-vd1", "cd3-ks-3.2-tkht-vd1",
        "Quy ước: AA → kiểu hình trội (T), Aa → trung gian (TG), aa → lặn (L).\n6 phép lai:\n- AA × AA → F1: 1 AA (100% T)\n- AA × Aa → F1: 1 AA : 1 Aa (1 T : 1 TG)\n- AA × aa → F1: 1 Aa (100% TG)\n- Aa × aa → F1: 1 Aa : 1 aa (1 TG : 1 L)\n- Aa × Aa → F1: 1 AA : 2 Aa : 1 aa (1 T : 2 TG : 1 L)\n- aa × aa → F1: 1 aa (100% L)",
        mode="textarea"
    )
    u1[11]["exercise"] = ex_item(
        "cd3-ks-3.2-tkht-vd2", "cd3-ks-3.2-tkht-vd2",
        "Ptc: AABB (xanh, trơn) × aabb (vàng, nhăn) → F1: 100% AaBb (tím, trơn).\nF1 × F1: AaBb × AaBb → F2:\n- Tỉ lệ kiểu hình: 3 xanh, trơn : 1 xanh, nhăn : 6 tím, trơn : 2 tím, nhăn : 3 vàng, trơn : 1 vàng, nhăn.\n- Tỉ lệ kiểu gene: 1 AABB : 2 AABb : 1 AAbb : 2 AaBB : 4 AaBb : 2 Aabb : 1 aaBB : 2 aaBb : 1 aabb.",
        mode="textarea"
    )

    # 2. Gene đa allele — Ví dụ 1, 2, 3 (ĐÁP ÁN 1.pdf trang 298–299)
    u1[15]["exercise"] = ex_item("cd3-ks-3.2-da-vd1-1", "cd3-ks-3.2-da-vd1", "Nhóm máu A: I^AI^A, I^AI^O; Nhóm máu B: I^BI^B, I^BI^O; Nhóm máu AB: I^AI^B; Nhóm máu O: I^OI^O", mode="input")
    u1[16]["exercise"] = ex_item("cd3-ks-3.2-da-vd1-2", "cd3-ks-3.2-da-vd1", "Máu A hoặc máu O", mode="input")
    u1[17]["exercise"] = ex_item("cd3-ks-3.2-da-vd1-3", "cd3-ks-3.2-da-vd1", "P: I^AI^O × I^BI^O", mode="input")

    u1[20]["exercise"] = ex_item("cd3-ks-3.2-da-vd2-1", "cd3-ks-3.2-da-vd2", "- Hoa đỏ: C^rC^r, C^rC^p, C^rC^y\n- Hoa tím: C^pC^p, C^pC^y\n- Hoa vàng: C^yC^y", mode="textarea")
    u1[21]["exercise"] = ex_item(
        "cd3-ks-3.2-da-vd2-2", "cd3-ks-3.2-da-vd2",
        "Đỏ × Tím có 6 sơ đồ lai:\n1. C^rC^r × C^pC^p → 1 C^rC^p (100% đỏ)\n2. C^rC^r × C^pC^y → 1 C^rC^p : 1 C^rC^y (100% đỏ)\n3. C^rC^p × C^pC^p → 1 C^rC^p : 1 C^pC^p (1 đỏ : 1 tím)\n4. C^rC^p × C^pC^y → 1 C^rC^p : 1 C^rC^y : 1 C^pC^p : 1 C^pC^y (1 đỏ : 1 tím)\n5. C^rC^y × C^pC^p → 1 C^rC^p : 1 C^pC^y (1 đỏ : 1 tím)\n6. C^rC^y × C^pC^y → 1 C^rC^p : 1 C^rC^y : 1 C^pC^y : 1 C^yC^y (2 đỏ : 1 tím : 1 vàng)",
        mode="textarea"
    )
    u1[22]["exercise"] = ex_item("cd3-ks-3.2-da-vd2-3", "cd3-ks-3.2-da-vd2", "21 phép lai (6 × 7 / 2 = 21)", mode="input", exact=["21", "21 phep lai"])

    u1[26]["exercise"] = ex_item("cd3-ks-3.2-da-vd3-1", "cd3-ks-3.2-da-vd3", "A1 (nâu) > A2 (đỏ) > A3 (vàng) > A4 (trắng)", mode="input")
    u1[27]["exercise"] = ex_item("cd3-ks-3.2-da-vd3-2", "cd3-ks-3.2-da-vd3", "- Nâu: A1A1, A1A2, A1A3, A1A4\n- Đỏ: A2A2, A2A3, A2A4\n- Vàng: A3A3, A3A4\n- Trắng: A4A4", mode="textarea")
    u1[28]["exercise"] = ex_item("cd3-ks-3.2-da-vd3-3", "cd3-ks-3.2-da-vd3", "6 phép lai (♂ A1A1 × 6 kiểu gene cái màu khác)", mode="input", exact=["6", "6 phep lai"])
    u1[29]["exercise"] = ex_item("cd3-ks-3.2-da-vd3-4", "cd3-ks-3.2-da-vd3", "1 nâu : 1 vàng hoặc 2 nâu : 1 vàng : 1 trắng", mode="input")

    # 3. Tương tác không allele — Ví dụ 1, 2 (ĐÁP ÁN 1.pdf trang 299)
    u1[38]["exercise"] = ex_item("cd3-ks-3.2-tt-vd1-1", "cd3-ks-3.2-tt-vd1", "Số loại kiểu gene: 9.\nTỉ lệ từng kiểu gene: 4 AaBb : 2 AABb : 2 AaBB : 2 Aabb : 2 aaBb : 1 AABB : 1 AAbb : 1 aaBB : 1 aabb", mode="textarea")
    u1[39]["exercise"] = ex_item("cd3-ks-3.2-tt-vd1-2", "cd3-ks-3.2-tt-vd1", "1/2 (50%)", mode="input", exact=["1/2", "50%", "0,5", "0.5", "8/16"])
    u1[40]["exercise"] = ex_item("cd3-ks-3.2-tt-vd1-3", "cd3-ks-3.2-tt-vd1", "1/3", mode="input", exact=["1/3"])
    u1[41]["exercise"] = ex_item("cd3-ks-3.2-tt-vd1-4", "cd3-ks-3.2-tt-vd1", "AaBb × aabb → Fa: 1 AaBb : 1 Aabb : 1 aaBb : 1 aabb (2 đen : 1 nâu : 1 vàng)", mode="input")

    u1[51]["text"] = u1[51]["text"].replace("kiểu kiểu genen kiểu hình", "kiểu gene, kiểu hình")
    u1[51]["exercise"] = ex_item("cd3-ks-3.2-tt-vd2-1", "cd3-ks-3.2-tt-vd2", "Cây đem lai với F1 là cây quả bầu dục, kiểu gene Aabb hoặc aaBb", mode="input")
    u1[52]["exercise"] = ex_item("cd3-ks-3.2-tt-vd2-2", "cd3-ks-3.2-tt-vd2", "P: AaBb (quả tròn) × aabb (quả dài) hoặc P: Aabb (quả bầu dục) × aaBb (quả bầu dục)", mode="input")

    save_topic(data, path)
    print("Updated chu_de_3.json")


# =====================================================================
# CHỦ ĐỀ 4
# =====================================================================
def enrich_chu_de_4():
    data, path = load_topic("chu_de_4.json")
    clean_old_interactive(data)

    lessons = data["lessons"]
    units = data["knowledge_system"]["units"]

    # ---------- LÝ THUYẾT 4.1: Sơ đồ lai phép lai thuận / nghịch ----------
    s5_41 = lessons[0]["sections"][5]["blocks"]
    s5_41[2]["interactive"] = {
        "id": "cd4-th-4.1-sdl",
        "mode": "fill",
        "answers": {
            "1:0": cell_ans(
                "Ptc: ♀ X^AX^A (mắt đỏ) × ♂ X^aY (mắt trắng)\nGp: X^A ; X^a, Y\nF1: 1 X^AX^a (♀ mắt đỏ) : 1 X^AY (♂ mắt đỏ) — 100% mắt đỏ\nF1 × F1: ♀ X^AX^a × ♂ X^AY\nF2: 1 X^AX^A : 1 X^AX^a : 1 X^AY : 1 X^aY\nTLKH: 2 ♀ mắt đỏ : 1 ♂ mắt đỏ : 1 ♂ mắt trắng (3 đỏ : 1 trắng)",
                multiline=True
            ),
            "1:1": cell_ans(
                "Ptc: ♀ X^aX^a (mắt trắng) × ♂ X^AY (mắt đỏ)\nGp: X^a ; X^A, Y\nF1: 1 X^AX^a (♀ mắt đỏ) : 1 X^aY (♂ mắt trắng)\nF1 × F1: ♀ X^AX^a × ♂ X^aY\nF2: 1 X^AX^a : 1 X^aX^a : 1 X^AY : 1 X^aY\nTLKH: 1 ♀ mắt đỏ : 1 ♀ mắt trắng : 1 ♂ mắt đỏ : 1 ♂ mắt trắng",
                multiline=True
            ),
        },
    }

    # ---------- LÝ THUYẾT 4.2: 2 Sơ đồ lai Liên kết gene & Hoán vị gene ----------
    s2_42 = lessons[1]["sections"][2]["blocks"]
    s2_42[3]["rows"] = [
        ["Yêu cầu", "Hoàn thành sơ đồ lai Liên kết gene (Morgan)"],
        ["Sơ đồ lai", "Ptc: Thân xám, cánh dài × Thân đen, cánh cụt\nGp: ...\nF1: ...\nCon ♂ F1 lai phân tích → GF1 → Fa: ..."],
    ]
    s2_42[3]["interactive"] = {
        "id": "cd4-th-4.2-sdl-lk",
        "mode": "fill",
        "answers": {
            "1:1": cell_ans(
                "Ptc: BV/BV (thân xám, cánh dài) × bv/bv (thân đen, cánh cụt)\nGp: BV ; bv\nF1: 100% BV/bv (thân xám, cánh dài)\nLai phân tích ♂ F1: ♂ BV/bv × ♀ bv/bv\nGF1: (1 BV : 1 bv) ; bv\nFa: 1 BV/bv (thân xám, cánh dài) : 1 bv/bv (thân đen, cánh cụt)",
                multiline=True
            ),
        },
    }

    s5_42 = lessons[1]["sections"][5]["blocks"]
    s5_42[11]["rows"] = [
        ["Yêu cầu", "Hoàn thành sơ đồ lai Hoán vị gene (Morgan, f = 17%)"],
        ["Sơ đồ lai", "Ptc: Thân xám, cánh dài × Thân đen, cánh cụt\nGp: ...\nF1: ...\nCon ♀ F1 lai phân tích (f = 17%) → GF1 → Fa: ..."],
    ]
    s5_42[11]["interactive"] = {
        "id": "cd4-th-4.2-sdl-hv",
        "mode": "fill",
        "answers": {
            "1:1": cell_ans(
                "Ptc: BV/BV (thân xám, cánh dài) × bv/bv (thân đen, cánh cụt)\nGp: BV ; bv\nF1: 100% BV/bv (thân xám, cánh dài)\nLai phân tích ♀ F1 (f = 17%): ♀ BV/bv × ♂ bv/bv\nGF1: (0,415 BV : 0,415 bv : 0,085 Bv : 0,085 bV) ; 1 bv\nFa: 41,5% BV/bv (xám, dài) : 41,5% bv/bv (đen, cụt) : 8,5% Bv/bv (xám, cụt) : 8,5% bV/bv (đen, dài)",
                multiline=True
            ),
        },
    }

    # ---------- HỆ THỐNG KIẾN THỨC 4.1 ----------
    u0 = units[0]["blocks"]
    c1_ans_4_1 = [
        "Là NST chỉ chứa các gene quy định tính trạng thường",
        "Là NST chứa gene quy định giới tính, ngoài ra còn chứa các gene quy định tính trạng thường",
        "Là sự di truyền của các NST giới tính → quyết định giới tính của sinh vật",
        "Sự di truyền của các tính trạng thường nằm trên NST giới tính",
        "Là vùng trên NST mà gene vừa có allele trên X, vừa có allele trên Y",
        "Là vùng trên NST mà gene chỉ có allele trên X hoặc chỉ có allele trên Y",
        "Là trường hợp gene trên NST Y di truyền từ giới XY sang con là giới XY, không biểu hiện tính trạng ở con là giới XX",
        "Là trường hợp gene trên NST X di truyền từ giới XX sang con là giới XY (hoặc bố truyền cho con gái, mẹ truyền cho con trai)",
        "Là phép lai đổi vai trò của bố và mẹ",
    ]
    u0[1]["interactive"] = {
        "id": "cd4-ks-4.1-c1",
        "mode": "fill",
        "answers": {f"{i}:2": cell_ans(v) for i, v in enumerate(c1_ans_4_1, start=1)},
    }
    u0[2]["exercise"] = ex_item(
        "cd4-ks-4.1-c2", "cd4-ks-4.1-c2",
        "- Giống nhau: số lượng NST 2n = 8; có 3 cặp NST thường giống nhau về hình thái, cấu trúc và luôn tương đồng.\n- Khác nhau: Cặp NST giới tính của con cái là XX → luôn tương đồng; của con đực là XY → có đoạn tương đồng, có đoạn không tương đồng.\n→ Kết luận: Các gene trên NST thường di truyền giống nhau giữa đực và cái; các gene trên NST giới tính di truyền khác nhau giữa 2 giới (gene trên X di truyền chéo, gene trên Y di truyền thẳng).",
        mode="textarea"
    )
    # 1. Di truyền liên kết với giới tính — Ví dụ 1, 2 (ĐÁP ÁN 1.pdf trang 300–301)
    u0[11]["exercise"] = ex_item(
        "cd4-ks-4.1-lkgt-vd1-1", "cd4-ks-4.1-lkgt-vd1",
        "- Kiểu gene mèo đực: X^DY → ♂ đen; X^dY → ♂ hung.\n- Kiểu gene mèo cái: X^DX^D → ♀ đen; X^dX^d → ♀ hung; X^DX^d → ♀ tam thể.\n- Giải thích: Mèo đực có cặp NST giới tính XY nên trong kiểu gene bình thường chỉ chứa 1 NST X (X^D hoặc X^d) và 1 NST Y → chỉ có màu đen hoặc hung, không thể chứa đồng thời cả X^D và X^d nên không có màu lông tam thể.",
        mode="textarea"
    )
    u0[13]["exercise"] = ex_item("cd4-ks-4.1-lkgt-vd1-th1", "cd4-ks-4.1-lkgt-vd1", "P: X^DX^d × X^DY → F1: 1 X^DX^D (♀ đen) : 1 X^DX^d (♀ tam thể) : 1 X^DY (♂ đen) : 1 X^dY (♂ hung)", mode="input")
    u0[14]["text"] = u0[14]["text"].replace("lại với", "lai với")
    u0[14]["exercise"] = ex_item("cd4-ks-4.1-lkgt-vd1-th2", "cd4-ks-4.1-lkgt-vd1", "P: X^DX^D × X^dY → F1: 1 X^DX^d (♀ tam thể) : 1 X^DY (♂ đen)", mode="input")
    u0[15]["exercise"] = ex_item("cd4-ks-4.1-lkgt-vd1-th3", "cd4-ks-4.1-lkgt-vd1", "P: X^DX^d × X^dY → F1: 1 X^DX^d (♀ tam thể) : 1 X^dX^d (♀ hung) : 1 X^DY (♂ đen) : 1 X^dY (♂ hung)", mode="input")

    u0[18]["exercise"] = ex_item("cd4-ks-4.1-lkgt-vd2-1", "cd4-ks-4.1-lkgt-vd2", "X^AX^a × X^AY", mode="input")
    u0[19]["exercise"] = ex_item("cd4-ks-4.1-lkgt-vd2-2", "cd4-ks-4.1-lkgt-vd2", "X^aX^a × X^AY", mode="input")
    u0[20]["exercise"] = ex_item("cd4-ks-4.1-lkgt-vd2-3", "cd4-ks-4.1-lkgt-vd2", "X^AX^A × X^AY hoặc X^AX^A × X^aY", mode="input")
    u0[21]["exercise"] = ex_item("cd4-ks-4.1-lkgt-vd2-4", "cd4-ks-4.1-lkgt-vd2", "X^AX^a × X^aY", mode="input")

    # 2. Tương tác gene liên quan đến NST giới tính — Ví dụ 1, 2 (ĐÁP ÁN 1.pdf trang 301)
    u0[31]["exercise"] = ex_item("cd4-ks-4.1-ttgt-vd1-1", "cd4-ks-4.1-ttgt-vd1", "AAX^BX^B × aaX^bY", mode="input")
    u0[32]["exercise"] = ex_item("cd4-ks-4.1-ttgt-vd1-2", "cd4-ks-4.1-ttgt-vd1", "6 ♀ đen : 2 ♀ trắng : 3 ♂ đen : 5 ♂ trắng", mode="input")
    u0[33]["exercise"] = ex_item("cd4-ks-4.1-ttgt-vd1-3", "cd4-ks-4.1-ttgt-vd1", "5/7", mode="input", exact=["5/7"])

    vd2_41_tf = ["Sai", "Đúng", "Sai", "Đúng", "Sai"]
    for idx_off, tf_val in enumerate(vd2_41_tf):
        u0[35 + idx_off]["exercise"] = ex_item(f"cd4-ks-4.1-ttgt-vd2-{idx_off+1}", "cd4-ks-4.1-ttgt-vd2", tf_val, mode="true_false")

    # ---------- HỆ THỐNG KIẾN THỨC 4.2 ----------
    u1 = units[1]["blocks"]
    c1_ans_4_2 = [
        "Là trường hợp các gene nằm trên cùng một NST di truyền cùng nhau và tạo thành một nhóm gene liên kết",
        "Tập hợp các gene liên kết thuộc mỗi cặp nhiễm sắc thể tương đồng",
        "Hiện tượng các allele tương ứng của một gene trao đổi vị trí cho nhau trên cặp NST tương đồng",
        "Là giá trị phản ánh mức độ trao đổi chéo giữa các gene cùng nằm trên 1 NST",
        "Là giao tử mang các gene hoán vị (còn được gọi là giao tử hoán vị)",
        "Sơ đồ biểu diễn trật tự sắp xếp và khoảng cách tương đối giữa các gene trên NST",
    ]
    u1[1]["interactive"] = {
        "id": "cd4-ks-4.2-c1",
        "mode": "fill",
        "answers": {f"{i}:2": cell_ans(v) for i, v in enumerate(c1_ans_4_2, start=1)},
    }

    # Câu 2: 10 kiểu gene liên kết (f = 40%, ĐÁP ÁN 1.pdf trang 302)
    c2_42_rows = [
        (2, "AB/AB", "1 AB", "1 AB"),
        (3, "Ab/Ab", "1 Ab", "1 Ab"),
        (4, "aB/aB", "1 aB", "1 aB"),
        (5, "ab/ab", "1 ab", "1 ab"),
        (7, "AB/Ab", "1 AB : 1 Ab", "1 AB : 1 Ab"),
        (8, "AB/aB", "1 AB : 1 aB", "1 AB : 1 aB"),
        (9, "Ab/ab", "1 Ab : 1 ab", "1 Ab : 1 ab"),
        (10, "aB/ab", "1 aB : 1 ab", "1 aB : 1 ab"),
        (12, "AB/ab", "AB = ab = 0,5", "AB = ab = 0,3; Ab = aB = 0,2"),
        (13, "Ab/aB", "Ab = aB = 0,5", "Ab = aB = 0,3; AB = ab = 0,2"),
    ]
    ans_map = {}
    for r, kg, no_hv, hv in c2_42_rows:
        ans_map[f"{r}:1"] = cell_ans(kg, multiline=False)
        ans_map[f"{r}:2"] = cell_ans(no_hv, multiline=False)
        ans_map[f"{r}:3"] = cell_ans(hv, multiline=(r >= 12))
    u1[3]["interactive"] = {"id": "cd4-ks-4.2-c2", "mode": "fill", "answers": ans_map}

    # 1. Liên kết gene — Ví dụ 1, 2 & Bài toán nghịch (ĐÁP ÁN 1.pdf trang 302–303)
    u1[11]["text"] = u1[11]["text"].replace("thu được E2", "thu được F2")
    u1[12]["exercise"] = ex_item("cd4-ks-4.2-lk-vd1-1", "cd4-ks-4.2-lk-vd1", "Tính trạng chiều cao và hình dạng quả di truyền liên kết hoàn toàn", mode="input")
    u1[13]["exercise"] = ex_item("cd4-ks-4.2-lk-vd1-2", "cd4-ks-4.2-lk-vd1", "Ptc: AB/AB × ab/ab → F1: 100% AB/ab (cao, tròn).\nF1 × F1: AB/ab × AB/ab → F2: 1 AB/AB : 2 AB/ab : 1 ab/ab (3 cao, tròn : 1 thấp, bầu dục).", mode="textarea")
    u1[14]["exercise"] = ex_item("cd4-ks-4.2-lk-vd1-3", "cd4-ks-4.2-lk-vd1", "50% (tương ứng 500 cây)", mode="input", exact=["50%", "1/2", "500", "500 cay", "0,5"])
    u1[16]["exercise"] = ex_item("cd4-ks-4.2-lk-vd1-th1", "cd4-ks-4.2-lk-vd1", "TLKG: 1 AB/AB : 2 AB/ab : 1 ab/ab — TLKH: 3 cao, tròn : 1 thấp, bầu dục", mode="input")
    u1[17]["exercise"] = ex_item("cd4-ks-4.2-lk-vd1-th2", "cd4-ks-4.2-lk-vd1", "TLKG: 4/9 AB/AB : 4/9 AB/ab : 1/9 ab/ab — TLKH: 8 cao, tròn : 1 thấp, bầu dục", mode="input")
    u1[18]["exercise"] = ex_item("cd4-ks-4.2-lk-vd1-th3", "cd4-ks-4.2-lk-vd1", "TLKG: 3/8 AB/AB : 2/8 AB/ab : 3/8 ab/ab — TLKH: 5 cao, tròn : 3 thấp, bầu dục", mode="input")

    # Ví dụ 2 bảng 10 phép lai liên kết (ĐÁP ÁN 1.pdf trang 302–303)
    # Lưu ý câu 10 trong app là Ab/ab Dd × aB/aB Dd (hoặc DD trong sách) → chuẩn hóa hiển thị đúng với đề trong PDF (DD) để khớp đáp án 1:1:1:1 và 1:1!
    u1[20]["rows"][5][5] = "Ab/ab Dd × aB/aB DD"
    u1[20]["interactive"] = {
        "id": "cd4-ks-4.2-lk-vd2",
        "mode": "fill",
        "answers": {
            "1:2": cell_ans("1 : 2 : 1", exact=["1:2:1"], multiline=False),
            "1:3": cell_ans("3 : 1", exact=["3:1"], multiline=False),
            "2:2": cell_ans("1 : 2 : 1", exact=["1:2:1"], multiline=False),
            "2:3": cell_ans("1 : 2 : 1", exact=["1:2:1"], multiline=False),
            "3:2": cell_ans("1 : 1 : 1 : 1", exact=["1:1:1:1"], multiline=False),
            "3:3": cell_ans("1 : 1 : 1 : 1", exact=["1:1:1:1"], multiline=False),
            "4:2": cell_ans("1 : 1 : 1 : 1", exact=["1:1:1:1"], multiline=False),
            "4:3": cell_ans("2 : 1 : 1", exact=["2:1:1"], multiline=False),
            "5:2": cell_ans("1 : 1 : 1 : 1", exact=["1:1:1:1"], multiline=False),
            "5:3": cell_ans("2 : 1 : 1", exact=["2:1:1"], multiline=False),
            "1:6": cell_ans("1 : 2 : 1", exact=["1:2:1"], multiline=False),
            "1:7": cell_ans("3 : 1", exact=["3:1"], multiline=False),
            "2:6": cell_ans("1 : 1", exact=["1:1"], multiline=False),
            "2:7": cell_ans("1 : 1", exact=["1:1"], multiline=False),
            "3:6": cell_ans("1 : 1 : 1 : 1", exact=["1:1:1:1"], multiline=False),
            "3:7": cell_ans("2 : 1 : 1", exact=["2:1:1"], multiline=False),
            "4:6": cell_ans("1:1:1:1:2:2:2:2:1:1:1:1", exact=["1:1:1:1:2:2:2:2:1:1:1:1", "2:2:2:2:1:1:1:1:1:1:1:1"], multiline=False),
            "4:7": cell_ans("3 : 3 : 3 : 3 : 1 : 1 : 1 : 1", exact=["3:3:3:3:1:1:1:1"], multiline=False),
            "5:6": cell_ans("1 : 1 : 1 : 1", exact=["1:1:1:1"], multiline=False),
            "5:7": cell_ans("1 : 1", exact=["1:1"], multiline=False),
        },
    }

    # Bài toán nghịch liên kết gene (ĐÁP ÁN 1.pdf trang 303)
    u1[27]["exercise"] = ex_item("cd4-ks-4.2-lkn-1", "cd4-ks-4.2-lkn", "P: ab/ab (hạt nhăn, không tua) × cây X: AB/Ab (hạt trơn, có tua)", mode="input")
    u1[29]["exercise"] = ex_item("cd4-ks-4.2-lkn-2", "cd4-ks-4.2-lkn", "P: Ab/ab × aB/ab", mode="input")
    u1[30]["exercise"] = ex_item("cd4-ks-4.2-lkn-3", "cd4-ks-4.2-lkn", "P: AB/ab × AB/ab", mode="input")

    # 2. Hoán vị gene — Bài toán thuận Ví dụ 1, 2 (ĐÁP ÁN 1.pdf trang 303)
    u1[60]["exercise"] = ex_item("cd4-ks-4.2-hv-vd1-1", "cd4-ks-4.2-hv-vd1", "TLKG: AB/ab = ab/ab = 0,3; Ab/ab = aB/ab = 0,2.\nTLKH: TT = LL = 0,3; TL = LT = 0,2.", mode="textarea")
    u1[61]["text"] = u1[61]["text"].replace("))", ")")
    u1[61]["exercise"] = ex_item("cd4-ks-4.2-hv-vd1-2", "cd4-ks-4.2-hv-vd1", "TLKG: AB/AB = ab/ab = 0,2; AB/ab = 0,4; AB/Ab = AB/aB = Ab/ab = aB/ab = 0,05.\nTLKH: LL = 0,2; TT = 0,7; TL = LT = 0,05.", mode="textarea")
    u1[62]["exercise"] = ex_item("cd4-ks-4.2-hv-vd1-3", "cd4-ks-4.2-hv-vd1", "TLKG: Ab/Ab = aB/aB = 0,175; Ab/aB = 0,35; AB/Ab = AB/aB = Ab/ab = aB/ab = 0,075.\nTLKH: LL = 0; TT = 0,5; TL = LT = 0,25.", mode="textarea")
    u1[63]["exercise"] = ex_item("cd4-ks-4.2-hv-vd1-4", "cd4-ks-4.2-hv-vd1", "TLKG (hoán vị 2 bên f=0,4): AB/AB = ab/ab = 0,09; Ab/Ab = aB/aB = 0,04; AB/Ab = AB/aB = Ab/ab = aB/ab = 0,12; AB/ab = 0,18; Ab/aB = 0,08.\nTLKH: LL = 0,09; TT = 0,59; TL = LT = 0,16.", mode="textarea")

    u1[65]["exercise"] = ex_item("cd4-ks-4.2-hv-vd2-1", "cd4-ks-4.2-hv-vd2", "- TLKG: AB/AB = ab/ab = 0,04; Ab/Ab = aB/aB = 0,09; AB/Ab = AB/aB = Ab/ab = aB/ab = 0,12; AB/ab = 0,08; Ab/aB = 0,18.\n- TLKH: 0,54 cao, dài : 0,21 cao, tròn : 0,21 thấp, dài : 0,04 thấp, tròn.", mode="textarea")
    u1[66]["exercise"] = ex_item("cd4-ks-4.2-hv-vd2-2", "cd4-ks-4.2-hv-vd2", "2/27 (0,04 / 0,54 = 2/27)", mode="input", exact=["2/27"])
    u1[67]["exercise"] = ex_item("cd4-ks-4.2-hv-vd2-3", "cd4-ks-4.2-hv-vd2", "12/25 (0,48 = 48%)", mode="input", exact=["12/25", "48%", "0,48", "0.48"])

    # 2. Hoán vị gene — Bài toán nghịch Ví dụ 1, 2 (ĐÁP ÁN 1.pdf trang 304)
    u1[78]["exercise"] = ex_item("cd4-ks-4.2-hvn-vd1-1", "cd4-ks-4.2-hvn-vd1", "P: Ab/Ab × aB/aB → F1: Ab/aB × Ab/aB; f = 0,08 (8%)", mode="input")
    u1[80]["exercise"] = ex_item("cd4-ks-4.2-hvn-vd1-2", "cd4-ks-4.2-hvn-vd1", "P: Ab/aB × ab/ab; f = 0,25 (25%)", mode="input")
    u1[81]["exercise"] = ex_item("cd4-ks-4.2-hvn-vd1-3", "cd4-ks-4.2-hvn-vd1", "P: Ab/aB × Ab/aB; f = 0,4 (40%)", mode="input")
    u1[82]["exercise"] = ex_item("cd4-ks-4.2-hvn-vd1-4", "cd4-ks-4.2-hvn-vd1", "P: AB/ab × Ab/ab; f = 0,25 (25%)", mode="input")

    u1[85]["exercise"] = ex_item("cd4-ks-4.2-hvn-vd2-1", "cd4-ks-4.2-hvn-vd2", "10% (f = 0,1)", mode="input", exact=["10%", "0,1", "0.1", "10"])
    u1[86]["exercise"] = ex_item("cd4-ks-4.2-hvn-vd2-2", "cd4-ks-4.2-hvn-vd2", "4 loại kiểu gene (X^{AB}X^{AB}, X^{AB}X^{Ab}, X^{AB}X^{aB}, X^{AB}X^{ab})", mode="input", exact=["4", "4 loai", "4 kg", "4 kieu gene"])
    u1[87]["exercise"] = ex_item("cd4-ks-4.2-hvn-vd2-3", "cd4-ks-4.2-hvn-vd2", "22,5%", mode="input", exact=["22,5%", "22.5%", "0,225", "0.225", "9/40"])

    # 3. Bài toán tổng hợp — Ví dụ 1, 2, 3 (ĐÁP ÁN 1.pdf trang 304)
    u1[96]["exercise"] = ex_item("cd4-ks-4.2-th-vd1-1", "cd4-ks-4.2-th-vd1", "TTT = 49,5%; TTL = 16,5%; LLT = 12%; TLT = LTT = 6,75%; TLL = LTL = 2,25%; LLL = 4%", mode="textarea")
    u1[97]["exercise"] = ex_item("cd4-ks-4.2-th-vd1-2", "cd4-ks-4.2-th-vd1", "8% (0,08)", mode="input", exact=["8%", "0,08", "0.08", "2/25"])
    u1[98]["exercise"] = ex_item("cd4-ks-4.2-th-vd1-3", "cd4-ks-4.2-th-vd1", "17% (0,17)", mode="input", exact=["17%", "0,17", "0.17"])

    u1[101]["exercise"] = ex_item("cd4-ks-4.2-th-vd2-1", "cd4-ks-4.2-th-vd2", "Tỉ lệ kiểu hình 4 tính trạng trội = 38,94%; tỉ lệ kiểu hình 3 tính trạng trội = 31,74%", mode="input")
    u1[102]["exercise"] = ex_item("cd4-ks-4.2-th-vd2-2", "cd4-ks-4.2-th-vd2", "8,84%", mode="input", exact=["8,84%", "8.84%", "0,0884", "0.0884"])
    u1[103]["exercise"] = ex_item("cd4-ks-4.2-th-vd2-3", "cd4-ks-4.2-th-vd2", "8,84%", mode="input", exact=["8,84%", "8.84%", "0,0884", "0.0884"])

    u1[104]["text"] = u1[104]["text"].replace("mặt đỏ", "mắt đỏ")
    u1[105]["exercise"] = ex_item("cd4-ks-4.2-th-vd3-1", "cd4-ks-4.2-th-vd3", "f = 20%; 28 kiểu gene và 12 kiểu hình", mode="input")
    u1[106]["exercise"] = ex_item("cd4-ks-4.2-th-vd3-2", "cd4-ks-4.2-th-vd3", "Tỉ lệ kiểu hình mang 2 tính trạng trội = 25%; tỉ lệ ruồi đực mang 1 tính trạng trội = 7,5% (0,075)", mode="input")
    u1[107]["exercise"] = ex_item("cd4-ks-4.2-th-vd3-3", "cd4-ks-4.2-th-vd3", "1,25% (0,0125)", mode="input", exact=["1,25%", "1.25%", "0,0125", "0.0125", "1/80"])
    u1[108]["exercise"] = ex_item("cd4-ks-4.2-th-vd3-4", "cd4-ks-4.2-th-vd3", "20% (0,2)", mode="input", exact=["20%", "0,2", "0.2", "1/5"])

    # ---------- HỆ THỐNG KIẾN THỨC 4.3 ----------
    u2 = units[2]["blocks"]
    c1_ans_4_3 = [
        "Là gene nằm trên các phân tử DNA ở tế bào chất (trong ti thể hoặc lục lạp)",
        "Là hiện tượng tính trạng của đời con chịu sự quyết định bởi vật chất di truyền của mẹ",
        "Là hiện tượng gene trong ti thể của thực vật bị đột biến làm cây không tạo được hạt phấn hữu thụ nhưng trứng vẫn hình thành bình thường",
        "Loại bỏ bao phấn khỏi hoa trong công tác lai giống",
        "Cây phát sinh chủng loại là sơ đồ mô tả mối quan hệ tiến hoá giữa các loài, được xây dựng dựa trên sự giống và khác nhau về các đặc điểm vật chất di truyền hay cơ thể",
        "Là quá trình xác định tính hợp pháp của các bằng chứng trong các sự việc vi phạm pháp luật dựa trên các kiến thức về khoa học pháp y và kĩ thuật hiện đại",
        "Là bệnh gây thoái hóa hệ thống thần kinh do các gene đột biến (trong nhân và tế bào chất) gây ra",
        "Là một bệnh lý về não gây tác động đến trí nhớ, suy nghĩ và hành vi",
        "Là bệnh do các gene đột biến trong ti thể gây ra",
    ]
    u2[0]["interactive"] = {
        "id": "cd4-ks-4.3-c1",
        "mode": "fill",
        "answers": {f"{i}:2": cell_ans(v) for i, v in enumerate(c1_ans_4_3, start=1)},
    }

    # ---------- HỆ THỐNG KIẾN THỨC 4.4 ----------
    u3 = units[3]["blocks"]
    c1_ans_4_4 = [
        "Sự biến đổi về kiểu hình của cùng một kiểu gene ở các môi trường khác nhau",
        "Là những biến đổi liên quan đến vật chất di truyền, xảy ra ở gene (cấp độ phân tử) hoặc nhiễm sắc thể (cấp độ tế bào)",
        "Tập hợp tất cả các kiểu hình của cùng một kiểu gene tương ứng các điều kiện môi trường sống khác nhau",
        "Thường có mức phản ứng hẹp hay nói cách khác sự biểu hiện của gene ít chịu ảnh hưởng của các yếu tố môi trường",
        "Do nhiều gene quy định, thường có mức phản ứng rộng",
        "Là một bệnh rối loạn chuyển hoá bẩm sinh (không chuyển hoá được amino acid phenylalanine) dẫn đến làm chậm phát triển trí tuệ",
    ]
    u3[1]["interactive"] = {
        "id": "cd4-ks-4.4-c1",
        "mode": "fill",
        "answers": {f"{i}:2": cell_ans(v) for i, v in enumerate(c1_ans_4_4, start=1)},
    }
    # Câu 2: Phân biệt Đột biến (col 2), Thường biến (col 3), Mức phản ứng (col 4) — ĐÁP ÁN 2.pdf trang 309–310
    # Lưu ý rows[0] và rows[1] là 2 dòng header → dữ liệu bắt đầu từ row index 2 (STT 1..19 → row 2..20)
    col_map = {"db": 2, "tb": 3, "mpu": 4}
    c2_44_seq = [
        "tb", "db", "tb", "tb", "db", "tb", "tb", "mpu", "db", "tb",
        "mpu", "mpu", "tb", "db", "tb", "tb", "db", "mpu", "tb"
    ]
    u3[3]["interactive"] = {
        "id": "cd4-ks-4.4-c2",
        "mode": "check_radio",
        "header_rows": 2,
        "radio_cols": [2, 3, 4],
        "col_labels": {"2": "Đột biến", "3": "Thường biến", "4": "Mức phản ứng"},
        "radio_answers": {str(i + 2): col_map[val] for i, val in enumerate(c2_44_seq)},
    }

    save_topic(data, path)
    print("Updated chu_de_4.json")


def count_stats():
    total_tables = 0
    total_ex = 0
    total_groups = 0
    total_inputs = 0
    for fn in ["chu_de_1.json", "chu_de_2.json", "chu_de_3.json", "chu_de_4.json"]:
        d, _ = load_topic(fn)
        t_t = t_e = t_g = t_in = 0
        def scan(blocks):
            nonlocal t_t, t_e, t_g, t_in
            for b in blocks:
                if b.get("interactive"):
                    t_t += 1
                    inter = b["interactive"]
                    if inter["mode"] == "fill":
                        t_in += len(inter.get("answers", {}))
                    elif inter["mode"] == "tf_rows":
                        t_in += len(inter.get("tf_answers", {}))
                    elif inter["mode"] == "check_single":
                        t_in += len(b.get("rows", [])) - inter.get("header_rows", 1)
                    elif inter["mode"] == "check_radio":
                        t_in += len(inter.get("radio_answers", {}))
                if b.get("exercise"):
                    t_e += 1
                    t_in += 1
                if b.get("exercise_group"):
                    t_g += 1
                    t_in += len(b["exercise_group"].get("items", []))
        for l in d.get("lessons", []):
            for s in l.get("sections", []):
                scan(s.get("blocks", []))
        for u in d.get("knowledge_system", {}).get("units", []):
            scan(u.get("blocks", []))
        print(f"  {fn}: {t_t} interactive tables, {t_e} exercise prompts, {t_g} exercise groups => {t_in} student input fields")
        total_tables += t_t
        total_ex += t_e
        total_groups += t_g
        total_inputs += t_in
    print(f"TOTAL: {total_tables} tables, {total_ex} prompts, {total_groups} groups => {total_inputs} interactive student inputs!")


if __name__ == "__main__":
    enrich_chu_de_1()
    enrich_chu_de_2()
    enrich_chu_de_3()
    enrich_chu_de_4()
    count_stats()

    # Đồng bộ ngay vào SQLite DB
    import database
    database.init_db()
    print("Synced SQLite database to bundled_version =", BUNDLED_VERSION)
