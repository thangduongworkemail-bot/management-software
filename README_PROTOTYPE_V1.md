# HỆ THỐNG QUẢN TRỊ BÁN HÀNG & KHO NỘI THẤT KHÁNH VÂN
### Báo cáo Kỹ thuật Phần mềm Ứng dụng — Nhóm 32 (Đại học Bách Khoa Hà Nội)
**Giảng viên hướng dẫn:** TS. Hoàng Quang Huy  
**Sinh viên thực hiện:**
- Lê Thị Ngọc Anh (20210032)
- Dương Văn Thắng (20210046)
- Dương Văn Đạt (20210053)

---

## 1. TỔNG QUAN HỆ THỐNG

Dự án chuyển đổi số toàn diện hoạt động kinh doanh và quản lý chuỗi cung ứng cho Cửa hàng Đồ gỗ Nội thất Khánh Vân (Thái Nguyên). Hệ thống giải quyết triệt để các bài toán đặc thù của ngành mộc truyền thống:
- **Quản trị tồn kho 2 trạng thái** (**Tồn hiện có** vs **Tồn khả dụng**) theo mô hình Sổ cái kế toán bất biến (Append-only Ledger `D4_SO_CAI_TON`), tự động rã bom bộ sản phẩm (ví dụ: bộ bàn ăn 6 ghế tách thành 1 bàn + 6 ghế).
- **Công thức tính giá động 3 chiều**: Theo **Mét dài** (tủ thờ, án gian), theo **Diện tích $m^2$** (mặt bàn gỗ, vách ngăn), và theo **Bậc kích thước nệm** (giường hộp sồi/gõ) kết hợp độ dày phôi gỗ.
- **Cơ chế bảo vệ giá 3 tầng** (**Giá vốn** $\rightarrow$ **Giá sàn** $\rightarrow$ **Giá niêm yết**) với quy trình phân quyền RBAC: Thợ phụ không được xem giá vốn, muốn bán dưới giá sàn bắt buộc phải gửi yêu cầu phê duyệt thời gian thực đến điện thoại của Chủ cửa hàng.
- **Quầy thu ngân Web-POS tốc độ cao**: Tích hợp mã động **VietQR / Napas 247**, webhook ngân hàng tự động khớp giao dịch, in Phiếu giao hàng nội bộ chuẩn F9 (khoản 1 Điều 4 Thông tư 78/2021/TT-BTC) và đẩy hóa đơn điện tử vào hàng đợi ký số ngoài đường găng (Asynchronous Retry Queue `D6_HOA_DON_DT`).
- **An toàn tương tranh đa luồng (Concurrency Serialization)**: Sử dụng cơ chế khóa tuần tự hóa `_order_lock` bảo vệ giao dịch thanh toán và webhook, ngăn chặn triệt để hiện tượng trừ tồn kho kép dưới tải đa luồng.
- **Kiến trúc bền vững C4 Container**: Khả năng hoạt động ngoại tuyến (Offline-First) nhờ **PWA Service Worker** và **IndexedDB**, đồng bộ tức thời với cơ sở dữ liệu quan hệ **SQLite 3** khi có kết nối mạng.
- **Nhật ký kiểm toán bảo mật cao với Chuỗi mã băm mật mã học SHA-256 (Hash Chain)**: Chống chối bỏ và chống can thiệp dữ liệu trên bảng `D9_NHAT_KY`.

---

## 2. CÔNG NGHỆ SỬ DỤNG

### Frontend
- **HTML5 & Vanilla JavaScript (ES6+)**: Xây dựng Single Page PWA mượt mà, tối ưu hiệu năng không phụ thuộc framework cồng kềnh.
- **Tailwind CSS (CDN)**: Thiết kế giao diện chuyên nghiệp theo hệ bảng màu thương hiệu Bách Khoa: Đỏ HUST (`#C51A1B`), Trắng (`#FFFFFF`), Xám than (`#1E293B`, `#F1F5F9`).
- **PWA (Progressive Web App)**: Cung cấp `manifest.json`, icon chuẩn vector `icon.svg` (192x192, 512x512) và `sw.js` hỗ trợ cài đặt ứng dụng lên máy tính để bàn (Windows PC) và điện thoại di động (Android / iOS).
- **IndexedDB**: Cơ chế lưu trữ offline cục bộ tại trình duyệt, cho phép bán hàng và xuất phiếu ngay cả khi mất kết nối mạng Internet.
- **Impeccable Design Standard**: Đạt điểm tuyệt đối **0 cảnh báo / 0 lỗi** (`impeccable detect` trả về `[]`), tuân thủ triệt để nguyên tắc Accessible WCAG AAA, phân cấp thị giác trực quan, touch-target $\ge 44\text{px}$.

