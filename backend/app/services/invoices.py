"""Hàng đợi hóa đơn điện tử nằm ngoài đường găng bán hàng (Retry Queue).

Đơn được chốt và giao hàng ngay; dòng hoa_don_dt ở trạng thái CHO_XUAT được ghi cùng
giao dịch chốt đơn. Worker lấy từng dòng (FOR UPDATE SKIP LOCKED) gửi cổng HĐĐT,
lỗi tạm thời thì hẹn thử lại với khoảng chờ tăng dần 1, 2, 4 ... tối đa 60 phút.
"""
import csv
import io
import json
from datetime import timedelta

from ..adapters import einvoice
from ..adapters.storage import lay_storage
from ..config import settings
from ..errors import LoiNghiepVu, khong_tim_thay
from ..security import NguoiDung
from . import audit, events
from .audit import HE_THONG


def khoang_cho_thu_lai(so_lan_thu: int) -> timedelta:
    return timedelta(seconds=min(60 * 2 ** max(0, so_lan_thu - 1), 3600))


def _yeu_cau(conn, hd: dict) -> einvoice.YeuCauHoaDon:
    don = conn.execute("SELECT * FROM don_hang WHERE id = %s", (hd["don_hang_id"],)).fetchone()
    dong = conn.execute(
        """SELECT d.mo_ta, d.so_luong, d.don_gia_ban, d.thanh_tien,
                  COALESCE(l.don_vi_tinh, CASE WHEN d.bo_san_pham_id IS NOT NULL THEN 'bộ' ELSE 'cái' END) AS dvt
           FROM dong_don d LEFT JOIN bien_the bt ON bt.id = d.bien_the_id
           LEFT JOIN mau_hang m ON m.id = bt.mau_hang_id LEFT JOIN loai_hang l ON l.id = m.loai_hang_id
           WHERE d.don_hang_id = %s ORDER BY d.id""", (hd["don_hang_id"],)).fetchall()
    phuong_thuc = conn.execute(
        "SELECT string_agg(DISTINCT phuong_thuc, ',') AS pt FROM thanh_toan WHERE don_hang_id = %s",
        (hd["don_hang_id"],)).fetchone()["pt"] or ""
    return einvoice.YeuCauHoaDon(
        hoa_don_id=hd["id"], ma_don=don["ma"], ten_nguoi_mua=hd["ten_nguoi_mua"], ma_so_thue=hd["ma_so_thue"],
        dia_chi=hd["dia_chi"], email=hd["email"],
        phuong_thuc_tt="TM/CK" if "," in phuong_thuc else ("TM" if phuong_thuc == "TIEN_MAT" else "CK"),
        dong=[einvoice.DongHoaDon(d["mo_ta"], d["dvt"], d["so_luong"], d["don_gia_ban"], d["thanh_tien"]) for d in dong],
        tong_tien=don["tong_tien"] - don["giam_tru"])


