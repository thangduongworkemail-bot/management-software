from datetime import datetime, timezone
from fractions import Fraction

import pytest

from app.adapters.payment import ky_payos, xac_thuc_webhook_payos
from app.adapters.storage import S3Storage
from app.domain import pricing
from app.domain.vietqr import crc16_ccitt, tao_chuoi_vietqr


def test_tu_tho_theo_chieu_dai_dung_vi_du_bao_cao():
    # 1.850.000 đ/m × 1,2 (gỗ Mít) × 2,4 m = 5.328.000 đ
    assert pricing.tinh_theo_chieu_dai(1_850_000, 2400, 1200) == 5_328_000


def test_chieu_dai_co_phu_phi_va_lam_tron_nghin():
    # 1.850.000 × 1,2 × 1,75 = 3.885.000 ; + 250.000 phụ phí
    assert pricing.tinh_theo_chieu_dai(1_850_000, 1750, 1200, 250_000) == 4_135_000
    # 1.333.333 × 1 × 1 = 1.333.333 -> 1.333.000 ; 1.333.500 -> 1.334.000 (nửa lên)
    assert pricing.tinh_theo_chieu_dai(1_333_333, 1000) == 1_333_000
    assert pricing.tinh_theo_chieu_dai(1_333_500, 1000) == 1_334_000


def test_theo_dien_tich():
    # 3.200.000 đ/m² × (1,6 × 0,8) × 1,5 + 300.000 = 6.444.000
    assert pricing.tinh_theo_dien_tich(3_200_000, 1600, 800, 1500, 300_000) == 6_444_000
    assert pricing.tinh_theo_dien_tich(1_000_000, 1000, 1000) == 1_000_000


@pytest.mark.parametrize("kt, gia", [(1200, 7_800_000), (1600, 7_800_000), (1601, 8_500_000), (1800, 8_500_000),
                                     (2200, 10_200_000)])
def test_theo_bac(kt, gia):
    bac = [{"toi_da_mm": 1800, "gia": 8_500_000}, {"toi_da_mm": 1600, "gia": 7_800_000},
           {"toi_da_mm": 2200, "gia": 10_200_000}]
    assert pricing.tinh_theo_bac(bac, kt) == gia


def test_theo_bac_vuot_bac_lon_nhat():
    with pytest.raises(pricing.LoiCongThuc):
        pricing.tinh_theo_bac([{"toi_da_mm": 2200, "gia": 1}], 2400)


def test_tinh_gia_dien_giai_doc_cho_khach():
    ct = pricing.CongThucGia(kieu=pricing.THEO_CHIEU_DAI, don_gia=1_850_000)
    kq = pricing.tinh_gia(ct, [2400], "Mít", 1200)
    assert kq.gia == 5_328_000
    assert kq.dien_giai == "1.850.000 đ/m × 1,2 (gỗ Mít) × 2,4 m = 5.328.000 đ"
    assert kq.tham_so["dai_mm"] == 2400


def test_dien_tich_can_hai_chieu():
    ct = pricing.CongThucGia(kieu=pricing.THEO_DIEN_TICH, don_gia=3_200_000)
    with pytest.raises(pricing.LoiCongThuc):
        pricing.tinh_gia(ct, [1600])


def test_tu_choi_dau_vao_am_hoac_so_thuc():
    with pytest.raises(pricing.LoiCongThuc):
        pricing.tinh_theo_chieu_dai(-1, 2400)
    with pytest.raises(pricing.LoiCongThuc):
        pricing.tinh_theo_chieu_dai(1_850_000, 2400.5)


def test_lam_tron_nghin():
    assert pricing.lam_tron_nghin(Fraction(1499, 1)) == 1000
    assert pricing.lam_tron_nghin(1500) == 2000
    assert pricing.lam_tron_nghin(0) == 0
    assert pricing.gia_theo_ty_le(5_328_000, 779) == 4_151_000


# --- VietQR, PayOS, S3 ------------------------------------------------------
def test_crc16_ccitt_gia_tri_chuan():
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_chuoi_vietqr():
    qr = tao_chuoi_vietqr("970436", "0011004455667", 17_200_000, "KV261026001")
    assert qr.startswith("000201010212")
    assert "0010A000000727" in qr and "0208QRIBFTTA" in qr
    assert "540817200000" in qr and "5303704" in qr and "5802VN" in qr
    assert "0811KV261026001" in qr
    assert qr[-8:-4] == "6304" and int(qr[-4:], 16) == crc16_ccitt(qr[:-4].encode())


def test_webhook_payos_chu_ky():
    data = {"orderCode": 123, "amount": 17_200_000, "description": "KV261026001", "reference": "FT123",
            "transactionDateTime": "2026-10-26 10:50:00", "counterAccountBankName": None}
    body = {"code": "00", "data": data, "signature": ky_payos(data, "khoa-test")}
    gd = xac_thuc_webhook_payos(body, "khoa-test")
    assert gd.so_tien == 17_200_000 and gd.ma_giao_dich == "FT123"
    body["data"] = {**data, "amount": 1}
    with pytest.raises(ValueError):
        xac_thuc_webhook_payos(body, "khoa-test")


def test_s3_presign_khop_vi_du_cua_aws():
    # Ví dụ chính thức trong tài liệu AWS "Authenticating Requests: Using Query Parameters"
    s3 = S3Storage(endpoint="https://s3.amazonaws.com", region="us-east-1", bucket="examplebucket",
                   access_key="AKIAIOSFODNN7EXAMPLE", secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
    url = s3.presign("GET", "test.txt", 86400, now=datetime(2013, 5, 24, tzinfo=timezone.utc), virtual_host=True)
    assert url.endswith("X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404")
