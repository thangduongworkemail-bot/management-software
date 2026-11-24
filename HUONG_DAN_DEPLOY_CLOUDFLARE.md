# Hướng dẫn deploy với Cloudflare Tunnel

Hệ thống chạy ngay trên một máy Windows (máy ở cửa hàng, hoặc máy của nhóm), còn **Cloudflare Tunnel** đưa nó ra
Internet bằng HTTPS:

- không cần IP tĩnh, không cần mở cổng trên router;
- cài được PWA và dùng camera trên điện thoại, vì đã có HTTPS.

```text
 Điện thoại / máy khách ──HTTPS──▶ Cloudflare ◀──kết nối từ trong ra── cloudflared (trên máy chủ)
                                                                            │ http://localhost:8000
                                                       API + PWA + Worker ◀─┘──▶ PostgreSQL 17 (cùng máy)
```

So với [Render](HUONG_DAN_DEPLOY_RENDER.md):

- **Ưu điểm:** miễn phí; dữ liệu, ảnh minh họa và file hóa đơn nằm trên ổ đĩa của máy nên không bị mất.
- **Nhược điểm:** máy chủ phải luôn bật và có mạng.

> **Vì sao không dùng Cloudflare Pages / Workers?** Hai dịch vụ này chạy hàm JavaScript ngắn, không chạy được
> máy chủ Python chạy liên tục kèm PostgreSQL và worker nền. Muốn dùng phải viết lại hệ thống, nên hướng dẫn này
> chỉ dùng Tunnel.

## 1. Chọn cách

| | **Cách A — Quick Tunnel** | **Cách B — Tunnel với tên miền riêng** |
|---|---|---|
| Tài khoản Cloudflare | Không cần | Cần (miễn phí) |
| Tên miền | Không cần | Cần một tên miền của mình, đã chuyển về Cloudflare |
| Địa chỉ | `https://<chuỗi-ngẫu-nhiên>.trycloudflare.com`, **đổi mỗi lần bật** | `https://khanhvan.<tên-miền>`, cố định |
| Giới hạn | Không đảm bảo hoạt động liên tục; tối đa 200 request cùng lúc (quá thì báo lỗi 429) | Theo gói Cloudflare |
| Khi khởi động lại máy | Phải chạy lại script, link mới | cloudflared là dịch vụ Windows, tự chạy lại |
| Phù hợp | Demo, bảo vệ đồ án, cho khách dùng thử | Dùng thật, nhận webhook PayOS (cần địa chỉ cố định) |

## 2. Chuẩn bị máy chủ (cả hai cách)

### 2.1. Phần mềm

Máy mới thì cài theo mục *Chạy trên Windows* trong [HUONG_DAN_V2.md](HUONG_DAN_V2.md). Cần có:

- PostgreSQL 17 chạy dưới dạng dịch vụ Windows;
- Python;
- Node.js.

`scripts\setup.ps1` tạo `backend\.venv` và các script tự dùng Python trong đó. Nếu máy dùng **Python khác**
(ví dụ env conda `ai_signal`), khai báo một lần rồi **mở PowerShell mới**:

```powershell
setx KHANHVAN_PYTHON "C:\ProgramData\miniconda3\envs\ai_signal\python.exe"
```

`start.ps1`, `demo-public.ps1` và `test.ps1` sẽ dùng Python này.

Các lệnh `& $py ...` trong hướng dẫn này chạy trong thư mục `backend`, với biến `$py` đặt như sau (đặt lại mỗi khi
mở PowerShell mới):

```powershell
cd backend
$py = if ($env:KHANHVAN_PYTHON) { $env:KHANHVAN_PYTHON } else { '.venv\Scripts\python.exe' }
```

Dựng CSDL và build giao diện (bỏ qua nếu đã chạy `setup.ps1`):

```powershell
& $py -m app.bootstrap                      # tạo CSDL, chạy migration, nạp dữ liệu mẫu nếu còn trống
cd ..\frontend;  npm ci;  npm run build;  cd ..\backend     # build PWA vào frontend\dist
```

Cài cloudflared, xong thì mở PowerShell mới:

```powershell
winget install --id Cloudflare.cloudflared
```

### 2.2. Bảo mật — bắt buộc trước khi mở ra Internet

Chép `backend\.env.example` thành `backend\.env` rồi sửa các dòng sau:

