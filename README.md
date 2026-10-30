# Hệ thống Quản lý & Bán hàng Nội thất gỗ Khanh Vân

Phần mềm bán hàng tại quầy (POS), quản lý kho nhiều xưởng, công nợ hai chiều và hóa đơn điện tử cho cửa hàng
**Nội thất gỗ Khanh Vân** (Thái Nguyên).

**Báo cáo Kỹ thuật Phần mềm Ứng dụng — Nhóm 32, Đại học Bách Khoa Hà Nội**
Giảng viên hướng dẫn: TS. Hoàng Quang Huy
Sinh viên thực hiện: Lê Thị Ngọc Anh (20210032) · Dương Văn Thắng (20210046) · Dương Văn Đạt (20210053)

Kho mã gồm hai thế hệ:

| Phiên bản | Thư mục | Công nghệ | Trạng thái |
|---|---|---|---|
| **Bản 2 (chính)** | `database/`, `backend/`, `frontend/`, `scripts/` | PostgreSQL 17 · FastAPI · Retry Worker · Vue 3 PWA | Đang phát triển, mọi tính năng mới làm ở đây |
| Bản 1 (prototype) | `server.py`, `index.html`, `sw.js`, `tests/` ở thư mục gốc | Python stdlib + SQLite | Giữ lại để đối chiếu, xem [README_PROTOTYPE_V1.md](README_PROTOTYPE_V1.md) |

Tài liệu bàn giao chi tiết của bản 2: [HUONG_DAN_V2.md](HUONG_DAN_V2.md).

---

## Mục lục

