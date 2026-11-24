"""Thông báo đẩy Web Push tới app điện thoại: mã hóa RFC 8291, VAPID RFC 8292, đăng ký, xếp hàng theo sự kiện,
cảnh báo tồn dưới ngưỡng, xử lý máy đã gỡ app, và các API /api/day/*."""
import os
import struct
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient

from app.adapters import webpush
from app.main import app
from app.services import day, events, inventory


# ---------------------------------------------------------------------------
# Mã hóa & VAPID (không cần CSDL)
# ---------------------------------------------------------------------------
def test_ma_hoa_khop_vi_du_rfc8291():
    """Bộ mẫu mục 5 của RFC 8291: cùng khóa tạm và salt phải ra đúng từng byte."""
    noi_dung = webpush.tu_b64u("V2hlbiBJIGdyb3cgdXAsIEkgd2FudCB0byBiZSBhIHdhdGVybWVsb24")
    khoa_tam = webpush.khoa_rieng_tu_b64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw")
    assert webpush.b64u(webpush.khoa_cong_khai_tho(khoa_tam)) == (
        "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8")
    than = webpush.ma_hoa(
        noi_dung,
        "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
        "BTBZMqHH6r4Tts7J_aSIgg", khoa_tam=khoa_tam, salt=webpush.tu_b64u("DGv6ra1nlYgDCS1FRnbzlw"))
    assert webpush.b64u(than) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6"
        "PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def _may_nhan():
    """Giả lập trình duyệt: cặp khóa P-256 + auth secret như PushSubscription.getKey()."""
    rieng = ec.generate_private_key(ec.SECP256R1())
    return rieng, webpush.b64u(webpush.khoa_cong_khai_tho(rieng)), webpush.b64u(os.urandom(16))


def _giai_ma(than: bytes, rieng: ec.EllipticCurvePrivateKey, auth: str) -> bytes:
    """Phía máy nhận (RFC 8291 mục 3.4): đọc phần đầu aes128gcm rồi giải mã."""
    salt, rs, do_dai_khoa = than[:16], *struct.unpack("!IB", than[16:21])
    khoa_gui = than[21:21 + do_dai_khoa]
    assert rs == 4096 and do_dai_khoa == 65
    pub_gui = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), khoa_gui)
    ecdh = rieng.exchange(ec.ECDH(), pub_gui)
    ikm = webpush._hkdf(webpush.tu_b64u(auth), ecdh,
                        b"WebPush: info\x00" + webpush.khoa_cong_khai_tho(rieng) + khoa_gui, 32)
    cek = webpush._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = webpush._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ban_ro = AESGCM(cek).decrypt(nonce, than[21 + do_dai_khoa:], None)
    assert ban_ro.endswith(b"\x02")
    return ban_ro[:-1]


def test_ma_hoa_ngau_nhien_giai_ma_duoc_va_moi_lan_khac_nhau():
    rieng, p256dh, auth = _may_nhan()
    goi = '{"tieu_de": "Thợ xin duyệt giá", "noi_dung": "Đơn #KV1 dưới giá sàn"}'.encode()
    a, b = webpush.ma_hoa(goi, p256dh, auth), webpush.ma_hoa(goi, p256dh, auth)
    assert a != b  # salt và khóa tạm mới mỗi lần
    assert _giai_ma(a, rieng, auth) == goi == _giai_ma(b, rieng, auth)


def test_noi_dung_qua_dai_bi_tu_choi():
    _, p256dh, auth = _may_nhan()
    with pytest.raises(ValueError):
        webpush.ma_hoa(b"x" * 4000, p256dh, auth)


def test_jwt_vapid_ky_es256_dung_aud():
    khoa = webpush.sinh_khoa()
    token = webpush.jwt_vapid("https://fcm.googleapis.com/fcm/send/abc:xyz", khoa, "mailto:no-reply@khanhvan.vn")
    claims = jwt.decode(token, khoa.public_key(), algorithms=["ES256"], audience="https://fcm.googleapis.com")
    assert claims["sub"] == "mailto:no-reply@khanhvan.vn"
    assert jwt.get_unverified_header(token)["alg"] == "ES256"


def test_khoa_rieng_luu_va_doc_lai():
    khoa = webpush.sinh_khoa()
    lai = webpush.khoa_rieng_tu_b64u(webpush.khoa_rieng_ra_b64u(khoa))
    assert webpush.khoa_cong_khai_tho(lai) == webpush.khoa_cong_khai_tho(khoa)