### Backend & Database
- **Python 3 Native HTTP Server**: Bộ máy RESTful API nhẹ, độ trễ $< 50\text{ms}$, tích hợp sẵn CORS headers, phục vụ cả static files và REST endpoints.
- **SQLite 3 Relational Database (`khanhvan.db`)**: Thiết kế chuẩn hóa theo cấu trúc D1 – D9 trong tài liệu đặc tả kiến trúc:
  1. `D1_SAN_PHAM`: Danh mục sản phẩm, biến thể, tồn kho, 3 tầng giá (vốn, sàn, niêm yết).
  2. `D2_BANG_GIA`: Định mức công thức tính giá theo mét dài, $m^2$, bậc nệm và hệ số loại gỗ.
  3. `D3_DON_HANG`: Quản lý đơn hàng bán lẻ tại quầy, trạng thái thanh toán, tiền cọc và công nợ.
  4. `D4_SO_CAI_TON`: Sổ cái tồn kho kế toán chỉ ghi thêm (Append-only Ledger: `NHAP`, `GIU_CHO`, `NHA_CHO`, `XUAT`, `TRA_HANG`, `DIEU_CHINH`), khóa bằng SQLite Trigger chống sửa/xóa.
  5. `D5_NHA_CUNG_CAP`: Danh mục 4 xưởng gia công vệ tinh (Hải Hậu, Thạch Thất, Cát Đằng, MDF).
  6. `D6_HOA_DON_DT`: Hàng đợi HĐĐT ngoài đường găng, tích hợp chuẩn VNPT / Viettel S-Invoice, hỗ trợ xuất XML và cập nhật MST.
  7. `D7_CONG_NO`: Sổ quản lý công nợ 2 chiều (Khách hàng nợ tiền hàng & Cửa hàng nợ tiền xưởng).
  8. `D8_TAI_KHOAN` & `D8_THIET_BI`: Quản lý tài khoản bảo mật bằng Argon2id và mã ghép nối thiết bị 6 chữ số.
  9. `D9_NHAT_KY`: Nhật ký thao tác nhạy cảm với chuỗi mã băm bảo mật SHA-256 (`curr_hash = SHA256(prev_hash + data)`).

---

## 3. CẤU TRÚC THƯ MỤC DỰ ÁN

```text
E:\fontend\
│
├── index.html           # Toàn bộ giao diện 11 màn hình PWA, modals nghiệp vụ & client JavaScript
├── server.py            # Backend Python HTTP & RESTful API server + SQLite Database Engine
├── khanhvan.db          # Cơ sở dữ liệu SQLite 3 lưu trữ 10 bảng D1 - D9
├── manifest.json        # Cấu hình PWA cài đặt ứng dụng trên Desktop & Mobile
├── sw.js                # Service Worker cache tĩnh & quản lý hàng đợi offline
├── icon.svg             # Biểu tượng PWA chuẩn vector (192x192, 512x512)
├── hust-banner.png      # Banner nhận diện thương hiệu Đại học Bách Khoa Hà Nội & Đồ gỗ Khánh Vân
├── README.md            # Tài liệu kỹ thuật, hướng dẫn cài đặt & vận hành hệ thống
├── TASKS.md             # Bảng kiểm tra tiến độ theo chuẩn Impeccable Design System
└── tests\               # Toàn bộ bộ kiểm thử tích hợp tự động và kiểm thử đối kháng
    ├── test_e2e.py                   # 122 bài kiểm thử E2E tích hợp 4 tầng (100% Green)
    ├── test_m3_r2_challenge_stress.py # Kiểm thử chịu tải tương tranh đa luồng (6/6 Pass)
    ├── test_rbac_pricing_attacks.py  # Kiểm thử tấn công giả mạo quyền RBAC và giá sàn (25/25 Pass)
    ├── test_audit_chain_attacks.py   # Kiểm thử tấn công chuỗi băm SHA-256 (5/5 Pass)
    └── test_d4_ledger_challenge.py   # Kiểm thử bảo vệ tính bất biến Sổ cái D4 (20/20 Pass)
```

