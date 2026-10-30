"""Luồng nghiệp vụ cốt lõi trên CSDL thật (mỗi test rollback)."""
import uuid
from datetime import datetime

import pytest

from app.adapters.payment import GiaoDichVao
from app.errors import LoiNghiepVu
from app.services import catalog, inventory, invoices, orders, payments

from .conftest import id_bien_the, ton


def _gd(ma_don, so_tien, ma_gd=None):
    return GiaoDichVao(nguon="PAYOS", ma_giao_dich=ma_gd or uuid.uuid4().hex[:10], so_tien=so_tien,
                       noi_dung=f"{ma_don} thanh toan", ngan_hang=None, thoi_diem=datetime.now(), du_lieu_goc={})


# --- Dữ liệu mẫu -------------------------------------------------------------
def test_seed_dung_kich_ban_bao_cao(conn):
    don = {r["ma"]: r for r in conn.execute("SELECT * FROM don_hang").fetchall()}
    assert don["KV261026001"]["trang_thai"] == "DA_THANH_TOAN"
    assert don["KV261026002"]["trang_thai"] == "CON_NO" and don["KV261026002"]["tong_tien"] == 5_328_000
    assert don["KV261027005"]["da_thu"] == 17_000_000 and don["KV261027005"]["trang_thai"] == "CHO_THANH_TOAN"
    assert don["KV261027006"]["trang_thai"] == "CHO_DUYET_GIA"
    assert conn.execute("SELECT count(*) AS n FROM nha_cung_cap").fetchone()["n"] == 3


# --- Tồn kho, bộ sản phẩm, giữ chỗ --------------------------------------------
def test_ban_bo_tru_ton_tung_thanh_phan(conn, chu):
    ban0, ghe0 = ton(conn, "BAN-AN-SOI-1600x800"), ton(conn, "GHE-AN-SOI")
    don = orders.tao_don(conn, chu, {"dong": [{"ma": "BO-BANAN-SOI-1600"}]})
    assert ton(conn, "BAN-AN-SOI-1600x800")["dang_giu_cho"] == ban0["dang_giu_cho"] + 1
    assert ton(conn, "GHE-AN-SOI")["dang_giu_cho"] == ghe0["dang_giu_cho"] + 6
    payments.ghi_nhan_thanh_toan(conn, chu, don["id"], 17_200_000, "TIEN_MAT")
    ban1, ghe1 = ton(conn, "BAN-AN-SOI-1600x800"), ton(conn, "GHE-AN-SOI")
    assert (ban1["ton_hien_co"], ban1["dang_giu_cho"]) == (ban0["ton_hien_co"] - 1, ban0["dang_giu_cho"])
    assert (ghe1["ton_hien_co"], ghe1["dang_giu_cho"]) == (ghe0["ton_hien_co"] - 6, ghe0["dang_giu_cho"])


def test_ton_kha_dung_cua_bo_theo_thanh_phan_thieu_nhat(conn, chu):
    ghe = id_bien_the(conn, "GHE-AN-SOI")
    kha_dung_ghe = ton(conn, "GHE-AN-SOI")["ton_kha_dung"]
    inventory.dieu_chinh(conn, chu, ghe, -(kha_dung_ghe - 7), "Ghế hỏng")  # còn 7 ghế -> chỉ đủ 1 bộ
    bo = catalog.tim_theo_ma(conn, "BO-BANAN-SOI-1600")
    assert bo["ton_kha_dung"] == 1


def test_khong_ban_vuot_ton(conn, chu):
    ton_ky = ton(conn, "KE-TIVI-MDF-1800")["ton_kha_dung"]
    with pytest.raises(LoiNghiepVu) as e:
        orders.tao_don(conn, chu, {"dong": [{"ma": "KE-TIVI-MDF-1800", "so_luong": ton_ky + 1}]})
    assert e.value.ma == "KHONG_DU_TON"


