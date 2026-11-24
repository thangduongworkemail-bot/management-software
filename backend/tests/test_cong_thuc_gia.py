"""Chủ tự cấu hình công thức giá hàng đặt kích thước riêng trên giao diện (báo cáo mục 1.2, FR-02)."""
import pytest
from fastapi.testclient import TestClient

from app.domain import pricing
from app.domain.pricing import CongThucGia, LoiCongThuc, kiem_tra_cong_thuc
from app.errors import LoiNghiepVu
from app.main import app
from app.services import catalog

from .conftest import id_bien_the


# ---------------------------------------------------------------------------
# Kiểm tra công thức (thuần, không CSDL)
# ---------------------------------------------------------------------------
def test_bac_gia_duoc_sap_xep_va_bo_truong_thua():
    ct = kiem_tra_cong_thuc(CongThucGia(kieu="THEO_BAC", don_gia=999, phu_phi=5,
                                        bac_gia=[{"toi_da_mm": 1800, "gia": 8_500_000},
                                                 {"toi_da_mm": 1600, "gia": 7_800_000}]))
    assert [b["toi_da_mm"] for b in ct.bac_gia] == [1600, 1800]
    assert ct.don_gia is None and ct.phu_phi == 0


def test_chieu_dai_giu_don_gia_va_bo_bac():
    ct = kiem_tra_cong_thuc(CongThucGia(kieu="THEO_CHIEU_DAI", don_gia=1_850_000, bac_gia=[{"toi_da_mm": 1, "gia": 1}]))
    assert ct.don_gia == 1_850_000 and ct.bac_gia == []


@pytest.mark.parametrize("ct, thong_bao", [
    (CongThucGia(kieu="THEO_MET_KHOI", don_gia=1), "Kiểu công thức"),
    (CongThucGia(kieu="THEO_CHIEU_DAI"), "Cần nhập đơn giá trên mét dài"),
    (CongThucGia(kieu="THEO_DIEN_TICH"), "Cần nhập đơn giá trên m²"),
    (CongThucGia(kieu="THEO_DIEN_TICH", don_gia=0), "lớn hơn 0"),
    (CongThucGia(kieu="THEO_BAC"), "ít nhất một bậc"),
    (CongThucGia(kieu="THEO_BAC", bac_gia=[{"toi_da_mm": 1600, "gia": 1}, {"toi_da_mm": 1600, "gia": 2}]), "trùng"),
    (CongThucGia(kieu="THEO_BAC", bac_gia=[{"toi_da_mm": 1600, "gia": 9}, {"toi_da_mm": 1800, "gia": 5}]), "rẻ hơn"),
    (CongThucGia(kieu="THEO_BAC", bac_gia=[{"toi_da_mm": 0, "gia": 9}]), "lớn hơn 0"),
    (CongThucGia(kieu="THEO_CHIEU_DAI", don_gia=1, kich_thuoc_min_mm=3000, kich_thuoc_max_mm=400), "nhỏ nhất"),
    (CongThucGia(kieu="THEO_CHIEU_DAI", don_gia=1, ty_le_gia_von_phan_nghin=900, ty_le_gia_san_phan_nghin=800),
     "Giá sàn phải cao hơn"),
    (CongThucGia(kieu="THEO_CHIEU_DAI", don_gia=1, ty_le_gia_san_phan_nghin=1200), "100%"),
])
def test_cong_thuc_sai_bi_tu_choi(ct, thong_bao):
    with pytest.raises(LoiCongThuc, match=thong_bao):
        kiem_tra_cong_thuc(ct)


# ---------------------------------------------------------------------------
# Lưu trên CSDL
# ---------------------------------------------------------------------------
def test_sua_don_gia_tu_tho_ap_dung_ngay_va_ghi_nhat_ky(conn, chu):
    tu_tho = id_bien_the(conn, "TUTHO-MIT-1270")
    assert catalog.tinh_gia_dat_rieng(conn, tu_tho, "2m4")["gia"] == 5_328_000   # 1.850.000 × 1,2 × 2,4
    don_cu = conn.execute("SELECT d.thanh_tien FROM dong_don d JOIN bien_the bt ON bt.id = d.bien_the_id "
                          "WHERE bt.ma_noi_bo = 'TUTHO-MIT-1270'").fetchall()

    kq = catalog.luu_cong_thuc(conn, chu, tu_tho, {"kieu": "THEO_CHIEU_DAI", "don_gia": 2_000_000, "phu_phi": 0,
                                                   "kich_thuoc_min_mm": 400, "kich_thuoc_max_mm": 3000,
                                                   "ty_le_gia_von_phan_nghin": 650, "ty_le_gia_san_phan_nghin": 800})
    assert kq["cong_thuc"]["don_gia"] == 2_000_000 and kq["he_so_phan_nghin"] == 1200
    assert catalog.tinh_gia_dat_rieng(conn, tu_tho, "2m4")["gia"] == 5_760_000   # 2.000.000 × 1,2 × 2,4

    nk = conn.execute("SELECT * FROM nhat_ky WHERE hanh_dong = 'SUA_CONG_THUC_GIA' ORDER BY id DESC LIMIT 1").fetchone()
    assert nk["du_lieu_truoc"]["don_gia"] == 1_850_000 and nk["du_lieu_sau"]["don_gia"] == 2_000_000
    # Đơn đã lập giữ nguyên bản chụp giá
    assert conn.execute("SELECT d.thanh_tien FROM dong_don d JOIN bien_the bt ON bt.id = d.bien_the_id "
                        "WHERE bt.ma_noi_bo = 'TUTHO-MIT-1270'").fetchall() == don_cu


