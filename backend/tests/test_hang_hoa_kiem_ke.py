"""Sửa thuộc tính mặt hàng, thêm / xóa / khôi phục, kiểm kê theo số đếm thực tế, thêm xưởng (mỗi test rollback)."""
import pytest

from app.errors import LoiNghiepVu
from app.services import catalog, inventory, orders

from .conftest import id_bien_the, ton


def test_seed_co_thong_so_chi_tiet(conn, chu):
    bt = catalog.lay_bien_the(conn, id_bien_the(conn, "TU-AO-MDF-4C"))
    assert bt["hoan_thien"] == "Melamine chống ẩm" and bt["bao_hanh_thang"] == 12 and bt["khoi_luong_kg"] == 120
    assert bt["thuoc_tinh"]["Số cánh"] == 4 and bt["thuoc_tinh"]["Có gương"] is True
    ghe = catalog.lay_bien_the(conn, id_bien_the(conn, "GHE-AN-SOI"))
    assert ghe["thuoc_tinh"]["Số chỗ ngồi"] == 1 and ghe["thuoc_tinh"]["Có đệm"] is True


def test_tim_kiem_theo_thong_so_chi_tiet(conn, chu):
    ma = [r["ma"] for r in catalog.tim_kiem(conn, "giam chan hafele", chu)]
    assert ma == ["TU-AO-MDF-4C"]


def test_sua_moi_thuoc_tinh_va_gia(conn, chu):
    bt_id = id_bien_the(conn, "KE-TIVI-MDF-1800")
    moi = catalog.sua_bien_the(conn, chu, bt_id, {
        "ma_noi_bo": "KE-TIVI-MDF-1800-V2", "ten_hien_thi": "Kệ tivi MDF 1m8 (mẫu 2025)", "mau_sac": "Trắng",
        "loai_go": "Sồi", "cao_mm": 500, "hoan_thien": "Sơn PU trắng", "bao_hanh_thang": 18,
        "thuoc_tinh": {"Số ngăn kéo": 3, "Có đèn LED": True}, "gia_san": 2_700_000, "gia_niem_yet": 3_000_000})
    assert (moi["ma"], moi["mau_sac"], moi["loai_go"], moi["cao_mm"]) == ("KE-TIVI-MDF-1800-V2", "Trắng", "Sồi", 500)
    assert moi["thuoc_tinh"] == {"Số ngăn kéo": 3, "Có đèn LED": True}
    # Sàn mới 2,7tr cao hơn niêm yết cũ 2,6tr: hợp lệ vì kiểm tra sau khi đổi cả hai mức
    assert (moi["gia_san"], moi["gia_niem_yet"]) == (2_700_000, 3_000_000)
    assert "ke-tivi-mdf-1800-v2" in moi["tim_kiem"] and "son pu trang" in moi["tim_kiem"]
    # Giá cũ vẫn còn trong lịch sử, không bị ghi đè
    assert any(g["so_tien"] == 2_600_000 and g["den_ngay"] for g in catalog.lich_su_gia(conn, bt_id))
    nk = conn.execute("SELECT du_lieu_truoc FROM nhat_ky WHERE hanh_dong = 'SUA_BIEN_THE' ORDER BY id DESC LIMIT 1"
                      ).fetchone()["du_lieu_truoc"]
    assert nk["ma_noi_bo"] == "KE-TIVI-MDF-1800" and nk["mau_sac"] == "Óc chó"


def test_sua_khong_cho_gia_san_vuot_niem_yet(conn, chu):
    with pytest.raises(LoiNghiepVu) as e:
        catalog.sua_bien_the(conn, chu, id_bien_the(conn, "KE-TIVI-MDF-1800"), {"gia_san": 9_000_000})
    assert e.value.ma == "GIA_SAN_VUOT_NIEM_YET"


def test_sua_tu_choi_loai_go_la_va_khong_doi_gi(conn, chu):
    bt_id = id_bien_the(conn, "KE-TIVI-MDF-1800")
    with pytest.raises(LoiNghiepVu) as e:
        catalog.sua_bien_the(conn, chu, bt_id, {"loai_go": "Gỗ lạ"})
    assert e.value.ma == "LOAI_GO_KHONG_CO"
    with pytest.raises(LoiNghiepVu) as e:
        catalog.sua_bien_the(conn, chu, bt_id, {"mau_sac": "Óc chó"})
    assert e.value.ma == "KHONG_CO_THAY_DOI"