def test_giu_cho_het_han_duoc_nha(conn, chu):
    truoc = ton(conn, "TU-AO-MDF-4C")
    don = orders.tao_don(conn, chu, {"dong": [{"ma": "TU-AO-MDF-4C", "so_luong": 2}]})
    assert ton(conn, "TU-AO-MDF-4C")["ton_kha_dung"] == truoc["ton_kha_dung"] - 2
    conn.execute("UPDATE don_hang SET giu_cho_den = now() - interval '1 minute' WHERE id = %s", (don["id"],))
    assert don["ma"] in orders.nha_giu_cho_het_han(conn)
    assert ton(conn, "TU-AO-MDF-4C")["ton_kha_dung"] == truoc["ton_kha_dung"]
    dong = conn.execute("SELECT loai, so_luong FROM so_cai_ton WHERE don_hang_id = %s ORDER BY id", (don["id"],)).fetchall()
    assert [(d["loai"], d["so_luong"]) for d in dong] == [("GIU_CHO", 2), ("NHA_CHO", -2)]
    assert orders.lay_don(conn, don["id"], chu)["trang_thai"] == "HET_HAN"


def test_don_da_thu_mot_phan_khong_bi_nha_giu_cho(conn):
    conn.execute("UPDATE don_hang SET giu_cho_den = now() - interval '1 hour' WHERE ma = 'KV261027005'")
    assert "KV261027005" not in orders.nha_giu_cho_het_han(conn)


def test_khach_tra_tien_sau_khi_het_han_van_giu_lai_hang(conn, chu):
    don = orders.tao_don(conn, chu, {"dong": [{"ma": "TU-AO-MDF-4C"}]})
    conn.execute("UPDATE don_hang SET giu_cho_den = now() - interval '1 minute' WHERE id = %s", (don["id"],))
    orders.nha_giu_cho_het_han(conn)
    kq = payments.nhan_giao_dich(conn, _gd(don["ma"], 5_200_000))
    assert kq["ket_qua"] == "DA_KHOP"
    sau = orders.lay_don(conn, don["id"], chu)
    assert sau["trang_thai"] == "DA_THANH_TOAN" and sau["trang_thai_giao"] == "DA_GIAO"


def test_nhap_kho_cap_nhat_gia_von_binh_quan_va_cong_no_xuong(conn, tho):
    bt = id_bien_the(conn, "KE-TIVI-MDF-1800")
    ton_truoc = ton(conn, "KE-TIVI-MDF-1800")["ton_hien_co"]
    von_cu = conn.execute("SELECT gia_von FROM v_gia_hien_hanh WHERE bien_the_id = %s", (bt,)).fetchone()["gia_von"]
    ncc = conn.execute("SELECT id, so_du_cong_no FROM nha_cung_cap WHERE ma = 'MDF'").fetchone()
    inventory.tao_phieu_nhap(conn, tho, ncc["id"], [{"bien_the_id": bt, "so_luong": 2, "gia_von_don_vi": 2_100_000}])
    von_moi = conn.execute("SELECT gia_von FROM v_gia_hien_hanh WHERE bien_the_id = %s", (bt,)).fetchone()["gia_von"]
    assert von_moi == round((ton_truoc * von_cu + 2 * 2_100_000) / (ton_truoc + 2))
    assert conn.execute("SELECT so_du_cong_no FROM nha_cung_cap WHERE id = %s", (ncc["id"],)).fetchone()[
        "so_du_cong_no"] == ncc["so_du_cong_no"] + 4_200_000
    lich_su = catalog.lich_su_gia(conn, bt)
    assert [g["den_ngay"] is None for g in lich_su if g["loai_gia"] == "GIA_VON"].count(True) == 1


# --- Giá sàn mềm -----------------------------------------------------------------
def test_tho_ban_duoi_gia_san_chuyen_cho_chu_duyet(conn, tho, chu):
    don = orders.tao_don(conn, tho, {"dong": [{"ma": "GUONG-HOP-SOI-1600", "don_gia_ban": 7_000_000}]})
    assert don["trang_thai"] == "CHO_DUYET_GIA"
    assert "gia_san_chup" not in don["dong"][0] and "gia_von_chup" not in don["dong"][0]
    assert ton(conn, "GUONG-HOP-SOI-1600")["dang_giu_cho"] >= 1  # hàng vẫn được giữ cho khách
    yc = conn.execute("SELECT noi_dung FROM yeu_cau_duyet WHERE don_hang_id = %s", (don["id"],)).fetchone()
    assert yc["noi_dung"]["dong"][0]["chenh_lech"] == 7_000_000 - 7_400_000
    assert conn.execute("SELECT 1 FROM thong_bao WHERE noi_dung LIKE %s", (f"%{don['ma']}%",)).fetchone()


