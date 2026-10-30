"""Kiểm thử qua HTTP: xác thực, phân quyền theo vai trò, idempotency, webhook có chữ ký."""
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.adapters.payment import ky_payos
from app.config import settings
from app.main import app
from app.security import ky_hmac


@pytest.fixture(scope="module")
def client(csdl):
    with TestClient(app) as c:
        yield c


def _dang_nhap(client, ten, mk):
    r = client.post("/api/auth/dang-nhap", json={"ten_dang_nhap": ten, "mat_khau": mk})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def chu(client):
    return _dang_nhap(client, "covan", "KhanhVan@2026")


@pytest.fixture(scope="module")
def tho(client):
    return _dang_nhap(client, "anhnam", "AnhNam@2026")


def test_sai_mat_khau(client):
    r = client.post("/api/auth/dang-nhap", json={"ten_dang_nhap": "covan", "mat_khau": "sai"})
    assert r.status_code == 401 and r.json()["loi"] == "SAI_DANG_NHAP"


def test_chua_dang_nhap_bi_chan(client):
    assert client.get("/api/hang-hoa").status_code == 401
    assert client.get("/api/hang-hoa", headers={"Authorization": "Bearer abc"}).status_code == 401


def test_tim_kiem_nhanh_va_an_gia_von_voi_tho(client, chu, tho):
    r = client.get("/api/hang-hoa/tim-kiem", params={"q": "giuong 1m8 soi"}, headers=tho)
    body = r.json()
    assert body["ket_qua"][0]["ma"] == "GUONG-HOP-SOI-1800"
    assert "gia_von" not in body["ket_qua"][0] and "gia_san" not in body["ket_qua"][0]
    assert body["thoi_gian_ms"] < 1000
    r = client.get("/api/hang-hoa/tim-kiem", params={"q": "giuong 1m8 soi"}, headers=chu)
    assert r.json()["ket_qua"][0]["gia_von"] > 0


def test_tho_khong_duoc_xac_nhan_tay_hay_xem_cong_no(client, tho):
    assert client.post("/api/don-hang/1/xac-nhan-tay", json={"bon_so_cuoi": "1234"}, headers=tho).status_code == 403
    assert client.get("/api/cong-no", headers=tho).status_code == 403
    assert client.get("/api/nhat-ky", headers=tho).status_code == 403
    assert client.post("/api/hang-hoa/bien-the/1/gia", json={"loai_gia": "GIA_SAN", "so_tien": 1},
                       headers=tho).status_code == 403


def test_tho_tinh_gia_dat_rieng_khong_thay_gia_san(client, tho):
    bt = next(r for r in client.get("/api/hang-hoa", headers=tho).json() if r["ma"] == "TUTHO-MIT-1270")
    r = client.post(f"/api/hang-hoa/bien-the/{bt['id']}/tinh-gia", json={"kich_thuoc": "2m4"}, headers=tho).json()
    assert r["gia"] == 5_328_000 and "gia_san" not in r and "gia_von" not in r


def test_tao_don_idempotent_qua_header(client, tho):
    key = str(uuid.uuid4())
    body = {"dong": [{"ma": "KE-TIVI-MDF-1800"}]}
    r1 = client.post("/api/don-hang", json=body, headers={**tho, "Idempotency-Key": key})
    r2 = client.post("/api/don-hang", json=body, headers={**tho, "Idempotency-Key": key})
    assert r1.status_code == 200 and r1.json()["id"] == r2.json()["id"] and r2.json()["trung_lap"]
    assert r1.json()["vietqr"].startswith("000201010212")


def test_webhook_payos(client, tho):
    don = client.post("/api/don-hang", json={"dong": [{"ma": "KE-TIVI-MDF-1800"}]}, headers=tho).json()
    data = {"orderCode": don["id"], "amount": don["con_phai_thu"], "description": f"{don['ma']} CK",
            "reference": f"FT{uuid.uuid4().hex[:8]}", "transactionDateTime": "2026-10-29 10:00:00"}
    sai = client.post("/api/webhook/payos", json={"data": data, "signature": "0" * 64})
    assert sai.status_code == 400
    dung = {"data": data, "signature": ky_payos(data, settings.payos_checksum_key)}
    assert client.post("/api/webhook/payos", json=dung).json()["ket_qua"] == "DA_KHOP"
    assert client.post("/api/webhook/payos", json=dung).json()["ket_qua"] == "TRUNG_LAP"
    assert client.get(f"/api/don-hang/{don['id']}", headers=tho).json()["trang_thai"] == "DA_THANH_TOAN"