| Dòng | Giá trị | Vì sao |
|---|---|---|
| `JWT_SECRET` | chuỗi ngẫu nhiên, tạo bằng `& $py -c "import secrets; print(secrets.token_urlsafe(48))"` | Không bắt buộc: để trống thì máy chủ tự sinh khóa ngẫu nhiên một lần và lưu trong CSDL. Không dùng các giá trị mẫu từng ghi trong mã nguồn (máy chủ sẽ bỏ qua chúng) |
| `DEV_MODE` | `1` khi demo, `0` khi dùng thật | `1` hiện nút "Mô phỏng Máy nhận tiền báo tiền về" |
| `VIETQR_BANK_BIN`, `VIETQR_ACCOUNT_NO`, `VIETQR_ACCOUNT_NAME` | tài khoản nhận tiền thật | Mặc định là tài khoản mẫu |
| `PAYOS_CHECKSUM_KEY` | khóa thật | Chỉ khi dùng PayOS |

Giữ nguyên `DATABASE_URL` và `PG_SUPERUSER_URL` như file mẫu (đã khớp PostgreSQL trên máy). Sửa `.env` xong
phải khởi động lại hệ thống; mọi người sẽ phải đăng nhập lại.

### 2.3. Không cho máy ngủ

Settings → System → Power → *Screen, sleep* → **When plugged in, put my device to sleep after: Never**.
Hoặc chạy lệnh: `powercfg /change standby-timeout-ac 0`

## 3. Cách A — Quick Tunnel (không cần tài khoản)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\demo-public.ps1        # bật, in ra link https://....trycloudflare.com
powershell -ExecutionPolicy Bypass -File scripts\demo-public.ps1 -Tat   # tắt API, Worker và tunnel
```

Script tắt bản đang chạy (nếu có), sau đó:

- chạy API và Worker ẩn, API chỉ nghe nội bộ `127.0.0.1:8000`;
- mở tunnel;
- in link ra màn hình và lưu vào `.tools\logs\link.txt`.

Log nằm trong `.tools\logs\`. Đóng cửa sổ PowerShell thì hệ thống vẫn chạy. Tắt máy hoặc mất mạng thì link chết;
lần bật sau sẽ có link khác.

## 4. Cách B — Tunnel với tên miền riêng

### B1. Đưa tên miền vào Cloudflare (làm một lần)

1. Mua một tên miền ở nhà đăng ký bất kỳ, ví dụ `noithatkhanhvan.vn`.
2. Vào [dash.cloudflare.com](https://dash.cloudflare.com) (đăng ký miễn phí) → **Domains** → **Onboard a domain**.
3. Nhập tên miền gốc (`noithatkhanhvan.vn`, không có `www`) → **Continue** → chọn gói **Free** → xem lại bản ghi
   DNS → **Continue**.
4. Cloudflare đưa ra **2 nameserver**. Vào trang quản lý tên miền ở nhà đăng ký, thay nameserver cũ bằng 2 nameserver
   này. Nếu tên miền đang bật DNSSEC thì tắt ở nhà đăng ký trước khi đổi.
5. Chờ tên miền chuyển trạng thái **Active** (Cloudflare gửi email báo). Có thể mất vài phút đến 24 giờ.

### B2. Tạo tunnel

1. Dashboard → **Networking** → **Tunnels** → **Create a tunnel**.
2. Đặt tên `khanhvan` → **Create Tunnel**.
3. Chọn hệ điều hành **Windows**. Dashboard hiện một lệnh cài đặt, dạng `cloudflared.exe service install eyJ...`.
   Chép lệnh đó, mở PowerShell bằng **Run as administrator**, dán vào và chạy. Lệnh này đăng ký cloudflared thành
   dịch vụ Windows, tự chạy khi bật máy.
4. Quay lại trang Cloudflare, chờ connector báo đã kết nối → **Continue**.

> Chuỗi `eyJ...` trong lệnh là **mật khẩu của tunnel**: ai có nó thì chạy được tunnel thay bạn.
> Không gửi cho người khác, không dán vào git hay tài liệu.

### B3. Trỏ tên miền vào hệ thống

Trong tunnel `khanhvan` → tab **Routes** → **Add route** → **Published application**:

| Ô | Điền |
|---|---|
| Subdomain | `khanhvan` → thành `https://khanhvan.noithatkhanhvan.vn`. Để trống nếu muốn dùng thẳng tên miền gốc |
| Domain | chọn tên miền ở bước B1 |
| Path | để trống |
| Service URL | `http://localhost:8000` |

Bấm **Add route**. Cloudflare tự tạo bản ghi DNS và chứng chỉ HTTPS.

Một số tài khoản còn hiện giao diện cũ (**Zero Trust → Networks → Tunnels**, tab **Public Hostname**). Khi đó điền:

- Subdomain: `khanhvan`
- Domain: chọn tên miền
- Type: `HTTP`
- URL: `localhost:8000`

