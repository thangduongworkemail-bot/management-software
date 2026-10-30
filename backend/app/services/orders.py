"""Đơn hàng, chốt chặn giá sàn mềm, giữ chỗ TTL, chốt đơn và báo giá.

Vòng đời đơn (trang_thai):
    CHO_DUYET_GIA -> CHO_THANH_TOAN -> (CON_NO) -> DA_THANH_TOAN
    CHO_DUYET_GIA -> DA_HUY (chủ từ chối);  CHO_THANH_TOAN -> HET_HAN (Worker nhả giữ chỗ sau 30 phút)
Trạng thái giao hàng (trang_thai_giao) tách riêng: CHUA_GIAO / DA_GIAO / CHO_XUONG_GIAO / XUNG_DOT_TON.
"""
import secrets
from datetime import datetime, timedelta

from psycopg.types.json import Jsonb

from ..config import settings
from ..domain.vietqr import tao_chuoi_vietqr
from ..errors import LoiNghiepVu, khong_tim_thay
from ..security import NguoiDung
from . import audit, catalog, codes, events, inventory

TRANG_THAI_CON_THU = ("CHO_DUYET_GIA", "CHO_THANH_TOAN", "CON_NO", "HET_HAN")


def con_phai_thu(don: dict) -> int:
    return max(0, don["tong_tien"] - don["giam_tru"] - don["da_thu"])


def khoa_don(conn, don_id: int) -> dict:
    don = conn.execute("SELECT * FROM don_hang WHERE id = %s FOR UPDATE", (don_id,)).fetchone()
    if not don:
        raise khong_tim_thay("đơn hàng")
    return don


def id_theo_ma(conn, ma: str) -> int:
    r = conn.execute("SELECT id FROM don_hang WHERE ma = %s", (ma.lstrip("#"),)).fetchone()
    if not r:
        raise khong_tim_thay(f"đơn {ma}")
    return r["id"]


# ---------------------------------------------------------------------------
# Định giá từng dòng (bản chụp giá tại thời điểm lập)
# ---------------------------------------------------------------------------
def dinh_gia_dong(conn, d: dict) -> dict:
    so_luong = int(d.get("so_luong") or 1)
    if so_luong <= 0:
        raise LoiNghiepVu("SO_LUONG_KHONG_HOP_LE", "Số lượng phải lớn hơn 0")

    bo_id, bt_id = d.get("bo_san_pham_id"), d.get("bien_the_id")
    if not bo_id and not bt_id and d.get("ma"):
        hang = catalog.tim_theo_ma(conn, d["ma"])
        bo_id, bt_id = (hang["id"], None) if hang["kieu"] == "BO" else (None, hang["id"])
    if not bo_id and not bt_id:
        raise LoiNghiepVu("THIEU_MAT_HANG", "Dòng đơn chưa chọn mặt hàng")

    if bo_id:
        bo = catalog.lay_bo(conn, int(bo_id))
        if not bo["dang_ban"]:
            raise LoiNghiepVu("NGUNG_BAN", f"{bo['ten']} đã ngừng bán")
        dong = {"bien_the_id": None, "bo_san_pham_id": bo["id"], "mo_ta": bo["ten"], "dat_rieng": False,
                "gia_niem_yet_chup": bo["gia_niem_yet"], "gia_san_chup": bo["gia_san"],
                "gia_von_chup": bo["gia_von"] or 0, "kieu_cong_thuc": None, "tham_so": {"ma": bo["ma"]}}
    else:
        bt = catalog.lay_bien_the(conn, int(bt_id))
        if not bt["dang_ban"]:
            raise LoiNghiepVu("NGUNG_BAN", f"{bt['ten']} đã ngừng bán")
        if bt["dat_theo_kich_thuoc"]:
            if not d.get("kich_thuoc"):
                raise LoiNghiepVu("THIEU_KICH_THUOC", f"{bt['ten']} là hàng đặt riêng, cần nhập kích thước")
            g = catalog.tinh_gia_dat_rieng(conn, bt["id"], d["kich_thuoc"])
            kt = " × ".join(str(mm) for mm in g["kich_thuoc_mm"])
            dong = {"bien_the_id": bt["id"], "bo_san_pham_id": None, "dat_rieng": True,
                    "mo_ta": f"{bt['ten']} — đặt riêng {kt} mm",
                    "gia_niem_yet_chup": g["gia"], "gia_san_chup": g["gia_san"], "gia_von_chup": g["gia_von"],
                    "kieu_cong_thuc": g["kieu_cong_thuc"],
                    "tham_so": {**g["tham_so"], "ma": bt["ma"], "dien_giai": g["dien_giai"]}}
        else:
            if bt["gia_niem_yet"] is None:
                raise LoiNghiepVu("CHUA_CO_GIA", f"{bt['ten']} chưa có giá niêm yết")
            dong = {"bien_the_id": bt["id"], "bo_san_pham_id": None, "mo_ta": bt["ten"], "dat_rieng": False,
                    "gia_niem_yet_chup": bt["gia_niem_yet"], "gia_san_chup": bt["gia_san"] or 0,
                    "gia_von_chup": bt["gia_von"] or 0, "kieu_cong_thuc": None, "tham_so": {"ma": bt["ma"]}}

    don_gia = d.get("don_gia_ban")
    don_gia = dong["gia_niem_yet_chup"] if don_gia is None else int(don_gia)
    if don_gia < 0:
        raise LoiNghiepVu("GIA_KHONG_HOP_LE", "Đơn giá bán không được âm")
    dong.update(so_luong=so_luong, don_gia_ban=don_gia, thanh_tien=don_gia * so_luong)
    return dong


