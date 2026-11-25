# Web App Giảng dạy & Ôn tập Sinh học 12 (CT GDPT 2018)

Ứng dụng Web đầy đủ Backend + Cơ sở dữ liệu SQLite hỗ trợ giảng dạy, học tập, luyện tập và quản lý điểm danh học sinh cho bộ môn **Sinh học 12**.

## 1. Khởi chạy nhanh trên máy

Mở Terminal tại thư mục dự án và chạy:

```bash
python3 server.py
```

Sau đó mở trình duyệt tại địa chỉ: **http://localhost:8080**

> Không cần cài đặt thêm thư viện ngoài (sử dụng Python 3 chuẩn + SQLite).

## 2. Tài khoản mẫu có sẵn

| Vai trò | Tên đăng nhập | Mật khẩu | Ghi chú |
|---|---|---|---|
| **Giáo viên** | `giaovien` | `123456` | Xem nhật ký vào/rời lớp, bảng điểm, biên tập Chủ đề & Câu hỏi, bật Chế độ trình chiếu / Xem như Học sinh |
| **Học sinh 1** | `hs_minhanh` | `123456` | Lớp 12A1 — tự động điểm danh giờ vào học & rời lớp |
| **Học sinh 2** | `hs_quochuy` | `123456` | Lớp 12A1 |
| **Học sinh 3** | `hs_thao` | `123456` | Lớp 12A2 |

- **Mã xác thực khi đăng ký tài khoản Giáo viên mới:** `GV-SINH12` (có thể đổi qua biến môi trường `TEACHER_INVITE_CODE`).

## 3. Các tính năng chính

1. **Phân quyền rõ ràng Học sinh / Giáo viên**:
   - Giao diện tối ưu cho từng vai trò. Giáo viên có thêm nút **Xem như Học sinh**, **Chế độ trình chiếu trên lớp**, và thẻ **Quản lý lớp học & Điểm danh**.
2. **Thẻ 1 — Lý thuyết & Video tương tác**:
   - Đầy đủ kiến thức và hình minh họa Chủ đề 1 (4 bài: DNA & Tái bản DNA, Gene & Truyền đạt TTDT, Operon Lac, Đột biến gene).
   - 4 **Phòng thí nghiệm mô phỏng tương tác trực tiếp** (Tái bản DNA bán bảo toàn, Bộ giải mã DNA → mRNA → Polypeptide, Công tắc bật/tắt Operon Lac, Phòng thí nghiệm Đột biến điểm).
   - **Video tương tác 2 chế độ**: Bài giảng hoạt họa có thuyết minh giọng đọc tiếng Việt + tự dừng hỏi kiểm tra; và chế độ nhúng Video YouTube/MP4 có gắn mốc thời gian hỏi đáp.
3. **Thẻ 2 — Hệ thống kiến thức**:
   - Sơ đồ tư duy tương tác mở rộng/thu gọn, bảng so sánh trọng tâm, bộ công thức giải nhanh và bộ thẻ ghi nhớ lật nhanh (Flashcards).
4. **Thẻ 3 — Hệ thống ôn tập (chuẩn 3 phần đề thi mới)**:
   - **3.1. Trắc nghiệm 4 đáp án** (1,0đ/câu).
   - **3.2. Trắc nghiệm Đúng/Sai** (4 ý a, b, c, d mỗi câu; tính điểm lũy tiến đúng chuẩn Bộ GD: 0,1 / 0,25 / 0,5 / 1,0đ).
   - **3.3. Trắc nghiệm trả lời ngắn** (tự chuẩn hóa số thập phân dấu `.` và `,`).
   - Hỗ trợ làm riêng từng phần hoặc **Đề tổng hợp 3 phần**, chấm tự động kèm giải thích chi tiết và lưu lịch sử điểm.
5. **Ghi nhận thời gian vào học & rời khỏi lớp học**:
   - Tự động check-in khi học sinh vào lớp, gửi nhịp hoạt động (heartbeat) định kỳ và tự động check-out khi nhấn **Rời lớp học**, **Đăng xuất** hoặc **đóng tab trình duyệt** (`sendBeacon`).
   - Giáo viên theo dõi trực tiếp trạng thái đang học, lọc theo lớp/học sinh và **Xuất báo cáo Excel (CSV)**.
6. **Hệ thống đăng nhập & cập nhật hồ sơ**:
   - Đăng ký, đăng nhập bảo mật (PBKDF2-SHA256), cập nhật đầy đủ thông tin cá nhân & đổi mật khẩu cho cả Học sinh và Giáo viên.

## 4. Cập nhật nội dung theo tài liệu nguồn của Thầy/Cô

- Dữ liệu gốc Chủ đề 1 nằm tại [data/topics/chu_de_1.json](data/topics/chu_de_1.json).
- Thầy/Cô có thể gửi trực tiếp file Word/PDF/nội dung Chủ đề 1 trong khung chat để tự động chuyển hóa và nạp chính xác vào ứng dụng, hoặc chỉnh sửa/nhập JSON trực tiếp trong thẻ **Quản lý lớp học → Biên tập Chủ đề & Câu hỏi**.

## 5. Sẵn sàng mở rộng lên trực tuyến (Supabase / Cloud)

- Thư mục [supabase/schema.sql](supabase/schema.sql) đã chuẩn bị sẵn cấu trúc bảng PostgreSQL tương ứng (`profiles`, `topics`, `study_sessions`, `quiz_attempts`, `lesson_progress`) để triển khai lên Supabase + Vercel/Render khi cần nhiều lớp truy cập từ xa.
