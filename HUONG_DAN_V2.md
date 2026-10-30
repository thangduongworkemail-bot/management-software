# Hệ thống hỗ trợ quản lý & bán hàng Nội thất gỗ Khanh Vân — Bản 2 (PostgreSQL + FastAPI + Vue PWA)

Bản 2 viết lại toàn bộ theo đặc tả kỹ thuật: PostgreSQL, FastAPI, Retry Worker riêng, PWA Vue 3
offline-first. Bản prototype cũ (`server.py`, `index.html`, SQLite) vẫn để nguyên ở thư mục gốc để đối chiếu.

## 1. Cấu trúc monorepo

```text
database/migrations/   DDL PostgreSQL: 001 bảng & ràng buộc, 002 trigger, 003 chỉ mục tìm kiếm & view,
                       004 thông số hàng hóa chi tiết + thông tin xưởng
backend/app/
  domain/              Logic thuần, không phụ thuộc CSDL: đọc kích thước, 3 công thức giá, VietQR
  adapters/            Kết nối ngoài: HĐĐT (Mock/VNPT/Viettel), PayOS, lưu file (Local/S3), thông báo
  services/            Nghiệp vụ: catalog, inventory, orders, payments, invoices, devices, sync, reports
  routers/             REST API (FastAPI); realtime.py = WebSocket qua LISTEN/NOTIFY
  worker.py            Tiến trình nền: Retry Queue HĐĐT, nhả giữ chỗ TTL, thông báo, kiểm tra toàn vẹn đêm
  bootstrap.py         Tạo role + database, chạy migration, nạp seed
backend/tests/         pytest: parser, công thức giá, bất biến sổ cái, luồng nghiệp vụ, API
frontend/src/          Vue 3 + Tailwind + Dexie (IndexedDB) + vite-plugin-pwa
docker-compose.yml     db + api + worker
scripts/               setup.ps1, start.ps1, test.ps1 (Windows)
```

## 2. Chạy trên Windows (không Docker)

Yêu cầu: Python 3.11+, Node.js 20+, PostgreSQL 17 (đã cài qua winget, superuser `postgres` / mật khẩu `postgres`).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # cài thư viện, tạo CSDL, migrate, seed, build PWA
powershell -ExecutionPolicy Bypass -File scripts\start.ps1     # chạy API + Worker -> http://localhost:8000
powershell -ExecutionPolicy Bypass -File scripts\test.ps1      # toàn bộ kiểm thử
```

Nạp lại dữ liệu mẫu từ đầu: `scripts\setup.ps1 -Reset`. Tài liệu API tự sinh: http://localhost:8000/docs

Phát triển giao diện có hot-reload: chạy API như trên, rồi `cd frontend && npm run dev` → http://localhost:5173
(Vite tự chuyển `/api`, `/ws` sang cổng 8000).

## 3. Chạy bằng Docker

```bash
docker compose up -d --build     # http://localhost:8000
```

## 4. Tài khoản demo

| Tài khoản | Mật khẩu | Vai trò |
|---|---|---|
| `covan` | `KhanhVan@2026` | Chủ cửa hàng — toàn quyền, duyệt giá sàn, xác nhận tay, chốt sổ |
| `anhnam` | `AnhNam@2026` | Thợ / Nhân viên — tra giá niêm yết, lập đơn, phiếu nhập; không thấy giá vốn/giá sàn |
| `admin` | `Admin@2026` | Quản trị — tài khoản, thiết bị, nhật ký |

## 5. Dữ liệu mẫu (khớp báo cáo)

- 3 xưởng: Đồ Thờ Cát Đẳng, Giường & Bàn Ghế Hải Hậu, Kho Gỗ Công Nghiệp MDF (3 phiếu nhập đầu kỳ).
- Mặt hàng: `BO-BANAN-SOI-1600` (bộ 1 bàn + 6 ghế), `GUONG-HOP-SOI-1800`, `TUTHO-MIT-1270` (đặt theo mét dài),
  cùng giường đặt theo bậc, mặt bàn đặt theo m², tủ áo/kệ tivi MDF, án gian gỗ gõ.
- Đơn: `#KV261026001` (đã xác nhận tay *4817, chờ xuất HĐĐT), `#KV261026002` (tủ thờ 2m4 = 5.328.000 đ, cọc 2 triệu),
  `#KV261027005` (chuyển 17,0 tr cho đơn 17,2 tr — lệch tiền), `#KV261027006` (Anh Nam xin bán dưới giá sàn).