def xu_ly_mot(conn, adapter: einvoice.EInvoiceAdapter | None = None) -> dict | None:
    """Gửi một hóa đơn đến hạn. Trả về dòng sau xử lý, None nếu hàng đợi trống."""
    hd = conn.execute(
        """SELECT * FROM hoa_don_dt WHERE trang_thai = 'CHO_XUAT' AND lan_thu_tiep <= now()
           ORDER BY lan_thu_tiep, id LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
    if not hd:
        return None
    adapter = adapter or einvoice.lay_adapter(hd["nha_cung_cap_hddt"])
    so_lan = hd["so_lan_thu"] + 1
    try:
        kq = adapter.phat_hanh(_yeu_cau(conn, hd))
    except einvoice.LoiTamThoi as e:
        het_luot = so_lan >= settings.einvoice_max_retries
        moi = conn.execute(
            """UPDATE hoa_don_dt SET so_lan_thu = %s, loi_cuoi = %s, trang_thai = %s, lan_thu_tiep = now() + %s
               WHERE id = %s RETURNING *""",
            (so_lan, str(e), "LOI" if het_luot else "CHO_XUAT", khoang_cho_thu_lai(so_lan), hd["id"])).fetchone()
        if het_luot:
            _bao_loi(conn, moi, f"Đã thử {so_lan} lần không thành công: {e}")
        return moi
    except einvoice.LoiVinhVien as e:
        moi = conn.execute("UPDATE hoa_don_dt SET so_lan_thu = %s, loi_cuoi = %s, trang_thai = 'LOI' WHERE id = %s "
                           "RETURNING *", (so_lan, str(e), hd["id"])).fetchone()
        _bao_loi(conn, moi, str(e))
        return moi

    link_xml = kq.link_xml
    if kq.xml and not link_xml:
        link_xml = lay_storage().luu(f"hoa-don/{hd['id']}-{kq.so_hoa_don}.xml", kq.xml.encode("utf-8"),
                                     "application/xml")
    moi = conn.execute(
        """UPDATE hoa_don_dt SET trang_thai = 'DA_XUAT', ky_hieu = %s, so_hoa_don = %s, link_pdf = %s, link_xml = %s,
                  so_lan_thu = %s, loi_cuoi = NULL, xuat_luc = now()
           WHERE id = %s RETURNING *""",
        (kq.ky_hieu, kq.so_hoa_don, kq.link_pdf, link_xml, so_lan, hd["id"])).fetchone()
    ma_don = conn.execute("SELECT ma FROM don_hang WHERE id = %s", (hd["don_hang_id"],)).fetchone()["ma"]
    audit.ghi(conn, HE_THONG, "XUAT_HDDT", "HOA_DON_DT", hd["id"],
              sau={"don": ma_don, "ky_hieu": kq.ky_hieu, "so_hoa_don": kq.so_hoa_don, "so_lan_thu": so_lan})
    events.phat(conn, "HDDT_DA_XUAT", {"hoa_don_id": hd["id"], "ma_don": ma_don, "so_hoa_don": kq.so_hoa_don})
    return moi


def _bao_loi(conn, hd: dict, ly_do: str) -> None:
    events.phat(conn, "HDDT_LOI", {"hoa_don_id": hd["id"], "ly_do": ly_do}, vai_tro=["CHU"])
    events.xep_hang_thong_bao(conn, "ZALO", settings.notify_owner_phone, "Hóa đơn điện tử cần xử lý", ly_do)


def cap_nhat_nguoi_mua(conn, nguoi: NguoiDung, hd_id: int, du_lieu: dict) -> dict:
    hd = conn.execute("SELECT * FROM hoa_don_dt WHERE id = %s FOR UPDATE", (hd_id,)).fetchone()
    if not hd:
        raise khong_tim_thay("hóa đơn")
    if hd["trang_thai"] == "DA_XUAT":
        raise LoiNghiepVu("DA_XUAT", "Hóa đơn đã phát hành, không sửa thông tin người mua", 409)
    mst = (du_lieu.get("ma_so_thue") or "").strip() or None
    if mst and not mst.replace("-", "").isdigit():
        raise LoiNghiepVu("MST_KHONG_HOP_LE", "Mã số thuế chỉ gồm chữ số (10 hoặc 13 số)")
    moi = conn.execute(
        """UPDATE hoa_don_dt SET ten_nguoi_mua = COALESCE(%s, ten_nguoi_mua), ma_so_thue = COALESCE(%s, ma_so_thue),
                  dia_chi = COALESCE(%s, dia_chi), email = COALESCE(%s, email),
                  trang_thai = 'CHO_XUAT', so_lan_thu = 0, lan_thu_tiep = now(), loi_cuoi = NULL
           WHERE id = %s RETURNING *""",
        (du_lieu.get("ten_nguoi_mua"), mst, du_lieu.get("dia_chi"), du_lieu.get("email"), hd_id)).fetchone()
    conn.execute("UPDATE don_hang SET can_hoa_don = TRUE WHERE id = %s", (hd["don_hang_id"],))
    audit.ghi(conn, nguoi, "CAP_NHAT_NGUOI_MUA_HDDT", "HOA_DON_DT", hd_id,
              truoc={k: hd[k] for k in ("ten_nguoi_mua", "ma_so_thue", "trang_thai")},
              sau={k: moi[k] for k in ("ten_nguoi_mua", "ma_so_thue", "trang_thai")})
    return moi


def thu_lai(conn, nguoi: NguoiDung, hd_id: int) -> dict:
    moi = conn.execute("""UPDATE hoa_don_dt SET trang_thai = 'CHO_XUAT', so_lan_thu = 0, lan_thu_tiep = now()
                          WHERE id = %s AND trang_thai = 'LOI' RETURNING *""", (hd_id,)).fetchone()
    if not moi:
        raise LoiNghiepVu("KHONG_THU_LAI_DUOC", "Chỉ thử lại hóa đơn đang lỗi", 409)
    audit.ghi(conn, nguoi, "THU_LAI_HDDT", "HOA_DON_DT", hd_id)
    return moi


def ghi_so_thu_cong(conn, nguoi: NguoiDung, hd_id: int, ky_hieu: str, so_hoa_don: str) -> dict:
    """Chủ đã tự xuất hóa đơn trên cổng của nhà cung cấp, chỉ ghi lại số."""
    moi = conn.execute(
        """UPDATE hoa_don_dt SET trang_thai = 'DA_XUAT', ky_hieu = %s, so_hoa_don = %s, xuat_luc = now(),
                  nha_cung_cap_hddt = nha_cung_cap_hddt || '/THU_CONG'
           WHERE id = %s AND trang_thai <> 'DA_XUAT' RETURNING *""", (ky_hieu, so_hoa_don, hd_id)).fetchone()
    if not moi:
        raise LoiNghiepVu("KHONG_GHI_DUOC", "Hóa đơn không tồn tại hoặc đã phát hành", 409)
    audit.ghi(conn, nguoi, "GHI_SO_HDDT_THU_CONG", "HOA_DON_DT", hd_id, sau={"ky_hieu": ky_hieu, "so": so_hoa_don})
    return moi


def danh_sach(conn, trang_thai: str | None = None) -> list[dict]:
    dieu_kien = "WHERE hd.trang_thai = %s" if trang_thai else "WHERE hd.trang_thai <> 'CHUA_CAN'"
    return conn.execute(
        f"""SELECT hd.*, dh.ma AS ma_don, dh.tong_tien - dh.giam_tru AS tong_tien
            FROM hoa_don_dt hd JOIN don_hang dh ON dh.id = hd.don_hang_id
            {dieu_kien} ORDER BY hd.tao_luc DESC LIMIT 200""", (trang_thai,) if trang_thai else ()).fetchall()


def goi_du_lieu(conn, dinh_dang: str = "csv") -> tuple[str, str]:
    """Gói dữ liệu hóa đơn chờ xuất để nhập tay vào phần mềm HĐĐT (CSV hoặc JSON)."""
    rows = conn.execute(
        """SELECT dh.ma AS ma_don, hd.ten_nguoi_mua, hd.ma_so_thue, hd.dia_chi, hd.email,
                  d.mo_ta, d.so_luong, d.don_gia_ban, d.thanh_tien
           FROM hoa_don_dt hd JOIN don_hang dh ON dh.id = hd.don_hang_id
           JOIN dong_don d ON d.don_hang_id = dh.id
           WHERE hd.trang_thai IN ('CHO_XUAT', 'LOI') ORDER BY dh.ma, d.id""").fetchall()
    if dinh_dang == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2, default=str), "application/json"
    buf = io.StringIO()
    buf.write("﻿")  # BOM để Excel mở đúng tiếng Việt
    w = csv.DictWriter(buf, fieldnames=["ma_don", "ten_nguoi_mua", "ma_so_thue", "dia_chi", "email", "mo_ta",
                                        "so_luong", "don_gia_ban", "thanh_tien"])
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue(), "text/csv; charset=utf-8"
