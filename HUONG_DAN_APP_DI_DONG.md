# App di động Khanh Vân: Android và iOS

Một mã nguồn Vue 3 (`frontend/`) chạy ở ba nơi:

| Cách dùng | Cài đặt | Nhận thông báo khi tắt app | In phiếu | Cập nhật bản mới |
|---|---|---|---|---|
| **PWA cài từ trình duyệt** (khuyên dùng) | Chrome (Android) / Safari (iPhone) › Thêm vào màn hình chính | Có (Android; iPhone/iPad iOS 16.4 trở lên) | In bằng trình duyệt | Tự cập nhật khi mở app |
| **App Android (file APK)** | Build bằng Android Studio, cài file `.apk` | Chưa (chỉ báo trong app khi đang mở) | Gửi phiếu qua Zalo/tin nhắn | Build và cài lại APK |
| **App iOS** | Build bằng Xcode trên máy Mac | Chưa (chỉ báo trong app khi đang mở) | Gửi phiếu qua Zalo/tin nhắn | Build lại bằng Xcode |

Cả ba đều tra giá và lập đơn được khi mất mạng (danh mục lưu trong IndexedDB, đơn tự đồng bộ khi có mạng lại),
chụp ảnh biên lai bằng camera, quét/hiện VietQR, và nhận sự kiện tức thời (WebSocket) khi app đang mở.

> Thông báo đẩy khi app đóng ở bản APK/iOS cần Firebase Cloud Messaging và tài khoản Apple Developer
> (plugin `@capacitor/push-notifications`). Bản PWA đã có đủ thông báo đẩy mà không cần hai dịch vụ này.

---

## 1. Điều kiện chung

- Máy chủ Khanh Vân (API + Worker) đang chạy: `scripts\start.ps1`, Docker, Render hoặc Cloudflare Tunnel.
- **PWA trên điện thoại cần HTTPS.** Service Worker, cài app, camera và thông báo chỉ chạy trên `https://` (hoặc `localhost`).
  Dùng Cloudflare Tunnel (`scripts\demo-public.ps1` hoặc tên miền riêng, xem `HUONG_DAN_DEPLOY_CLOUDFLARE.md`) hoặc Render.
- App gốc (APK/iOS) nối được cả máy chủ `http://192.168.x.x:8000` trong cùng wifi (đã cho phép mạng nội bộ),
  nhưng khi dùng qua Internet vẫn phải là `https://`.

## 2. Cài PWA lên điện thoại

### Android (Chrome)
1. Mở địa chỉ máy chủ bằng **Chrome**, đăng nhập.
2. Bấm **Cài app** ở dải gợi ý trên trang Tổng quan, hoặc menu **⋮ › Cài đặt ứng dụng**.
3. Biểu tượng *Khanh Vân* xuất hiện ngoài màn hình chính. Nhấn giữ biểu tượng để vào thẳng *Bán hàng / Đơn hàng / Kho*.

### iPhone / iPad (Safari)
1. Mở địa chỉ máy chủ bằng **Safari** (không mở trong Zalo/Facebook vì trình duyệt nhúng không có nút cài).
2. Bấm nút **Chia sẻ** (ô vuông có mũi tên lên) › **Thêm vào MH chính** › **Thêm**.
3. Mở app từ biểu tượng mới. App chạy toàn màn hình, thanh trạng thái nằm trên nền đỏ.

## 3. Bật thông báo đẩy

Trên điện thoại: thanh dưới cùng › **Thêm** › *Thông báo trên máy này* › **Bật thông báo** › cho phép.
Trên máy tính: trang **Nhân viên & Nhật ký**. Bấm **Gửi thử** để kiểm tra.

| Sự kiện | Ai nhận | Chạm vào mở |
|---|---|---|
| Thợ xin bán dưới giá sàn | Chủ | Đơn hàng |
| Chủ duyệt / từ chối giá | Thợ đã xin | Bán hàng |
| Tiền về lệch, giao dịch chưa khớp đơn | Chủ | Đối soát |
| Hóa đơn điện tử lỗi sau nhiều lần thử | Chủ | HĐĐT & Công nợ |
| Đơn bán ngoại tuyến thiếu hàng khi đồng bộ | Chủ | Đơn hàng |
| Máy nhận tiền mất kết nối | Chủ | Trung tâm sự cố |
| Mặt hàng có tồn khả dụng chạm ngưỡng tối thiểu (kèm tên xưởng) | Chủ | Kho & Xưởng |

