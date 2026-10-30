# BẢNG GIAO VIỆC — Mockup Nội thất Khanh Vân

Người giao việc & nghiệm thu: **Claude (Claude Code)**
Người thực hiện: **Antigravity**
File làm việc chính: `index.html`

---

## QUY TẮC LÀM VIỆC (Antigravity đọc kỹ trước khi làm)

1. **Mỗi lần chỉ làm 1 task**: lấy task đầu tiên từ trên xuống có trạng thái `TODO` hoặc `CẦN SỬA` (ưu tiên `CẦN SỬA`).
2. Khi bắt đầu, đổi trạng thái task đó thành `ĐANG LÀM`.
3. **Chỉ sửa đúng phạm vi task.** Không "tiện tay" sửa chỗ khác, không định dạng lại (reformat) toàn file, không đổi tên class/id ngoài phạm vi. Gặp vấn đề ngoài phạm vi thì ghi vào mục *Báo cáo*, không tự sửa.
4. **Không lách công cụ kiểm tra tự động** (ví dụ: ghi đè class Tailwind bằng `!important` để qua bộ kiểm tra của impeccable). Nếu công cụ báo lỗi mà task không yêu cầu sửa thì ghi lại trong báo cáo.
5. Trong `TASKS.md` chỉ được sửa **dòng Trạng thái** và **mục Báo cáo của Antigravity** của task đang làm.
6. Làm xong: đổi trạng thái thành `CHỜ DUYỆT` và viết báo cáo gồm: đã sửa những gì, ở màn hình nào, điểm nào chưa chắc chắn hoặc đã quyết định khác yêu cầu (kèm lý do).
7. **Không tự đánh dấu `XONG`.** Chỉ người duyệt được đánh dấu `XONG` hoặc `CẦN SỬA` (kèm nhận xét).
8. Không được xóa hoặc sửa thư mục `.review/` (dùng để đối chiếu khi nghiệm thu).

Trạng thái hợp lệ: `TODO` → `ĐANG LÀM` → `CHỜ DUYỆT` → `XONG` hoặc `CẦN SỬA`

---

## T01 — Thống nhất trạng thái đơn #KV261026001 giữa các màn hình
**Ưu tiên:** Cao · **Trạng thái:** `TODO`

**Vấn đề:** Cùng một đơn #KV261026001 nhưng màn hình thì nói "đang giữ chỗ, chờ tiền" (Màn 1, 3, 9), màn hình thì nói "đã xác nhận tay, đã thanh toán" (Màn 4, 5, 7, 8). Màn 1 vừa ghi "cần chủ duyệt xác nhận tiền tay #KV261026001" vừa ghi "Cô Vân đã xác nhận tay đơn #KV261026001 • 10 phút trước". Người chấm đồ án sẽ thấy mâu thuẫn.

**Cách sửa:**
- Giữ **#KV261026001 = đơn ĐÃ thanh toán bằng xác nhận tay** (giữ nguyên ở Màn 4, 5, 7, 8).
- Tạo đơn mới **#KV261027015** (cùng sản phẩm Bộ bàn ghế ăn 6 ghế Gỗ Sồi, 17.200.000 đ) là **đơn đang giữ chỗ, chờ khách chuyển khoản**. Thay mã ở:
  - Màn 1: thẻ "ĐANG GIỮ CHỖ / CHỜ TIỀN".
  - Màn 3: dòng sổ cái `GIU_CHO (30p)` và thẻ "ĐƠN ĐANG GIỮ CHỖ".
  - Màn 9 (POS): nhãn "Đơn 1", nội dung CK VietQR.
  - Màn 10 (điện thoại 1 và 2): mã đơn ở tiêu đề, dưới mã QR và trên nút xác nhận (nếu có).
- Màn 1, thẻ "CẦN CHỦ CỬA HÀNG DUYỆT (2 YÊU CẦU)": thay dòng "xác nhận tiền tay (#KV261026001 - 17.2tr)" bằng "1 đơn lệch tiền #KV261027005 (-200k) chờ xử lý" (khớp Màn 4). Vẫn giữ tổng là 2 yêu cầu.