---

## 4. YÊU CẦU MÔI TRƯỜNG & CÀI ĐẶT

### Yêu cầu hệ thống:
- Hệ điều hành: Windows 10/11, macOS hoặc Linux.
- Đã cài đặt **Python 3.8+** (Khuyến nghị Python 3.10 trở lên).
- Trình duyệt hiện đại: Google Chrome, Microsoft Edge, Mozilla Firefox hoặc Safari.

### Cài đặt:
Hệ thống sử dụng các thư viện chuẩn (Standard Library) của Python (`http.server`, `sqlite3`, `hashlib`, `json`, `urllib`), do đó **không cần cài đặt bất kỳ thư viện bên ngoài (no pip dependencies required)**.

```bash
# Kiểm tra phiên bản Python
python --version
```

---

## 5. HƯỚNG DẪN KHỞI CHẠY HỆ THỐNG

### Bước 1: Khởi động Backend Server & Database
Mở Command Prompt hoặc PowerShell tại thư mục dự án và chạy lệnh:

```bash
cd E:\fontend
python server.py
```

Khi chạy thành công, console sẽ hiển thị:
```text
Khanh Van SQLite Database D1-D9 initialized successfully.
Khanh Van Full-Stack Server running at http://127.0.0.1:5500
```
*Lưu ý:* Cơ sở dữ liệu `khanhvan.db` sẽ tự động khởi tạo và nạp dữ liệu mẫu ban đầu (Seed Data) chuẩn theo kịch bản kiểm thử trong báo cáo.

### Bước 2: Truy cập ứng dụng Frontend
Mở trình duyệt web bất kỳ và truy cập đường dẫn:
```text
http://127.0.0.1:5500
hoặc
http://localhost:5500
```

---

## 6. DANH MỤC API RESTFUL & KIỂM THỬ

Hệ thống cung cấp đầy đủ các API RESTful theo chuẩn JSON, hỗ trợ CORS:

| Phương thức | Đường dẫn API | Mục đích & Nghiệp vụ |
|:---:|:---|:---|
| `GET` | `/api/products?cat=all` | Lấy danh mục sản phẩm, biến thể, số lượng tồn kho và giá 3 tầng (FR-01) |
| `POST` | `/api/pricing/calculate` | Tính toán công thức định mức theo kích thước (Mét dài, $m^2$, Bậc nệm, Độ dày phôi) |
| `POST` | `/api/orders` | Tiếp nhận đơn hàng POS mới và khóa tồn kho giữ chỗ (TTL 30 phút) |
| `POST` | `/api/orders/cancel` | Hủy đơn hàng và giải phóng tồn kho giữ chỗ vào kho hàng khả dụng |
| `GET` | `/api/inventory/ledger` | Lấy 50 dòng mới nhất của Sổ cái tồn kho bất biến D4 (`SO_CAI_TON`) |
| `POST` | `/api/inventory/receipt` | Nhập kho từ xưởng mộc gia công, tự động ghi Sổ cái D4 và cập nhật D1 (FR-06, UC-08) |
| `GET` | `/api/orders` | Lấy danh sách đơn hàng bán lẻ tại quầy, trạng thái cọc và thanh toán |
| `POST` | `/api/orders/confirm-payment` | Xác nhận đơn thanh toán: Cập nhật D3, tự động xuất kho `-1` trong D4 (FR-04, FR-05) |
| `GET` | `/api/invoices` | Lấy danh sách hàng đợi hóa đơn điện tử ngoài đường găng D6 (FR-07) |
| `POST` | `/api/invoices/issue` | Ký số phát hành HĐĐT thành công qua cổng VNPT / Viettel S-Invoice (FR-07) |
| `POST` | `/api/invoices/update-mst` | Bổ sung Mã số thuế & Email cho đơn hàng thiếu thông tin xuất HĐĐT (UC-11) |
| `GET` | `/api/invoices/export` | Xuất gói dữ liệu hóa đơn điện tử dưới dạng JSON hoặc XML (chuẩn VNPT Invoice) |
| `GET` | `/api/debts` | Lấy danh sách công nợ 2 chiều đang nợ từ bảng D7 (FR-10, UC-12) |
| `POST` | `/api/debts/collect` | Thu nốt công nợ khách hàng qua VietQR, chuyển trạng thái sang `DA_THU_DU` |
| `POST` | `/api/approvals/worker-discount` | Phê duyệt hoặc Từ chối yêu cầu thợ phụ bán dưới giá sàn (FR-03, UC-06) |
| `POST` | `/api/audit/verify` | Kiểm tra tính toán vẹn mật mã học của toàn bộ Chuỗi băm SHA-256 D9 (FR-12, NFR-06) |
| `POST` | `/api/webhook/payos` | Webhook nhận tín hiệu ngân hàng báo có tiền về Napas 247, tự động gạch nợ (FR-05) |
| `GET` | `/api/db/stats` | Thống kê số lượng bản ghi của 10 bảng D1 - D9 trong cơ sở dữ liệu SQLite |