def test_chu_duyet_thi_don_tiep_tuc_chu_tu_choi_thi_nha_hang(conn, tho, chu):
    d1 = orders.tao_don(conn, tho, {"dong": [{"ma": "GUONG-HOP-SOI-1600", "don_gia_ban": 7_000_000}]})
    yc1 = conn.execute("SELECT id FROM yeu_cau_duyet WHERE don_hang_id = %s", (d1["id"],)).fetchone()["id"]
    sau = orders.duyet_yeu_cau(conn, chu, yc1, True)
    assert sau["trang_thai"] == "CHO_THANH_TOAN" and sau["giu_cho_den"] is not None

    giu_truoc = ton(conn, "GUONG-HOP-SOI-1600")["dang_giu_cho"]
    d2 = orders.tao_don(conn, tho, {"dong": [{"ma": "GUONG-HOP-SOI-1600", "don_gia_ban": 6_000_000}]})
    yc2 = conn.execute("SELECT id FROM yeu_cau_duyet WHERE don_hang_id = %s", (d2["id"],)).fetchone()["id"]
    assert orders.duyet_yeu_cau(conn, chu, yc2, False, "Thấp quá")["trang_thai"] == "DA_HUY"
    assert ton(conn, "GUONG-HOP-SOI-1600")["dang_giu_cho"] == giu_truoc
    with pytest.raises(LoiNghiepVu):
        orders.duyet_yeu_cau(conn, chu, yc2, True)


def test_chu_ban_duoi_gia_san_khong_can_duyet(conn, chu):
    assert orders.tao_don(conn, chu, {"dong": [{"ma": "GUONG-HOP-SOI-1600", "don_gia_ban": 7_000_000}]}
                          )["trang_thai"] == "CHO_THANH_TOAN"


def test_duyet_xong_ma_da_thu_du_thi_chot_luon(conn, tho, chu):
    don = orders.tao_don(conn, tho, {"dong": [{"ma": "GUONG-HOP-SOI-1600", "don_gia_ban": 7_000_000}]})
    payments.ghi_nhan_thanh_toan(conn, tho, don["id"], 7_000_000, "TIEN_MAT")
    assert orders.lay_don(conn, don["id"], chu)["trang_thai"] == "CHO_DUYET_GIA"
    yc = conn.execute("SELECT id FROM yeu_cau_duyet WHERE don_hang_id = %s", (don["id"],)).fetchone()["id"]
    assert orders.duyet_yeu_cau(conn, chu, yc, True)["trang_thai"] == "DA_THANH_TOAN"


# --- Hàng đặt riêng ----------------------------------------------------------
def test_tinh_gia_dat_rieng_tu_csdl(conn):
    bt = id_bien_the(conn, "TUTHO-MIT-1270")
    kq = catalog.tinh_gia_dat_rieng(conn, bt, "2m4")
    assert kq["gia"] == 5_328_000 and kq["kich_thuoc_mm"] == [2400]
    assert catalog.tinh_gia_dat_rieng(conn, id_bien_the(conn, "GUONG-HOP-SOI-DATRIENG"), "1m8")["gia"] == 8_500_000
    assert catalog.tinh_gia_dat_rieng(conn, id_bien_the(conn, "MATBAN-GODO-DATRIENG"), "1m6 x 80cm")["gia"] == 6_444_000
    with pytest.raises(LoiNghiepVu) as e:
        catalog.tinh_gia_dat_rieng(conn, bt, "3m5")
    assert e.value.ma == "KICH_THUOC_NGOAI_DUNG_SAI"


def test_dong_don_dat_rieng_luu_ban_chup_va_khong_tru_kho(conn, chu):
    ledger_truoc = conn.execute("SELECT count(*) AS n FROM so_cai_ton").fetchone()["n"]
    don = orders.tao_don(conn, chu, {"dong": [{"ma": "TUTHO-MIT-1270", "kich_thuoc": "1,8m"}]})
    d = don["dong"][0]
    assert d["dat_rieng"] and d["kieu_cong_thuc"] == "THEO_CHIEU_DAI"
    assert d["don_gia_ban"] == 3_996_000 and d["tham_so"]["dai_mm"] == 1800
    assert conn.execute("SELECT count(*) AS n FROM so_cai_ton").fetchone()["n"] == ledger_truoc
    payments.ghi_nhan_thanh_toan(conn, chu, don["id"], 3_996_000, "TIEN_MAT")
    assert orders.lay_don(conn, don["id"], chu)["trang_thai_giao"] == "CHO_XUONG_GIAO"


