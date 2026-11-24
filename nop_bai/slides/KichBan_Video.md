# Kịch bản video demo 3–5 phút — noi_that_173820_n32

Quay màn hình máy tính 1366×768 (hoặc lớn hơn), thu tiếng thuyết minh. Dữ liệu là dữ liệu mẫu (synthetic): chạy
`python -m app.bootstrap --reset` trong `src/backend` trước khi quay để các đơn mẫu ở đúng trạng thái ban đầu.
Phần điện thoại quay bằng điện thoại thật, nếu chưa có thì dùng chế độ giả lập thiết bị của trình duyệt.

| Thời điểm | Màn hình | Thao tác | Lời thuyết minh (gợi ý) |
|---|---|---|---|
| 0:00–0:25 | Slide 1–2 | Lướt qua bài toán | "Cửa hàng nội thất gỗ gặp ba vấn đề: giá hàng đặt riêng tính tay, tồn kho rải ở nhiều xưởng, hóa đơn điện tử lỗi làm kẹt việc bán. Nhóm làm phần mềm thay sổ tay và KiotViet." |
| 0:25–1:15 | Đăng nhập → Bán hàng | Đăng nhập `anhnam` (Thợ). Gõ `tu tho`, chọn tủ thờ đặt theo mét dài, gõ `2m4`, bấm **Tính** | "Thợ gõ không dấu vẫn ra đúng hàng, dưới một giây. Tủ thờ 2m4 ra 5.328.000 đồng theo công thức Chủ cài. Thợ không bao giờ thấy giá vốn hay giá sàn." |
| 1:15–1:45 | Bán hàng | Thêm giường 1m8, sửa đơn giá xuống dưới giá sàn, lập đơn | "Khách trả thấp hơn giá sàn thì Thợ không tự bán được: đơn chuyển sang chờ Chủ duyệt, hàng vẫn được giữ." |
| 1:45–2:20 | Tổng quan (Chủ) | Đăng xuất, đăng nhập `covan`. Khung **CẦN CHỦ DUYỆT** → **Chủ duyệt** | "Chủ nhận thông báo ngay, kể cả trên điện thoại đang tắt app. Duyệt xong, đơn chuyển sang chờ thu tiền." |
| 2:20–2:55 | Đối soát & Chốt ngày | Giao dịch 17,0 triệu cho đơn 17,2 triệu → **Chấp nhận giảm** | "Khách chuyển thiếu 200 nghìn: hệ thống báo lệch tiền thay vì tự chốt. Chủ chọn thu bù hoặc chấp nhận giảm; khi chốt, kho tự xuất và hóa đơn điện tử vào hàng đợi." |
| 2:55–3:20 | HĐĐT & Công nợ, Kho & Xưởng | Xem hàng đợi hóa đơn, ô đỏ hàng sắp hết | "Worker gửi hóa đơn ở nền và tự thử lại khi nhà cung cấp lỗi, nên việc bán không bị kẹt. Hàng dưới ngưỡng tối thiểu được tô đỏ và báo cho Chủ." |
| 3:20–3:40 | Nhân viên & Nhật ký | Bấm **Kiểm tra toàn vẹn chuỗi** | "Mọi thao tác đều vào nhật ký nối chuỗi băm. Ai sửa lén trong cơ sở dữ liệu thì phép kiểm tra này chỉ ra đúng dòng bị sửa." |
| 3:40–4:05 | Điện thoại | Mở web trên điện thoại, cài app, tra `ban uong nuoc` | "Cùng một mã nguồn chạy trên điện thoại, cài được ra màn hình chính, mất mạng vẫn tra giá và lập đơn." |
| 4:05–4:40 | Terminal + slide 8–9 | Chạy `python -m pytest -q` (đã quay sẵn), mở tab Actions trên GitHub | "236 test chạy trên PostgreSQL thật, độ phủ 80 %, CI chạy ở mỗi lần push. Rà soát bảo mật đã sửa hai lỗi mức cao; tra giá p95 là 146 mili giây khi 10 người dùng cùng lúc." |
| 4:40–5:00 | Slide 11–12 | Đã làm / chưa làm, bước tiếp theo | "Phần còn lại là hóa đơn điện tử thật, thử trên điện thoại thật và cho cửa hàng dùng thử. Cảm ơn thầy và các bạn." |

**Lưu ý khi quay:**
- Không quay thông tin cá nhân hay dữ liệu thật của cửa hàng.
- Không mở file `.env`.
- Video dài hơn 10 MB thì để link Google Drive trong README, không đưa vào repo nộp bài.
