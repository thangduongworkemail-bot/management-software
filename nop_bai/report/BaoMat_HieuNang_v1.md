# Rà soát bảo mật, hiệu năng và đánh giá AI v1 — noi_that_173820_n32

Phiên bản: 24/11/2026, làm sớm cho Tuần 13.
Phụ trách: 202414375 (backend), 202414028 (frontend).

## 1. Phương pháp

| Hạng mục | Cách kiểm tra |
|---|---|
| Xác thực, phân quyền | Gọi lần lượt mọi endpoint trong OpenAPI (82 đường dẫn, 92 thao tác) mà không có token, đối chiếu danh sách endpoint công khai. Test tự động `test_moi_endpoint_khac_deu_doi_dang_nhap` lặp lại phép kiểm tra này ở mỗi lần chạy CI |
| Lộ dữ liệu nội bộ | Thợ không được nhận `gia_von`, `gia_san`: `test_api.py`, `test_hang_mau_bo_sung.py`, `test_cong_thuc_gia.py` |
| Khóa bí mật, cấu hình | Đọc `config.py`, `.env.example`, `docker-compose.yml`; quét mã nguồn bằng các mẫu regex của CI lớp (`validate_submission.py`) |
| Dữ liệu đầu vào | Đọc mọi chỗ ghép chuỗi SQL; kiểm tra Pydantic model của các router; kiểm tra tải tệp lên |
| Thư viện | `pip-audit` trên `requirements.txt`; `npm audit` cho frontend (tách thư viện chạy trong trình duyệt và công cụ build) |

## 2. Phát hiện và xử lý

| # | Phát hiện | Mức | Đã xử lý | Bằng chứng |
|---|---|---|---|---|
| B1 | Khóa ký JWT mặc định (`khanhvan-dev-secret-…`) nằm trong mã nguồn công khai. Máy nào không đặt `JWT_SECRET` (kể cả bản demo qua Internet) đều cho phép người ngoài tự ký token vai trò Chủ. `.env.example` và `docker-compose.yml` cũng có khóa mẫu | **Cao** | Bỏ khóa mặc định. Không đặt `JWT_SECRET` thì mỗi CSDL tự sinh khóa ngẫu nhiên 48 byte, lưu trong `cau_hinh_he_thong`. Ba giá trị từng công khai bị bỏ qua nếu ai đó vẫn đặt | `test_token_ky_bang_khoa_cong_khai_bi_tu_choi` (3 khóa), `test_khoa_tu_sinh_luu_trong_csdl_va_on_dinh`, `test_jwt_secret_dat_bang_gia_tri_mau_thi_bi_bo_qua` |
| B2 | Webhook PayOS chấp nhận khóa demo công khai cả khi chạy thật: ai cũng giả được báo "tiền về" để chốt đơn | **Cao** | Khi `DEV_MODE=0` mà khóa vẫn là khóa demo, webhook trả 503 `PAYOS_CHUA_CAU_HINH` | `test_webhook_payos_tu_choi_khoa_demo_khi_chay_that` |
| B3 | Đăng nhập không giới hạn số lần sai (dò mật khẩu) | Trung bình | Sai 5 lần trong 15 phút với cùng cặp (tài khoản, IP) thì tạm khóa cặp đó và ghi nhật ký `TAM_KHOA_DANG_NHAP`. Khóa theo cặp nên kẻ dò từ một máy không khóa được Chủ ở máy khác | `test_sai_mat_khau_5_lan_thi_tam_khoa_rieng_cap_tai_khoan_va_may` |
| B4 | Trang đăng nhập luôn hiện nút chọn nhanh tài khoản demo, kèm mật khẩu, kể cả khi chạy thật | Trung bình | Chỉ hiện khi máy chủ báo `che_do_demo` (DEV_MODE=1) qua `/api/suc-khoe` | `test_suc_khoe_bao_che_do_demo` |
| B5 | Thư viện có lỗ hổng đã công bố. Backend: PyJWT 2.10.1 (4 mã), Starlette 0.46.2 kéo theo FastAPI 0.115.12 (8 mã), pytest 8.3.5. Frontend chạy trên trình duyệt: Vue 3.5.13 (mức cao). Công cụ build: postcss, Vite 6.3.5, serialize-javascript (qua vite-plugin-pwa), tinypool (qua vitest 3, mức nghiêm trọng), sharp 0.34 | Cao | Nâng: FastAPI 0.165.0 (Starlette 1.10.0), PyJWT 2.15.0, pytest 9.0.3, Vue 3.5.46, Vite 6.4.6, postcss 8.5.33, vite-plugin-pwa 1.3.0, vitest 5.1.1, sharp 0.35.5. Sau khi nâng: toàn bộ test đạt, máy chủ thật khởi động và chạy đúng | `pip-audit`: *No known vulnerabilities found*. `npm audit --omit=dev`: *0 vulnerabilities* |
| B6 | Luồng LISTEN realtime bị "hồi sinh" khi máy chủ khởi động lại trong cùng tiến trình, đẩy sự kiện vào vòng lặp đã đóng | Thấp (độ tin cậy) | Mỗi luồng một cờ dừng riêng; bỏ sự kiện khi vòng lặp đã đóng | `test_worker.py` chạy với `-W error::RuntimeWarning` không còn cảnh báo |