# --- Thanh toán, webhook, HĐĐT -------------------------------------------------
def test_chot_don_dua_hoa_don_vao_hang_doi_cung_giao_dich(conn, chu):
    don = orders.tao_don(conn, chu, {"dong": [{"ma": "KE-TIVI-MDF-1800"}], "can_hoa_don": True,
                                     "khach_hang": {"ten": "Cty ABC", "ma_so_thue": "4600999999"}})
    assert orders.lay_don(conn, don["id"], chu)["hoa_don"] is None
    kq = payments.ghi_nhan_thanh_toan(conn, chu, don["id"], 3_000_000, "TIEN_MAT")
    assert kq["tien_thoi"] == 400_000
    hd = kq["don"]["hoa_don"]
    assert hd["trang_thai"] == "CHO_XUAT" and hd["ma_so_thue"] == "4600999999"
    assert conn.execute("SELECT 1 FROM phieu_ban_hang WHERE don_hang_id = %s", (don["id"],)).fetchone()


def test_webhook_gui_lai_khong_ghi_nhan_hai_lan(conn, chu):
    don = orders.tao_don(conn, chu, {"dong": [{"ma": "KE-TIVI-MDF-1800"}]})
    gd = _gd(don["ma"], 2_600_000, "FT-TRUNG-01")
    assert payments.nhan_giao_dich(conn, gd)["ket_qua"] == "DA_KHOP"
    assert payments.nhan_giao_dich(conn, gd)["ket_qua"] == "TRUNG_LAP"
    assert conn.execute("SELECT count(*) AS n FROM thanh_toan WHERE don_hang_id = %s", (don["id"],)).fetchone()["n"] == 1


def test_lech_tien_va_chap_nhan_giam(conn, chu):
    don = orders.id_theo_ma(conn, "KV261027005")
    assert orders.lay_don(conn, don, chu)["con_phai_thu"] == 200_000
    sau = payments.chap_nhan_giam(conn, chu, don, "Khách quen")
    assert sau["trang_thai"] == "DA_THANH_TOAN" and sau["giam_tru"] == 200_000


def test_tien_ve_sau_xac_nhan_tay_duoc_doi_soat(conn):
    don = orders.id_theo_ma(conn, "KV261026001")
    kq = payments.nhan_giao_dich(conn, _gd("KV261026001", 17_200_000))
    assert kq["ket_qua"] == "DOI_SOAT" and kq["lech"] == 0
    assert conn.execute("SELECT da_thu FROM don_hang WHERE id = %s", (don,)).fetchone()["da_thu"] == 17_200_000
    assert not conn.execute("SELECT 1 FROM thanh_toan WHERE xac_nhan_tay AND NOT da_doi_soat").fetchone()


def test_xac_nhan_tay_bat_buoc_bang_chung(conn, chu):
    don = orders.tao_don(conn, chu, {"dong": [{"ma": "KE-TIVI-MDF-1800"}]})
    with pytest.raises(LoiNghiepVu) as e:
        payments.xac_nhan_tay(conn, chu, don["id"])
    assert e.value.ma == "THIEU_BANG_CHUNG"


def test_coc_va_thu_no_cap_nhat_du_no_khach(conn, chu):
    kh = conn.execute("SELECT khach_hang_id FROM don_hang WHERE ma = 'KV261026002'").fetchone()["khach_hang_id"]
    assert conn.execute("SELECT du_no FROM khach_hang WHERE id = %s", (kh,)).fetchone()["du_no"] == 3_328_000
    payments.ghi_nhan_thanh_toan(conn, chu, orders.id_theo_ma(conn, "KV261026002"), 3_328_000, "TIEN_MAT")
    assert conn.execute("SELECT du_no FROM khach_hang WHERE id = %s", (kh,)).fetchone()["du_no"] == 0


def test_idempotency_key_khong_tao_don_trung(conn, chu):
    key = str(uuid.uuid4())
    d1 = orders.tao_don(conn, chu, {"dong": [{"ma": "KE-TIVI-MDF-1800"}], "idempotency_key": key})
    d2 = orders.tao_don(conn, chu, {"dong": [{"ma": "KE-TIVI-MDF-1800"}], "idempotency_key": key})
    assert d1["id"] == d2["id"] and d2["trung_lap"]


