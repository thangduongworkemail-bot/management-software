"""Nhập danh mục từ file KiotViet vào CSDL; từ đồng nghĩa áp dụng cả phía mặt hàng (mỗi test rollback)."""
from app import nhap_kiotviet
from app.services import catalog

from .conftest import ton
from .test_kiotviet import _csv, _dong

FILE_THU = _csv(
    _dong("SP900001", "Tủ áo gỗ lát", "7,000,000.0", "4,500,000.0", "2.0", "CHÂN:2 buồng"),
    _dong("SP900002", "Tủ áo gỗ lát", "8,000,000.0", "5,300,000.0", "0.0", "CHÂN:3 buồng", "SP900001"),
    _dong("SP900003", "kệ ti vi gỗ xồi Nga", "10,000,000.0", "5,400,000.0", "1.0", "CHÂN:2m4"),
    _dong("SP900004", "đài nến", "3,000,000.0", "1,200,000.0", "3.0", dvt="bộ"),
    _dong("SP900005", "xập thờ gỗ mít ta", "13,000,000.0", "8,800,000.0", "1.0", "CHÂN:chân 16"),
    _dong("SP900006", "bàn thờ treo gỗ pơ-mu", "500,000.0", "330,000.0", "0.0", "CHÂN:61cm"),
)


def test_nhap_tao_mau_bien_the_gia_va_ton_dau_ky(conn, chu):
    bc = nhap_kiotviet.nhap(conn, chu, FILE_THU, "thu.csv")
    assert bc["da_nhap"] == [f"SP90000{i}" for i in range(1, 7)] and bc["ton_dau_ky"] == 7 and bc["so_mau"] == 5
    assert bc["theo_nhom"] == {"Tủ / Kệ": 3, "Đồ thờ": 3}

    tu = catalog.tim_theo_ma(conn, "SP900002")
    assert (tu["ten"], tu["mau_hang"], tu["loai_hang"]) == ("Tủ áo gỗ lát – 3 buồng", "Tủ áo gỗ lát", "Tủ / Kệ")
    assert (tu["gia_niem_yet"], tu["gia_von"], tu["gia_san"]) == (8_000_000, 5_300_000, None)
    assert catalog.tim_theo_ma(conn, "SP900001")["mau_hang_id"] == tu["mau_hang_id"]
    ke = catalog.tim_theo_ma(conn, "SP900003")
    assert (ke["loai_go"], ke["dai_mm"], ke["thuoc_tinh"], ke["don_vi_tinh"]) == ("Sồi", 2400, {"Chân": "2m4"}, "cái")
    nen = catalog.tim_theo_ma(conn, "SP900004")
    assert (nen["loai_hang"], nen["don_vi_tinh"]) == ("Đồ thờ", "bộ")

    # Tồn KiotViet -> một dòng DIEU_CHINH "tồn đầu kỳ" trong sổ cái; tồn 0 thì không ghi gì
    assert ton(conn, "SP900001")["ton_hien_co"] == 2 and ton(conn, "SP900002")["ton_hien_co"] == 0
    so_cai = conn.execute("""SELECT sc.loai, sc.so_luong, sc.ly_do FROM so_cai_ton sc JOIN bien_the bt
                             ON bt.id = sc.bien_the_id WHERE bt.ma_noi_bo LIKE 'SP90000%' ORDER BY sc.id""").fetchall()
    assert [(r["loai"], r["so_luong"]) for r in so_cai] == [("DIEU_CHINH", 2), ("DIEU_CHINH", 1), ("DIEU_CHINH", 3),
                                                            ("DIEU_CHINH", 1)]
    assert so_cai[0]["ly_do"] == "Tồn đầu kỳ chuyển từ KiotViet (SP900001)"
    nk = conn.execute("SELECT du_lieu_sau FROM nhat_ky WHERE hanh_dong = 'NHAP_KIOTVIET' ORDER BY id DESC LIMIT 1"
                      ).fetchone()["du_lieu_sau"]
    assert nk["so_mat_hang"] == 6 and nk["file"] == "thu.csv"


def test_chay_lai_khong_nhap_trung(conn, chu):
    nhap_kiotviet.nhap(conn, chu, FILE_THU, "thu.csv")
    bc = nhap_kiotviet.nhap(conn, chu, FILE_THU, "thu.csv")
    assert bc["da_nhap"] == [] and len(bc["bo_qua"]) == 6 and bc["dong_nghia_moi"] == []
    assert ton(conn, "SP900001")["ton_hien_co"] == 2


def test_hang_kiotviet_tim_duoc_ca_theo_ten_thuong_lan_ten_chuan(conn, chu):
    bc = nhap_kiotviet.nhap(conn, chu, FILE_THU, "thu.csv")
    assert "xồi = sồi" in bc["dong_nghia_moi"]

    def ma(q):
        return [r["ma"] for r in catalog.tim_kiem(conn, q, chu)]
    # Dữ liệu mẫu có từ đồng nghĩa "tủ áo" = "tủ quần áo", "bàn thờ" = "tủ thờ", "kệ ti vi" = "kệ tivi":
    # câu tìm bị đổi sang tên chuẩn nhưng hàng đặt tên theo cách gọi thường vẫn phải ra
    assert {"SP900001", "SP900002"} <= set(ma("tủ áo gỗ lát"))
    assert "SP900006" in ma("bàn thờ treo")
    assert ma("ke tivi soi 2m4") == ["SP900003"]
    assert ma("sập thờ mít") == ["SP900005"]


def test_them_dong_nghia_cap_nhat_chi_muc_hang_cu(conn, chu):
    loai = conn.execute("SELECT id FROM loai_hang WHERE ma = 'BAN_GHE'").fetchone()["id"]
    catalog.tao_bien_the(conn, chu, {"ten_mau_moi": "Ghế đôn", "loai_hang_id": loai, "ma_noi_bo": "GHE-DON-MIT",
                                     "ten_hien_thi": "Ghế đôn gỗ mít", "gia_niem_yet": 900_000})
    def tim_kiem_luu():
        return conn.execute("SELECT tim_kiem FROM bien_the WHERE ma_noi_bo = 'GHE-DON-MIT'").fetchone()["tim_kiem"]
    assert "ghe dau" not in tim_kiem_luu()
    catalog.them_dong_nghia(conn, chu, "ghế đôn", "ghế đẩu")
    assert tim_kiem_luu().endswith(" ghe dau")
    assert "GHE-DON-MIT" in [r["ma"] for r in catalog.tim_kiem(conn, "ghế đẩu", chu)]