def _khach_hang(conn, du_lieu: dict) -> int | None:
    if du_lieu.get("khach_hang_id"):
        return int(du_lieu["khach_hang_id"])
    kh = du_lieu.get("khach_hang")
    if not kh or not (kh.get("ten") or kh.get("so_dien_thoai")):
        return None
    if kh.get("so_dien_thoai"):
        cu = conn.execute("SELECT id FROM khach_hang WHERE so_dien_thoai = %s ORDER BY id LIMIT 1",
                          (kh["so_dien_thoai"],)).fetchone()
        if cu:
            conn.execute(
                """UPDATE khach_hang SET ma_so_thue = COALESCE(%s, ma_so_thue), email = COALESCE(%s, email),
                          dia_chi = COALESCE(%s, dia_chi) WHERE id = %s""",
                (kh.get("ma_so_thue") or None, kh.get("email") or None, kh.get("dia_chi") or None, cu["id"]))
            return cu["id"]
    return conn.execute(
        """INSERT INTO khach_hang (ten, so_dien_thoai, ma_so_thue, email, dia_chi)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (kh.get("ten") or "Khách lẻ", kh.get("so_dien_thoai") or None, kh.get("ma_so_thue") or None,
         kh.get("email") or None, kh.get("dia_chi") or None)).fetchone()["id"]


# ---------------------------------------------------------------------------
# Lập đơn
# ---------------------------------------------------------------------------
def tao_don(conn, nguoi: NguoiDung, du_lieu: dict, kenh: str = "QUAY", ma: str | None = None,
            duoc_duyet_san: bool = False) -> dict:
    key = du_lieu.get("idempotency_key")
    if key:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(key),))
        cu = conn.execute("SELECT id FROM don_hang WHERE idempotency_key = %s", (str(key),)).fetchone()
        if cu:
            return {**lay_don(conn, cu["id"], nguoi), "trung_lap": True}

    dong_vao = du_lieu.get("dong") or []
    if not dong_vao:
        raise LoiNghiepVu("DON_RONG", "Đơn hàng phải có ít nhất một mặt hàng")
    dong = [dinh_gia_dong(conn, d) for d in dong_vao]

    duoi_san = [d for d in dong if d["don_gia_ban"] < d["gia_san_chup"]]
    can_duyet = bool(duoi_san) and not nguoi.la_chu and not duoc_duyet_san
    co_hang_san = any(not d["dat_rieng"] for d in dong)
    tong = sum(d["thanh_tien"] for d in dong)
    trang_thai = "CHO_DUYET_GIA" if can_duyet else "CHO_THANH_TOAN"
    giu_cho_den = (datetime.now().astimezone() + timedelta(minutes=settings.hold_ttl_minutes)
                   if trang_thai == "CHO_THANH_TOAN" and co_hang_san else None)

    don = conn.execute(
        """INSERT INTO don_hang (ma, khach_hang_id, bao_gia_id, nguoi_lap_id, kenh, trang_thai, tong_tien,
                                 giu_cho_den, can_hoa_don, idempotency_key, ghi_chu)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (ma or codes.ma_tiep_theo(conn, "KV"), _khach_hang(conn, du_lieu), du_lieu.get("bao_gia_id"), nguoi.id,
         kenh, trang_thai, tong, giu_cho_den, bool(du_lieu.get("can_hoa_don")), key, du_lieu.get("ghi_chu"))
    ).fetchone()

    for d in dong:
        conn.execute(
            """INSERT INTO dong_don (don_hang_id, bien_the_id, bo_san_pham_id, mo_ta, so_luong, don_gia_ban,
                                     gia_niem_yet_chup, gia_san_chup, gia_von_chup, kieu_cong_thuc, tham_so,
                                     thanh_tien, dat_rieng)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (don["id"], d["bien_the_id"], d["bo_san_pham_id"], d["mo_ta"], d["so_luong"], d["don_gia_ban"],
             d["gia_niem_yet_chup"], d["gia_san_chup"], d["gia_von_chup"], d["kieu_cong_thuc"],
             Jsonb(d["tham_so"]), d["thanh_tien"], d["dat_rieng"]))

    if co_hang_san:
        # Đơn lập lúc mất mạng không bị từ chối khi đồng bộ: đánh dấu xung đột để chủ quyết định
        thieu = inventory.giu_cho_don(conn, don, giu_cho_den, nguoi, bat_buoc=(kenh != "NGOAI_TUYEN"))
        if thieu:
            conn.execute("UPDATE don_hang SET trang_thai_giao = 'XUNG_DOT_TON', giu_cho_den = NULL WHERE id = %s",
                         (don["id"],))
            events.phat(conn, "XUNG_DOT_TON", {"don_id": don["id"], "ma": don["ma"], "thieu": thieu}, vai_tro=["CHU"])

    if can_duyet:
        noi_dung = {"dong": [{"mo_ta": d["mo_ta"], "gia_san": d["gia_san_chup"], "xin_ban": d["don_gia_ban"],
                              "chenh_lech": d["don_gia_ban"] - d["gia_san_chup"]} for d in duoi_san]}
        yc = conn.execute(
            """INSERT INTO yeu_cau_duyet (don_hang_id, loai, noi_dung, nguoi_yeu_cau_id)
               VALUES (%s, 'BAN_DUOI_GIA_SAN', %s, %s) RETURNING id""",
            (don["id"], Jsonb(noi_dung), nguoi.id)).fetchone()
        events.phat(conn, "YEU_CAU_DUYET", {"yeu_cau_id": yc["id"], "don_id": don["id"], "ma": don["ma"],
                                            "nguoi_yeu_cau": nguoi.ho_ten, **noi_dung}, vai_tro=["CHU"])
        events.xep_hang_thong_bao(conn, "ZALO", settings.notify_owner_phone, "Yêu cầu bán dưới giá sàn",
                                  f"{nguoi.ho_ten} xin bán đơn #{don['ma']} dưới giá sàn. Mở app để duyệt.")

    audit.ghi(conn, nguoi, "TAO_DON", "DON_HANG", don["ma"],
              sau={"tong_tien": tong, "trang_thai": trang_thai, "kenh": kenh,
                   "ban_duoi_gia_san": bool(duoi_san), "so_dong": len(dong)})
    events.phat(conn, "DON_MOI", {"don_id": don["id"], "ma": don["ma"], "trang_thai": trang_thai})
    return lay_don(conn, don["id"], nguoi)


# ---------------------------------------------------------------------------
# Duyệt giá sàn
# ---------------------------------------------------------------------------
def duyet_yeu_cau(conn, nguoi: NguoiDung, yeu_cau_id: int, dong_y: bool, ly_do: str | None = None) -> dict:
    yc = conn.execute("SELECT * FROM yeu_cau_duyet WHERE id = %s FOR UPDATE", (yeu_cau_id,)).fetchone()
    if not yc:
        raise khong_tim_thay("yêu cầu duyệt")
    if yc["trang_thai"] != "CHO_DUYET":
        raise LoiNghiepVu("DA_XU_LY", "Yêu cầu này đã được xử lý", 409)
    don = khoa_don(conn, yc["don_hang_id"])
    if don["trang_thai"] != "CHO_DUYET_GIA":
        raise LoiNghiepVu("TRANG_THAI_KHONG_HOP_LE", "Đơn không còn chờ duyệt giá", 409)

    conn.execute("UPDATE yeu_cau_duyet SET trang_thai = %s, nguoi_duyet_id = %s, ly_do = %s, duyet_luc = now() "
                 "WHERE id = %s", ("DA_DUYET" if dong_y else "TU_CHOI", nguoi.id, ly_do, yeu_cau_id))
    if dong_y:
        if con_phai_thu(don) == 0:
            chot_don(conn, nguoi, don)
        else:
            co_giu = bool(inventory.dang_giu_cua_don(conn, don["id"]))
            conn.execute("UPDATE don_hang SET trang_thai = 'CHO_THANH_TOAN', giu_cho_den = %s WHERE id = %s",
                         (datetime.now().astimezone() + timedelta(minutes=settings.hold_ttl_minutes) if co_giu else None,
                          don["id"]))
    else:
        inventory.nha_cho_don(conn, don, "Chủ từ chối bán dưới giá sàn", nguoi)
        conn.execute("UPDATE don_hang SET trang_thai = 'DA_HUY', giu_cho_den = NULL WHERE id = %s", (don["id"],))

    audit.ghi(conn, nguoi, "DUYET_GIA_SAN" if dong_y else "TU_CHOI_GIA_SAN", "DON_HANG", don["ma"],
              truoc={"trang_thai": "CHO_DUYET_GIA"}, sau={"dong_y": dong_y, "ly_do": ly_do, **yc["noi_dung"]})
    events.phat(conn, "KET_QUA_DUYET", {"don_id": don["id"], "ma": don["ma"], "dong_y": dong_y, "ly_do": ly_do},
                nguoi_nhan_id=yc["nguoi_yeu_cau_id"])
    return lay_don(conn, don["id"], nguoi)


def yeu_cau_cho_duyet(conn) -> list[dict]:
    return conn.execute(
        """SELECT yc.*, dh.ma AS ma_don, dh.tong_tien, tk.ho_ten AS nguoi_yeu_cau
           FROM yeu_cau_duyet yc JOIN don_hang dh ON dh.id = yc.don_hang_id
           JOIN tai_khoan tk ON tk.id = yc.nguoi_yeu_cau_id
           WHERE yc.trang_thai = 'CHO_DUYET' ORDER BY yc.tao_luc""").fetchall()


# ---------------------------------------------------------------------------
# Chốt đơn: xuất kho + phiếu bán hàng + đưa HĐĐT vào hàng đợi, trong CÙNG giao dịch
# ---------------------------------------------------------------------------
def chot_don(conn, nguoi: NguoiDung, don: dict) -> None:
    don = khoa_don(conn, don["id"])
    if don["trang_thai_giao"] == "XUNG_DOT_TON":
        giao = "XUNG_DOT_TON"
    else:
        inventory.xuat_kho_don(conn, don, nguoi)
        giao = "CHO_XUONG_GIAO" if _co_dat_rieng(conn, don["id"]) else "DA_GIAO"
    conn.execute("UPDATE don_hang SET trang_thai = 'DA_THANH_TOAN', trang_thai_giao = %s, giu_cho_den = NULL "
                 "WHERE id = %s", (giao, don["id"]))
    don = {**don, "trang_thai": "DA_THANH_TOAN", "trang_thai_giao": giao}

    chi_tiet = lay_don(conn, don["id"], nguoi)
    conn.execute(
        """INSERT INTO phieu_ban_hang (don_hang_id, so_phieu, noi_dung) VALUES (%s, %s, %s)
           ON CONFLICT (don_hang_id) DO NOTHING""",
        (don["id"], f"PBH-{don['ma']}", Jsonb(_noi_dung_phieu(chi_tiet))))

    kh = conn.execute("SELECT * FROM khach_hang WHERE id = %s", (don["khach_hang_id"],)).fetchone() \
        if don["khach_hang_id"] else None
    conn.execute(
        """INSERT INTO hoa_don_dt (don_hang_id, trang_thai, nha_cung_cap_hddt, ten_nguoi_mua, ma_so_thue, dia_chi, email)
           VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (don_hang_id) DO NOTHING""",
        (don["id"], "CHO_XUAT" if don["can_hoa_don"] else "CHUA_CAN", settings.einvoice_provider.upper(),
         kh and kh["ten"], kh and kh["ma_so_thue"], kh and kh["dia_chi"], kh and kh["email"]))

    cap_nhat_du_no(conn, don["khach_hang_id"])
    audit.ghi(conn, nguoi, "CHOT_DON", "DON_HANG", don["ma"],
              sau={"tong_tien": don["tong_tien"], "giam_tru": don["giam_tru"], "trang_thai_giao": giao,
                   "can_hoa_don": don["can_hoa_don"]})
    events.phat(conn, "DON_DA_THANH_TOAN", {"don_id": don["id"], "ma": don["ma"]})


def _co_dat_rieng(conn, don_id: int) -> bool:
    return bool(conn.execute("SELECT 1 FROM dong_don WHERE don_hang_id = %s AND dat_rieng LIMIT 1",
                             (don_id,)).fetchone())


def _noi_dung_phieu(don: dict) -> dict:
    return {
        "ma_don": don["ma"], "khach": don.get("ten_khach") or "Khách lẻ", "nguoi_ban": don.get("nguoi_lap"),
        "dong": [{"mo_ta": d["mo_ta"], "so_luong": d["so_luong"], "don_gia": d["don_gia_ban"],
                  "thanh_tien": d["thanh_tien"]} for d in don["dong"]],
        "tong_tien": don["tong_tien"], "giam_tru": don["giam_tru"], "da_thu": don["da_thu"],
        "ghi_chu": "Phiếu bán hàng nội bộ — không phải hóa đơn điện tử",
    }


def cap_nhat_du_no(conn, khach_hang_id: int | None) -> None:
    if not khach_hang_id:
        return
    conn.execute(
        """UPDATE khach_hang SET du_no = (
               SELECT COALESCE(sum(tong_tien - giam_tru - da_thu), 0) FROM don_hang
               WHERE khach_hang_id = %s AND trang_thai = 'CON_NO')
           WHERE id = %s""", (khach_hang_id, khach_hang_id))


# ---------------------------------------------------------------------------
# Thao tác khác trên đơn
# ---------------------------------------------------------------------------
def ban_chiu(conn, nguoi: NguoiDung, don_id: int, ghi_chu: str | None = None) -> dict:
    """Chủ cho khách lấy hàng trước, trả sau: xuất kho ngay, đơn chuyển CON_NO."""
    don = khoa_don(conn, don_id)
    if don["trang_thai"] not in ("CHO_THANH_TOAN", "CON_NO"):
        raise LoiNghiepVu("TRANG_THAI_KHONG_HOP_LE", "Chỉ bán chịu được đơn đang chờ thanh toán", 409)
    if not don["khach_hang_id"]:
        raise LoiNghiepVu("THIEU_KHACH_HANG", "Bán chịu phải có thông tin khách hàng")
    if don["trang_thai_giao"] == "XUNG_DOT_TON":
        raise LoiNghiepVu("XUNG_DOT_TON", "Đơn đang thiếu hàng, chưa giao được", 409)
    inventory.xuat_kho_don(conn, don, nguoi)
    giao = "CHO_XUONG_GIAO" if _co_dat_rieng(conn, don_id) else "DA_GIAO"
    conn.execute("UPDATE don_hang SET trang_thai = 'CON_NO', trang_thai_giao = %s, giu_cho_den = NULL, "
                 "ghi_chu = COALESCE(%s, ghi_chu) WHERE id = %s", (giao, ghi_chu, don_id))
    cap_nhat_du_no(conn, don["khach_hang_id"])
    audit.ghi(conn, nguoi, "BAN_CHIU", "DON_HANG", don["ma"], sau={"con_no": con_phai_thu(don)})
    return lay_don(conn, don_id, nguoi)


def huy_don(conn, nguoi: NguoiDung, don_id: int, ly_do: str) -> dict:
    don = khoa_don(conn, don_id)
    if don["trang_thai"] in ("DA_THANH_TOAN", "DA_HUY"):
        raise LoiNghiepVu("TRANG_THAI_KHONG_HOP_LE", "Đơn đã thanh toán hoặc đã hủy, dùng chức năng trả hàng", 409)
    if conn.execute("SELECT 1 FROM dong_don WHERE don_hang_id = %s AND da_xuat LIMIT 1", (don_id,)).fetchone():
        raise LoiNghiepVu("DA_XUAT_KHO", "Đơn đã giao hàng, dùng chức năng trả hàng", 409)
    if not nguoi.la_chu and don["nguoi_lap_id"] != nguoi.id:
        raise LoiNghiepVu("KHONG_DU_QUYEN", "Chỉ người lập đơn hoặc chủ được hủy đơn", 403)
    inventory.nha_cho_don(conn, don, f"Hủy đơn: {ly_do}", nguoi)
    conn.execute("UPDATE don_hang SET trang_thai = 'DA_HUY', giu_cho_den = NULL WHERE id = %s", (don_id,))
    cap_nhat_du_no(conn, don["khach_hang_id"])
    audit.ghi(conn, nguoi, "HUY_DON", "DON_HANG", don["ma"], truoc={"trang_thai": don["trang_thai"]},
              sau={"ly_do": ly_do, "can_hoan_tien": don["da_thu"]})
    return lay_don(conn, don_id, nguoi)


def tra_hang(conn, nguoi: NguoiDung, don_id: int, ly_do: str) -> dict:
    don = khoa_don(conn, don_id)
    if don["trang_thai"] not in ("DA_THANH_TOAN", "CON_NO"):
        raise LoiNghiepVu("TRANG_THAI_KHONG_HOP_LE", "Chỉ trả hàng cho đơn đã giao", 409)
    tra = inventory.nhap_tra_hang(conn, don, nguoi, ly_do)
    conn.execute("UPDATE don_hang SET trang_thai = 'DA_HUY', ghi_chu = %s WHERE id = %s",
                 (f"Trả hàng: {ly_do}", don_id))
    cap_nhat_du_no(conn, don["khach_hang_id"])
    audit.ghi(conn, nguoi, "TRA_HANG", "DON_HANG", don["ma"], sau={"ly_do": ly_do, "so_tien_hoan": don["da_thu"],
                                                                  "bien_the": tra})
    return lay_don(conn, don_id, nguoi)


def giai_quyet_xung_dot(conn, nguoi: NguoiDung, don_id: int, cach: str) -> dict:
    don = khoa_don(conn, don_id)
    if don["trang_thai_giao"] != "XUNG_DOT_TON":
        raise LoiNghiepVu("KHONG_XUNG_DOT", "Đơn không ở trạng thái xung đột tồn", 409)
    if cach == "CHO_XUONG_GIAO":
        conn.execute("UPDATE don_hang SET trang_thai_giao = 'CHO_XUONG_GIAO' WHERE id = %s", (don_id,))
    elif cach == "HUY":
        conn.execute("UPDATE don_hang SET trang_thai = 'DA_HUY', trang_thai_giao = 'CHUA_GIAO' WHERE id = %s",
                     (don_id,))
        cap_nhat_du_no(conn, don["khach_hang_id"])
    else:
        raise LoiNghiepVu("CACH_KHONG_HOP_LE", "Cách xử lý phải là CHO_XUONG_GIAO hoặc HUY")
    audit.ghi(conn, nguoi, "XU_LY_XUNG_DOT_TON", "DON_HANG", don["ma"], sau={"cach": cach})
    return lay_don(conn, don_id, nguoi)


def giao_hang(conn, nguoi: NguoiDung, don_id: int) -> dict:
    """Giao nốt hàng cho đơn chờ xưởng (hàng đặt riêng đã về / hàng thiếu đã nhập)."""
    don = khoa_don(conn, don_id)
    if don["trang_thai_giao"] != "CHO_XUONG_GIAO" or don["trang_thai"] not in ("DA_THANH_TOAN", "CON_NO"):
        raise LoiNghiepVu("TRANG_THAI_KHONG_HOP_LE", "Đơn không ở trạng thái chờ xưởng giao", 409)
    inventory.xuat_kho_don(conn, don, nguoi)
    conn.execute("UPDATE don_hang SET trang_thai_giao = 'DA_GIAO' WHERE id = %s", (don_id,))
    audit.ghi(conn, nguoi, "GIAO_HANG", "DON_HANG", don["ma"])
    return lay_don(conn, don_id, nguoi)


def nha_giu_cho_het_han(conn) -> list[str]:
    """Worker: đơn chờ chuyển khoản quá TTL mà chưa thu đồng nào -> nhả giữ chỗ (ghi NHA_CHO)."""
    het = conn.execute(
        """SELECT * FROM don_hang
           WHERE trang_thai = 'CHO_THANH_TOAN' AND giu_cho_den < now() AND da_thu = 0
           ORDER BY giu_cho_den FOR UPDATE SKIP LOCKED""").fetchall()
    for don in het:
        inventory.nha_cho_don(conn, don, f"Hết hạn giữ chỗ {settings.hold_ttl_minutes} phút", None)
        conn.execute("UPDATE don_hang SET trang_thai = 'HET_HAN', giu_cho_den = NULL WHERE id = %s", (don["id"],))
        audit.ghi(conn, None, "NHA_GIU_CHO_TU_DONG", "DON_HANG", don["ma"])
        events.phat(conn, "GIU_CHO_HET_HAN", {"don_id": don["id"], "ma": don["ma"]})
    return [d["ma"] for d in het]


def giu_cho_lai(conn, nguoi: NguoiDung, don: dict) -> None:
    """Đơn đã hết hạn nhưng khách vẫn trả tiền: giữ lại hàng nếu còn, không thì đánh dấu xung đột."""
    thieu = inventory.giu_cho_don(conn, don, None, nguoi, bat_buoc=False)
    conn.execute("UPDATE don_hang SET trang_thai = 'CHO_THANH_TOAN', trang_thai_giao = %s WHERE id = %s",
                 ("XUNG_DOT_TON" if thieu else don["trang_thai_giao"], don["id"]))


# ---------------------------------------------------------------------------
# Đọc đơn
# ---------------------------------------------------------------------------
def lay_don(conn, don_id: int, nguoi: NguoiDung) -> dict:
    don = conn.execute(
        """SELECT dh.*, kh.ten AS ten_khach, kh.so_dien_thoai, kh.ma_so_thue, tk.ho_ten AS nguoi_lap
           FROM don_hang dh LEFT JOIN khach_hang kh ON kh.id = dh.khach_hang_id
           JOIN tai_khoan tk ON tk.id = dh.nguoi_lap_id WHERE dh.id = %s""", (don_id,)).fetchone()
    if not don:
        raise khong_tim_thay("đơn hàng")
    dong = conn.execute("SELECT * FROM dong_don WHERE don_hang_id = %s ORDER BY id", (don_id,)).fetchall()
    if not nguoi.xem_gia_von:
        dong = [{k: v for k, v in d.items() if k not in ("gia_von_chup", "gia_san_chup")} for d in dong]
    don["dong"] = dong
    don["thanh_toan"] = conn.execute(
        """SELECT tt.*, tk.ho_ten AS nguoi_ghi_nhan,
                  COALESCE(json_agg(json_build_object('kieu', bc.kieu, 'gia_tri', bc.gia_tri))
                           FILTER (WHERE bc.id IS NOT NULL), '[]') AS bang_chung
           FROM thanh_toan tt LEFT JOIN tai_khoan tk ON tk.id = tt.nguoi_ghi_nhan_id
           LEFT JOIN bang_chung_tien bc ON bc.thanh_toan_id = tt.id
           WHERE tt.don_hang_id = %s GROUP BY tt.id, tk.ho_ten ORDER BY tt.id""", (don_id,)).fetchall()
    yc = conn.execute("SELECT id, trang_thai, ly_do, tao_luc, duyet_luc, noi_dung FROM yeu_cau_duyet "
                      "WHERE don_hang_id = %s ORDER BY id", (don_id,)).fetchall()
    if not nguoi.xem_gia_von:
        for r in yc:
            r.pop("noi_dung", None)
    don["yeu_cau_duyet"] = yc
    don["hoa_don"] = conn.execute("SELECT * FROM hoa_don_dt WHERE don_hang_id = %s", (don_id,)).fetchone()
    don["con_phai_thu"] = con_phai_thu(don)
    don["vietqr"] = (tao_chuoi_vietqr(settings.vietqr_bank_bin, settings.vietqr_account_no, don["con_phai_thu"],
                                      don["ma"])
                     if don["con_phai_thu"] > 0 and don["trang_thai"] in TRANG_THAI_CON_THU else None)
    don["tai_khoan_nhan"] = {"ngan_hang_bin": settings.vietqr_bank_bin, "so_tai_khoan": settings.vietqr_account_no,
                             "chu_tai_khoan": settings.vietqr_account_name}
    return don


def danh_sach_don(conn, trang_thai: str | None = None, tu_khoa: str | None = None, gioi_han: int = 50) -> list[dict]:
    dieu_kien, tham_so = [], []
    if trang_thai:
        dieu_kien.append("(dh.trang_thai = %s OR dh.trang_thai_giao = %s)")
        tham_so += [trang_thai, trang_thai]
    if tu_khoa:
        dieu_kien.append("(dh.ma ILIKE %s OR f_chuan_hoa(COALESCE(kh.ten, '')) LIKE '%%' || f_chuan_hoa(%s) || '%%' "
                         "OR kh.so_dien_thoai LIKE %s)")
        tham_so += [f"%{tu_khoa}%", tu_khoa, f"%{tu_khoa}%"]
    where = f"WHERE {' AND '.join(dieu_kien)}" if dieu_kien else ""
    return conn.execute(
        f"""SELECT dh.id, dh.ma, dh.trang_thai, dh.trang_thai_giao, dh.tong_tien, dh.da_thu, dh.giam_tru, dh.kenh,
                   dh.giu_cho_den, dh.tao_luc, dh.can_hoa_don, kh.ten AS ten_khach, tk.ho_ten AS nguoi_lap,
                   (SELECT string_agg(mo_ta, ', ') FROM dong_don WHERE don_hang_id = dh.id) AS tom_tat
            FROM don_hang dh LEFT JOIN khach_hang kh ON kh.id = dh.khach_hang_id
            JOIN tai_khoan tk ON tk.id = dh.nguoi_lap_id
            {where} ORDER BY dh.tao_luc DESC LIMIT %s""", (*tham_so, gioi_han)).fetchall()


# ---------------------------------------------------------------------------
# Báo giá (giữ giá 7 ngày, chia sẻ bằng liên kết công khai)
# ---------------------------------------------------------------------------
def tao_bao_gia(conn, nguoi: NguoiDung, du_lieu: dict) -> dict:
    dong = [dinh_gia_dong(conn, d) for d in (du_lieu.get("dong") or [])]
    if not dong:
        raise LoiNghiepVu("BAO_GIA_RONG", "Báo giá phải có ít nhất một mặt hàng")
    bg = conn.execute(
        """INSERT INTO bao_gia (ma, khach_hang_id, nguoi_lap_id, tong_tien, ma_chia_se, het_han_luc, ghi_chu)
           VALUES (%s, %s, %s, %s, %s, now() + make_interval(days => %s), %s) RETURNING *""",
        (codes.ma_tiep_theo(conn, "BG"), _khach_hang(conn, du_lieu), nguoi.id, sum(d["thanh_tien"] for d in dong),
         secrets.token_urlsafe(12), settings.quote_ttl_days, du_lieu.get("ghi_chu"))).fetchone()
    for d in dong:
        conn.execute(
            """INSERT INTO dong_bao_gia (bao_gia_id, bien_the_id, bo_san_pham_id, mo_ta, so_luong, don_gia_chup,
                                         kieu_cong_thuc, tham_so, thanh_tien)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (bg["id"], d["bien_the_id"], d["bo_san_pham_id"], d["mo_ta"], d["so_luong"], d["don_gia_ban"],
             d["kieu_cong_thuc"], Jsonb(d["tham_so"]), d["thanh_tien"]))
    audit.ghi(conn, nguoi, "TAO_BAO_GIA", "BAO_GIA", bg["ma"], sau={"tong_tien": bg["tong_tien"]})
    return lay_bao_gia(conn, bg["id"])


