# Hướng dẫn deploy lên Render

Đưa hệ thống Bản 2 (PostgreSQL + FastAPI + Worker + PWA) lên [Render](https://render.com) qua giao diện web,
không cần cài gì thêm trên máy. Kết quả: một địa chỉ HTTPS dạng `https://khanhvan.onrender.com` mở được trên
máy tính và điện thoại (cài được PWA, quét được mã QR vì đã có HTTPS).

## 1. Kiến trúc trên Render

```text
 Trình duyệt / điện thoại ──HTTPS──▶  Web Service "khanhvan" (Docker, backend/Dockerfile)
                                       ├─ uvicorn: API + giao diện PWA + WebSocket
                                       └─ worker: hàng đợi HĐĐT, nhả giữ chỗ, thông báo, kiểm tra toàn vẹn
                                              │ Internal Database URL (cùng vùng)
                                              ▼
                                     PostgreSQL "khanhvan-db" (bản 17)
```

Chỉ cần **2 thành phần**. Worker chạy chung container với web, vì hai lý do:

- gói Free không có Background Worker;
- ổ đĩa của Render chỉ gắn được vào một dịch vụ, mà worker cũng ghi file (XML hóa đơn) vào cùng chỗ với web.

Chọn gói trước khi làm:

| | **Free** — demo đồ án | **Starter + Disk** — dùng thật |
|---|---|---|
| Web Service | Ngủ sau 15 phút không ai truy cập; lần mở đầu chờ khoảng 1 phút | Chạy liên tục |
| Worker | Ngủ cùng web: HĐĐT, nhả giữ chỗ chỉ chạy khi web đang thức | Chạy liên tục |
| Ảnh minh họa, file XML HĐĐT | **Mất** mỗi khi web ngủ, khởi động lại hoặc deploy lại | Lưu trên Disk, giữ nguyên |
| PostgreSQL | 1 GB, **tự hết hạn sau 30 ngày** (còn 14 ngày để nâng cấp, sau đó bị xóa), không sao lưu | Theo gói, có sao lưu |

Giá các gói trả phí xem tại trang Pricing của Render.

## 2. Chuẩn bị

### Deploy đúng repo, đúng nhánh

Code mới nhất **chỉ nằm ở repo `thangduongworkemail-bot/management-software`, nhánh `finnal`**. Mọi chỗ khác là bản cũ:

| Repo | Nhánh | Nội dung |
|---|---|---|
| `thangduongworkemail-bot/management-software` | **`finnal`** | **Bản mới nhất, deploy nhánh này** |
| `thangduongworkemail-bot/management-software` | `main` (nhánh mặc định của repo) | Bản 2 đời đầu, lịch sử commit tách rời hẳn với `finnal` |
| `datduong41026/KTPMUD` (repo cũ) | `main`, `nhap-kiotviet-anh-minh-hoa` | Bản cũ, không còn cập nhật |

Khi tạo service, Render **tự điền nhánh mặc định của repo là `main`**, tức bản cũ. Phải tự đổi sang `finnal`.
Muốn Render tự chọn đúng: chủ repo vào GitHub → repo → **Settings** → **General** → **Default branch** → chọn `finnal`.

Xem commit mới nhất của từng nhánh trên GitHub (chạy trên máy, trong thư mục dự án):

```powershell
git fetch origin
git log -1 --oneline origin/finnal     # ví dụ: 9bdddae Slide thuyết trình và kịch bản video demo
```

### Tài khoản

1. Code cần deploy đã được **đẩy lên GitHub** ở nhánh `finnal` (`git push origin finnal`). Sửa trên máy mà chưa push
   thì Render không thấy.
2. Đăng ký Render bằng tài khoản GitHub. Khi Render hỏi quyền, chọn **Only select repositories → management-software**.
   Repo thuộc tài khoản `thangduongworkemail-bot`, nên nếu repo không hiện trong danh sách của Render thì chủ repo phải cấp:
   GitHub → Settings → Applications → Render → Configure → thêm `management-software`.

## 3. Bước 1 — Tạo cơ sở dữ liệu

Dashboard → **New** → **Postgres**, điền:

| Ô | Điền |
|---|---|
| Name | `khanhvan-db` |
| Database | `khanhvan` |
| User | `khanhvan` |
| Region | **Singapore** (gần Việt Nam nhất). Web Service ở bước sau **phải chọn cùng vùng** |
| PostgreSQL Version | `17` |
| Datadog API Key | để trống |
| Instance Type / Plan | `Free` (demo) hoặc gói trả phí |

Bấm **Create Database**, chờ trạng thái chuyển **Available**. Trong trang của database, mục **Connections**, có hai địa chỉ:

- **Internal Database URL**: dùng cho Web Service ở bước 2.
- **External Database URL**: dùng khi kết nối từ máy mình (nhập hàng KiotViet, sao lưu).

Hai extension `unaccent` và `pg_trgm` (cần cho tìm kiếm tiếng Việt) được ứng dụng tự tạo ở lần chạy đầu, không cần làm tay.

## 4. Bước 2 — Tạo Web Service

Dashboard → **New** → **Web Service** → chọn repo **management-software**, điền:

| Ô | Điền | Ghi chú |
|---|---|---|
| Name | `khanhvan` | Thành địa chỉ `https://khanhvan.onrender.com`. Tên đã có người dùng (kể cả service cũ của chính mình) thì Render tự thêm hậu tố, ví dụ `khanhvan-ab12.onrender.com` |
| Language | `Docker` | |
| Branch | **`finnal`** | Render điền sẵn `main` = **bản cũ**, phải đổi |
| Region | **Singapore** | Trùng vùng với database |
| Root Directory | **để trống** | Dockerfile cần thấy cả `frontend/`, `backend/`, `database/` |
| Instance Type | `Free` hoặc `Starter` | |

### Biến môi trường (Environment Variables)

Bấm **Add Environment Variable** cho từng dòng:

| Key | Value | Ghi chú |
|---|---|---|
| `DATABASE_URL` | dán **Internal Database URL** ở bước 1 | Bắt buộc |
| `JWT_SECRET` | bấm **Generate**, hoặc gõ chuỗi ngẫu nhiên ≥ 32 ký tự | Nên đặt. Để trống thì máy chủ tự sinh khóa và lưu trong CSDL. Đổi giá trị này thì mọi người phải đăng nhập lại |
| `TZ` | `ICT-7` | Giờ Việt Nam (UTC+7). Máy chủ Render chạy giờ UTC; thiếu dòng này thì mã đơn tạo từ 0h đến 7h sáng mang ngày hôm trước |
| `DEV_MODE` | `1` khi demo, `0` khi dùng thật | `1` hiện nút "Mô phỏng Máy nhận tiền báo tiền về" ở quầy |
| `EINVOICE_PROVIDER` | `MOCK` | Viettel/VNPT chưa thử với tài khoản thật |
| `VIETQR_BANK_BIN` | mã BIN ngân hàng, ví dụ `970436` (Vietcombank) | Mặc định là **tài khoản mẫu**; dùng thật phải đổi kẻo khách chuyển nhầm |
| `VIETQR_ACCOUNT_NO` | số tài khoản nhận tiền | |
| `VIETQR_ACCOUNT_NAME` | tên chủ tài khoản, IN HOA không dấu | |
| `PAYOS_CHECKSUM_KEY` | khóa checksum PayOS | Chỉ khi dùng webhook PayOS |
| `LOCAL_STORAGE_DIR` | `/data/storage` | **Chỉ khi có Disk** (gói trả phí, xem bên dưới) |

Không cần khai báo `PORT`: Render tự đặt, lệnh chạy bên dưới đã đọc biến này.
Không cần `PG_SUPERUSER_URL`: Render đã tạo sẵn user và database.

### Mục Advanced

| Ô | Điền |
|---|---|
| Health Check Path | `/api/suc-khoe` |
| Dockerfile Path | `./backend/Dockerfile` |
| Docker Build Context Directory | `.` (thư mục gốc repo) |
| Docker Command | dòng dưới đây |
| Auto-Deploy | `On Commit`: mỗi lần đẩy code lên nhánh đã chọn thì tự deploy lại |

Docker Command: xóa hết nội dung cũ trong ô, chép đúng dòng này, không thêm dấu ngoặc kép:

```text
python -m app.khoi_dong
```

Lệnh này (file `backend/app/khoi_dong.py`) chạy lần lượt: tạo bảng và migration mới; nạp dữ liệu mẫu nếu CSDL còn
trống; bật worker chạy nền; rồi chạy web ở đúng cổng Render cấp (`$PORT`). Đây cũng là `CMD` của Dockerfile, nên để
trống ô vẫn chạy đúng; điền rõ ra để chắc không còn sót lệnh cũ.

**Đừng dùng chuỗi lệnh shell** kiểu `/bin/sh -c "… && (python -m app.worker &) && …"` (bản cũ của hướng dẫn này):
ô Docker Command của Render không chạy được cú pháp đó, deploy báo `/bin/sh: 4: Syntax error: "(" unexpected`.

**Disk (chỉ gói trả phí)**: bấm **Add Disk**, điền:

- Name: `storage`
- Mount Path: `/data/storage`
- Size: `1` GB

Kèm theo đó thêm biến `LOCAL_STORAGE_DIR=/data/storage` như bảng trên. Khi đã gắn Disk, mỗi lần deploy web sẽ tạm
ngừng vài chục giây, vì Render dừng bản cũ rồi mới chạy bản mới.

Bấm **Deploy Web Service**. Lần đầu build mất khoảng 5–10 phút (cài thư viện Node + Python, build PWA).
Trong tab **Logs**, deploy thành công khi thấy lần lượt:

```text
Bỏ qua bước tạo role/database (không kết nối được superuser) ...   <- bình thường trên Render
Đã nạp dữ liệu mẫu                                                  <- chỉ lần đầu
Worker khởi động (HĐĐT: MOCK)
Uvicorn running on http://0.0.0.0:10000
```

## 5. Bước 3 — Việc phải làm ngay sau lần deploy đầu

1. Mở `https://<tên-service>.onrender.com`, đăng nhập `covan` / `KhanhVan@2026`.
2. **Đổi mật khẩu cả 3 tài khoản mẫu.** Mật khẩu mẫu được ghi công khai trong README, nên ai biết địa chỉ trang
   cũng đăng nhập được. Cách đổi: menu **Nhân viên & Nhật ký** → nút **Đặt lại MK** cạnh từng tài khoản
   `covan`, `anhnam`, `admin`.
3. Dữ liệu mẫu (đơn `#KV2610…`, khách hàng, xưởng) là dữ liệu demo theo báo cáo. Khi dùng thật nên tạo database
   mới, nạp hàng thật (bước 4) rồi đổi mật khẩu.

## 6. Bước 4 — Đưa danh sách sản phẩm KiotViet lên CSDL Render

Gói Free không có Shell trên Render, nên chạy lệnh nhập **từ máy mình** qua **External Database URL**.
Lệnh này chạy được với mọi gói. Làm sau khi bước 2 đã deploy xong (cần có bảng và tài khoản Chủ). Trong PowerShell:

```powershell
cd backend
$env:DATABASE_URL = '<dán External Database URL>?sslmode=require'
$py = 'C:\ProgramData\miniconda3\envs\ai_signal\python.exe'
& $py -m app.nhap_kiotviet ..\data_bo_sung\DanhSachSanPham_KV17112026-230038-395_khoi_phuc.csv --xem-truoc
& $py -m app.nhap_kiotviet ..\data_bo_sung\DanhSachSanPham_KV17112026-230038-395_khoi_phuc.csv
Remove-Item Env:DATABASE_URL     # để các lệnh sau không vô tình ghi vào CSDL trên Render
```

`--xem-truoc` chạy thử rồi hoàn tác. Chạy lại lệnh nhập không tạo trùng: mã đã có thì bỏ qua.
Nếu báo không kết nối được: mở database trên Render, tìm phần giới hạn IP truy cập (Access Control / Networking →
Inbound IP), kiểm tra có cho phép IP của máy mình không.

## 7. Cập nhật và sao lưu

- **Cập nhật code**: commit rồi `git push origin finnal`, Render tự build và deploy lại. Migration mới
  (`database/migrations/*.sql`) tự áp dụng khi khởi động. Dữ liệu và tài khoản giữ nguyên, không nạp lại dữ liệu mẫu.
- **Deploy tay / khởi động lại**: trong trang service, nút **Manual Deploy** → *Deploy latest commit* hoặc *Restart service*.
- **Sao lưu** (bắt buộc với database Free trước khi hết hạn 30 ngày). Từ máy đã cài PostgreSQL 17:

  ```powershell
  & 'C:\Program Files\PostgreSQL\17\bin\pg_dump.exe' -Fc -d '<External Database URL>?sslmode=require' -f khanhvan.dump
  ```

  Khôi phục sang database mới:

  ```powershell
  & 'C:\Program Files\PostgreSQL\17\bin\pg_restore.exe' --no-owner -d '<External URL mới>?sslmode=require' khanhvan.dump
  ```

  Sau đó đổi `DATABASE_URL` của Web Service sang Internal URL mới.

## 8. Render vẫn chạy bản cũ

Làm lần lượt, dừng ở bước tìm ra nguyên nhân.

**Bước A: xem Render đang chạy commit nào.** Mở trang service, vào tab **Events**. Dòng deploy trên cùng có dạng
`Deploy live for 9bdddae: Slide thuyết trình…`. So mã commit đó với `git log -1 --oneline origin/finnal` (mục 2).

| Events hiển thị | Nghĩa là | Làm tiếp |
|---|---|---|
| Trùng commit của `origin/finnal` | Render đã chạy code mới. Lỗi nằm ở địa chỉ đang mở, trình duyệt hoặc dữ liệu | Bước C |
| `9ef5afd` hoặc `33cea21` | Đang build nhánh `main` hoặc repo cũ | Bước B |
| Dòng mới nhất là **Deploy failed** | Bản mới build hoặc khởi động lỗi, nên Render **giữ nguyên bản cũ đang chạy** | Bấm vào dòng đó xem log, tra bảng mục 9 |
| Cũ hơn `origin/finnal`, không có lần deploy nào mới hơn | Code chưa push, hoặc Auto-Deploy đang tắt | `git push origin finnal`, rồi **Manual Deploy → Deploy latest commit** |

**Bước B: sửa repo và nhánh.** Trang service → **Settings** → mục **Build & Deploy**, kiểm tra:

| Ô | Phải là |
|---|---|
| Repository | `https://github.com/thangduongworkemail-bot/management-software` |
| Branch | `finnal` |
| Root Directory | trống |
| Dockerfile Path | `./backend/Dockerfile` |
| Docker Build Context Directory | `.` |

Lưu, rồi bấm **Manual Deploy → Deploy latest commit** và quay lại bước A. Đúng commit mà giao diện vẫn cũ thì
**Manual Deploy → Clear build cache & deploy**.

**Bước C: Render đã chạy code mới mà trang vẫn cũ.**

- **Mở nhầm địa chỉ.** Service cũ còn chạy thì đang giữ tên `khanhvan.onrender.com`, còn service mới mang hậu tố.
  Chép địa chỉ hiện ở đầu trang của **service mới**, đừng gõ theo trí nhớ. Service cũ không dùng nữa thì vào
  Settings của nó → **Suspend Web Service** (hoặc **Delete**) để khỏi nhầm.
- **Trình duyệt còn giữ giao diện cũ.** PWA lưu sẵn giao diện để chạy offline, nên lần mở đầu sau deploy vẫn hiện bản cũ,
  vài giây sau tự tải lại sang bản mới. Không tự đổi thì trên máy tính bấm **Ctrl+Shift+R**; vẫn không được thì
  **F12 → Application → Storage → Clear site data** rồi tải lại. Điện thoại đã cài app: tắt hẳn app rồi mở lại,
  hoặc gỡ app và cài lại từ trình duyệt. Mở thử bằng tab ẩn danh để biết chắc lỗi có phải do bộ nhớ đệm không.
- **Dữ liệu cũ.** `DATABASE_URL` vẫn trỏ vào database của service cũ thì máy chủ thấy CSDL đã có dữ liệu và **bỏ qua
  nạp dữ liệu mẫu**, nên danh mục thiếu 30 mặt hàng gỗ bổ sung. Có hai cách:
  - giữ dữ liệu cũ, thêm hàng: chạy từ máy mình qua External Database URL như mục 6, nhưng thay lệnh nhập bằng
    `& $py -m app.hang_mau_bo_sung --xem-truoc` rồi `& $py -m app.hang_mau_bo_sung` (chạy lại không tạo trùng);
  - dữ liệu sạch: tạo database mới (bước 1), đổi `DATABASE_URL` của Web Service sang Internal URL mới, rồi
    **Manual Deploy → Deploy latest commit**.

## 9. Xử lý sự cố

| Hiện tượng (trong Logs) | Nguyên nhân / cách sửa |
|---|---|
| Build lỗi `COPY failed` / không thấy `frontend/package.json` | Root Directory phải **trống** và Docker Build Context Directory là `.` |
| `/bin/sh: 4: Syntax error: "(" unexpected`, rồi `Exited with status 2` | Ô Docker Command còn chuỗi lệnh shell cũ. Sửa thành `python -m app.khoi_dong` (mục 4) |
| `No module named app.khoi_dong` | Render đang build commit cũ chưa có file này. `git push origin finnal`, rồi xem mục 8 |
| Deploy treo rồi báo không thấy cổng mở (*no open ports*) | Docker Command không phải `python -m app.khoi_dong`, hoặc Render build nhầm nhánh cũ (mục 8) |
| `could not translate host name "dpg-..."` | Web Service và database khác vùng. Internal URL chỉ dùng được khi cùng vùng: tạo lại một trong hai cho cùng Singapore |
| `permission denied to create extension` | Vào database → **Connect** → chép lệnh PSQL, chạy `CREATE EXTENSION IF NOT EXISTS unaccent; CREATE EXTENSION IF NOT EXISTS pg_trgm;` rồi **Manual Deploy → Restart service** |
| Mở trang thấy màn hình chờ khoảng 1 phút | Gói Free đang ngủ và đang khởi động lại, bình thường |
| Mọi người bị đăng xuất | Vừa đổi `JWT_SECRET`, hoặc token hết hạn (12 giờ). Đăng nhập lại |
| Ảnh minh họa / file XML hóa đơn biến mất | Gói Free không lưu file lâu dài. Cần gói trả phí + Disk (bước 2) |

**Lưu ý về lưu file trên S3.** Ứng dụng có hỗ trợ lưu file lên S3 (`STORAGE_PROVIDER=S3`), nhưng hiện chưa dùng được
cho ảnh minh họa: link ảnh S3 là link có chữ ký, chỉ sống 7 ngày. Muốn giữ ảnh lâu dài thì dùng Disk như trên.
