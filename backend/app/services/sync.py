"""Đồng bộ cho PWA offline-first: tải danh mục về IndexedDB và đẩy lên đơn lập lúc mất mạng."""
import uuid
from datetime import datetime

import psycopg

from ..errors import LoiNghiepVu
from ..security import NguoiDung
from . import catalog, orders, payments


def danh_muc(conn, nguoi: NguoiDung) -> dict:
    return {
        "thoi_diem": datetime.now().astimezone(),
        "hang_hoa": catalog.danh_sach(conn, nguoi),
        "cong_thuc": conn.execute(
            """SELECT ct.bien_the_id, ct.kieu, ct.don_gia, ct.phu_phi, ct.bac_gia, ct.kich_thuoc_min_mm,
                      ct.kich_thuoc_max_mm, bt.loai_go, COALESCE(h.he_so_phan_nghin, 1000) AS he_so_phan_nghin
               FROM cong_thuc_gia ct JOIN bien_the bt ON bt.id = ct.bien_the_id
               LEFT JOIN he_so_go h ON h.loai_go = bt.loai_go""").fetchall(),
        "tu_dong_nghia": conn.execute("SELECT tu_khoa_cn, tu_chuan_cn FROM tu_dong_nghia").fetchall(),
        "loai_hang": catalog.loai_hang(conn),
    }


def day_don_ngoai_tuyen(conn_factory, nguoi: NguoiDung, danh_sach: list[dict]) -> list[dict]:
    """Mỗi đơn đồng bộ trong giao dịch riêng: một đơn lỗi không làm hỏng cả lô."""
    ket_qua = []
    for don in danh_sach:
        key = don.get("idempotency_key")
        try:
            uuid.UUID(str(key))
        except (ValueError, TypeError):
            ket_qua.append({"idempotency_key": key, "ok": False, "loi": "THIEU_IDEMPOTENCY_KEY"})
            continue
        try:
            with conn_factory() as conn:
                kq = orders.tao_don(conn, nguoi, {**don, "idempotency_key": str(key)}, kenh="NGOAI_TUYEN")
                tt = don.get("thanh_toan")
                if tt and not kq.get("trung_lap") and kq["con_phai_thu"] > 0:
                    payments.ghi_nhan_thanh_toan(conn, nguoi, kq["id"], int(tt["so_tien"]),
                                                 tt.get("phuong_thuc", "TIEN_MAT"), la_coc=bool(tt.get("la_coc")))
                    kq = orders.lay_don(conn, kq["id"], nguoi)
            ket_qua.append({"idempotency_key": key, "ok": True, "trung_lap": bool(kq.get("trung_lap")),
                            "don_id": kq["id"], "ma": kq["ma"], "trang_thai": kq["trang_thai"],
                            "trang_thai_giao": kq["trang_thai_giao"]})
        except LoiNghiepVu as e:
            ket_qua.append({"idempotency_key": key, "ok": False, "loi": e.ma, "thong_bao": e.thong_bao})
        except psycopg.Error as e:
            ket_qua.append({"idempotency_key": key, "ok": False, "loi": f"CSDL_{e.sqlstate}",
                            "thong_bao": e.diag.message_primary})
    return ket_qua