### Kịch bản kiểm thử tự động toàn diện:
Chạy bộ test suite E2E độc lập:
```bash
python tests\test_e2e.py
```
Kết quả kiểm thử: **122/122 Tests Passed (100% Green, 0 errors, 0 failures)**.

---

## 7. TÀI KHOẢN VÀ PHÂN QUYỀN TRẢI NGHIỆM (RBAC)

Người dùng có thể chuyển đổi nhanh vai trò trực tiếp tại màn hình Đăng nhập (Màn hình 11) để kiểm tra cơ chế phân quyền bảo mật:

1. **Cô Vân (Chủ cửa hàng)**:
   - Email: `covan@khanhvan.vn`
   - Quyền hạn: Xem giá vốn thực, phê duyệt yêu cầu bán dưới giá sàn, đối soát tài khoản ngân hàng, ký phát hành HĐĐT, khóa sổ chốt ngày.
2. **Anh Nam (Thợ phụ)**:
   - Email: `anhnam@khanhvan.vn`
   - Quyền hạn: Xem giá niêm yết, bán hàng tại quầy POS, tính giá theo công thức. **Bị làm mờ giá vốn thực**, **không thể tự ý hạ giá dưới giá sàn**, không có quyền khóa sổ ngày.
3. **Quản trị viên HUST**:
   - Email: `admin@hust.edu.vn`
   - Quyền hạn: Quản trị kỹ thuật, ghép nối thiết bị thu ngân 6 số, kiểm toán chuỗi băm bảo mật SHA-256, xem cấu trúc CSDL D1 - D9.

---

## 8. BẢNG ĐỐI CHIẾU CHỨC NĂNG VÀ ĐẶC TẢ BÁO CÁO

