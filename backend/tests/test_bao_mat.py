"""Rà soát bảo mật Tuần 13: khóa ký JWT không còn là giá trị công khai, chống dò mật khẩu,
webhook PayOS từ chối khóa demo khi chạy thật, trang đăng nhập biết khi nào được hiện tài khoản demo."""
import dataclasses
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app import db, security
from app.config import settings
from app.main import app
from app.routers import auth as auth_router
from app.routers import payments as payments_router


@pytest.fixture(scope="module")
def client(csdl):
    with TestClient(app) as c:
        yield c


def _token_gia(khoa: str, sub: str = "1") -> str:
    bay_gio = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "vai_tro": "CHU", "ho_ten": "Giả mạo", "iat": bay_gio,
                       "exp": bay_gio + timedelta(hours=1)}, khoa, algorithm="HS256")


@pytest.mark.filterwarnings("ignore:The HMAC key is")   # khóa công khai cũ ngắn: PyJWT cảnh báo, đúng ý đồ test
@pytest.mark.parametrize("khoa", sorted(security.KHOA_DA_CONG_KHAI))
def test_token_ky_bang_khoa_cong_khai_bi_tu_choi(client, khoa):
    r = client.get("/api/auth/toi", headers={"Authorization": f"Bearer {_token_gia(khoa)}"})
    assert r.status_code == 401 and r.json()["loi"] == "TOKEN_KHONG_HOP_LE"


def test_khoa_tu_sinh_luu_trong_csdl_va_on_dinh(csdl):
    assert not settings.jwt_secret   # môi trường test không đặt JWT_SECRET
    khoa = security.khoa_bi_mat()
    assert len(khoa) >= 48 and khoa not in security.KHOA_DA_CONG_KHAI
    with db.transaction() as conn:
        luu = conn.execute("SELECT gia_tri FROM cau_hinh_he_thong WHERE khoa = 'JWT_SECRET'").fetchone()
    assert luu["gia_tri"] == khoa == security.khoa_bi_mat()


def test_jwt_secret_dat_bang_gia_tri_mau_thi_bi_bo_qua(csdl, monkeypatch):
    monkeypatch.setattr(security, "settings", dataclasses.replace(settings, jwt_secret="doi-khoa-bi-mat-nay"))
    assert security.khoa_bi_mat() != "doi-khoa-bi-mat-nay"
    monkeypatch.setattr(security, "settings", dataclasses.replace(settings, jwt_secret="x" * 40))
    assert security.khoa_bi_mat() == "x" * 40


def test_sai_mat_khau_5_lan_thi_tam_khoa_rieng_cap_tai_khoan_va_may(client, monkeypatch):
    monkeypatch.setattr(auth_router, "_lan_sai", {})
    dang_nhap = lambda ten, mk: client.post("/api/auth/dang-nhap", json={"ten_dang_nhap": ten, "mat_khau": mk})
    for _ in range(auth_router.SAI_TOI_DA):
        assert dang_nhap("covan", "doan-bua").status_code == 401
    r = dang_nhap("covan", "KhanhVan@2026")        # mật khẩu đúng cũng phải chờ
    assert r.status_code == 429 and r.json()["loi"] == "THU_SAI_QUA_NHIEU"
    assert dang_nhap("anhnam", "AnhNam@2026").status_code == 200   # tài khoản khác không bị ảnh hưởng
    with db.transaction() as conn:
        ghi = conn.execute("SELECT * FROM nhat_ky WHERE hanh_dong = 'TAM_KHOA_DANG_NHAP' ORDER BY id DESC LIMIT 1"
                           ).fetchone()
    assert ghi and ghi["thuc_the_id"] == "covan" and ghi["du_lieu_sau"]["so_lan_sai"] == auth_router.SAI_TOI_DA

    monkeypatch.setattr(auth_router, "_lan_sai", {})   # hết thời gian khóa
    assert dang_nhap("covan", "doan-bua").status_code == 401
    assert dang_nhap("covan", "KhanhVan@2026").status_code == 200
    assert auth_router._lan_sai == {}                  # đăng nhập đúng xóa đếm lần sai


def test_webhook_payos_tu_choi_khoa_demo_khi_chay_that(client, monkeypatch):
    monkeypatch.setattr(payments_router, "settings", dataclasses.replace(settings, dev_mode=False))
    r = client.post("/api/webhook/payos", json={"data": {"orderCode": 1}, "signature": "0" * 64})
    assert r.status_code == 503 and r.json()["loi"] == "PAYOS_CHUA_CAU_HINH"


def test_suc_khoe_bao_che_do_demo(client):
    assert client.get("/api/suc-khoe").json() == {"ok": True, "che_do_demo": True}


# Endpoint không cần đăng nhập, mỗi cái có cơ chế bảo vệ riêng
CONG_KHAI = {
    ("POST", "/api/auth/dang-nhap"): "giới hạn lần sai",
    ("GET", "/api/suc-khoe"): "chỉ trả trạng thái",
    ("GET", "/api/public/bao-gia/{ma_chia_se}"): "mã chia sẻ ngẫu nhiên, không có giá vốn",
    ("POST", "/api/webhook/payos"): "chữ ký HMAC PayOS",
    ("POST", "/api/thiet-bi/ghep-noi"): "mã ghép nối một lần do Chủ tạo",
    ("POST", "/api/thiet-bi/giao-dich"): "chữ ký HMAC của thiết bị",
    ("POST", "/api/thiet-bi/bao-song"): "chữ ký HMAC của thiết bị",
}


def test_moi_endpoint_khac_deu_doi_dang_nhap(client):
    sai = []
    duong_dan = app.openapi()["paths"]
    for path, cac_phuong_thuc in duong_dan.items():
        for phuong_thuc in cac_phuong_thuc:
            if (phuong_thuc.upper(), path) in CONG_KHAI:
                continue
            url = path
            while "{" in url:
                url = url[:url.index("{")] + "1" + url[url.index("}") + 1:]
            r = client.request(phuong_thuc.upper(), url, json={})
            if r.status_code != 401:
                sai.append((phuong_thuc.upper(), path, r.status_code))
    assert len(duong_dan) > 60 and not sai, sai
    assert set(CONG_KHAI) <= {(m.upper(), p) for p, ops in duong_dan.items() for m in ops}