def test_doi_he_so_go_ap_dung_cho_moi_hang_cung_go(conn, chu):
    tu_tho = id_bien_the(conn, "TUTHO-MIT-1270")
    catalog.dat_he_so_go(conn, chu, "Mít", 1300)
    assert catalog.tinh_gia_dat_rieng(conn, tu_tho, "2m4")["gia"] == 5_772_000   # 1.850.000 × 1,3 × 2,4
    them = catalog.dat_he_so_go(conn, chu, "  Lim  ", 1800)
    assert them["loai_go"] == "Lim" and them["he_so_phan_nghin"] == 1800


def test_chuyen_hang_thuong_sang_dat_rieng_khi_het_ton(conn, chu):
    con_ton = id_bien_the(conn, "GUONG-HOP-SOI-1800")
    bac = {"kieu": "THEO_BAC", "bac_gia": [{"toi_da_mm": 1600, "gia": 7_000_000}, {"toi_da_mm": 1800, "gia": 8_000_000}]}
    with pytest.raises(LoiNghiepVu) as e:
        catalog.luu_cong_thuc(conn, chu, con_ton, bac)
    assert e.value.ma == "CON_TON_KHO"

    moi = catalog.tao_bien_the(conn, chu, {"ma_noi_bo": "GIUONG-TEST-DATRIENG", "ten_hien_thi": "Giường thử đặt riêng",
                                          "mau_hang_id": conn.execute("SELECT mau_hang_id FROM bien_the WHERE id = %s",
                                                                      (con_ton,)).fetchone()["mau_hang_id"],
                                          "loai_go": "Sồi"})
    kq = catalog.luu_cong_thuc(conn, chu, moi["id"], bac)
    assert kq["dat_theo_kich_thuoc"] is True
    assert catalog.tinh_gia_dat_rieng(conn, moi["id"], "1m7")["gia"] == 8_000_000
    assert conn.execute("SELECT 1 FROM nhat_ky WHERE hanh_dong = 'TAO_CONG_THUC_GIA' AND thuc_the_id = %s",
                        (str(moi["id"]),)).fetchone()


def test_luu_cong_thuc_sai_thanh_loi_nghiep_vu(conn, chu):
    with pytest.raises(LoiNghiepVu) as e:
        catalog.luu_cong_thuc(conn, chu, id_bien_the(conn, "TUTHO-MIT-1270"), {"kieu": "THEO_CHIEU_DAI"})
    assert e.value.ma == "CONG_THUC_KHONG_HOP_LE"


# ---------------------------------------------------------------------------
# API & phân quyền
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client(csdl):
    with TestClient(app) as c:
        yield c


def _dang_nhap(client, ten, mk):
    r = client.post("/api/auth/dang-nhap", json={"ten_dang_nhap": ten, "mat_khau": mk})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_api_chi_chu_duoc_cau_hinh_cong_thuc(client):
    chu, tho = _dang_nhap(client, "covan", "KhanhVan@2026"), _dang_nhap(client, "anhnam", "AnhNam@2026")
    mat_ban = client.get("/api/hang-hoa/tim-kiem", params={"q": "MATBAN-GODO-DATRIENG"}, headers=chu).json()["ket_qua"][0]
    duong = f"/api/hang-hoa/bien-the/{mat_ban['id']}/cong-thuc"

    assert client.get(duong, headers=tho).status_code == 403
    assert client.put(duong, headers=tho, json={"kieu": "THEO_DIEN_TICH", "don_gia": 1}).status_code == 403
    assert client.put("/api/hang-hoa/he-so-go", headers=tho, json={"loai_go": "Lim", "he_so_phan_nghin": 1800}).status_code == 403

    hien_tai = client.get(duong, headers=chu).json()
    assert hien_tai["cong_thuc"]["kieu"] == "THEO_DIEN_TICH" and hien_tai["loai_go"] == "Gõ đỏ"

    r = client.put(duong, headers=chu, json={"kieu": "THEO_DIEN_TICH", "ty_le_gia_san_phan_nghin": 800})
    assert r.status_code == 400 and r.json()["loi"] == "CONG_THUC_KHONG_HOP_LE"
    r = client.put(duong, headers=chu, json={"kieu": "THEO_BAC", "bac_gia": [{"toi_da_mm": -5, "gia": 1}]})
    assert r.status_code == 422

    # Lưu lại đúng giá trị cũ (test này commit qua pool thật, không để lại thay đổi)
    r = client.put(duong, headers=chu, json=hien_tai["cong_thuc"])
    assert r.status_code == 200, r.text
    assert r.json()["cong_thuc"] == hien_tai["cong_thuc"]
    assert pricing.THEO_DIEN_TICH == r.json()["cong_thuc"]["kieu"]
