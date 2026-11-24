"""Thông báo đẩy (Web Push) tới app trên điện thoại của Chủ và Thợ.

Luồng: nghiệp vụ gọi `events.phat()` → nếu loại sự kiện cần đẩy, mỗi máy đã đăng ký của người nhận
được xếp một dòng `thong_bao` kênh PUSH (cùng giao dịch, rollback thì không gửi) → Worker gửi và
tự thử lại khi dịch vụ đẩy lỗi tạm thời; máy đã gỡ app (404/410) thì xóa đăng ký.
"""
import logging
import re

from cryptography.hazmat.primitives.asymmetric import ec
from psycopg.types.json import Jsonb

from ..adapters import webpush
from ..config import settings
from ..errors import LoiNghiepVu
from ..security import NguoiDung

log = logging.getLogger("khanhvan.day")


class LoiGuiDay(Exception):
    """Lỗi tạm thời: Worker sẽ thử lại sau."""


def _ton_duoi_nguong(d: dict) -> tuple[str, str]:
    ds = d["danh_sach"]
    dau = "; ".join(f"{h['ten']} còn {h['ton_kha_dung']}" + (f" ({h['xuong']})" if h.get("xuong") else "")
                    for h in ds[:3])
    them = f" và {len(ds) - 3} mặt hàng khác" if len(ds) > 3 else ""
    return f"{len(ds)} mặt hàng sắp hết", f"{dau}{them}. Liên hệ xưởng để nhập thêm."


# loại sự kiện -> (vai trò nhận mặc định, hàm tạo (tiêu đề, nội dung), trang mở khi chạm, khẩn)
SU_KIEN_DAY = {
    "YEU_CAU_DUYET": (["CHU"], lambda d: (
        "Thợ xin duyệt giá", f"{d['nguoi_yeu_cau']} xin bán đơn #{d['ma']} dưới giá sàn. Chạm để duyệt."),
        "/don-hang", True),
    "KET_QUA_DUYET": (None, lambda d: (
        "Chủ đã duyệt giá" if d["dong_y"] else "Chủ từ chối giá",
        f"Đơn #{d['ma']}: " + ("tiếp tục thu tiền." if d["dong_y"] else (d.get("ly_do") or "đơn đã hủy."))),
        "/ban-hang", True),
    "LECH_TIEN": (["CHU"], lambda d: ("Tiền về bị lệch", d["thong_bao"]), "/doi-soat", True),
    "GIAO_DICH_CHUA_KHOP": (["CHU"], lambda d: ("Tiền về chưa khớp đơn", d["thong_bao"]), "/doi-soat", False),
    "HDDT_LOI": (["CHU"], lambda d: ("Hóa đơn điện tử cần xử lý", d["ly_do"]), "/hoa-don", False),
    "XUNG_DOT_TON": (["CHU"], lambda d: (
        "Đơn bán ngoại tuyến thiếu hàng", f"Đơn #{d['ma']} vượt tồn khả dụng, cần xử lý."), "/don-hang", True),
    "MAY_NHAN_TIEN_MAT_KET_NOI": (["CHU"], lambda d: (
        "Máy nhận tiền mất kết nối", f"\"{d['ten']}\" không báo sống. Trong lúc chờ, cứ bán và xác nhận tay."),
        "/su-co", False),
    "TON_DUOI_NGUONG": (["CHU"], _ton_duoi_nguong, "/kho", False),
}


def xep_hang_theo_su_kien(conn, loai: str, du_lieu: dict, vai_tro: list[str] | None,
                          nguoi_nhan_id: int | None) -> int:
    """Gọi từ events.phat(). Trả về số thông báo đã xếp hàng."""
    cau_hinh = SU_KIEN_DAY.get(loai)
    if not cau_hinh:
        return 0
    vai_tro_mac_dinh, tao, url, khan = cau_hinh
    vai_tro = vai_tro or vai_tro_mac_dinh
    if not vai_tro and not nguoi_nhan_id:
        return 0
    try:
        tieu_de, noi_dung = tao(du_lieu)
    except (KeyError, TypeError):
        log.exception("Thiếu dữ liệu để tạo thông báo đẩy %s", loai)
        return 0
    return _xep_hang(conn, tieu_de, noi_dung, {"url": url, "loai": loai, "khan": khan},
                     vai_tro=vai_tro, tai_khoan_id=nguoi_nhan_id)