### B4. Chạy hệ thống, tự chạy khi đăng nhập Windows

Chạy tay (giữ cửa sổ mở):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Nếu Windows hỏi có cho Python qua tường lửa không, chọn **Cancel**: tunnel kết nối từ trong máy ra nên không cần
mở cổng nào.

Muốn hệ thống tự chạy mỗi khi đăng nhập Windows, mở PowerShell bằng **Run as administrator** rồi chạy đoạn dưới.
Sửa `$goc` thành thư mục dự án trên máy:

```powershell
$goc = 'D:\KTPMUD'
$hanh_dong = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$goc\scripts\start.ps1`""
$khi = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$cai_dat = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero)   # mặc định Windows tự dừng sau 72 giờ
Register-ScheduledTask -TaskName 'KhanhVan - May chu' -Action $hanh_dong -Trigger $khi -Settings $cai_dat
```

- Gỡ: `Unregister-ScheduledTask -TaskName 'KhanhVan - May chu'`.
- Chạy kiểu này không có cửa sổ, nên không xem được log. Khi cần tìm lỗi, tắt task (Task Scheduler → *End*) rồi chạy
  tay `start.ps1` để xem.

### B5. Kiểm tra

- Dùng điện thoại bằng **4G** (không dùng Wi-Fi của cửa hàng), mở `https://khanhvan.<tên-miền>` → đăng nhập → thử tìm
  hàng, lập đơn. Thông báo tức thời (WebSocket) đi qua tunnel bình thường.
- Nếu dùng PayOS, khai báo địa chỉ webhook: `https://khanhvan.<tên-miền>/api/webhook/payos`.

## 5. Ngay sau lần chạy đầu

1. Đăng nhập `covan` / `KhanhVan@2026` → menu **Nhân viên & Nhật ký** → **Đặt lại MK** cho cả 3 tài khoản mẫu
   (`covan`, `anhnam`, `admin`). Mật khẩu mẫu được ghi công khai trong README.
2. Không mở cổng 8000 hay 5432 trên router: tunnel đã lo phần truy cập từ ngoài vào, PostgreSQL chỉ cần nghe trong máy.
3. Danh sách sản phẩm KiotViet nhập thẳng vào CSDL trên máy (đã nhập rồi thì chạy lại sẽ tự bỏ qua):

   ```powershell
   & $py -m app.nhap_kiotviet ..\data_bo_sung\DanhSachSanPham_KV17112026-230038-395_khoi_phuc.csv
   ```

## 6. Sao lưu

Dữ liệu chỉ nằm trên máy này: hỏng ổ đĩa là mất. Nên sao lưu mỗi ngày và chép bản sao lưu sang chỗ khác
(USB, Google Drive):

```powershell
$env:PGPASSWORD = 'khanhvan'
& 'C:\Program Files\PostgreSQL\17\bin\pg_dump.exe' -Fc -h localhost -U khanhvan -d khanhvan `
  -f "D:\SaoLuu\khanhvan-$(Get-Date -Format yyyyMMdd).dump"
```

Kèm theo đó, chép thư mục `backend\storage` (ảnh minh họa, XML hóa đơn).

Khôi phục bằng:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\pg_restore.exe' --clean --no-owner -h localhost -U khanhvan -d khanhvan <file.dump>
```

## 7. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Mở link thấy trang lỗi Cloudflare **1033** | cloudflared không chạy hoặc mất kết nối. Mở *Services* → **Cloudflared** → *Start*; kiểm tra mạng (cần ra được Internet qua cổng 7844) |
| Lỗi **502 Bad Gateway** | Tunnel chạy nhưng hệ thống chưa chạy. Chạy `start.ps1`; trên máy chủ mở thử `http://localhost:8000` |
| Lỗi **429** | Quick Tunnel vượt 200 request cùng lúc. Chuyển sang cách B |
| `demo-public.ps1` báo *Chưa có cloudflared* | `winget install --id Cloudflare.cloudflared`, rồi mở PowerShell mới |
| `demo-public.ps1` báo *Không lấy được link* | Xem `.tools\logs\tunnel.log`; mạng có thể chặn Cloudflare |
| Script báo không tìm thấy `python.exe` | Chạy `setup.ps1`, hoặc đặt `KHANHVAN_PYTHON` (mục 2.1) rồi mở PowerShell mới |
| Mọi người bị đăng xuất | Vừa đổi `JWT_SECRET`, hoặc token hết hạn (12 giờ). Đăng nhập lại |
| Đã sửa code nhưng giao diện vẫn cũ | Build lại (`cd frontend; npm run build`), khởi động lại hệ thống, tải lại trang hai lần để PWA cập nhật |