def test_may_nhan_tien_ghep_noi_va_ky_hmac(client, chu, tho):
    ma = client.post("/api/thiet-bi/ma-ghep", json={"ten": "Điện thoại test", "loai": "MAY_NHAN_TIEN"},
                     headers=chu).json()["ma_ghep"]
    tb = client.post("/api/thiet-bi/ghep-noi", json={"ma_ghep": ma}).json()
    assert client.post("/api/thiet-bi/ghep-noi", json={"ma_ghep": ma}).status_code == 400  # mã dùng một lần

    don = client.post("/api/don-hang", json={"dong": [{"ma": "KE-TIVI-MDF-1800"}]}, headers=tho).json()
    raw = json.dumps({"ma_giao_dich": f"FT{uuid.uuid4().hex[:8]}", "so_tien": don["con_phai_thu"],
                      "noi_dung": f"{don['ma']} chuyen khoan"}).encode()
    ts = str(int(time.time()))
    headers = {"X-Thiet-Bi": str(tb["thiet_bi_id"]), "X-Thoi-Gian": ts, "Content-Type": "application/json"}
    sai = client.post("/api/thiet-bi/giao-dich", content=raw, headers={**headers, "X-Chu-Ky": "00"})
    assert sai.status_code == 401
    r = client.post("/api/thiet-bi/giao-dich", content=raw,
                    headers={**headers, "X-Chu-Ky": ky_hmac(tb["khoa_ky"], f"{ts}.".encode() + raw)})
    assert r.json()["ket_qua"] == "DA_KHOP"

    client.post(f"/api/thiet-bi/{tb['thiet_bi_id']}/thu-hoi", headers=chu)
    ts = str(int(time.time()))
    r = client.post("/api/thiet-bi/bao-song", content=b"{}",
                    headers={"X-Thiet-Bi": str(tb["thiet_bi_id"]), "X-Thoi-Gian": ts,
                             "X-Chu-Ky": ky_hmac(tb["khoa_ky"], f"{ts}.".encode() + b"{}")})
    assert r.status_code == 401  # đã thu hồi


def test_bao_gia_cong_khai_khong_lo_gia_noi_bo(client, tho):
    bg = client.post("/api/bao-gia", json={"dong": [{"ma": "TUTHO-MIT-1270", "kich_thuoc": "2m4"}]}, headers=tho).json()
    pub = client.get(f"/api/public/bao-gia/{bg['ma_chia_se']}")
    assert pub.status_code == 200
    text = pub.text
    assert "5328000" in text and "gia_von" not in text and "gia_san" not in text
    assert client.get("/api/public/bao-gia/khong-ton-tai").status_code == 404


def test_tong_quan_theo_vai_tro(client, chu, tho):
    assert "loi_nhuan_gop_thang" in client.get("/api/tong-quan", headers=chu).json()
    assert "loi_nhuan_gop_thang" not in client.get("/api/tong-quan", headers=tho).json()


def test_dong_bo_ngoai_tuyen(client, tho):
    key = str(uuid.uuid4())
    don = {"idempotency_key": key, "dong": [{"ma": "KE-TIVI-MDF-1800"}],
           "thanh_toan": {"phuong_thuc": "TIEN_MAT", "so_tien": 2_600_000}}
    r = client.post("/api/sync/don-hang", json={"don": [don, don, {"dong": []}]}, headers=tho).json()["ket_qua"]
    assert r[0]["ok"] and r[0]["trang_thai"] == "DA_THANH_TOAN"
    assert r[1]["trung_lap"] and r[1]["don_id"] == r[0]["don_id"]
    assert not r[2]["ok"]


def test_rang_buoc_csdl_tra_loi_than_thien(client, chu):
    r = client.post("/api/hang-hoa/bien-the", headers=chu, json={
        "mau_hang_id": 1, "ma_noi_bo": "GUONG-HOP-SOI-1800", "ten_hien_thi": "Trùng mã"})
    assert r.status_code == 409 and r.json()["loi"] == "CSDL_23505"


def test_nhat_ky_toan_ven(client, chu):
    r = client.get("/api/nhat-ky/kiem-tra", headers=chu).json()
    assert r["toan_ven"] and r["so_dong"] > 10


def test_sua_xoa_kiem_ke_chi_danh_cho_chu(client, tho):
    assert client.patch("/api/hang-hoa/bien-the/1", json={"mau_sac": "Đỏ"}, headers=tho).status_code == 403
    assert client.post("/api/hang-hoa/bien-the/1/xoa", json={"ly_do": "Thử xóa"}, headers=tho).status_code == 403
    assert client.post("/api/kho/kiem-ke", json={"ly_do": "Thử", "dong": [{"bien_the_id": 1, "so_thuc_te": 0}]},
                       headers=tho).status_code == 403


def test_them_xuong_kiem_tra_du_lieu(client, tho):
    r = client.post("/api/kho/xuong", json={"ten": "Xưởng thử", "so_dien_thoai": "abc"}, headers=tho)
    assert r.status_code == 422


def test_sua_bien_the_qua_api_khong_doi_gi(client, chu):
    bt = next(r for r in client.get("/api/hang-hoa", headers=chu).json() if r["ma"] == "TUTHO-MIT-1760")
    r = client.patch(f"/api/hang-hoa/bien-the/{bt['id']}", json={"mau_sac": bt["mau_sac"], "hoan_thien": bt["hoan_thien"]},
                     headers=chu)
    assert r.status_code == 400 and r.json()["loi"] == "KHONG_CO_THAY_DOI"
