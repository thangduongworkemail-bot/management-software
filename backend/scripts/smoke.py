"""Kiểm tra đầu-cuối trên hệ thống đang chạy (API + Worker): python scripts/smoke.py [http://localhost:8000]"""
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
c = httpx.Client(base_url=BASE, timeout=10)


def dang_nhap(ten, mk):
    r = c.post("/api/auth/dang-nhap", json={"ten_dang_nhap": ten, "mat_khau": mk})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def buoc(ten, dk):
    print(("  OK  " if dk else " LỖI ") + ten)
    if not dk:
        sys.exit(1)


chu, tho = dang_nhap("covan", "KhanhVan@2026"), dang_nhap("anhnam", "AnhNam@2026")

r = c.get("/").text
buoc("PWA được phục vụ tại /", "<div id=\"app\">" in r)
buoc("Service Worker có mặt", c.get("/sw.js").status_code == 200)

kq = c.get("/api/hang-hoa/tim-kiem", params={"q": "giuong 1m8 soi"}, headers=tho).json()
buoc(f"Tìm 'giuong 1m8 soi' -> {kq['ket_qua'][0]['ma']} trong {kq['thoi_gian_ms']} ms",
     kq["ket_qua"][0]["ma"] == "GUONG-HOP-SOI-1800" and kq["thoi_gian_ms"] < 1000)
buoc("Thợ không nhận được giá vốn / giá sàn", "gia_von" not in kq["ket_qua"][0] and "gia_san" not in kq["ket_qua"][0])

tu_tho = next(h for h in c.get("/api/hang-hoa", headers=tho).json() if h["ma"] == "TUTHO-MIT-1270")
g = c.post(f"/api/hang-hoa/bien-the/{tu_tho['id']}/tinh-gia", json={"kich_thuoc": "2m4"}, headers=tho).json()
buoc(f"Tủ thờ 2m4: {g['dien_giai']}", g["gia"] == 5_328_000)

don = c.post("/api/don-hang", json={"dong": [{"ma": "BO-BANAN-SOI-1600"}], "can_hoa_don": True,
                                     "khach_hang": {"ten": "Khách smoke test", "ma_so_thue": "4600111222"}},
             headers=tho).json()
buoc(f"Thợ lập đơn #{don['ma']} bộ bàn ăn, giữ chỗ đến {don['giu_cho_den'][11:16]}, có VietQR",
     don["trang_thai"] == "CHO_THANH_TOAN" and don["vietqr"])

tien = c.post("/api/dev/mo-phong-tien-ve", json={"ma_don": don["ma"]}, headers=chu).json()
buoc("Máy nhận tiền báo tiền về -> tự khớp đơn", tien["ket_qua"] == "DA_KHOP")
sau = c.get(f"/api/don-hang/{don['id']}", headers=tho).json()
buoc("Đơn đã thanh toán, đã giao, HĐĐT vào hàng đợi", sau["trang_thai"] == "DA_THANH_TOAN"
     and sau["trang_thai_giao"] == "DA_GIAO" and sau["hoa_don"]["trang_thai"] == "CHO_XUAT")

for _ in range(20):
    hd = c.get(f"/api/don-hang/{don['id']}", headers=tho).json()["hoa_don"]
    if hd["trang_thai"] == "DA_XUAT":
        break
    time.sleep(1)
buoc(f"Worker phát hành HĐĐT số {hd['ky_hieu']}-{hd['so_hoa_don']}", hd["trang_thai"] == "DA_XUAT")

duoi_san = c.post("/api/don-hang", json={"dong": [{"ma": "GUONG-HOP-SOI-1600", "don_gia_ban": 7_000_000}]},
                  headers=tho).json()
buoc("Thợ bán dưới giá sàn -> chờ Chủ duyệt", duoi_san["trang_thai"] == "CHO_DUYET_GIA")
yc = next(y for y in c.get("/api/yeu-cau-duyet", headers=chu).json() if y["don_hang_id"] == duoi_san["id"])
buoc("Chủ duyệt -> đơn chuyển sang chờ thanh toán",
     c.post(f"/api/yeu-cau-duyet/{yc['id']}", json={"dong_y": True}, headers=chu).json()["trang_thai"] == "CHO_THANH_TOAN")

buoc("Thợ bị chặn xác nhận tay (403)",
     c.post(f"/api/don-hang/{duoi_san['id']}/xac-nhan-tay", json={"bon_so_cuoi": "1234"}, headers=tho).status_code == 403)
kt = c.get("/api/nhat-ky/kiem-tra", headers=chu).json()
buoc(f"Chuỗi băm nhật ký toàn vẹn ({kt['so_dong']} dòng)", kt["toan_ven"])
print("\nHoàn tất kiểm tra đầu-cuối.")