## 6. Các quyết định thiết kế chính

| Yêu cầu | Cách hiện thực |
|---|---|
| Sổ cái tồn kho & nhật ký bất biến | Trigger `BEFORE UPDATE/DELETE/TRUNCATE` ném lỗi `KV001` (002_triggers.sql) |
| Chuỗi băm nhật ký | Trigger tự tính `current_hash = SHA256(prev_hash | nội dung)`; khóa advisory + cấp id sau khóa nên ghi đồng thời vẫn đúng thứ tự; hàm `kiem_tra_chuoi_nhat_ky()` phát hiện sửa/xóa |
| Tồn hiện có / khả dụng | Tính từ sổ cái trong view `v_ton_kho`; XUAT, NHA_CHO lưu số âm nên "NHAP + TRA_HANG + DIEU_CHINH − XUAT" là một phép cộng |
| Không bán vượt tồn | `SELECT … FOR UPDATE` các biến thể theo thứ tự id trước khi kiểm tra & ghi GIU_CHO/XUAT |
| Bộ sản phẩm | Dòng đơn tham chiếu bộ; khi giữ/xuất được rã thành thành phần; tồn bộ = min(thành phần / định mức) |
| Giữ chỗ 30 phút | `don_hang.giu_cho_den`; Worker ghi NHA_CHO cho đơn quá hạn **chưa thu đồng nào** (đơn đã thu một phần không tự hủy) |
| Giá sàn mềm | Thợ bán dưới sàn → đơn `CHO_DUYET_GIA` (vẫn giữ hàng), tạo yêu cầu, đẩy WebSocket + Zalo cho Chủ; API không bao giờ trả `gia_von`/`gia_san` cho Thợ |
| Đổi giá không ghi đè | Trigger chỉ cho phép đóng `den_ngay` của mức đang mở; unique index một mức mở mỗi loại giá |
| Bản chụp dòng đơn | `dong_don` lưu đơn giá, giá niêm yết/sàn/vốn, công thức, tham số; trigger cấm sửa (trừ cờ `da_xuat`) |
| HĐĐT ngoài đường găng | Khi đơn thu đủ (chốt): xuất kho + phiếu bán hàng + dòng `hoa_don_dt` CHO_XUAT trong **cùng một giao dịch**; Worker gửi bằng `FOR UPDATE SKIP LOCKED`, lỗi tạm thời thử lại sau 1, 2, 4… tối đa 60 phút, tối đa 10 lần |
| Webhook idempotent | `giao_dich_nh.ma_bam = SHA256(nguồn|mã GD)` UNIQUE + `ON CONFLICT DO NOTHING`; tiền về cho đơn đã xác nhận tay được dùng để đối soát, không ghi thu lần hai |
| Máy nhận tiền | Ghép bằng mã 6 số (10 phút, dùng một lần) → cấp khóa HMAC riêng; mỗi request ký `HMAC(khoá, "ts.body")`, lệch giờ ≤ 5 phút; thu hồi là vô hiệu ngay |
| Offline-first | PWA precache giao diện; Dexie lưu danh mục, bảng giá, công thức, từ đồng nghĩa; đơn mất mạng lưu kèm UUID, đồng bộ qua `/api/sync/don-hang`; thiếu hàng khi đồng bộ → `XUNG_DOT_TON`, không tự hủy |
| Tìm kiếm tiếng Việt < 1 giây | `f_unaccent` IMMUTABLE + cột `tim_kiem` do trigger điền (kèm token "1800 1m8") + GIN `gin_trgm_ops`; từ đồng nghĩa thay trước khi tìm; không khớp đủ từ thì tìm gần đúng bằng `word_similarity` |
| Thông số hàng hóa | Cột chung (hoàn thiện, kiểu dáng, vật liệu phụ, xuất xứ, khối lượng, bảo hành, đơn vị, mô tả) + `thuoc_tinh` JSONB theo mẫu của nhóm hàng (`loai_hang.thuoc_tinh_mau`, khóa là nhãn tiếng Việt); tìm kiếm phủ cả các thông số này |
| Kiểm kê, sửa, thêm, xóa hàng | Tab *Kho → Kiểm kê & hàng hóa* (Chủ): nhập số thực đếm, chênh lệch tính dưới khóa rồi ghi `DIEU_CHINH`; sửa mọi thuộc tính (đổi giá vẫn qua lịch sử giá); thêm hàng kèm tồn ban đầu; *xóa* = ngừng bán, tồn còn lại ghi điều chỉnh về 0, có thể khôi phục (không xóa cứng vì sổ cái/đơn cũ tham chiếu) |
| Thêm xưởng khi nhập kho | Nút *+ Xưởng mới* trong phiếu nhập (Chủ và Thợ), mã xưởng tự sinh, chặn trùng tên không dấu |
| Tiền & kích thước | BIGINT VNĐ, INTEGER mm, hệ số gỗ INTEGER phần nghìn; công thức tính bằng phân số, làm tròn nghìn đồng nửa lên |