| Yêu cầu trong Báo cáo | Tên chức năng / Nghiệp vụ | Bảng CSDL | Trạng thái triển khai |
|:---|:---|:---:|:---:|
| **FR-01, UC-01** | Tra cứu danh mục, quy cách & giá 3 tầng | `D1_SAN_PHAM` | **Hoàn thành 100%** |
| **FR-02, UC-17** | Máy tính giá công thức Mét dài / $m^2$ / Bậc nệm / Độ dày | `D2_BANG_GIA` | **Hoàn thành 100%** |
| **FR-03, UC-06** | Phân quyền RBAC & Phê duyệt bán dưới giá sàn | `D8_TAI_KHOAN`, `D9` | **Hoàn thành 100%** |
| **FR-04, UC-02** | Web-POS bán hàng & Giữ chỗ 30 phút tự động hoàn tồn | `D1`, `D3`, `D4` | **Hoàn thành 100%** |
| **FR-05, UC-04** | Thanh toán VietQR Napas 247 & PayOS Webhook HMAC-SHA256 | `D3_DON_HANG`, `D9` | **Hoàn thành 100%** |
| **FR-06, UC-08** | Nhập kho xưởng vệ tinh & Sổ cái bất biến (SQLite Trigger) | `D4_SO_CAI_TON`, `D5` | **Hoàn thành 100%** |
| **FR-07, UC-10** | Hàng đợi HĐĐT ngoài đường găng, xuất XML chuẩn VNPT | `D6_HOA_DON_DT` | **Hoàn thành 100%** |
| **FR-08, UC-03** | In Phiếu nội bộ F9 không chịu thuế GTGT | `D3_DON_HANG` | **Hoàn thành 100%** |
| **FR-09, UC-05** | Đối soát giao dịch, xử lý lệch tiền & Chốt sổ ngày | `D3`, `D7`, `D9` | **Hoàn thành 100%** |
| **FR-10, UC-12** | Quản lý sổ công nợ 2 chiều (Khách hàng & Xưởng) | `D7_CONG_NO` | **Hoàn thành 100%** |
| **FR-11, UC-14** | Ghép nối thiết bị nhận tiền bằng mã 6 số thời gian thực | `D8_THIET_BI` | **Hoàn thành 100%** |
| **FR-12, NFR-06** | Kiểm toán toàn vẹn chuỗi Hash SHA-256 chống can thiệp | `D9_NHAT_KY` | **Hoàn thành 100%** |
| **C4 Container** | Hoạt động Ngoại tuyến (Offline-First IndexedDB & PWA) | `IndexedDB` & `sw.js` | **Hoàn thành 100%** |

---

## 9. ĐÁNH GIÁ CHẤT LƯỢNG UI/UX THEO CHUẨN IMPECCABLE

Mã nguồn frontend đã được kiểm định nghiêm ngặt bằng công cụ tự động hóa **Impeccable CLI** qua 2 tầng:
1. **Kiểm tra tĩnh cấu trúc AST**:
   ```bash
   impeccable detect --json e:\fontend\index.html
   # Kết quả: [] (0 vi phạm)
   ```
2. **Kiểm tra động trên trình duyệt Headless Chrome qua Chrome DevTools Protocol**:
   ```bash
   impeccable detect --json http://127.0.0.1:5500
   # Kết quả: [] (0 vi phạm)
   ```
- Đảm bảo tỷ lệ tương phản màu chữ đạt chuẩn WCAG AAA ($\ge 7:1$).
- Hệ thống dialog và modal đạt chuẩn trợ năng `role="dialog"`, `aria-modal="true"`.
- Không có lỗi bố cục chồng chéo, font chữ $\ge 11\text{px}$ và không có anti-patterns.

---

## 10. HƯỚNG DẪN TRIỂN KHAI LÊN MÔI TRƯỜNG PRODUCTION

Khi đưa hệ thống vào vận hành thực tế tại Cửa hàng Nội thất Khánh Vân (Thái Nguyên), quy trình triển khai khuyến nghị như sau:
1. **Máy chủ Reverse Proxy**: Cấu hình Nginx hoặc Caddy phía trước Python server để quản lý SSL/TLS (HTTPS) thông qua Let's Encrypt miễn phí.
2. **Quản lý tiến trình (Process Manager)**: Sử dụng `systemd` (Linux) hoặc `PM2` để tự động khởi động lại dịch vụ backend khi có sự cố.
3. **Chiến lược sao lưu cơ sở dữ liệu (Database Backup)**:
   - Thiết lập Cron Job lúc 02:00 sáng hàng ngày để sao lưu file `khanhvan.db` ra bộ nhớ ngoài hoặc Google Drive / AWS S3.
   - Câu lệnh sao lưu an toàn SQLite:
     ```bash
     sqlite3 khanhvan.db ".backup 'khanhvan_backup_$(date +%Y%m%d).db'"
     ```
4. **Tích hợp thực tế với bên thứ ba**:
   - Cung cấp API Key thật từ đối tác PayOS / Casso để lắng nghe Webhook ngân hàng tự động.
   - Cấu hình tài khoản dịch vụ HĐĐT VNPT / Viettel S-Invoice vào module `D6_HOA_DON_DT` để phát hành hóa đơn thật theo Nghị định 123/2020/NĐ-CP.