- iPhone/iPad chỉ bật được khi đã **cài ra màn hình chính** và chạy iOS 16.4 trở lên.
- Mỗi mặt hàng sắp hết được nhắc tối đa một lần mỗi 24 giờ; nhập đủ lại rồi tụt tiếp thì nhắc ngay.
- Một máy đổi người đăng nhập thì thông báo chuyển sang người mới; đăng xuất thì máy không nhận thông báo của người cũ.
- Khóa VAPID của cửa hàng tự sinh một lần và lưu trong bảng `cau_hinh_he_thong`. Có thể đặt cố định bằng biến
  `VAPID_PRIVATE_KEY` (đổi khóa làm mọi máy phải bật lại thông báo). `VAPID_SUBJECT` mặc định là `mailto:` + `SENDGRID_FROM`.

## 4. Build app Android (APK)

Cần: Node.js 22+, **Android Studio** bản mới (có sẵn JDK 21 và Android SDK 36).

```powershell
cd frontend
npm install
# (tuỳ chọn) đặt sẵn địa chỉ máy chủ để người dùng khỏi phải gõ:
$env:VITE_MAY_CHU = 'https://ten-cua-hang.onrender.com'
npm run app:android        # build giao diện, chép vào android/, mở Android Studio
```

Trong Android Studio: **Build › Build App Bundle(s) / APK(s) › Build APK(s)**. File ra ở
`frontend/android/app/build/outputs/apk/debug/app-debug.apk`. Chép sang điện thoại, cho phép *cài ứng dụng không rõ nguồn*
rồi mở file để cài. Phát hành chính thức: **Build › Generate Signed App Bundle / APK** với khóa ký riêng của cửa hàng.

Không dùng Android Studio: `cd frontend\android; .\gradlew.bat assembleDebug` (cần `JAVA_HOME` trỏ tới JDK 21 và `ANDROID_HOME`).

## 5. Build app iOS

Cần máy **Mac** có Xcode bản mới. Dự án dùng Swift Package Manager, không cần CocoaPods.

```bash
cd frontend
npm install
VITE_MAY_CHU=https://ten-cua-hang.onrender.com npm run app:ios   # build, chép vào ios/, mở Xcode
```

Trong Xcode: chọn *App* › **Signing & Capabilities** › chọn Team (Apple ID miễn phí cài được lên iPhone của mình,
hết hạn sau 7 ngày; đưa lên App Store/TestFlight cần Apple Developer Program). Cắm iPhone, bấm **Run**.

## 6. Dùng app lần đầu (APK/iOS)

1. Mở app: màn **Kết nối máy chủ cửa hàng** hiện ra (trừ khi build đã đặt `VITE_MAY_CHU`).
2. Gõ địa chỉ như trên máy tính quầy, ví dụ `ten-cua-hang.onrender.com` (tự thêm `https://`) hoặc
   `192.168.1.10:8000` khi dùng chung wifi (tự thêm `http://`). App gọi `/api/suc-khoe` để kiểm tra trước khi lưu.
3. Đăng nhập. Đổi máy chủ sau này: **Thêm › Máy chủ › Đổi** (đăng xuất rồi chọn lại).

Máy chủ cho phép app gọi API từ `capacitor://localhost` (iOS), `https://localhost` (Android) qua biến `CORS_ORIGINS`.

## 7. Bảo trì

| Việc | Lệnh (trong `frontend/`) |
|---|---|
| Đổi biểu tượng / màn chờ | Sửa `public/icon.svg` rồi `npm run icons` (sinh PNG cho PWA, Android, iOS; biểu tượng iOS không có kênh trong suốt theo yêu cầu Apple) |
| Chép bản giao diện mới vào hai app gốc | `npm run app:sync` |
| Đổi tên / mã app | `capacitor.config.json` (`appName`, `appId` = `vn.khanhvan.banhang`) rồi `npx cap sync` |
| Quyền camera / thư viện ảnh iOS | `ios/App/App/Info.plist` (`NSCameraUsageDescription`, `NSPhotoLibraryUsageDescription`) |
| Cho phép máy chủ HTTP trong LAN | Android: `usesCleartextTraffic` trong `AndroidManifest.xml`; iOS: `NSAllowsLocalNetworking` |

Các file liên quan: `src/nen-tang.js` (phân biệt web/PWA/app gốc, địa chỉ máy chủ, chia sẻ, nút Quay lại Android),
`src/day.js` + `public/day-thong-bao.js` (thông báo đẩy), `src/cai-dat.js` + `components/CaiDatApp.vue` (gợi ý cài app),
`components/ChonMayChu.vue`, `backend/app/adapters/webpush.py`, `backend/app/services/day.py`, `database/migrations/007_thong_bao_day.sql`.

**Quy tắc khi viết thêm giao diện:** mọi đường dẫn tới máy chủ (`/api/…`, `/files/…`, link báo giá) phải đi qua
`urlMayChu()` / `urlCongKhai()` trong `nen-tang.js`, nếu không app gốc sẽ gọi nhầm vào chính nó.