**Tiêu chí nghiệm thu:**
- [ ] Không còn chỗ nào mô tả #KV261026001 là đang giữ chỗ / chờ tiền / chờ duyệt.
- [ ] #KV261027015 xuất hiện đúng ở các vị trí kể trên, số tiền 17.200.000 đ.
- [ ] Các số tổng (2 yêu cầu, 2 đơn giữ chỗ) vẫn đúng.
- [ ] Không có thay đổi nào ngoài các chỗ trên.

**Báo cáo của Antigravity:**
_(chưa có)_

**Nhận xét của người duyệt:**
_(chưa có)_

---

## T02 — Sửa số liệu phi thực tế và số lượng xưởng
**Ưu tiên:** Cao · **Trạng thái:** `TODO`

**Vấn đề:**
1. Màn 1: "DOANH THU THUẦN THÁNG NÀY: 7.081.590.000 đ" (hơn 7 tỷ) không khớp mức ~68 triệu/ngày của một cửa hàng (cả tháng chỉ khoảng 1,5–2 tỷ).
2. Màn 1: thẻ doanh thu **hôm nay** lại ghi "Tăng 40.8% so với **tháng trước**", tức là so ngày với tháng.
3. Màn 1 ghi "TỒN KHO THEO **3** NGUỒN XƯỞNG" nhưng các màn khác còn có **Xưởng Giường Thạch Thất** (Màn 1 phần hoạt động gần đây, Màn 2, Màn 3, Màn 5). Thực tế có 4 nguồn hàng.
4. Màn 5: "Tủ thờ 5.328tr" viết sai định dạng.

**Cách sửa:**
1. Đổi doanh thu tháng thành **1.481.590.000 đ**.
2. Đổi thành "Tăng 12,5% so với trung bình ngày tháng trước".
3. Thẻ tồn kho ở Màn 1: đổi tiêu đề thành "4 NGUỒN XƯỞNG", lưới `grid-cols-3` → `grid-cols-4`, thêm ô "4. Xưởng Giường Thạch Thất · 36 sản phẩm · Đủ hàng bán", theo đúng cấu trúc HTML của 3 ô hiện có.
   Màn 0, dòng "Quản lý tồn kho 3 xưởng" → "4 xưởng".
4. "Tủ thờ 5.328tr" → "Tủ thờ 5.328.000 đ".

**Tiêu chí nghiệm thu:**
- [ ] 4 điểm trên đã sửa, không còn chữ "3 xưởng" / "3 NGUỒN XƯỞNG".
- [ ] Ô xưởng thứ 4 dùng cùng class với 3 ô còn lại.
- [ ] Không có thay đổi ngoài các chỗ trên.

**Báo cáo của Antigravity:**
_(chưa có)_

**Nhận xét của người duyệt:**
_(chưa có)_

---

## T03 — Cho thanh điều hướng bấm được và đánh dấu đúng màn đang xem
**Ưu tiên:** Trung bình · **Trạng thái:** `TODO`

**Vấn đề:**
1. Thanh menu đỏ trong Màn 1–8 dùng `<span>` nên không bấm được.
2. Thanh chuyển nhanh cố định trên cùng (`<header>`) luôn tô trắng cả "0. Đăng nhập" lẫn "9. Quầy POS", không phản ánh màn đang xem.
3. Header là `fixed`, bấm link neo (`#screen-...`) thì phần đầu màn hình bị header che mất.

**Cách sửa:**
1. Đổi các `<span class="nav-item ...">` trong menu Màn 1–8 thành `<a href="#screen-...">` trỏ đúng màn tương ứng (1→`#screen-1-dashboard` … 8→`#screen-8-backup-print`). Giữ nguyên class.
2. Header: bỏ tô trắng cố định ở link "0." và "9.". Viết JS (đặt trong thẻ `<script>` có sẵn) dùng `IntersectionObserver` để tô trắng (`bg-white text-red-main`) link của màn đang hiển thị, đồng thời thêm `aria-current="true"` cho link đó.
3. Thêm `scroll-margin-top` (khoảng 72px, cao hơn header) cho các `section[id^="screen-"]`.

**Tiêu chí nghiệm thu:**
- [ ] Bấm mọi mục menu ở Màn 1–8 đều cuộn tới đúng màn.
- [ ] Khi cuộn trang, chỉ đúng 1 link trên header được tô sáng, đúng màn đang xem.
- [ ] Tiêu đề màn hình không bị header che sau khi bấm link.
- [ ] Không có lỗi trong Console.