def _xep_hang(conn, tieu_de: str, noi_dung: str, du_lieu: dict, *, vai_tro: list[str] | None = None,
              tai_khoan_id: int | None = None) -> int:
    hang = conn.execute(
        """INSERT INTO thong_bao (kenh, nguoi_nhan, tieu_de, noi_dung, du_lieu)
           SELECT 'PUSH', d.id::text, %s, %s, %s
           FROM dang_ky_day d JOIN tai_khoan tk ON tk.id = d.tai_khoan_id
           WHERE tk.kich_hoat AND (%s::text[] IS NULL OR tk.vai_tro = ANY(%s::text[]))
                 AND (%s::int IS NULL OR tk.id = %s::int)
           RETURNING id""",
        (tieu_de, noi_dung, Jsonb(du_lieu), vai_tro, vai_tro, tai_khoan_id, tai_khoan_id)).fetchall()
    return len(hang)


# ---------------------------------------------------------------------------
# Khóa VAPID của cửa hàng
# ---------------------------------------------------------------------------
def khoa_vapid(conn) -> ec.EllipticCurvePrivateKey:
    """Ưu tiên biến môi trường VAPID_PRIVATE_KEY; không có thì sinh một lần và lưu vào CSDL.

    Đổi khóa làm mọi đăng ký cũ mất hiệu lực (người dùng phải bật lại thông báo), nên giữ cố định.
    """
    if settings.vapid_private_key:
        return webpush.khoa_rieng_tu_b64u(settings.vapid_private_key)
    conn.execute("INSERT INTO cau_hinh_he_thong (khoa, gia_tri) VALUES ('VAPID_PRIVATE_KEY', %s) "
                 "ON CONFLICT (khoa) DO NOTHING", (webpush.khoa_rieng_ra_b64u(webpush.sinh_khoa()),))
    gia_tri = conn.execute("SELECT gia_tri FROM cau_hinh_he_thong WHERE khoa = 'VAPID_PRIVATE_KEY'").fetchone()
    return webpush.khoa_rieng_tu_b64u(gia_tri["gia_tri"])


def khoa_cong_khai(conn) -> str:
    """applicationServerKey trình duyệt cần khi đăng ký."""
    return webpush.b64u(webpush.khoa_cong_khai_tho(khoa_vapid(conn)))


def chu_the_vapid() -> str:
    return settings.vapid_subject or f"mailto:{settings.sendgrid_from}"


# ---------------------------------------------------------------------------
# Đăng ký / hủy theo máy
# ---------------------------------------------------------------------------
_HOP_LE_B64U = re.compile(r"^[A-Za-z0-9_-]+=*$")