## 7. Kiểm thử

| Bộ test | Nội dung | Kết quả lần chạy gần nhất |
|---|---|---|
| `backend/tests/test_dimension_parser.py` | "1m8", "1,8m", "180", "2m4", "1m8 x 2m"… → mm; cảnh báo dung sai; đầu vào sai | đạt |
| `backend/tests/test_pricing.py` | 3 công thức giá, làm tròn nghìn; VietQR CRC; chữ ký PayOS; SigV4 khớp ví dụ AWS | đạt |
| `backend/tests/test_ledger_immutability.py` | Chặn UPDATE/DELETE/TRUNCATE sổ cái & nhật ký; phát hiện sửa/xóa lén khi tắt trigger; ràng buộc dấu số lượng, không âm | đạt |
| `backend/tests/test_business_flows.py` | Bộ sản phẩm, chống bán vượt tồn, TTL giữ chỗ, giá vốn bình quân, giá sàn mềm, đặt riêng, HĐĐT cùng giao dịch, webhook trùng, lệch tiền, đối soát, offline xung đột, Retry Queue, tìm kiếm 20.000 biến thể < 1 giây | đạt |
| `backend/tests/test_hang_hoa_kiem_ke.py` | Thông số chi tiết, sửa thuộc tính + giá, thêm hàng kèm tồn ban đầu, xóa/khôi phục, chặn xóa hàng đang giữ/thuộc bộ, kiểm kê theo số đếm, thêm xưởng | đạt |
| `backend/tests/test_api.py` | Đăng nhập, RBAC, idempotency qua header, webhook có chữ ký, ghép nối & ký HMAC thiết bị, báo giá công khai, đồng bộ offline | đạt |
| `frontend/src/lib/lib.test.js` | Bản JS của bộ đọc kích thước & công thức giá cho kết quả giống backend | đạt |

Tổng: 141 test pytest + 15 test vitest. Ngoài ra `backend/scripts/smoke.py` chạy kịch bản đầu-cuối trên hệ thống đang chạy
(tìm kiếm → lập đơn → tiền về → chốt đơn → Worker xuất HĐĐT → duyệt giá sàn → kiểm tra chuỗi băm).

## 8. Tích hợp bên ngoài — trạng thái thật

| Adapter | Trạng thái |
|---|---|
| HĐĐT Mock | Mặc định, chạy demo được, cấp số và sinh XML; `EINVOICE_MOCK_FAIL_RATE` để thử Retry Queue |
| Viettel S-Invoice, VNPT Invoice | Dựng theo tài liệu công khai, **chưa thử với tài khoản thật** — phải đối chiếu tài liệu kỹ thuật được cấp trước khi bật |
| VietQR | Chuỗi EMVCo/Napas 247 chuẩn, có CRC16; quét được bằng app ngân hàng |
| PayOS webhook | Xác thực chữ ký HMAC-SHA256 theo đặc tả PayOS; cần `PAYOS_CHECKSUM_KEY` thật |
| S3 / Cloudinary | Ký URL SigV4 tự viết, đã kiểm thử khớp ví dụ chính thức của AWS; chưa thử với bucket thật |
| Zalo OA / SendGrid / SMS | Gửi thật khi có khóa API, nếu không chỉ ghi log |
| Xuất PDF hóa đơn | Mock chưa sinh PDF (chỉ XML); báo giá & phiếu in dùng chức năng In/Lưu PDF của trình duyệt |

Chế độ demo (`DEV_MODE=1`) có nút "Mô phỏng Máy nhận tiền báo tiền về" ở quầy để thử luồng tự xác nhận mà không cần ngân hàng.
Truy cập PWA từ điện thoại trong mạng LAN cần HTTPS (Service Worker, camera chỉ chạy trên kết nối an toàn hoặc `localhost`).