# ---------------------------------------------------------------------------
# Đăng ký & xếp hàng theo sự kiện (CSDL, rollback sau mỗi test)
# ---------------------------------------------------------------------------
def _dang_ky(conn, nguoi, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1"):
    _, p256dh, auth = _may_nhan()
    return day.dang_ky(conn, nguoi, f"https://web.push.apple.com/{uuid.uuid4().hex}", p256dh, auth, user_agent)


def _hang_doi(conn, *dk_ids):
    return conn.execute("SELECT * FROM thong_bao WHERE kenh = 'PUSH' AND nguoi_nhan = ANY(%s) ORDER BY id",
                        ([str(i) for i in dk_ids],)).fetchall()


def test_khoa_vapid_sinh_mot_lan_roi_giu_nguyen(conn):
    a = day.khoa_cong_khai(conn)
    assert len(webpush.tu_b64u(a)) == 65 and day.khoa_cong_khai(conn) == a


def test_dang_ky_nhan_ra_may_va_chuyen_nguoi_khi_doi_tai_khoan(conn, chu, tho):
    dk = _dang_ky(conn, chu)
    assert dk["thiet_bi"] == "iPhone/iPad Safari"
    endpoint = conn.execute("SELECT * FROM dang_ky_day WHERE id = %s", (dk["id"],)).fetchone()
    # Thợ đăng nhập trên cùng máy: đăng ký chuyển sang Thợ, Chủ không nhận nữa
    day.dang_ky(conn, tho, endpoint["endpoint"], endpoint["p256dh"], endpoint["auth"], "Android Chrome/120")
    assert conn.execute("SELECT tai_khoan_id FROM dang_ky_day WHERE id = %s", (dk["id"],)).fetchone()[
        "tai_khoan_id"] == tho.id
    assert day.huy(conn, chu, endpoint["endpoint"]) is False   # không hủy được máy của người khác
    assert day.huy(conn, tho, endpoint["endpoint"]) is True


def test_dang_ky_tu_choi_khoa_sai(conn, chu):
    from app.errors import LoiNghiepVu
    with pytest.raises(LoiNghiepVu):
        day.dang_ky(conn, chu, "https://fcm.googleapis.com/x", "khong-phai-diem-p256", "abcdefgh", None)
    with pytest.raises(LoiNghiepVu):
        day.dang_ky(conn, chu, "http://khong-an-toan/x", _may_nhan()[1], "abcdefgh", None)


def test_su_kien_can_xu_ly_duoc_day_dung_nguoi(conn, chu, tho):
    may_chu, may_tho = _dang_ky(conn, chu), _dang_ky(conn, tho)
    events.phat(conn, "YEU_CAU_DUYET", {"yeu_cau_id": 1, "don_id": 1, "ma": "KV999", "nguoi_yeu_cau": "Anh Nam"},
                vai_tro=["CHU"])
    hang = _hang_doi(conn, may_chu["id"], may_tho["id"])
    assert [h["nguoi_nhan"] for h in hang] == [str(may_chu["id"])]
    assert hang[0]["tieu_de"] == "Thợ xin duyệt giá" and "KV999" in hang[0]["noi_dung"]
    assert hang[0]["du_lieu"] == {"url": "/don-hang", "loai": "YEU_CAU_DUYET", "khan": True}

    # Kết quả duyệt chỉ tới đúng người xin
    events.phat(conn, "KET_QUA_DUYET", {"don_id": 1, "ma": "KV999", "dong_y": False, "ly_do": "Giá thấp quá"},
                nguoi_nhan_id=tho.id)
    moi = _hang_doi(conn, may_chu["id"], may_tho["id"])[1:]
    assert [h["nguoi_nhan"] for h in moi] == [str(may_tho["id"])]
    assert moi[0]["tieu_de"] == "Chủ từ chối giá" and "Giá thấp quá" in moi[0]["noi_dung"]

    # Sự kiện thường (đơn mới) chỉ cập nhật màn hình qua WebSocket, không làm rung điện thoại
    events.phat(conn, "DON_MOI", {"don_id": 1, "ma": "KV999", "trang_thai": "CHO_THANH_TOAN"})
    assert len(_hang_doi(conn, may_chu["id"], may_tho["id"])) == 2


def test_tai_khoan_bi_khoa_khong_nhan(conn, chu):
    may = _dang_ky(conn, chu)
    conn.execute("UPDATE tai_khoan SET kich_hoat = FALSE WHERE id = %s", (chu.id,))
    events.phat(conn, "HDDT_LOI", {"hoa_don_id": 1, "ly_do": "Sai MST"}, vai_tro=["CHU"])
    assert _hang_doi(conn, may["id"]) == []


def test_canh_bao_ton_duoi_nguong_mot_lan_moi_ngay(conn, chu):
    may = _dang_ky(conn, chu)
    conn.execute("DELETE FROM canh_bao_ton")
    ma = "GUONG-HOP-SOI-1800"
    conn.execute("UPDATE bien_the SET ton_toi_thieu = 999 WHERE ma_noi_bo = %s", (ma,))
    lan1 = inventory.canh_bao_ton_thap(conn)
    assert ma in [h["ma"] for h in lan1]
    hang = _hang_doi(conn, may["id"])
    assert len(hang) == 1 and hang[0]["du_lieu"]["url"] == "/kho"
    assert hang[0]["tieu_de"] == f"{len(lan1)} mặt hàng sắp hết"
    giuong = next(h for h in lan1 if h["ma"] == ma)
    assert giuong["xuong"]  # có tên xưởng để Chủ biết gọi ai

    assert inventory.canh_bao_ton_thap(conn) == []        # đã báo trong 24 giờ: không báo lặp
    assert len(_hang_doi(conn, may["id"])) == 1

    # Nhập đủ lại (ngưỡng về 0, còn hàng) thì xóa dấu; tụt lại lần nữa thì báo ngay
    conn.execute("UPDATE bien_the SET ton_toi_thieu = 0 WHERE ma_noi_bo = %s", (ma,))
    inventory.canh_bao_ton_thap(conn)
    assert not conn.execute("SELECT 1 FROM canh_bao_ton c JOIN bien_the bt ON bt.id = c.bien_the_id "
                            "WHERE bt.ma_noi_bo = %s", (ma,)).fetchone()
    conn.execute("UPDATE bien_the SET ton_toi_thieu = 999 WHERE ma_noi_bo = %s", (ma,))
    assert [h["ma"] for h in inventory.canh_bao_ton_thap(conn)] == [ma]


# ---------------------------------------------------------------------------
# Gửi: máy đã gỡ app, lỗi tạm thời
# ---------------------------------------------------------------------------
def _gia_lap_gui(monkeypatch, ma_http, ghi=None):
    def gui(dk, goi, khoa, chu_the, **kw):
        if ghi is not None:
            ghi.append((dk["endpoint"], goi, chu_the, kw))
        return webpush.KetQuaGui(ma_http, "")
    monkeypatch.setattr(webpush, "gui", gui)


def test_gui_thanh_cong_mang_dung_noi_dung(conn, chu, monkeypatch):
    may = _dang_ky(conn, chu)
    events.phat(conn, "LECH_TIEN", {"thong_bao": "Đơn #KV1 chuyển thiếu 200.000 đ"}, vai_tro=["CHU"])
    tb = _hang_doi(conn, may["id"])[0]
    da_gui = []
    _gia_lap_gui(monkeypatch, 201, da_gui)
    day.gui_thong_bao(conn, tb)
    (endpoint, goi, chu_the, kw), = da_gui
    assert goi == {"tieu_de": "Tiền về bị lệch", "noi_dung": "Đơn #KV1 chuyển thiếu 200.000 đ",
                   "url": "/doi-soat", "the": "LECH_TIEN"}
    assert chu_the.startswith("mailto:") and kw["khan"] is True


def test_may_da_go_app_thi_xoa_dang_ky(conn, chu, monkeypatch):
    may = _dang_ky(conn, chu)
    events.phat(conn, "HDDT_LOI", {"hoa_don_id": 1, "ly_do": "Sai MST"}, vai_tro=["CHU"])
    _gia_lap_gui(monkeypatch, 410)
    day.gui_thong_bao(conn, _hang_doi(conn, may["id"])[0])   # không ném lỗi: không cần thử lại
    assert not conn.execute("SELECT 1 FROM dang_ky_day WHERE id = %s", (may["id"],)).fetchone()


def test_dich_vu_day_loi_tam_thoi_thi_thu_lai(conn, chu, monkeypatch):
    may = _dang_ky(conn, chu)
    events.phat(conn, "HDDT_LOI", {"hoa_don_id": 1, "ly_do": "Sai MST"}, vai_tro=["CHU"])
    _gia_lap_gui(monkeypatch, 503)
    with pytest.raises(day.LoiGuiDay):
        day.gui_thong_bao(conn, _hang_doi(conn, may["id"])[0])
    assert conn.execute("SELECT 1 FROM dang_ky_day WHERE id = %s", (may["id"],)).fetchone()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client(csdl):
    with TestClient(app) as c:
        yield c


def _dang_nhap(client, ten, mk):
    r = client.post("/api/auth/dang-nhap", json={"ten_dang_nhap": ten, "mat_khau": mk})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_api_bat_thu_va_tat_thong_bao(client, monkeypatch):
    h = _dang_nhap(client, "covan", "KhanhVan@2026")
    assert client.get("/api/day/khoa").status_code == 401
    khoa = client.get("/api/day/khoa", headers=h).json()["khoa_cong_khai"]
    assert len(webpush.tu_b64u(khoa)) == 65

    assert client.post("/api/day/thu", headers=h).json()["loi"] == "CHUA_DANG_KY"
    _, p256dh, auth = _may_nhan()
    endpoint = f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}"
    r = client.post("/api/day/dang-ky", headers={**h, "User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/130"},
                    json={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}})
    assert r.status_code == 200, r.text
    assert r.json()["thiet_bi"] == "Android Chrome"
    try:
        _gia_lap_gui(monkeypatch, 201)
        kq = client.post("/api/day/thu", headers=h).json()
        assert kq["thanh_cong"] >= 1
        assert any(m["thiet_bi"] == "Android Chrome" for m in client.get("/api/day/may", headers=h).json())
    finally:
        assert client.post("/api/day/huy", headers=h, json={"endpoint": endpoint}).json() == {"da_huy": True}


def test_api_cors_cho_app_dien_thoai(client):
    for origin in ("capacitor://localhost", "https://localhost"):
        r = client.options("/api/auth/dang-nhap", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"})
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
    r = client.options("/api/auth/dang-nhap", headers={
        "Origin": "https://trang-la.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