def _mo_ta_may(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    for mau, ten in ((r"iPhone|iPad", "iPhone/iPad"), (r"Android", "Android"), (r"Windows", "Máy tính Windows"),
                     (r"Macintosh", "Máy Mac"), (r"Linux", "Máy Linux")):
        if re.search(mau, user_agent):
            trinh_duyet = next((t for m, t in ((r"Edg/", "Edge"), (r"CriOS|Chrome/", "Chrome"),
                                               (r"Firefox/", "Firefox"), (r"Safari/", "Safari")) if re.search(m, user_agent)), "")
            return f"{ten} {trinh_duyet}".strip()
    return user_agent[:60]


def dang_ky(conn, nguoi: NguoiDung, endpoint: str, p256dh: str, auth: str, user_agent: str | None) -> dict:
    if not endpoint.startswith("https://"):
        raise LoiNghiepVu("DANG_KY_KHONG_HOP_LE", "Địa chỉ dịch vụ đẩy phải là HTTPS", 400)
    if not (_HOP_LE_B64U.match(p256dh) and _HOP_LE_B64U.match(auth)):
        raise LoiNghiepVu("DANG_KY_KHONG_HOP_LE", "Khóa mã hóa của máy không hợp lệ", 400)
    try:
        webpush.ma_hoa(b"{}", p256dh, auth)   # khóa sai đường cong thì báo ngay, không đợi lúc gửi
    except ValueError:
        raise LoiNghiepVu("DANG_KY_KHONG_HOP_LE", "Khóa mã hóa của máy không hợp lệ", 400) from None
    # Cùng một máy đổi người đăng nhập thì đăng ký chuyển sang người mới (người cũ không nhận nữa).
    return conn.execute(
        """INSERT INTO dang_ky_day (tai_khoan_id, endpoint, p256dh, auth, thiet_bi)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (endpoint) DO UPDATE SET tai_khoan_id = EXCLUDED.tai_khoan_id, p256dh = EXCLUDED.p256dh,
               auth = EXCLUDED.auth, thiet_bi = EXCLUDED.thiet_bi, cap_nhat_luc = now()
           RETURNING id, thiet_bi, tao_luc""",
        (nguoi.id, endpoint, p256dh, auth, _mo_ta_may(user_agent))).fetchone()


def huy(conn, nguoi: NguoiDung, endpoint: str) -> bool:
    return conn.execute("DELETE FROM dang_ky_day WHERE endpoint = %s AND tai_khoan_id = %s RETURNING id",
                        (endpoint, nguoi.id)).fetchone() is not None


def ds_may_cua(conn, nguoi: NguoiDung) -> list[dict]:
    return conn.execute("SELECT id, thiet_bi, tao_luc, cap_nhat_luc FROM dang_ky_day WHERE tai_khoan_id = %s "
                        "ORDER BY cap_nhat_luc DESC", (nguoi.id,)).fetchall()


# ---------------------------------------------------------------------------
# Gửi
# ---------------------------------------------------------------------------
def _gui_toi(conn, dk: dict, tieu_de: str, noi_dung: str, du_lieu: dict | None) -> webpush.KetQuaGui:
    du_lieu = du_lieu or {}
    goi = {"tieu_de": tieu_de, "noi_dung": noi_dung, "url": du_lieu.get("url", "/"),
           "the": du_lieu.get("loai")}  # cùng "the" thì thông báo mới thay thông báo cũ trên máy
    kq = webpush.gui(dk, goi, khoa_vapid(conn), chu_the_vapid(), khan=bool(du_lieu.get("khan")))
    if kq.het_hieu_luc:
        conn.execute("DELETE FROM dang_ky_day WHERE id = %s", (dk["id"],))
        log.info("Xóa đăng ký đẩy #%s (máy đã gỡ app hoặc tắt thông báo)", dk["id"])
    return kq


def gui_thong_bao(conn, tb: dict) -> None:
    """Worker gọi cho một dòng thong_bao kênh PUSH. Ném LoiGuiDay để được thử lại."""
    dk = conn.execute("SELECT * FROM dang_ky_day WHERE id = %s", (int(tb["nguoi_nhan"]),)).fetchone()
    if not dk:
        return  # máy đã hủy đăng ký sau khi xếp hàng: coi như xong
    try:
        kq = _gui_toi(conn, dk, tb["tieu_de"], tb["noi_dung"], tb.get("du_lieu"))
    except Exception as e:  # mất mạng, hết thời gian chờ
        raise LoiGuiDay(f"Không gửi được tới dịch vụ đẩy: {e}") from e
    if kq.thanh_cong or kq.het_hieu_luc:
        return
    raise LoiGuiDay(f"Dịch vụ đẩy trả {kq.ma_http}: {kq.noi_dung}")


def gui_thu(conn, nguoi: NguoiDung) -> dict:
    """Gửi ngay một thông báo thử tới mọi máy của người đang đăng nhập (không qua hàng đợi)."""
    may = conn.execute("SELECT * FROM dang_ky_day WHERE tai_khoan_id = %s", (nguoi.id,)).fetchall()
    if not may:
        raise LoiNghiepVu("CHUA_DANG_KY", "Máy này chưa bật thông báo", 409)
    ket_qua = []
    for dk in may:
        try:
            kq = _gui_toi(conn, dk, "Thông báo đã bật",
                          "Từ giờ máy này sẽ nhận yêu cầu duyệt giá, tiền về lệch và cảnh báo hàng sắp hết.",
                          {"url": "/", "loai": "THU"})
            ket_qua.append({"thiet_bi": dk["thiet_bi"], "ok": kq.thanh_cong,
                            "loi": None if kq.thanh_cong else f"HTTP {kq.ma_http}"})
        except Exception as e:
            ket_qua.append({"thiet_bi": dk["thiet_bi"], "ok": False, "loi": str(e)[:200]})
    return {"so_may": len(may), "thanh_cong": sum(k["ok"] for k in ket_qua), "chi_tiet": ket_qua}