## 3. Các điểm đã đạt, không cần sửa

- **Phân quyền:** 85/92 thao tác bắt buộc đăng nhập và kiểm tra vai trò (Chủ, Thợ, Quản trị). 7 thao tác công khai đều có cơ chế riêng:

  | Endpoint công khai | Cơ chế bảo vệ |
  |---|---|
  | Đăng nhập | Giới hạn số lần sai |
  | `/api/suc-khoe` | Chỉ trả trạng thái |
  | Báo giá công khai | Mã chia sẻ ngẫu nhiên, không có giá vốn |
  | Webhook PayOS | Chữ ký HMAC |
  | Ghép nối thiết bị | Mã ghép nối một lần do Chủ tạo |
  | Máy nhận tiền (2 endpoint) | Chữ ký HMAC kèm dấu thời gian chống phát lại |

  Tải tệp lên chỉ nhận URL do máy chủ ký, có hạn dùng.
- **Không lộ giá nội bộ:** API không bao giờ trả giá vốn hay giá sàn cho Thợ, kể cả qua tìm kiếm, tính giá, đồng bộ ngoại tuyến hay báo giá.
- **SQL:** mọi giá trị đều truyền qua tham số. Các đoạn ghép chuỗi chỉ dùng hằng số hoặc tên cột trong danh sách cho phép (`TRUONG_SUA`, `COT_CONG_THUC`).
- **Mật khẩu:** băm bằng Argon2id. Đổi mật khẩu cần mật khẩu cũ. Không tự khóa được tài khoản của chính mình.
- **Tệp tải lên:** tối đa 10 MB. Ảnh minh họa chỉ nhận JPG, PNG, WebP, GIF. Tên tệp lưu do máy chủ sinh.
- **Nhật ký:** chỉ ghi thêm, nối chuỗi băm SHA-256, có job kiểm tra toàn vẹn hằng đêm.
- **CORS:** chỉ mở cho origin của app gốc, không bật `allow_credentials`. API dùng header Bearer, không dùng cookie, nên không bị CSRF.

## 4. Còn tồn tại và hướng xử lý

| Vấn đề | Mức | Hướng xử lý |
|---|---|---|
| 4 lỗ hổng mức trung bình của `minimatch` trong `workbox-build` (qua vite-plugin-pwa bản mới nhất 1.3.0) | Thấp: chỉ dùng lúc build, không chạy trên máy chủ hay trình duyệt | Theo dõi bản vá của workbox |
| Token WebSocket truyền qua query string, có thể xuất hiện trong log truy cập | Thấp | Đổi sang gửi token trong tin nhắn đầu tiên sau khi kết nối |
| Bộ đếm lần đăng nhập sai nằm trong bộ nhớ: khởi động lại thì mất; chạy nhiều tiến trình API thì mỗi tiến trình đếm riêng | Thấp với cách triển khai một tiến trình hiện tại | Chuyển sang bảng trong CSDL nếu chạy nhiều tiến trình |
| Tải tệp lên đọc hết nội dung rồi mới kiểm tra 10 MB | Thấp: URL tải lên phải do máy chủ ký | Kiểm tra `Content-Length` trước khi đọc |
| Bản demo qua Internet chạy `DEV_MODE=1`: có nút mô phỏng tiền về và tài khoản demo | Chấp nhận cho demo, chỉ có dữ liệu mẫu | Chạy thật: `DEV_MODE=0`, đổi mật khẩu 3 tài khoản mẫu, đặt `PAYOS_CHECKSUM_KEY` thật |