def lay_bao_gia(conn, bao_gia_id: int | None = None, ma_chia_se: str | None = None) -> dict:
    cot, gia_tri = ("bg.id", bao_gia_id) if bao_gia_id else ("bg.ma_chia_se", ma_chia_se)
    bg = conn.execute(
        f"""SELECT bg.*, kh.ten AS ten_khach, tk.ho_ten AS nguoi_lap, bg.het_han_luc < now() AS da_het_han
            FROM bao_gia bg LEFT JOIN khach_hang kh ON kh.id = bg.khach_hang_id
            JOIN tai_khoan tk ON tk.id = bg.nguoi_lap_id WHERE {cot} = %s""", (gia_tri,)).fetchone()
    if not bg:
        raise khong_tim_thay("báo giá")
    bg["dong"] = conn.execute("SELECT mo_ta, so_luong, don_gia_chup, thanh_tien, kieu_cong_thuc, tham_so, bien_the_id, "
                              "bo_san_pham_id FROM dong_bao_gia WHERE bao_gia_id = %s ORDER BY id",
                              (bg["id"],)).fetchall()
    return bg


def bao_gia_cong_khai(conn, ma_chia_se: str) -> dict:
    bg = lay_bao_gia(conn, ma_chia_se=ma_chia_se)
    if bg["da_het_han"]:
        raise LoiNghiepVu("BAO_GIA_HET_HAN", "Báo giá đã hết hạn", 410)
    return {"ma": bg["ma"], "ten_khach": bg["ten_khach"], "nguoi_lap": bg["nguoi_lap"], "tao_luc": bg["tao_luc"],
            "het_han_luc": bg["het_han_luc"], "tong_tien": bg["tong_tien"], "ghi_chu": bg["ghi_chu"],
            "dong": [{"mo_ta": d["mo_ta"], "so_luong": d["so_luong"], "don_gia": d["don_gia_chup"],
                      "thanh_tien": d["thanh_tien"], "dien_giai": (d["tham_so"] or {}).get("dien_giai")}
                     for d in bg["dong"]],
            "cua_hang": {"ten": "Cửa hàng Nội thất gỗ Khanh Vân", "dia_chi": "TP. Thái Nguyên"}}


def tao_don_tu_bao_gia(conn, nguoi: NguoiDung, bao_gia_id: int, idempotency_key: str | None = None) -> dict:
    bg = lay_bao_gia(conn, bao_gia_id)
    if bg["da_het_han"]:
        raise LoiNghiepVu("BAO_GIA_HET_HAN", "Báo giá đã quá 7 ngày, cần lập báo giá mới", 410)
    nguoi_lap = conn.execute("SELECT vai_tro FROM tai_khoan WHERE id = %s", (bg["nguoi_lap_id"],)).fetchone()
    dong = [{"bien_the_id": d["bien_the_id"], "bo_san_pham_id": d["bo_san_pham_id"], "so_luong": d["so_luong"],
             "don_gia_ban": d["don_gia_chup"], "kich_thuoc": (d["tham_so"] or {}).get("nhap")} for d in bg["dong"]]
    return tao_don(conn, nguoi, {"dong": dong, "khach_hang_id": bg["khach_hang_id"], "bao_gia_id": bg["id"],
                                 "idempotency_key": idempotency_key},
                   duoc_duyet_san=nguoi_lap["vai_tro"] == "CHU")
