"""30 mặt hàng nội thất gỗ bổ sung (app/hang_mau_bo_sung.py): dữ liệu hợp lệ, nạp qua service đúng sổ sách,
chạy lại không trùng, tìm kiếm và phân quyền giá như hàng thật."""
import re

from app import hang_mau_bo_sung as hm
from app import seed
from app.services import catalog, inventory, orders

from .conftest import id_bien_the

MA_HOP_LE = re.compile(r"^[A-Z0-9][A-Za-z0-9-]*$")


# --- Dữ liệu (không cần CSDL) -------------------------------------------------------
def test_du_lieu_30_mat_hang_hop_le():
    assert len(hm.HANG_MAU) == 30
    ma = [h.ma for h in hm.HANG_MAU]
    assert len(set(ma)) == 30 and all(MA_HOP_LE.match(m) for m in ma)
    ma_seed = {bt[0] for *_, ds in seed.MAU_HANG for bt in ds}
    assert not set(ma) & ma_seed, "trùng mã với dữ liệu mẫu gốc"
    nhom = {l[0] for l in seed.LOAI_HANG}
    go = {g for g, _ in seed.HE_SO_GO} | {g for g, _ in hm.LOAI_GO_MOI}
    for h in hm.HANG_MAU:
        assert h.loai in nhom and h.go in go and h.xuong in hm.XUONG, h.ma
        if h.cong_thuc:   # hàng đặt riêng: giá theo công thức, không nhập kho
            assert h.gia is None and h.nhap is None and h.toi_thieu == 0, h.ma
        else:
            san, niem_yet = h.gia
            so_luong, gia_nhap = h.nhap
            assert 0 < gia_nhap < san <= niem_yet and so_luong > 0, h.ma
            assert niem_yet % 1000 == 0 and san % 1000 == 0, h.ma


def test_du_lieu_bo_san_pham_va_dong_nghia():
    ma = {h.ma: h for h in hm.HANG_MAU}
    for _, _, _, niem_yet, san, thanh_phan in hm.BO_MOI:
        assert san <= niem_yet
        assert all(m in ma and ma[m].nhap for m, _ in thanh_phan)
        tong_le = sum(ma[m].gia[1] * sl for m, sl in thanh_phan)
        assert niem_yet < tong_le, "mua cả bộ phải rẻ hơn mua lẻ"
    assert len({k for k, _ in hm.DONG_NGHIA_MOI}) == len(hm.DONG_NGHIA_MOI)


# --- Nạp vào CSDL ---------------------------------------------------------------------
def test_nap_qua_service_dung_so_sach(conn, chu):
    kq = hm.nap(conn, chu)
    assert len(kq["mat_hang"]) == 30 and kq["bo_qua"] == []
    assert kq["loai_go_moi"] == ["Cao su", "Thông", "Gụ"]
    assert len(kq["xuong_moi"]) == 2 and len(kq["phieu_nhap"]) == 5
    assert kq["bo"] == ["BO-BANAN-CAOSU-1200", "BO-SOFA-SOI-BANTRA"] and len(kq["dong_nghia"]) == 6

    for h in hm.HANG_MAU:
        bt = catalog.lay_bien_the(conn, id_bien_the(conn, h.ma))
        assert bt["dat_theo_kich_thuoc"] == (h.cong_thuc is not None)
        if h.cong_thuc:
            assert bt["kieu_cong_thuc"] == h.cong_thuc["kieu"] and not bt["ton_hien_co"]
            continue
        assert (bt["gia_san"], bt["gia_niem_yet"]) == h.gia, h.ma
        assert (bt["ton_hien_co"], bt["gia_von"]) == h.nhap, h.ma   # giá vốn bình quân từ phiếu nhập
        assert bt["xuat_xu"] == hm.XUAT_XU[h.xuong] and bt["mo_ta"] == h.mo_ta
        assert set(h.thuoc_tinh.items()) <= set(bt["thuoc_tinh"].items())

    tong_phieu = sum(t for *_, t in kq["phieu_nhap"])
    assert tong_phieu == sum(h.nhap[0] * h.nhap[1] for h in hm.HANG_MAU if h.nhap)
    sl_nhap = conn.execute(
        """SELECT sum(s.so_luong) AS n FROM so_cai_ton s JOIN bien_the bt ON bt.id = s.bien_the_id
           WHERE s.loai = 'NHAP' AND bt.ma_noi_bo = ANY(%s)""", ([h.ma for h in hm.HANG_MAU],)).fetchone()["n"]
    assert sl_nhap == sum(h.nhap[0] for h in hm.HANG_MAU if h.nhap)
    dong_ky = conn.execute("SELECT so_du_cong_no FROM nha_cung_cap WHERE ten = 'Xưởng Mộc Đồng Kỵ'").fetchone()
    assert dong_ky["so_du_cong_no"] == sum(h.nhap[0] * h.nhap[1] for h in hm.HANG_MAU
                                           if h.nhap and h.xuong == "DONG_KY")