## 5. Hiệu năng

**Môi trường:**
- Máy phát triển Windows 10 chạy cùng lúc máy chủ API (uvicorn, một tiến trình) và PostgreSQL 17.11.
- Python 3.13.2 với FastAPI 0.165.0.
- Dữ liệu mẫu có 41 mặt hàng.
- Đo bằng `backend/scripts/do_hieu_nang.py`, 10 luồng gọi đồng thời, mỗi loại 300 yêu cầu.
- Phần ghi chạy 100 lần, mỗi lần ROLLBACK.

| Thao tác | p50 (ms) | p95 (ms) | Lớn nhất (ms) | Thông lượng | Lỗi |
|---|---:|---:|---:|---:|---:|
| Tra giá `tim-kiem` (10 từ khóa khác nhau) | 64,9 | 146,2 | 254,2 | 133 yêu cầu/s | 0 |
| Tính giá hàng đặt riêng `tinh-gia` | 33,7 | 43,5 | 89,7 | 282 yêu cầu/s | 0 |
| Trang tổng quan của Chủ | 60,3 | 105,8 | 188,4 | 152 yêu cầu/s | 0 |
| Tải danh mục cho chế độ ngoại tuyến | 130,8 | 181,2 | 254,9 | 75 yêu cầu/s | 0 |
| Bán 1 món, thu đủ tiền mặt, chốt đơn (xuất kho, phiếu bán, hàng đợi HĐĐT, nhật ký) | 26,0 | 30,9 | 130,9 | 35 đơn/s (một luồng) | 0 |

**Đối chiếu yêu cầu:**
- **NFR-02** đạt cả hai vế, với dư địa lớn:
  - tra giá (yêu cầu dưới 1 giây): p95 là 146 ms khi 10 người tra cùng lúc;
  - tạo đơn và trừ kho (yêu cầu dưới 2 giây): p95 là 31 ms.
- Với 20.000 mặt hàng, `test_tim_kiem_20000_bien_the_duoi_1_giay` vẫn đạt dưới 1 giây.
- Cửa hàng có 1 chủ và 1–2 thợ, nên tải thật thấp hơn nhiều so với 10 người dùng đồng thời.
- Chốt đơn mất khoảng 26 ms, gồm khóa hàng theo thứ tự id, ghi sổ cái, phiếu bán, hàng đợi HĐĐT và nhật ký chuỗi băm.

**Giới hạn của phép đo:**
- Máy chủ và CSDL nằm trên cùng một máy, không qua mạng thật hay Cloudflare.
- Chưa đo trên máy chủ thuê (Render).
- Chưa đo khi Worker gửi HĐĐT cùng lúc.

## 6. Đánh giá AI

**Không áp dụng.** Sản phẩm không có mô-đun AI hay mô hình học máy. Các chức năng nghe giống "thông minh" đều là luật tất định, kiểm thử được bằng test thường:
- **Tra giá tiếng Việt:** bỏ dấu, từ đồng nghĩa, mã kích thước, chỉ mục trigram của PostgreSQL.
- **Định giá:** công thức mét dài, m², bậc kích thước.
- **Đọc kích thước:** quy tắc phân tích chuỗi.

AI chỉ được dùng trong quá trình phát triển (xem README mục 6). Mọi phần do AI hỗ trợ đều phải qua bộ test tự động.

## 7. Cách chạy lại

```bash
cd src/backend
python -m pytest -q tests/test_bao_mat.py           # kiểm tra bảo mật tự động (9 test)
pip install pip-audit && pip-audit -r requirements.txt
cd ../frontend && npm audit --omit=dev
cd ../backend && uvicorn app.main:app --port 8000 &   # rồi:
python scripts/do_hieu_nang.py --url http://127.0.0.1:8000 --luong 10 --so-lan 300 --lan-ghi 100
```