def test_them_mat_hang_phat_hien_khi_kiem_ke(conn, chu):
    loai = conn.execute("SELECT id FROM loai_hang WHERE ma = 'TU_KE'").fetchone()["id"]
    bt = catalog.tao_bien_the(conn, chu, {
        "ten_mau_moi": "Tủ giày", "loai_hang_id": loai, "ma_noi_bo": "TU-GIAY-SOI-900",
        "ten_hien_thi": "Tủ giày Gỗ Sồi 90cm", "loai_go": "Sồi", "dai_mm": 900, "rong_mm": 350, "cao_mm": 1000,
        "thuoc_tinh": {"Số cánh": 2}, "gia_von": 1_500_000, "gia_san": 1_900_000, "gia_niem_yet": 2_200_000,
        "ton_ban_dau": 3, "ly_do": "Kiểm kê quý 4: phát hiện 3 cái chưa có mã"})
    assert (bt["mau_hang"], bt["loai_hang"], bt["ton_hien_co"], bt["gia_niem_yet"]) == ("Tủ giày", "Tủ / Kệ", 3, 2_200_000)
    dong = inventory.so_cai(conn, bt["id"])
    assert [(d["loai"], d["so_luong"]) for d in dong] == [("DIEU_CHINH", 3)]


def test_xoa_ghi_ve_0_an_khoi_danh_muc_va_khoi_phuc(conn, chu):
    bt_id = id_bien_the(conn, "TU-AO-MDF-4C")
    ton_truoc = ton(conn, "TU-AO-MDF-4C")["ton_hien_co"]
    assert ton_truoc > 0
    catalog.xoa_bien_the(conn, chu, bt_id, "Ngừng nhập mẫu này")
    assert ton(conn, "TU-AO-MDF-4C")["ton_hien_co"] == 0
    assert all(h["ma"] != "TU-AO-MDF-4C" for h in catalog.danh_sach(conn, chu))
    assert any(h["ma"] == "TU-AO-MDF-4C" for h in catalog.danh_sach(conn, chu, ca_ngung_ban=True))
    assert catalog.tim_kiem(conn, "tu quan ao mdf", chu) == []
    with pytest.raises(LoiNghiepVu) as e:
        orders.tao_don(conn, chu, {"dong": [{"ma": "TU-AO-MDF-4C"}]})
    assert e.value.ma == "NGUNG_BAN"
    assert catalog.khoi_phuc_bien_the(conn, chu, bt_id)["dang_ban"] is True


def test_khong_xoa_hang_dang_giu_cho_hoac_thuoc_bo(conn, chu):
    orders.tao_don(conn, chu, {"dong": [{"ma": "GUONG-HOP-SOI-1800"}]})
    with pytest.raises(LoiNghiepVu) as e:
        catalog.xoa_bien_the(conn, chu, id_bien_the(conn, "GUONG-HOP-SOI-1800"), "Thử xóa")
    assert e.value.ma == "DANG_GIU_CHO"
    with pytest.raises(LoiNghiepVu) as e:
        catalog.xoa_bien_the(conn, chu, id_bien_the(conn, "GHE-AN-SOI"), "Thử xóa")
    assert e.value.ma in ("THUOC_BO_SAN_PHAM", "DANG_GIU_CHO")


def test_kiem_ke_theo_so_dem_thuc_te(conn, chu):
    a, b = id_bien_the(conn, "TU-AO-MDF-4C"), id_bien_the(conn, "ANGIAN-GODO-1970")
    ta, tb = ton(conn, "TU-AO-MDF-4C")["ton_hien_co"], ton(conn, "ANGIAN-GODO-1970")["ton_hien_co"]
    kq = inventory.kiem_ke(conn, chu, [{"bien_the_id": a, "so_thuc_te": ta - 1},
                                       {"bien_the_id": b, "so_thuc_te": tb}], "Kiểm kê cuối tháng 10")
    assert kq == [{"bien_the_id": a, "truoc": ta, "sau": ta - 1, "lech": -1}]
    assert ton(conn, "TU-AO-MDF-4C")["ton_hien_co"] == ta - 1


def test_kiem_ke_khong_xuong_duoi_so_dang_giu(conn, chu):
    orders.tao_don(conn, chu, {"dong": [{"ma": "GUONG-HOP-SOI-1600", "so_luong": 2}]})
    with pytest.raises(LoiNghiepVu) as e:
        inventory.kiem_ke(conn, chu, [{"bien_the_id": id_bien_the(conn, "GUONG-HOP-SOI-1600"), "so_thuc_te": 1}],
                          "Đếm thiếu")
    assert e.value.ma == "DIEU_CHINH_AM"


def test_them_xuong_moi_roi_nhap_kho(conn, tho):
    x = inventory.tao_xuong(conn, tho, {"ten": "Xưởng Mộc Đồng Kỵ", "lien_he": "Anh Toàn", "so_dien_thoai": "0915000444",
                                        "dia_chi": "Đồng Kỵ, Từ Sơn, Bắc Ninh", "loai_hang": "Bàn ghế"})
    assert x["ma"] == "XUONG_MOC_DONG_KY" and x["han_thanh_toan_ngay"] == 30
    with pytest.raises(LoiNghiepVu) as e:
        inventory.tao_xuong(conn, tho, {"ten": "xuong moc dong ky"})
    assert e.value.ma == "XUONG_DA_CO"
    pn = inventory.tao_phieu_nhap(conn, tho, x["id"], [
        {"bien_the_id": id_bien_the(conn, "GHE-AN-SOI"), "so_luong": 2, "gia_von_don_vi": 1_300_000}])
    assert pn["nha_cung_cap_id"] == x["id"]