def test_chay_lai_khong_tao_trung(conn, chu):
    hm.nap(conn, chu)
    so_phieu = conn.execute("SELECT count(*) AS n FROM phieu_nhap").fetchone()["n"]
    lan_hai = hm.nap(conn, chu)
    assert lan_hai["mat_hang"] == [] and len(lan_hai["bo_qua"]) == 30
    assert lan_hai["phieu_nhap"] == [] and lan_hai["bo"] == [] and lan_hai["xuong_moi"] == []
    assert lan_hai["loai_go_moi"] == [] and lan_hai["dong_nghia"] == []
    assert conn.execute("SELECT count(*) AS n FROM phieu_nhap").fetchone()["n"] == so_phieu


def test_gia_hang_dat_rieng(conn, chu):
    hm.nap(conn, chu)
    gia = lambda ma, kt: catalog.tinh_gia_dat_rieng(conn, id_bien_the(conn, ma), kt)["gia"]  # noqa: E731
    assert gia("GIUONG-TANG-THONG-DATRIENG", "1m2") == 7_600_000          # theo bậc
    assert gia("TU-BEP-XOAN-DATRIENG", "3m") == 18_150_000                # 5,5 tr/m × 1,1 (Xoan đào) × 3 m
    # 4,8 tr/m² × 6,24 m² × 0,6 (MDF) = 17.971.200, làm tròn nghìn, + 500k công lắp
    assert gia("TU-AM-TUONG-MDF-DATRIENG", "2m4 x 2m6") == 18_471_000


def test_tim_kiem_dong_nghia_va_an_gia_voi_tho(conn, chu, tho):
    hm.nap(conn, chu)
    ma = lambda q, ai: [r["ma"] for r in catalog.tim_kiem(conn, q, ai)]  # noqa: E731
    assert "BAN-TRA-SOI-1100" in ma("bàn uống nước", chu)
    assert ma("tab dau giuong", chu)[0] == "TU-DAU-GIUONG-SOI"
    assert "GIUONG-TANG-THONG-DATRIENG" in ma("giường 2 tầng", chu)
    assert "BAN-TRANG-DIEM-SOI" in ma("ban phan", chu)
    assert "BANTHO-TREO-SOI-810" in ma("bàn thờ treo", chu)
    for r in catalog.tim_kiem(conn, "gỗ sồi", tho):
        assert "gia_von" not in r and "gia_san" not in r


def test_canh_bao_ton_thap_va_ban_bo(conn, chu):
    hm.nap(conn, chu)
    canh_bao = {h["ma"]: h for h in inventory.canh_bao_ton_thap(conn)}
    assert {"BANTHO-TREO-SOI-810", "TU-DAU-GIUONG-SOI"} <= set(canh_bao)
    assert canh_bao["BANTHO-TREO-SOI-810"]["xuong"] == "Xưởng Đồ Thờ Cát Đẳng"
    assert "TU-AO-XOAN-3C" not in canh_bao

    bo = catalog.tim_kiem(conn, "BO-BANAN-CAOSU-1200", chu)[0]
    assert bo["ton_kha_dung"] == 4 and bo["gia_niem_yet"] == 4_350_000   # 4 bàn, 16 ghế -> 4 bộ
    don = orders.tao_don(conn, chu, {"dong": [{"ma": "BO-BANAN-CAOSU-1200"}],
                                     "khach_hang": {"ten": "Khách thử", "so_dien_thoai": "0900000001"}})
    assert don["tong_tien"] == 4_350_000
