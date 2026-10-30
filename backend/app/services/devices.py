"""Ghép nối thiết bị bằng mã 6 số, cấp khóa ký HMAC riêng cho từng thiết bị, báo sống (heartbeat)."""
import secrets
import time

from ..config import settings
from ..errors import LoiNghiepVu, khong_tim_thay
from ..security import NguoiDung, ky_hmac, sha256_hex, so_sanh_an_toan, tao_khoa_ky
from . import audit


def tao_ma_ghep(conn, nguoi: NguoiDung, ten: str, loai: str) -> dict:
    ma = f"{secrets.randbelow(1_000_000):06d}"
    tb = conn.execute(
        """INSERT INTO thiet_bi (ten, loai, ma_ghep_hash, ma_ghep_het_han, chu_so_huu_id)
           VALUES (%s, %s, %s, now() + make_interval(mins => %s), %s) RETURNING id, ten, loai, ma_ghep_het_han""",
        (ten, loai, sha256_hex(ma), settings.pairing_ttl_minutes, nguoi.id)).fetchone()
    audit.ghi(conn, nguoi, "TAO_MA_GHEP_NOI", "THIET_BI", tb["id"], sau={"ten": ten, "loai": loai})
    return {**tb, "ma_ghep": ma}


def ghep_noi(conn, ma_ghep: str) -> dict:
    tb = conn.execute(
        """SELECT * FROM thiet_bi WHERE trang_thai = 'CHO_GHEP' AND ma_ghep_hash = %s AND ma_ghep_het_han > now()
           FOR UPDATE""", (sha256_hex(ma_ghep.replace(" ", "")),)).fetchone()
    if not tb:
        raise LoiNghiepVu("MA_GHEP_SAI", "Mã ghép nối không đúng hoặc đã hết hạn", 400)
    khoa = tao_khoa_ky()
    conn.execute("""UPDATE thiet_bi SET trang_thai = 'HOAT_DONG', khoa_ky = %s, ma_ghep_hash = NULL,
                    lan_bao_song = now() WHERE id = %s""", (khoa, tb["id"]))
    audit.ghi(conn, None, "GHEP_NOI_THIET_BI", "THIET_BI", tb["id"], sau={"ten": tb["ten"], "loai": tb["loai"]},
              thiet_bi_id=tb["id"])
    return {"thiet_bi_id": tb["id"], "ten": tb["ten"], "loai": tb["loai"], "khoa_ky": khoa}


def xac_thuc_yeu_cau(conn, thiet_bi_id: int, thoi_gian: str, chu_ky: str, body: bytes) -> dict:
    """Thiết bị ký: HMAC_SHA256(khoa_ky, "<unix_ts>.<raw_body>"); lệch giờ tối đa 5 phút."""
    try:
        ts = int(thoi_gian)
    except (TypeError, ValueError):
        raise LoiNghiepVu("CHU_KY_KHONG_HOP_LE", "Thiếu dấu thời gian", 401)
    if abs(time.time() - ts) > settings.device_clock_skew_seconds:
        raise LoiNghiepVu("CHU_KY_HET_HAN", "Yêu cầu quá cũ hoặc đồng hồ thiết bị lệch", 401)
    tb = conn.execute("SELECT * FROM thiet_bi WHERE id = %s", (thiet_bi_id,)).fetchone()
    if not tb or tb["trang_thai"] != "HOAT_DONG":
        raise LoiNghiepVu("THIET_BI_KHONG_HOP_LE", "Thiết bị chưa ghép nối hoặc đã bị thu hồi", 401)
    if not so_sanh_an_toan(ky_hmac(tb["khoa_ky"], f"{ts}.".encode() + body), chu_ky or ""):
        raise LoiNghiepVu("CHU_KY_KHONG_HOP_LE", "Chữ ký thiết bị không đúng", 401)
    return tb


def bao_song(conn, thiet_bi_id: int) -> None:
    conn.execute("UPDATE thiet_bi SET lan_bao_song = now() WHERE id = %s", (thiet_bi_id,))


def thu_hoi(conn, nguoi: NguoiDung, thiet_bi_id: int) -> dict:
    tb = conn.execute("""UPDATE thiet_bi SET trang_thai = 'THU_HOI', khoa_ky = NULL, ma_ghep_hash = NULL
                         WHERE id = %s RETURNING id, ten, trang_thai""", (thiet_bi_id,)).fetchone()
    if not tb:
        raise khong_tim_thay("thiết bị")
    audit.ghi(conn, nguoi, "THU_HOI_THIET_BI", "THIET_BI", thiet_bi_id, sau={"ten": tb["ten"]})
    return tb


def danh_sach(conn) -> list[dict]:
    return conn.execute(
        """SELECT id, ten, loai, trang_thai, lan_bao_song, tao_luc, ma_ghep_het_han,
                  (loai = 'MAY_NHAN_TIEN' AND trang_thai = 'HOAT_DONG'
                   AND (lan_bao_song IS NULL OR lan_bao_song < now() - make_interval(mins => %s))) AS mat_ket_noi
           FROM thiet_bi WHERE trang_thai <> 'CHO_GHEP' OR ma_ghep_het_han > now()
           ORDER BY id""", (settings.heartbeat_warn_minutes,)).fetchall()
