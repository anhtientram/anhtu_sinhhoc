#!/usr/bin/env python3
"""
Chuẩn hoá toàn bộ dữ liệu 4 Chủ đề Sinh học 12 theo SGK Sinh học 12 (Kết nối tri thức với cuộc sống):
1. Thống nhất đánh số đề mục các bài trong từng chủ đề:
   - Chủ đề 1: 1.1, 1.2, 1.3, 1.4
   - Chủ đề 2: 2.1, 2.2, 2.3
   - Chủ đề 3: 3.1, 3.2
   - Chủ đề 4: 4.1, 4.2, 4.3, 4.4
   (Đồng bộ cả Lý thuyết, Hệ thống kiến thức, Sơ đồ tư duy và Câu hỏi ôn tập)
2. Bổ sung mục "Yêu cầu cần đạt" chuẩn SGK cho tất cả các bài chưa có.
3. Chỉnh sửa toàn bộ lỗi chính tả, lỗi OCR, thuật ngữ và cách viết kiểu gene chuẩn SGK.
4. Đồng bộ lại vào data/topics/chu_de_1..4.json và data/sinhhoc12.db (giữ nguyên youtube_videos).
"""
import json
import os
import re

from database import get_conn, now_iso

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(BASE_DIR, "data", "topics")

# 1. Yêu cầu cần đạt chuẩn trích từ SGK Sinh học 12 (Kết nối tri thức với cuộc sống)
YCCD_BY_LESSON_ID = {
    "chu-de-1-bai-1": [
        "1. Dựa vào cấu trúc hoá học của phân tử DNA, trình bày được chức năng của DNA.",
        "2. Nêu được ý nghĩa của các kết cặp đặc hiệu A – T và G – C.",
        "3. Phân tích được cơ chế tái bản của DNA là một quá trình tự sao thông tin di truyền từ tế bào mẹ sang tế bào con hay từ thế hệ này sang thế hệ sau.",
    ],
    "chu-de-1-bai-2": [
        "1. Nêu được khái niệm và cấu trúc của gene. Phân biệt được các loại gene dựa vào cấu trúc và chức năng của gene.",
        "2. Phân biệt được các loại RNA. Phân tích được bản chất phiên mã thông tin di truyền là cơ chế tổng hợp RNA dựa trên DNA.",
        "3. Nêu được khái niệm phiên mã ngược và ý nghĩa.",
        "4. Nêu được khái niệm và các đặc điểm của mã di truyền.",
        "5. Trình bày được cơ chế tổng hợp protein từ bản sao là RNA có bản chất là quá trình dịch mã.",
        "6. Vẽ và giải thích được sơ đồ liên kết ba quá trình thể hiện cơ chế di truyền ở cấp phân tử là quá trình truyền đạt thông tin di truyền.",
        "7. Phát biểu được khái niệm hệ gene. Trình bày được một số thành tựu và ứng dụng của việc giải trình tự hệ gene người.",
    ],
    "chu-de-1-bai-3": [
        "1. Trình bày được thí nghiệm trên operon lac của vi khuẩn E. coli.",
        "2. Phân tích được ý nghĩa của điều hoà biểu hiện gene trong tế bào và trong quá trình phát triển cá thể.",
        "3. Nêu được ứng dụng của điều hoà biểu hiện gene.",
    ],
    "chu-de-1-bai-4": [
        "1. Nêu được khái niệm đột biến gene; phân biệt được các dạng đột biến gene.",
        "2. Phân tích được nguyên nhân, cơ chế phát sinh đột biến gene.",
        "3. Trình bày được vai trò của đột biến gene trong tiến hoá, chọn giống và nghiên cứu di truyền.",
        "4. Nêu được khái niệm, nguyên lí và một số thành tựu của công nghệ DNA tái tổ hợp.",
        "5. Nêu được khái niệm, nguyên lí và một số thành tựu tạo thực vật và động vật biến đổi gene.",
        "6. Tranh luận, phản biện được về việc sản xuất và sử dụng sản phẩm biến đổi gene và đạo đức sinh học.",
    ],
    "chu-de-2-bai-3": [
        "1. Xác định được các loại giao tử và tỉ lệ từng loại giao tử tạo ra từ một kiểu gene trong giảm phân bình thường (phân li độc lập, liên kết gene và hoán vị gene).",
        "2. Tính được tỉ lệ giao tử liên kết và giao tử hoán vị dựa vào tần số hoán vị gene (f).",
        "3. Phân biệt và xác định được số loại giao tử tối đa, tỉ lệ giao tử ở cấp độ tế bào (tế bào sinh tinh, tế bào sinh trứng) và cấp độ cơ thể.",
    ],
    "chu-de-3-bai-1": [
        "1. Nêu được bối cảnh ra đời thí nghiệm của Mendel.",
        "2. Trình bày được cách bố trí và tiến hành thí nghiệm của Mendel.",
        "3. Nêu được tính quy luật của hiện tượng di truyền và giải thích thí nghiệm của Mendel.",
        "4. Trình bày được cơ sở tế bào học của các thí nghiệm của Mendel dựa trên mối quan hệ giữa nguyên phân, giảm phân và thụ tinh.",
        "5. Nêu được vì sao các quy luật di truyền của Mendel đặt nền móng cho di truyền học hiện đại.",
    ],
    "chu-de-3-bai-2": [
        "1. Giải thích được sản phẩm của các allele của cùng một gene và của các gene khác nhau có thể tương tác với nhau quy định tính trạng.",
        "2. Phân biệt được các kiểu tương tác: trội không hoàn toàn, đồng trội, tương tác cộng gộp, tương tác giữa các gene không allele, gene đa allele và tính đa hiệu của gene.",
    ],
    "chu-de-4-bai-1": [
        "1. Nêu được khái niệm NST giới tính; di truyền giới tính.",
        "2. Phân tích được cơ chế di truyền xác định giới tính; giải thích được tỉ lệ lí thuyết giới tính trong tự nhiên thường là 1 : 1.",
        "3. Trình bày được quan điểm của bản thân về việc điều khiển giới tính ở người theo ý muốn.",
        "4. Nêu được bối cảnh ra đời và cách bố trí thí nghiệm của Morgan, qua đó nêu được khái niệm di truyền liên kết với giới tính.",
        "5. Vận dụng những hiểu biết về di truyền giới tính và liên kết với giới tính để giải thích các vấn đề trong thực tiễn (điều khiển giới tính trong chăn nuôi, phát hiện bệnh do rối loạn cơ chế phân li, tổ hợp NST giới tính,...).",
    ],
    "chu-de-4-bai-2": [
        "1. Trình bày được cách bố trí và tiến hành thí nghiệm của Morgan, từ đó phát biểu được khái niệm liên kết gene.",
        "2. Phân tích được cơ sở tế bào học và ý nghĩa của liên kết gene.",
        "3. Trình bày được thí nghiệm của Morgan, từ đó phát biểu được khái niệm hoán vị gene.",
        "4. Phân tích được cơ sở tế bào học và ý nghĩa của hoán vị gene.",
        "5. Nêu được ý nghĩa của việc lập bản đồ di truyền.",
        "6. Nêu được quan điểm của Mendel và Morgan về tính quy luật của hiện tượng di truyền.",
    ],
    "chu-de-4-bai-3": [
        "1. Trình bày được bối cảnh ra đời thí nghiệm của Correns.",
        "2. Trình bày được thí nghiệm chứng minh di truyền gene ngoài nhân của Correns, từ đó giải thích được gene không những tồn tại trong nhân mà còn tồn tại ngoài nhân (trong các bào quan như ti thể, lạp thể).",
        "3. Trình bày được đặc điểm di truyền của gene ngoài nhân và một số ứng dụng.",
    ],
    "chu-de-4-bai-4": [
        "1. Phân tích được sự tương tác giữa kiểu gene và môi trường.",
        "2. Nêu được khái niệm mức phản ứng. Lấy được ví dụ minh hoạ.",
        "3. Trình bày được bản chất di truyền là di truyền mức phản ứng.",
        "4. Vận dụng được hiểu biết về thường biến và mức phản ứng của một kiểu gene, giải thích một số ứng dụng trong thực tiễn (tạo và chọn giống, kĩ thuật chăn nuôi, trồng trọt,...).",
        "5. Nêu được một số thành tựu chọn, tạo giống cây trồng và vật nuôi.",
    ],
}

