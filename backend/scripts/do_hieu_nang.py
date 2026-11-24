"""Đo hiệu năng (Tuần 13). Chạy trong backend/:

    python scripts/do_hieu_nang.py [--url http://127.0.0.1:8000] [--luong 10] [--so-lan 200] [--lan-ghi 50]

Phần 1, HTTP chỉ đọc: --luong luồng cùng gọi API đang chạy ở --url, mỗi loại yêu cầu --so-lan lần:
tra giá, tính giá hàng đặt riêng, trang tổng quan của Chủ, tải danh mục cho chế độ ngoại tuyến.
Phần 2, ghi: ngay trong CSDL của DATABASE_URL, lập đơn + thu đủ tiền mặt + chốt đơn (xuất kho, phiếu bán hàng,
xếp hàng đợi HĐĐT, nhật ký) rồi ROLLBACK, nên không để lại dữ liệu nào.
In trung vị (p50), p95, lớn nhất (ms) và số yêu cầu mỗi giây.
"""
import argparse
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402
from app.security import NguoiDung  # noqa: E402
from app.services import orders, payments  # noqa: E402

TU_KHOA = ["giuong 1m8 soi", "tu tho", "ban uong nuoc", "tu ao 4 canh", "sofa go", "ke tivi", "ban an 6 ghe",
           "tu quan ao xoan dao", "giuong tang", "ban tho treo"]


def phan_vi(ds: list[float], p: float) -> float:
    ds = sorted(ds)
    return ds[min(len(ds) - 1, int(round(p / 100 * (len(ds) - 1))))]


def in_dong(ten: str, thoi_gian_ms: list[float], tong_giay: float, loi: int) -> None:
    print(f"{ten:34} {len(thoi_gian_ms):5} {statistics.median(thoi_gian_ms):8.1f} {phan_vi(thoi_gian_ms, 95):8.1f} "
          f"{max(thoi_gian_ms):8.1f} {len(thoi_gian_ms) / tong_giay:8.1f} {loi:4}")


def dang_nhap(url: str, ten: str, mk: str) -> dict:
    r = httpx.post(f"{url}/api/auth/dang-nhap", json={"ten_dang_nhap": ten, "mat_khau": mk}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def do_http(url: str, luong: int, so_lan: int) -> None:
    tho = dang_nhap(url, "anhnam", "AnhNam@2026")
    chu = dang_nhap(url, "covan", "KhanhVan@2026")
    tu_tho = httpx.get(f"{url}/api/hang-hoa/tim-kiem", params={"q": "TUTHO-MIT-1270"},
                       headers=tho).json()["ket_qua"][0]["id"]
    yeu_cau = {
        "Tra giá (tim-kiem)": lambda c, i: c.get("/api/hang-hoa/tim-kiem", params={"q": TU_KHOA[i % len(TU_KHOA)]},
                                                 headers=tho),
        "Tính giá đặt riêng (tinh-gia)": lambda c, i: c.post(f"/api/hang-hoa/bien-the/{tu_tho}/tinh-gia",
                                                              json={"kich_thuoc": f"2m{i % 9 + 1}"}, headers=tho),
        "Tổng quan của Chủ (tong-quan)": lambda c, i: c.get("/api/tong-quan", headers=chu),
        "Danh mục ngoại tuyến (sync)": lambda c, i: c.get("/api/sync/danh-muc", headers=tho),
    }
    rieng = threading.local()

    def khach() -> httpx.Client:
        if not hasattr(rieng, "c"):
            rieng.c = httpx.Client(base_url=url, timeout=30)
        return rieng.c

    print(f"Phần 1: HTTP chỉ đọc tới {url}, {luong} luồng đồng thời")
    print(f"{'Yêu cầu':34} {'Số':>5} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8} {'req/s':>8} {'lỗi':>4}")
    for ten, goi in yeu_cau.items():
        def mot(i, goi=goi):
            t = time.perf_counter()
            r = goi(khach(), i)
            return (time.perf_counter() - t) * 1000, r.status_code
        with ThreadPoolExecutor(luong) as ex:
            list(ex.map(mot, range(luong)))          # làm nóng kết nối
            t0 = time.perf_counter()
            kq = list(ex.map(mot, range(so_lan)))
            tong = time.perf_counter() - t0
        in_dong(ten, [ms for ms, _ in kq], tong, sum(1 for _, ma in kq if ma != 200))


def do_ghi(lan: int) -> None:
    print(f"\nPhần 2: lập đơn + thu tiền mặt + chốt đơn, {lan} lần, mỗi lần ROLLBACK")
    with db.connect() as conn:
        tk = conn.execute("SELECT id, vai_tro, ho_ten FROM tai_khoan WHERE ten_dang_nhap = 'anhnam'").fetchone()
        tho = NguoiDung(id=tk["id"], vai_tro=tk["vai_tro"], ho_ten=tk["ho_ten"])
        ma = conn.execute(
            """SELECT bt.ma_noi_bo FROM v_ton_kho t JOIN bien_the bt ON bt.id = t.bien_the_id
               WHERE t.ton_kha_dung >= 1 AND bt.dang_ban AND NOT bt.dat_theo_kich_thuoc
               ORDER BY t.ton_kha_dung DESC LIMIT 1""").fetchone()["ma_noi_bo"]
        conn.rollback()
        thoi_gian = []
        t0 = time.perf_counter()
        for _ in range(lan):
            t = time.perf_counter()
            don = orders.tao_don(conn, tho, {"dong": [{"ma": ma}]})
            payments.ghi_nhan_thanh_toan(conn, tho, don["id"], don["tong_tien"], "TIEN_MAT")
            thoi_gian.append((time.perf_counter() - t) * 1000)
            trang_thai = conn.execute("SELECT trang_thai FROM don_hang WHERE id = %s", (don["id"],)).fetchone()
            assert trang_thai["trang_thai"] == "DA_THANH_TOAN", trang_thai
            conn.rollback()
        tong = time.perf_counter() - t0
    print(f"Mặt hàng dùng để đo: {ma}")
    print(f"{'Thao tác':34} {'Số':>5} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8} {'lần/s':>8} {'lỗi':>4}")
    in_dong("Bán 1 món, thu đủ tiền mặt, chốt", thoi_gian, tong, 0)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--luong", type=int, default=10)
    p.add_argument("--so-lan", type=int, default=200)
    p.add_argument("--lan-ghi", type=int, default=50)
    a = p.parse_args()
    do_http(a.url.rstrip("/"), a.luong, a.so_lan)
    do_ghi(a.lan_ghi)


if __name__ == "__main__":
    main()