**Báo cáo của Antigravity:**
_(chưa có)_

**Nhận xét của người duyệt:**
_(chưa có)_

---

## T04 — Gỡ phần CSS ghi đè class Tailwind
**Ưu tiên:** Trung bình · **Trạng thái:** `TODO`

**Vấn đề:** Trong `<style>` có các khối "Explicit padding utilities for static parser compliance", "Type scale hierarchy" và "Explicit container padding to satisfy Impeccable insets". Các khối này định nghĩa lại `.p-3`, `.p-4`, `.px-6`, `h1`, `h2`, `h3`… kèm `!important`, làm class Tailwind không còn đúng nghĩa (ví dụ `.p-3` thành `0.85rem 1rem`). Hệ quả: `h1` ở Màn 0 có `text-lg` nhưng bị ép thành 1.875rem, nhìn code không đoán được giao diện thật.

**Cách sửa:**
1. Xóa 3 khối CSS kể trên.
2. Chỗ nào thật sự cần khoảng cách hay cỡ chữ khác thì sửa trực tiếp bằng class Tailwind chuẩn ở phần tử đó (ví dụ `p-3` → `px-4 py-3`).
3. Mở trang so sánh trước và sau: bố cục không được vỡ, khác biệt chỉ nằm ở mức vài pixel.

**Tiêu chí nghiệm thu:**
- [ ] Trong `<style>` không còn selector nào trùng tên class Tailwind (`.p-*`, `.px-*`, `.py-*`) và không còn `h1/h2/h3 { … !important }`.
- [ ] Không còn `!important` nào chỉ để lách bộ kiểm tra.
- [ ] Báo cáo liệt kê những phần tử đã thêm class bù.

**Báo cáo của Antigravity:**
_(chưa có)_

**Nhận xét của người duyệt:**
_(chưa có)_

---

## T05 — Trợ năng (accessibility) cho form đăng nhập
**Ưu tiên:** Thấp · **Trạng thái:** `TODO`

**Vấn đề:** Ở Màn 0, các `<label>` không gắn với `<input>`. Ba nút chọn vai trò không báo trạng thái đang chọn. Hàm `selectRole()` ghi đè toàn bộ `className` nên nút đang chọn mất class `border border-red-main` so với lúc mới tải trang.

**Cách sửa:**
1. Thêm `for="login-username"` / `for="login-password"` cho label.
2. Thêm `aria-pressed="true|false"` cho 3 nút vai trò; `selectRole()` cập nhật `aria-pressed`.
3. Sửa `selectRole()` để bật/tắt class bằng `classList` thay vì gán `className`, sao cho nút đang chọn luôn giống hệt trạng thái lúc mới tải trang.

**Tiêu chí nghiệm thu:**
- [ ] Bấm vào chữ label thì con trỏ nhảy vào ô nhập tương ứng.
- [ ] Đổi vai trò qua lại nhiều lần: nút đang chọn luôn cùng kiểu dáng, `aria-pressed` đúng.

**Báo cáo của Antigravity:**
_(chưa có)_

**Nhận xét của người duyệt:**
_(chưa có)_

---

## T06 — Thống nhất biểu tượng (icon)
**Ưu tiên:** Thấp · **Trạng thái:** `TODO`

**Vấn đề:** Trang đã nạp Font Awesome nhưng chỉ dùng cho 1 icon QR; các chỗ khác dùng emoji (👤 Màn 1, 🛒 Màn 1, 📷 Màn 10). Ô VietQR ở Màn 9 chỉ là ô chữ, còn Màn 10 dùng icon QR.

**Cách sửa:** Thay emoji bằng icon Font Awesome tương ứng (`fa-user`, `fa-cart-shopping`, `fa-camera`). Ô VietQR ở Màn 9 dùng `fa-qrcode` giống Màn 10.

**Tiêu chí nghiệm thu:**
- [ ] Không còn emoji trong `index.html`.
- [ ] Icon có màu và cỡ hợp với chữ bên cạnh.

**Báo cáo của Antigravity:**
_(chưa có)_

**Nhận xét của người duyệt:**
_(chưa có)_