# 2. Bảng sửa lỗi chính tả, thuật ngữ và cách viết kiểu gene chuẩn SGK
EXACT_REPLACEMENTS = [
    # --- Lỗi chính tả & OCR Chủ đề 1 ---
    ("mang gốc photphat", "mang gốc phosphate"),
    ("giữa hai mặt đơn yếu", "giữa hai mạch đơn yếu"),
    ("cầu trúc", "cấu trúc"),
    ("Cầu trúc", "Cấu trúc"),
    ("trong các tỉ thể và lục lạp", "trong các ti thể và lục lạp"),
    ("tê bào", "tế bào"),
    ("animo acid", "amino acid"),
    ("làm khuôn đề tổng hợp", "làm khuôn để tổng hợp"),
    ("các protein và enzym\nRNA polymerase", "các protein và enzyme RNA polymerase"),
    ("protein và enzym ", "protein và enzyme "),
    ("tính hiệu kết thúc", "tín hiệu kết thúc"),
    ("bộ ba đôi mã", "bộ ba đối mã"),
    ("liên kết peptide giứa amino acid", "liên kết peptide giữa amino acid"),
    ("β-galatosidase", "β-galactosidase"),
    ("transecetylase", "transacetylase"),
    ("điều hoạt biểu hiện", "điều hoà biểu hiện"),
    ("Điều hoạt biểu hiện", "Điều hoà biểu hiện"),
    ("không liên với vùng O", "không liên kết với vùng O"),
    ("thể đột biển", "thể đột biến"),
    ("tỉa UV", "tia UV"),
    ("5-bromouracil BrU)", "5-bromouracil (5-BrU)"),
    ("protein tái tổ và đưa vào", "protein tái tổ hợp và đưa vào"),
    ("Biểu hiện gen:", "Biểu hiện gene:"),
    ("tổng hợp B-carotene", "tổng hợp β-carotene"),
    ("thay thế l cặp", "thay thế 1 cặp"),
    ("→1 cặp", "→ 1 cặp"),
    ("amino acid valin ", "amino acid valine "),
    ("nhận đinh nào đúng", "nhận định nào đúng"),
    ("1mm = 103µm = 106 nm = 107Å", "1 mm = 10^3 µm = 10^6 nm = 10^7 Å"),
    ("1µm = 104 Å", "1 µm = 10^4 Å"),
    ("L = × 3,4Å", "L = (N/2) × 3,4 Å"),
    ("CK = .", "CK = N/20."),
    ("A% = T% = = . ; G% = X% = = (C1%+C2)/(2)", "A% = T% = (A1% + T1%)/2 = (A1% + A2%)/2 ; G% = C% = (G1% + C1%)/2 = (C1% + C2%)/2"),
    ("21 = 2", "2^1 = 2"),
    ("22 = 4", "2^2 = 4"),
    ("21 – 1 = 1", "2^1 – 1 = 1"),
    ("22 – 1 = 3", "2^2 – 1 = 3"),
    ("21 – 2 = 0", "2^1 – 2 = 0"),
    ("22 – 2 = 2", "2^2 – 2 = 2"),
    ("2k – 1", "2^k – 1"),
    ("2k – 2", "2^k – 2"),
    ("| k lần | … | 2k |", "| k lần | … | 2^k |"),
    ("chứa N15", "chứa 15N"),
    ("chứa N14", "chứa 14N"),
    ("có N14", "có 14N"),
    ("loại N14 và N15", "loại 14N và 15N"),
    ("= Để làm tốt dạng này", "- Để làm tốt dạng này"),
    ("tạo ra 4 allele mới có trình tự nucleotide như sau:", "tạo ra 3 allele mới có trình tự nucleotide như sau:"),
    ("3’TAC CTG GTA ATG TTCAATC5’", "3’TAC CTG GTA ATG TCA ATC5’"),
    # --- Lỗi chính tả & kiểu gene Chủ đề 2 ---
    ("trên trên nhiễm sắc thể", "trên nhiễm sắc thể"),
    ("nhiễm sắc nhiễm sắc có thể", "nhiễm sắc thể có thể"),
    ("nhiễm sắc nhiễm sắc", "nhiễm sắc thể"),
    ("protein histon.", "protein histone."),
    ("147 cặp nucleotide", "146 cặp nucleotide"),
    ("khác nhau giữa Hợp tử (2n) giới đực", "khác nhau giữa giới đực"),
    ("tiền hoá", "tiến hoá"),
    ("tiền hóa", "tiến hóa"),
    ("môi trường nội nào", "môi trường nội bào"),
    ("Cri - du - char", "Cri-du-chat"),
    ("mất lồi thành mắt dẹt", "mắt lồi thành mắt dẹt"),
    ("sử dụng đề xác định", "sử dụng để xác định"),
    ("thể một (2n 1)", "thể một (2n − 1)"),
    ("thể không (2n2)", "thể không (2n − 2)"),
    ("(2n + 1, 2n 1, 2n + 2, 2n 2,...)", "(2n + 1, 2n − 1, 2n + 2, 2n − 2,...)"),
    ("MỐI QUAN HỆ GIỮA KIỂU GENE MÔI TRƯỜNG VÀ KIỂU HÌNH", "MỐI QUAN HỆ GIỮA KIỂU GENE, MÔI TRƯỜNG VÀ KIỂU HÌNH"),
    ("(n+l)", "(n + 1)"),
    ("(n -1)", "(n − 1)"),
    ("kết hợp với nhân hoặc kết hợp", "kết hợp với nhau hoặc kết hợp"),
    ("đột biến lệch có thể xảy ra", "đột biến lệch bội có thể xảy ra"),
    ("Kiểu gene đồng hợp A A → A", "Kiểu gene đồng hợp AA → A"),
    ("tỉ lệ bằng 1-f/2", "tỉ lệ bằng (1 − f)/2"),
    ("Tế bào sinh tỉnh tế bào sinh tinh", "tế bào sinh tinh"),
    ("kiêu gene", "kiểu gene"),
    # --- Lỗi chính tả Chủ đề 3 ---
    ("thuyểt", "thuyết"),
    ("giả thuyểt", "giả thuyết"),
    ("xuất hiện l trong 2", "xuất hiện 1 trong 2"),
    ("phải do l cặp", "phải do 1 cặp"),
    ("tồn tại riêng lė", "tồn tại riêng rẽ"),
    ("qua giao từ", "qua giao tử"),
    ("chỉ chứa l trong 2", "chỉ chứa 1 trong 2"),
    ("cặp nhân tổ di truyển", "cặp nhân tố di truyền"),
    ("di truyển", "di truyền"),
    ("hiện đai.", "hiện đại."),
    ("NST tổn tại", "NST tồn tại"),
    ("dần đến sự phân li", "dẫn đến sự phân li"),
    ("chỉ chứa l NST", "chỉ chứa 1 NST"),
    ("chỉ còn l allele", "chỉ còn 1 allele"),
    ("ý nghĩa qui luật", "ý nghĩa quy luật"),
    ("Ý nghĩa qui luật", "Ý nghĩa quy luật"),
    ("từ đỏ, có thể", "từ đó, có thể"),
    ("3 hạt vàng : l hạt xanh", "3 hạt vàng : 1 hạt xanh"),
    ("cặp bổ mẹ thuần chủng", "cặp bố mẹ thuần chủng"),
    ("chọn lọc cá đặc tính tốt", "chọn lọc các đặc tính tốt"),
    ("tương tác đề quy định", "tương tác để quy định"),
    ("cùng một gene vùng biểu hiện", "cùng một gene cùng biểu hiện"),
    ("Cucur bita pepo", "Cucurbita pepo"),
    ("Lathyrus odorarus", "Lathyrus odoratus"),
    ("hoàn toàn sắc tổ", "hoàn toàn sắc tố"),
    ("chó tha mồi Labrado", "chó tha mồi Labrador"),
    ("màu xanh lụC.", "màu xanh lục."),
    # --- Lỗi chính tả & kiểu gene Chủ đề 4 ---
    ("châu châu, dê,...", "châu chấu, dế,..."),
    ("châu châu, dê", "châu chấu, dế"),
    ("không thụ tỉnh", "không thụ tinh"),
    ("thụ tỉnh", "thụ tinh"),
    ("(XX, XXX, OX)", "(XX, XXX, XO)"),
    ("qui định", "quy định"),
    ("loạn dưỡng cơ Duchene", "loạn dưỡng cơ Duchenne"),
    ("Quy ước gen:", "Quy ước gene:"),
    ("trên cùng nhiễm sắc thể. di truyền", "trên cùng nhiễm sắc thể di truyền"),
    ("trao đối chéo", "trao đổi chéo"),
    ("Tschermark", "Tschermak"),
    ("tiền hành thí nghiệm", "tiến hành thí nghiệm"),
    ("tiền hành", "tiến hành"),
    ("phân từ DNA", "phân tử DNA"),
    ("Trong thí nghiệm của tế bào sinh trứng Correns", "Trong thí nghiệm của Correns"),
    ("(tai, chí, đuôi và mõm)", "(tai, chi, đuôi và mõm)"),
    ("sắc tố melanine", "sắc tố melanin"),
    ("nhưng biểu gene ở các bộ phận", "nhưng biểu hiện gene ở các bộ phận"),
    ("yếu tổ môi trường", "yếu tố môi trường"),
    ("mỗi cặp gene chỉ phối", "mỗi cặp gene chi phối"),
    # --- Thuật ngữ chuẩn GDPT 2018 ---
    ("mARN", "mRNA"),
    ("tARN", "tRNA"),
    ("rARN", "rRNA"),
    ("ADN", "DNA"),
    # --- Chuẩn hoá cách viết kiểu gene bị dính liền / lỗi chỉ số OMML ---
    ("AaX_E^DX_e^d", "Aa X^{DE}X^{de}"),
    ("AaBbX_e^DX_E^d", "AaBb X^{De}X^{dE}"),
    ("Ab/abX_D^HX_d^h", "Ab/ab X^{HD}X^{hd}"),
    ("aB/abX_d^hY_d^H", "aB/ab X^{hd}Y^{Hd}"),
    ("AaBD/BD", "Aa BD/BD"),
    ("AaBD/bd", "Aa BD/bd"),
    ("AaBd/bDcho", "Aa Bd/bD cho"),
    ("AaBd/bD", "Aa Bd/bD"),
    ("AB/abDdEe", "AB/ab DdEe"),
    ("AB/abDd", "AB/ab Dd"),
    ("Ab/aBDd", "Ab/aB Dd"),
    ("Ab/aBdd", "Ab/aB dd"),
    ("Ab/abDd", "Ab/ab Dd"),
    ("aB/aBDd", "aB/aB Dd"),
    ("aB/abDd", "aB/ab Dd"),
    ("ab/abDd", "ab/ab Dd"),
    ("AD/adBb", "AD/ad Bb"),
]