1. [Tính năng](#1-tính-năng)
2. [Kiến trúc](#2-kiến-trúc)
3. [Cấu trúc thư mục](#3-cấu-trúc-thư-mục)
4. [Cài đặt và chạy](#4-cài-đặt-và-chạy)
5. [Tài khoản và phân quyền](#5-tài-khoản-và-phân-quyền)
6. [Dữ liệu mẫu](#6-dữ-liệu-mẫu)
7. [Thiết kế dữ liệu và các bảo đảm toàn vẹn](#7-thiết-kế-dữ-liệu-và-các-bảo-đảm-toàn-vẹn)
8. [API](#8-api)
9. [Cấu hình](#9-cấu-hình)
10. [Kiểm thử](#10-kiểm-thử)
11. [Tích hợp bên ngoài](#11-tích-hợp-bên-ngoài)
12. [Mở cho khách dùng thử qua Internet](#12-mở-cho-khách-dùng-thử-qua-internet)
13. [Giới hạn đã biết](#13-giới-hạn-đã-biết)

---

## 1. Tính năng

**Bán hàng tại quầy**
- Tra giá tiếng Việt có dấu hoặc không dấu, hiểu từ đồng nghĩa ("tủ áo" = "tủ quần áo") và kích thước viết tắt ("giường 1m8 sồi"), dưới 1 giây trên 20.000 mặt hàng.
- Hàng đặt theo kích thước riêng tính giá theo 3 công thức: **mét dài** (tủ thờ, án gian), **m²** (mặt bàn) và **bậc kích thước** (giường), có nhân hệ số loại gỗ.
- Giá 3 tầng: giá vốn → giá sàn → giá niêm yết. Thợ bán dưới giá sàn thì đơn chờ Chủ duyệt (đẩy thông báo tức thời), hàng vẫn được giữ.
- Sinh mã **VietQR** (Napas 247) tại quầy. Tiền về qua webhook PayOS hoặc "Máy nhận tiền" (điện thoại đọc thông báo ngân hàng, ký HMAC) thì đơn tự xác nhận. Có xác nhận tay và xử lý lệch tiền.
- Đặt cọc, bán chịu, trả hàng, báo giá có link chia sẻ công khai, in phiếu giao hàng.
- **Offline-first:** mất mạng vẫn tra giá và lập đơn; đơn mang mã idempotency và tự đồng bộ khi có mạng lại.

**Kho và xưởng**
- Tồn kho tính từ **sổ cái chỉ ghi thêm**: tồn hiện có, đang giữ chỗ, tồn khả dụng. Giữ chỗ 30 phút, quá hạn tự nhả.
- Bộ sản phẩm (ví dụ bộ bàn ăn 1 bàn + 6 ghế) tự rã thành từng món khi giữ hoặc xuất kho.
- Phiếu nhập theo xưởng, giá vốn bình quân gia quyền, công nợ phải trả xưởng. Thêm xưởng mới ngay trong phiếu nhập.
- **Kiểm kê:** nhập số đếm thực tế, hệ thống tự ghi dòng điều chỉnh. Sửa mọi thuộc tính mặt hàng, thêm hàng mới kèm tồn ban đầu, xóa (ngừng bán) và khôi phục.
- Thông số hàng hóa chi tiết: loại gỗ, màu, hoàn thiện bề mặt, kiểu dáng, phụ kiện, kích thước, khối lượng, bảo hành, xuất xứ, cùng thuộc tính riêng theo nhóm hàng (số cánh, số ngăn kéo, kích thước nệm…).

**Tài chính và hóa đơn**
- Hóa đơn điện tử tách khỏi việc bán: đơn thu đủ thì xếp hàng đợi, Worker gửi lên nhà cung cấp và tự thử lại khi lỗi (1, 2, 4… phút, tối đa 60 phút, 10 lần).
- Đối soát giao dịch ngân hàng, chốt sổ cuối ngày, công nợ khách hàng và công nợ xưởng.

**Quản trị và kiểm toán**
- 3 vai trò Chủ / Thợ / Quản trị; Thợ không bao giờ nhận được giá vốn hay giá sàn từ API.
- Nhật ký thao tác có **chuỗi băm SHA-256**, phát hiện được sửa hoặc xóa lén; job kiểm tra toàn vẹn chạy hằng đêm.
- Cập nhật tức thời qua WebSocket (đơn mới, tiền về, yêu cầu duyệt giá).
- Trung tâm sự cố: hướng dẫn xử lý mất mạng, máy nhận tiền mất kết nối, HĐĐT lỗi…

## 2. Kiến trúc

```text
 Trình duyệt / điện thoại (PWA Vue 3)
   ├─ IndexedDB (Dexie): danh mục, bảng giá, đơn chờ đồng bộ
   └─ Service Worker: chạy được khi mất mạng
          │ HTTPS REST + WebSocket
          ▼
 FastAPI (backend/app) ── phục vụ luôn bản build PWA
   ├─ routers/   REST API, kiểm tra quyền theo vai trò
   ├─ services/  nghiệp vụ (nhận conn, không tự commit)
   ├─ domain/    logic thuần: đọc kích thước, công thức giá, VietQR
   ├─ adapters/  HĐĐT (Mock/Viettel/VNPT), PayOS, lưu file (Local/S3), Zalo/SendGrid
   └─ realtime   LISTEN/NOTIFY → WebSocket
          │
          ▼
 PostgreSQL 17 ◄──── Retry Worker (app/worker.py)
   unaccent, pg_trgm,     hàng đợi HĐĐT, nhả giữ chỗ TTL,
   trigger bất biến,      gửi thông báo, kiểm tra toàn vẹn đêm
   chuỗi băm nhật ký
```

| Thành phần | Công nghệ |
|---|---|
| CSDL | PostgreSQL 17 (unaccent, pg_trgm, JSONB, trigger PL/pgSQL) |
| Backend | Python 3.11+, FastAPI 0.115, psycopg 3 + psycopg-pool, argon2-cffi, PyJWT, httpx |
| Frontend | Vue 3.5, vue-router 4, Vite 6, Tailwind CSS 3, Dexie 4, vite-plugin-pwa, qrcode |
| Kiểm thử | pytest (CSDL thật), vitest |
| Triển khai | Script PowerShell cho Windows, Docker Compose, Cloudflare Tunnel cho bản dùng thử |

## 3. Cấu trúc thư mục

```text
database/migrations/      001 bảng & ràng buộc · 002 trigger · 003 chỉ mục tìm kiếm & view · 004 thông số chi tiết
backend/
  app/
    domain/               dimension.py, pricing.py, vietqr.py, text.py
    adapters/             einvoice.py, payment.py, storage.py, notify.py
    services/             catalog, inventory, orders, payments, invoices, devices, sync, reports, audit…
    routers/              auth, catalog, inventory, sales, payments, invoices, system
    main.py               ứng dụng FastAPI + phục vụ PWA
    worker.py             Retry Worker
    bootstrap.py          tạo role/CSDL, migrate, seed
    seed.py               dữ liệu mẫu
  tests/                  pytest
  scripts/smoke.py        kịch bản đầu-cuối trên hệ thống đang chạy
  requirements.txt, Dockerfile, .env.example
frontend/
  src/views/              12 màn hình: Bán hàng, Đơn hàng, Kho & Xưởng, Hàng hóa & Giá, Đối soát, HĐĐT & Công nợ…
  src/components/         hộp thoại, mã QR, form sửa hàng hóa…
  src/lib/                bản JS của bộ đọc kích thước & công thức giá (khớp backend), tìm kiếm ngoại tuyến
  src/db.js, sync.js      IndexedDB và đồng bộ đơn ngoại tuyến
scripts/                  setup.ps1, start.ps1, test.ps1, demo-public.ps1
docker-compose.yml        db + api + worker
HUONG_DAN_V2.md           tài liệu bàn giao chi tiết
```

## 4. Cài đặt và chạy

### Yêu cầu

- Python 3.11 trở lên
- Node.js 20 trở lên
- PostgreSQL 17 (trên Windows có thể cài bằng `winget install PostgreSQL.PostgreSQL.17`; các script mặc định dùng superuser `postgres` / mật khẩu `postgres`)

### Windows: cài và chạy bằng script

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # tạo venv, cài thư viện, tạo CSDL, migrate, seed, build PWA
powershell -ExecutionPolicy Bypass -File scripts\start.ps1     # chạy API + Worker
```

Mở http://localhost:8000. Tài liệu API tự sinh có tại http://localhost:8000/docs.

Nạp lại dữ liệu mẫu từ đầu (xóa toàn bộ dữ liệu): `scripts\setup.ps1 -Reset`.

### Docker

```bash
docker compose up -d --build     # http://localhost:8000
```

### Chạy thủ công (Linux/macOS hoặc khi cần từng bước)

```bash
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                              # sửa DATABASE_URL, PG_SUPERUSER_URL nếu cần
python -m app.bootstrap                           # tạo role + CSDL, migrate, seed (bỏ qua seed nếu đã có dữ liệu)
uvicorn app.main:app --port 8000                  # API
python -m app.worker                              # Worker, chạy ở terminal khác

cd ../frontend
npm install && npm run build                      # API tự phục vụ frontend/dist
```

Phát triển giao diện có hot-reload: chạy API như trên rồi `npm run dev` trong `frontend/` và mở http://localhost:5173 (Vite tự chuyển `/api`, `/ws` sang cổng 8000).

Các lệnh hữu ích khác:

| Lệnh (chạy trong `backend/`) | Tác dụng |
|---|---|
| `python -m app.bootstrap --reset` | Xóa sạch schema, dựng lại và nạp dữ liệu mẫu |
| `python -m app.migrate` | Chỉ áp dụng migration mới |
| `python -m app.worker --mot-lan` | Chạy mỗi tác vụ nền một lần rồi thoát |
| `python -m app.worker --kiem-tra-toan-ven` | Chạy ngay job kiểm tra toàn vẹn |
| `python scripts/smoke.py` | Kịch bản đầu-cuối trên hệ thống đang chạy |

## 5. Tài khoản và phân quyền

Tài khoản trong dữ liệu mẫu (trang đăng nhập có nút chọn nhanh khi chạy ở chế độ demo):

| Tài khoản | Mật khẩu | Vai trò | Quyền chính |
|---|---|---|---|
| `covan` | `KhanhVan@2026` | Chủ cửa hàng | Toàn quyền: giá vốn, duyệt giá sàn, xác nhận tiền tay, kiểm kê, sửa/thêm/xóa hàng, chốt sổ |
| `anhnam` | `AnhNam@2026` | Thợ / nhân viên | Tra giá niêm yết, lập đơn, phiếu nhập, thêm xưởng; không thấy giá vốn/giá sàn |
| `admin` | `Admin@2026` | Quản trị | Tài khoản, thiết bị, nhật ký hệ thống |

> Đây là mật khẩu demo công khai. Khi triển khai thật phải đổi mật khẩu, đặt `JWT_SECRET` riêng và tắt `DEV_MODE`.

## 6. Dữ liệu mẫu

- 3 xưởng: Đồ Thờ Cát Đẳng, Giường & Bàn Ghế Hải Hậu, Kho Gỗ Công Nghiệp MDF (kèm 3 phiếu nhập đầu kỳ).
- 11 mặt hàng thuộc 5 nhóm (đồ thờ, giường, tủ/kệ, bàn ghế, gỗ công nghiệp) có đủ thông số chi tiết, trong đó 3 mặt hàng đặt theo kích thước (mét dài, m², bậc), và bộ `BO-BANAN-SOI-1600` (1 bàn + 6 ghế).
- Đơn hàng theo kịch bản báo cáo:
  - `#KV261026001`: đã xác nhận tay (4 số cuối *4817), chờ xuất HĐĐT.
  - `#KV261026002`: tủ thờ 2m4 = 5.328.000 đ, đã cọc 2 triệu.
  - `#KV261027005`: chuyển khoản 17,0 triệu cho đơn 17,2 triệu (lệch tiền).
  - `#KV261027006`: Thợ xin bán dưới giá sàn, chờ Chủ duyệt.

## 7. Thiết kế dữ liệu và các bảo đảm toàn vẹn

Lược đồ viết bằng SQL thuần trong `database/migrations/`, áp dụng theo thứ tự tên file. Tiền lưu `BIGINT` (đồng), kích thước `INTEGER` (mm), hệ số `INTEGER` phần nghìn (1200 = 1,2).

| Yêu cầu | Cách hiện thực |
|---|---|
| Sổ cái tồn kho và nhật ký không sửa được | Trigger chặn `UPDATE/DELETE/TRUNCATE` trên `so_cai_ton`, `nhat_ky` (lỗi `KV001`) |
| Tồn kho luôn đúng | Không lưu số tồn; view `v_ton_kho` cộng sổ cái (NHAP/TRA_HANG/GIU_CHO dương, XUAT/NHA_CHO âm) |
| Không bán vượt tồn khi hai quầy bán cùng lúc | `SELECT … FOR UPDATE` các mặt hàng theo thứ tự id trước khi kiểm tra và ghi |
| Đổi giá không mất lịch sử | `gia_hieu_luc` chỉ cho đóng mức đang mở rồi mở mức mới; dòng đơn chụp lại giá lúc bán (lỗi `KV002` nếu sửa) |
| Nhật ký chống chối bỏ | Trigger tính `current_hash = SHA256(prev_hash ‖ nội dung)` dưới khóa advisory; hàm `kiem_tra_chuoi_nhat_ky()` phát hiện sửa/xóa |
| Thanh toán chốt đơn nhất quán | `orders.chot_don()` là đường duy nhất: xuất kho + phiếu bán hàng + xếp HĐĐT trong **một giao dịch** |
| Webhook / đồng bộ không ghi trùng | Mã băm giao dịch `UNIQUE` + `ON CONFLICT DO NOTHING`; đơn ngoại tuyến mang UUID idempotency |
| Xóa mặt hàng | Là ngừng bán: tồn còn lại ghi điều chỉnh về 0, đơn cũ và sổ cái giữ nguyên, khôi phục được |
| Tìm kiếm tiếng Việt nhanh | `f_unaccent` IMMUTABLE + cột `tim_kiem` do trigger điền (kèm token kích thước "1800 1m8") + GIN `gin_trgm_ops` |

## 8. API

Toàn bộ API có tài liệu tương tác tại `/docs` (OpenAPI). Các nhóm chính:

| Nhóm | Tiền tố | Ví dụ |
|---|---|---|
| Tài khoản | `/api/auth`, `/api/tai-khoan` | `POST /api/auth/dang-nhap`, `POST /api/auth/doi-mat-khau` |
| Hàng hóa & giá | `/api/hang-hoa` | `GET /tim-kiem?q=giuong 1m8 soi`, `POST /bien-the`, `PATCH /bien-the/{id}`, `POST /bien-the/{id}/gia`, `POST /bien-the/{id}/tinh-gia` |
| Kho & xưởng | `/api/kho` | `POST /phieu-nhap`, `POST /kiem-ke`, `POST /xuong`, `GET /so-cai` |
| Bán hàng | `/api/don-hang`, `/api/bao-gia` | `POST /api/don-hang` (header `Idempotency-Key`), `POST /{id}/tra-hang`, `GET /api/public/bao-gia/{ma}` |
| Thanh toán & đối soát | `/api/don-hang/{id}/…`, `/api/doi-soat`, `/api/chot-ngay` | `POST /api/webhook/payos`, `POST /api/thiet-bi/giao-dich` (ký HMAC) |
| Hóa đơn điện tử | `/api/hoa-don` | `POST /{id}/thu-lai`, `GET /goi-du-lieu` |
| Hệ thống | `/api` | `GET /tong-quan`, `GET /nhat-ky/kiem-tra`, `GET /sync/danh-muc`, `POST /sync/don-hang` |
| Realtime | `/ws?token=…` | WebSocket, sự kiện lọc theo vai trò |

Lỗi nghiệp vụ trả về dạng `{"loi": "MA_LOI", "thong_bao": "…", "chi_tiet": …}`.

## 9. Cấu hình

Đọc từ biến môi trường hoặc `backend/.env` (mẫu: [backend/.env.example](backend/.env.example)).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DATABASE_URL` | `postgresql://khanhvan:khanhvan@localhost:5432/khanhvan` | CSDL ứng dụng |
| `PG_SUPERUSER_URL` | `postgresql://postgres:postgres@localhost:5432/postgres` | Chỉ dùng khi bootstrap tạo role/CSDL |
| `JWT_SECRET` | khóa dev | **Bắt buộc đổi** khi triển khai |
| `DEV_MODE` | `1` | `1` bật nút mô phỏng tiền về; đặt `0` khi chạy thật |
| `VIETQR_BANK_BIN`, `VIETQR_ACCOUNT_NO`, `VIETQR_ACCOUNT_NAME` | tài khoản mẫu | Tài khoản nhận tiền in trên mã QR |
| `PAYOS_CHECKSUM_KEY` | khóa demo | Xác thực chữ ký webhook PayOS |
| `EINVOICE_PROVIDER` | `MOCK` | `MOCK` / `VIETTEL` / `VNPT` (kèm `*_URL`, `*_USERNAME`, `*_PASSWORD`) |
| `STORAGE_PROVIDER` | `LOCAL` | `LOCAL` hoặc `S3` (S3, Cloudinary S3 API, MinIO, R2) |
| `ZALO_OA_ACCESS_TOKEN`, `SENDGRID_API_KEY` | trống | Để trống thì thông báo chỉ ghi log |
| `HOLD_TTL_MINUTES`, `JWT_TTL_MINUTES`, `INTEGRITY_CHECK_HOUR` | 30, 720, 2 | Thời gian giữ chỗ, hạn phiên, giờ chạy kiểm tra đêm |

## 10. Kiểm thử

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1     # pytest + vitest
```

Hoặc từng phần: `cd backend && python -m pytest -q`, `cd frontend && npx vitest run`.
Pytest tự dựng một CSDL riêng `khanhvan_test` (migrate + seed) mỗi lần chạy; mỗi test chạy trong giao dịch và rollback.

| Bộ test | Nội dung |
|---|---|
| `test_dimension_parser.py` | "1m8", "1,8m", "180", "2m4", "1m8 x 2m"… → mm, cảnh báo dung sai |
| `test_pricing.py` | 3 công thức giá, làm tròn nghìn đồng, VietQR CRC16, chữ ký PayOS, AWS SigV4 |
| `test_ledger_immutability.py` | Chặn sửa/xóa sổ cái & nhật ký, phát hiện sửa lén khi tắt trigger |
| `test_business_flows.py` | Bộ sản phẩm, chống bán vượt tồn, TTL giữ chỗ, giá vốn bình quân, giá sàn mềm, HĐĐT, webhook trùng, lệch tiền, đối soát, offline xung đột, tìm kiếm 20.000 mặt hàng < 1 giây |
| `test_hang_hoa_kiem_ke.py` | Thông số chi tiết, sửa thuộc tính + giá, thêm/xóa/khôi phục hàng, kiểm kê, thêm xưởng |
| `test_api.py` | Đăng nhập, phân quyền, idempotency, webhook có chữ ký, ghép nối thiết bị HMAC, báo giá công khai, đồng bộ offline |
| `frontend/src/lib/lib.test.js` | Bản JS của bộ đọc kích thước & công thức giá cho kết quả giống backend |

Kết quả lần chạy gần nhất: **141 test pytest + 15 test vitest đều đạt.**

## 11. Tích hợp bên ngoài

| Tích hợp | Trạng thái |
|---|---|
| HĐĐT Mock | Mặc định; cấp số và sinh XML; `EINVOICE_MOCK_FAIL_RATE` để thử cơ chế thử lại |
| Viettel S-Invoice, VNPT Invoice | Viết theo tài liệu công khai, **chưa chạy thử với tài khoản thật** |
| VietQR | Chuỗi EMVCo/Napas 247 có CRC16, quét được bằng app ngân hàng |
| PayOS webhook | Xác thực HMAC-SHA256; cần `PAYOS_CHECKSUM_KEY` thật |
| S3 / Cloudinary | Ký URL SigV4, đã kiểm thử khớp ví dụ chính thức của AWS; chưa thử với bucket thật |
| Zalo OA / SendGrid | Gửi thật khi có khóa API |

## 12. Mở cho khách dùng thử qua Internet

Trên Windows, sau khi đã chạy `setup.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\demo-public.ps1        # chạy API, Worker và Cloudflare Quick Tunnel, in ra link https
powershell -ExecutionPolicy Bypass -File scripts\demo-public.ps1 -Tat   # tắt
```

Script cần `cloudflared.exe` trong `.tools/` (không đưa lên git; tải tại trang phát hành của cloudflare/cloudflared).
Link đổi mỗi lần bật lại và chỉ hoạt động khi máy đang chạy.

## 13. Giới hạn đã biết

- Docker Compose chưa được chạy thử trên máy phát triển (máy không cài Docker).
- Adapter Viettel/VNPT chưa thử với tài khoản thật; HĐĐT Mock chưa sinh PDF (báo giá và phiếu in dùng chức năng In/Lưu PDF của trình duyệt).
- Bộ sản phẩm chưa có màn hình sửa thành phần.
- PWA trên điện thoại trong mạng LAN cần HTTPS (Service Worker và camera chỉ chạy trên kết nối an toàn hoặc `localhost`).
- WebSocket truyền token qua query string nên token có thể xuất hiện trong log truy cập của máy chủ.