## 8. Kịch bản kiểm thử trên điện thoại

Cột *Kết quả* ghi những gì đã chạy tự động trên máy phát triển (Edge giả lập iPhone 390×844 và Android 412×915,
Puppeteer, máy chủ thật + PostgreSQL). Các ca *máy thật* cần chạy trên điện thoại trước buổi bảo vệ.

| Mã | Kịch bản | Kỳ vọng | Kết quả |
|---|---|---|---|
| MB-01 | Mở web trên điện thoại, đăng nhập Chủ | Thanh dưới có Tổng quan, Bán hàng, Đơn hàng, Kho, Thêm; menu trên ẩn | Đạt (tự động) |
| MB-02 | Bấm Thêm | Hiện các chức năng còn lại, thẻ Thông báo, Cài app, Đăng xuất | Đạt (tự động) |
| MB-03 | Bán hàng: gõ `giuong 1m8 soi` | Ra Giường hộp Gỗ Sồi Nga 1m8, giá 8.500.000 đ, dưới 1 giây | Đạt (tự động, 24,5 ms) |
| MB-04 | Mở trên máy tính 1366×800 | Giao diện cũ: menu trên, không có thanh dưới | Đạt (tự động) |
| MB-05 | Manifest & Service Worker | 4 biểu tượng (có maskable), 3 phím tắt, `sw.js` đăng ký | Đạt (tự động) |
| MB-06 | App gốc mở lần đầu | Hiện màn Kết nối máy chủ; địa chỉ sai báo lỗi dễ hiểu; địa chỉ đúng thì lưu | Đạt (tự động, giả lập WebView Android) |
| MB-07 | App gốc gọi API khác origin | Đăng nhập, tìm hàng, WebSocket đều chạy (CORS đúng) | Đạt (tự động, giả lập) |
| MB-08 | Bật thông báo, bấm Gửi thử | Dịch vụ đẩy nhận (HTTP 2xx), máy hiện "Thông báo đã bật" | Đạt (tự động, Edge + Microsoft WNS thật) |
| MB-09 | Chủ sửa công thức tủ thờ 1.850.000 → 2.000.000 đ/m, thử 2m4 | Xem trước 5.760.000 đ, lưu, máy chủ tính lại 5.760.000 đ | Đạt (tự động) |
| MB-10 | Tắt wifi + 4G, lập đơn tiền mặt | Đơn lưu trong máy, thanh trên báo "MẤT MẠNG", có mạng lại tự đồng bộ, không trùng | Cần chạy máy thật |
| MB-11 | Cài PWA trên iPhone (Safari › Thêm vào MH chính) | Biểu tượng KV đỏ, mở toàn màn hình, không bị tai thỏ che | Cần chạy máy thật |
| MB-12 | Thợ xin bán dưới giá sàn khi app của Chủ đang tắt | Điện thoại Chủ rung, chạm vào mở Đơn hàng | Cần chạy máy thật (Android + iPhone) |
| MB-13 | Xác nhận tay: chụp ảnh biên lai bằng camera | Mở camera sau, ảnh được thu nhỏ rồi tải lên | Cần chạy máy thật |
| MB-14 | APK: nút Quay lại khi đang mở hộp thoại | Đóng hộp thoại, không rời trang; ở trang đầu thì thu nhỏ app | Cần chạy máy thật |
| MB-15 | APK: Phiếu bán hàng › Gửi phiếu | Mở bảng chia sẻ Android, gửi được qua Zalo | Cần chạy máy thật |

Kiểm thử tự động tương ứng: `backend/tests/test_thong_bao_day.py` (mã hóa khớp bộ mẫu RFC 8291, VAPID, đăng ký,
xếp hàng theo sự kiện, tồn dưới ngưỡng, máy gỡ app, CORS), `backend/tests/test_cong_thuc_gia.py`,
`frontend/src/lib/may-chu.test.js` (chuẩn hóa địa chỉ máy chủ).

## 9. Giới hạn đã biết

- Hai dự án gốc `frontend/android` và `frontend/ios` được sinh và đồng bộ trên máy phát triển nhưng **chưa được biên dịch**
  (máy không có JDK/Android SDK, và iOS chỉ build được trên Mac). Các ca MB-10 đến MB-15 cần chạy trên máy thật.
- Bản APK/iOS chưa có thông báo đẩy khi app đóng (cần FCM/APNs) và không in trực tiếp được (gửi phiếu qua chia sẻ).
- Safari trên iPhone xóa dữ liệu ngoại tuyến của web **chưa cài** sau 7 ngày không mở; PWA đã cài ra màn hình chính
  thì không bị. Vì vậy trên iPhone nên cài PWA.