# Một số sửa riêng chỉ áp dụng cho giá trị ô bảng '2k' đứng đơn độc
CELL_EXACT = {
    "2k": "2^k",
}


def clean_text(s: str) -> str:
    if not isinstance(s, str) or not s:
        return s
    if s in CELL_EXACT:
        return CELL_EXACT[s]
    out = s
    for old, new in EXACT_REPLACEMENTS:
        if old in out:
            out = out.replace(old, new)
    # Chuẩn hoá khoảng trắng thừa trước dấu phẩy/chấm do OCR nếu có
    out = re.sub(r"([A-Za-z0-9])×([A-Za-z0-9])", r"\1 × \2", out)
    return out


def walk_and_clean(obj, parent_key=""):
    if isinstance(obj, str):
        # Không động vào đường dẫn file ảnh / ID
        if parent_key in ("id", "lesson_id", "src", "image", "url") or obj.startswith(("/uploads/", "uploads/", "/images/", "http")):
            return obj
        return clean_text(obj)
    if isinstance(obj, list):
        return [walk_and_clean(x, parent_key) for x in obj]
    if isinstance(obj, dict):
        return {k: walk_and_clean(v, k) for k, v in obj.items()}
    return obj


def main():
    conn = get_conn()
    ts = now_iso()

    for topic_idx in range(1, 5):
        jpath = os.path.join(TOPICS_DIR, f"chu_de_{topic_idx}.json")
        if not os.path.exists(jpath):
            continue
        with open(jpath, "r", encoding="utf-8") as f:
            topic = json.load(f)

        # 1. Clean spelling & genotype notation across entire topic
        topic = walk_and_clean(topic)
        topic["bundled_version"] = "2026.11.26-sgk-v2"

        # 2. Unify lesson numbering to X.1, X.2, X.3... & inject Yêu cầu cần đạt where missing
        lesson_num_map = {}
        for l_idx, lesson in enumerate(topic.get("lessons", []), 1):
            new_num = f"{topic_idx}.{l_idx}"
            lid = lesson.get("id", "")
            lesson["number"] = new_num
            lesson_num_map[lid] = new_num

            sections = lesson.get("sections") or []
            has_yccd = any("yêu cầu cần đạt" in (s.get("heading") or "").lower() for s in sections)
            if not has_yccd and lid in YCCD_BY_LESSON_ID:
                yccd_lines = YCCD_BY_LESSON_ID[lid]
                yccd_sec = {
                    "heading": "Yêu cầu cần đạt",
                    "points": yccd_lines,
                    "blocks": [{"type": "paragraph", "text": ln, "is_bold": False} for ln in yccd_lines],
                }
                lesson["sections"] = [yccd_sec] + sections

        # 3. Sync numbering in knowledge_system.units & mindmap.branches
        ks = topic.get("knowledge_system") or {}
        for u_idx, unit in enumerate(ks.get("units") or [], 1):
            unit["lesson_number"] = f"{topic_idx}.{u_idx}"
        mindmap = ks.get("mindmap") or {}
        for b_idx, br in enumerate(mindmap.get("branches") or [], 1):
            title = br.get("title") or ""
            # Replace prefix like "BÀI 1:", "Bài 1:", "Phần A:", "Mục 4.1:" -> "1.1:"
            new_prefix = f"{topic_idx}.{b_idx}:"
            if re.match(r"^(?:BÀI|Bài|Phần|Mục)\s*[A-Za-z0-9.]+\s*[:\-–]?\s*", title):
                br["title"] = re.sub(
                    r"^(?:BÀI|Bài|Phần|Mục)\s*[A-Za-z0-9.]+\s*[:\-–]?\s*",
                    new_prefix + " ",
                    title,
                )
            elif not title.startswith(new_prefix):
                br["title"] = f"{new_prefix} {title}"

        # 4. Sync numbering in review questions
        rev = topic.get("review") or {}
        for kind in ("mcq", "true_false", "short_answer"):
            for q in rev.get(kind, []):
                lid = q.get("lesson_id") or ""
                if lid in lesson_num_map:
                    q["lesson"] = lesson_num_map[lid]

        # Save JSON
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(topic, f, ensure_ascii=False, indent=2)

        # Sync into SQLite (preserving youtube_videos if present in DB)
        row = conn.execute("SELECT content_json FROM topics WHERE id = ?", (topic["id"],)).fetchone()
        if row:
            old_db = json.loads(row["content_json"])
            if old_db.get("youtube_videos") and not topic.get("youtube_videos"):
                topic["youtube_videos"] = old_db["youtube_videos"]
            conn.execute(
                "UPDATE topics SET title = ?, subtitle = ?, content_json = ?, updated_at = ? WHERE id = ?",
                (
                    topic["title"],
                    topic.get("subtitle", ""),
                    json.dumps(topic, ensure_ascii=False),
                    ts,
                    topic["id"],
                ),
            )
        print(
            f"Refined {topic['id']}: lessons={[l['number'] for l in topic['lessons']]}, "
            f"all_have_yccd={all(any('yêu cầu cần đạt' in s['heading'].lower() for s in l['sections']) for l in topic['lessons'])}"
        )

    conn.commit()
    conn.close()
    print("DONE refining all 4 topics!")


if __name__ == "__main__":
    main()