def test_don_ngoai_tuyen_thieu_hang_danh_dau_xung_dot_khong_tu_huy(conn, tho, chu):
    ton_ky = ton(conn, "ANGIAN-GODO-1970")["ton_kha_dung"]
    don = orders.tao_don(conn, tho, {"dong": [{"ma": "ANGIAN-GODO-1970", "so_luong": ton_ky + 1}],
                                     "idempotency_key": str(uuid.uuid4())}, kenh="NGOAI_TUYEN")
    assert don["trang_thai_giao"] == "XUNG_DOT_TON" and don["trang_thai"] == "CHO_THANH_TOAN"
    assert orders.giai_quyet_xung_dot(conn, chu, don["id"], "CHO_XUONG_GIAO")["trang_thai_giao"] == "CHO_XUONG_GIAO"


def test_retry_queue_hoa_don(conn, chu):
    from app.adapters import einvoice

    class CongLoi(einvoice.EInvoiceAdapter):
        def phat_hanh(self, yc):
            raise einvoice.LoiTamThoi("timeout")

    conn.execute("UPDATE hoa_don_dt SET lan_thu_tiep = now() - interval '1 second' WHERE trang_thai = 'CHO_XUAT'")
    hd = invoices.xu_ly_mot(conn, CongLoi())
    assert hd["trang_thai"] == "CHO_XUAT" and hd["so_lan_thu"] == 1 and hd["loi_cuoi"] == "timeout"
    assert conn.execute("SELECT lan_thu_tiep > now() + interval '50 seconds' AS ok FROM hoa_don_dt WHERE id = %s",
                        (hd["id"],)).fetchone()["ok"]
    conn.execute("UPDATE hoa_don_dt SET lan_thu_tiep = now() - interval '1 second' WHERE id = %s", (hd["id"],))
    xong = invoices.xu_ly_mot(conn, einvoice.MockAdapter(ti_le_loi=0))
    assert xong["trang_thai"] == "DA_XUAT" and xong["so_hoa_don"] and xong["link_xml"]


def test_khoang_cho_thu_lai_tang_dan():
    assert [invoices.khoang_cho_thu_lai(n).total_seconds() for n in (1, 2, 3, 7, 20)] == [60, 120, 240, 3600, 3600]


# --- Tìm kiếm tiếng Việt -------------------------------------------------------
@pytest.mark.parametrize("q, ma", [
    ("giuong 1m8 soi", "GUONG-HOP-SOI-1800"), ("Giường hộp sồi 1,8m", "GUONG-HOP-SOI-1800"),
    ("tủ áo", "TU-AO-MDF-4C"), ("tu ao mdf", "TU-AO-MDF-4C"), ("bàn thờ mít", "TUTHO-MIT-1270"),
    ("bo ban an 6 ghe soi", "BO-BANAN-SOI-1600"), ("an gian go do", "ANGIAN-GODO-1970"),
    ("ke ti vi", "KE-TIVI-MDF-1800"), ("giuong hop soii", "GUONG-HOP-SOI-1800"),
])
def test_tim_kiem_khong_dau_dong_nghia(conn, chu, q, ma):
    assert ma in [r["ma"] for r in catalog.tim_kiem(conn, q, chu)]


def test_tim_kiem_tho_khong_thay_gia_von(conn, tho):
    kq = catalog.tim_kiem(conn, "giuong", tho)
    assert kq and all("gia_von" not in r and "gia_san" not in r for r in kq)


def test_tim_kiem_20000_bien_the_duoi_1_giay(conn, chu):
    import time
    mau = conn.execute("SELECT id FROM mau_hang LIMIT 1").fetchone()["id"]
    conn.execute(
        """INSERT INTO bien_the (mau_hang_id, ma_noi_bo, ten_hien_thi, loai_go, dai_mm, rong_mm)
           SELECT %s, 'TEST-' || g, 'Mẫu thử ' || (ARRAY['Giường','Tủ','Kệ','Bàn','Ghế'])[g %% 5 + 1] || ' số ' || g,
                  (ARRAY['Sồi','Mít','MDF'])[g %% 3 + 1], 1000 + (g %% 20) * 100, 500 + (g %% 10) * 100
           FROM generate_series(1, 20000) g""", (mau,))
    conn.execute("ANALYZE bien_the")
    bat_dau = time.perf_counter()
    kq = catalog.tim_kiem(conn, "giuong 1m8 soi", chu)
    assert time.perf_counter() - bat_dau < 1.0
    assert kq and kq[0]["ma"]
