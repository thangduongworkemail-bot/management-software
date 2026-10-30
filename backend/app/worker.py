"""Tiến trình nền (Retry Worker), chạy riêng với API:

    python -m app.worker            # chạy liên tục
    python -m app.worker --mot-lan  # chạy mỗi tác vụ một lần rồi thoát

Tác vụ: gửi HĐĐT trong hàng đợi (thử lại khi lỗi), nhả giữ chỗ hết hạn TTL 30 phút,
gửi thông báo, cảnh báo Máy nhận tiền mất báo sống, kiểm tra toàn vẹn dữ liệu hằng đêm.
"""
import argparse
import logging
import signal
import time
from datetime import datetime, timedelta

from . import db
from .adapters import notify
from .config import settings
from .services import audit, events, invoices, orders

log = logging.getLogger("khanhvan.worker")


def xu_ly_hddt(toi_da: int = 20) -> int:
    so = 0
    for _ in range(toi_da):
        with db.transaction() as conn:
            kq = invoices.xu_ly_mot(conn)
        if kq is None:
            break
        so += 1
        log.info("HĐĐT #%s -> %s (lần %s)%s", kq["id"], kq["trang_thai"], kq["so_lan_thu"],
                 f": {kq['loi_cuoi']}" if kq["loi_cuoi"] else "")
    return so


def nha_giu_cho() -> list[str]:
    with db.transaction() as conn:
        ma = orders.nha_giu_cho_het_han(conn)
    if ma:
        log.info("Nhả giữ chỗ hết hạn: %s", ", ".join(ma))
    return ma


def gui_thong_bao(toi_da: int = 20) -> int:
    so = 0
    with db.transaction() as conn:
        hang = conn.execute(
            """SELECT * FROM thong_bao WHERE trang_thai = 'CHO_GUI' AND lan_thu_tiep <= now()
               ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED""", (toi_da,)).fetchall()
        for tb in hang:
            try:
                notify.gui(tb["kenh"], tb["nguoi_nhan"], tb["tieu_de"], tb["noi_dung"])
                conn.execute("UPDATE thong_bao SET trang_thai = 'DA_GUI', so_lan_thu = so_lan_thu + 1 WHERE id = %s",
                             (tb["id"],))
                so += 1
            except Exception as e:
                lan = tb["so_lan_thu"] + 1
                conn.execute(
                    """UPDATE thong_bao SET so_lan_thu = %s, loi_cuoi = %s, trang_thai = %s,
                              lan_thu_tiep = now() + %s WHERE id = %s""",
                    (lan, str(e)[:500], "LOI" if lan >= 5 else "CHO_GUI", invoices.khoang_cho_thu_lai(lan), tb["id"]))
    return so


def kiem_tra_bao_song() -> list[str]:
    with db.transaction() as conn:
        mat = conn.execute(
            """SELECT id, ten FROM thiet_bi WHERE loai = 'MAY_NHAN_TIEN' AND trang_thai = 'HOAT_DONG'
               AND lan_bao_song < now() - make_interval(mins => %s)""", (settings.heartbeat_warn_minutes,)).fetchall()
        for tb in mat:
            tieu_de = f"Máy nhận tiền '{tb['ten']}' mất kết nối"
            da_bao = conn.execute("SELECT 1 FROM thong_bao WHERE tieu_de = %s AND tao_luc > now() - interval '1 hour'",
                                  (tieu_de,)).fetchone()
            if not da_bao:
                events.xep_hang_thong_bao(conn, "ZALO", settings.notify_owner_phone, tieu_de,
                                          "Kiểm tra mạng và pin điện thoại. Trong lúc chờ, cứ bán và xác nhận tay.")
                events.phat(conn, "MAY_NHAN_TIEN_MAT_KET_NOI", {"thiet_bi_id": tb["id"], "ten": tb["ten"]},
                            vai_tro=["CHU"])
    return [t["ten"] for t in mat]


def kiem_tra_toan_ven() -> dict:
    """Job hằng đêm: chuỗi băm nhật ký, sổ cái không âm, tiền đã thu khớp các khoản thu, công nợ khớp."""
    with db.transaction() as conn:
        loi_chuoi = audit.kiem_tra_chuoi(conn)
        ton_am = conn.execute(
            """SELECT bien_the_id, ton_hien_co, dang_giu_cho, ton_kha_dung FROM v_ton_kho
               WHERE ton_hien_co < 0 OR dang_giu_cho < 0 OR ton_kha_dung < 0""").fetchall()
        lech_tien = conn.execute(
            """SELECT dh.ma, dh.da_thu, COALESCE(sum(tt.so_tien), 0)::bigint AS tong_khoan_thu
               FROM don_hang dh LEFT JOIN thanh_toan tt ON tt.don_hang_id = dh.id
               GROUP BY dh.id HAVING dh.da_thu <> COALESCE(sum(tt.so_tien), 0)""").fetchall()
        chua_xuat = conn.execute(
            """SELECT DISTINCT dh.ma FROM don_hang dh JOIN dong_don d ON d.don_hang_id = dh.id
               WHERE dh.trang_thai = 'DA_THANH_TOAN' AND dh.trang_thai_giao = 'DA_GIAO'
                 AND NOT d.dat_rieng AND NOT d.da_xuat""").fetchall()
        lech_no = conn.execute(
            """SELECT kh.id, kh.du_no, COALESCE(sum(dh.tong_tien - dh.giam_tru - dh.da_thu)
                      FILTER (WHERE dh.trang_thai = 'CON_NO'), 0)::bigint AS tinh_lai
               FROM khach_hang kh LEFT JOIN don_hang dh ON dh.khach_hang_id = kh.id
               GROUP BY kh.id HAVING kh.du_no <> COALESCE(sum(dh.tong_tien - dh.giam_tru - dh.da_thu)
                      FILTER (WHERE dh.trang_thai = 'CON_NO'), 0)""").fetchall()
        ket_qua = {"chuoi_nhat_ky": loi_chuoi, "ton_am": ton_am, "lech_tien_da_thu": lech_tien,
                   "don_giao_chua_xuat_kho": chua_xuat, "lech_cong_no_khach": lech_no}
        ket_qua["toan_ven"] = not any(ket_qua.values())
        audit.ghi(conn, None, "KIEM_TRA_TOAN_VEN", "HE_THONG", datetime.now().date().isoformat(), sau=ket_qua)
        if not ket_qua["toan_ven"]:
            events.xep_hang_thong_bao(conn, "ZALO", settings.notify_owner_phone, "Cảnh báo toàn vẹn dữ liệu",
                                      "Job kiểm tra đêm phát hiện sai lệch, xem Nhật ký hệ thống.")
    log.info("Kiểm tra toàn vẹn: %s", "OK" if ket_qua["toan_ven"] else ket_qua)
    return ket_qua


def den_gio_kiem_tra_dem() -> bool:
    if datetime.now().hour < settings.integrity_check_hour:
        return False
    with db.transaction() as conn:
        return not conn.execute("SELECT 1 FROM nhat_ky WHERE hanh_dong = 'KIEM_TRA_TOAN_VEN' "
                                "AND thoi_diem::date = current_date").fetchone()


LICH = [  # (chu kỳ giây, tác vụ)
    (5, xu_ly_hddt),
    (15, nha_giu_cho),
    (10, gui_thong_bao),
    (60, kiem_tra_bao_song),
    (300, lambda: den_gio_kiem_tra_dem() and kiem_tra_toan_ven()),
]


def chay(mot_lan: bool = False) -> None:
    dung = {"co": False}

    def tat(*_):
        dung["co"] = True
    signal.signal(signal.SIGINT, tat)
    signal.signal(signal.SIGTERM, tat)

    lan_chay = {i: datetime.min for i in range(len(LICH))}
    log.info("Worker khởi động (HĐĐT: %s)", settings.einvoice_provider)
    while not dung["co"]:
        for i, (chu_ky, tac_vu) in enumerate(LICH):
            if mot_lan or datetime.now() - lan_chay[i] >= timedelta(seconds=chu_ky):
                try:
                    tac_vu()
                except Exception:
                    log.exception("Tác vụ %s lỗi", getattr(tac_vu, "__name__", i))
                lan_chay[i] = datetime.now()
        if mot_lan:
            break
        time.sleep(1)
    db.close_pool()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--mot-lan", action="store_true", help="chạy mỗi tác vụ một lần rồi thoát")
    p.add_argument("--kiem-tra-toan-ven", action="store_true", help="chạy ngay job kiểm tra toàn vẹn")
    a = p.parse_args()
    if a.kiem_tra_toan_ven:
        kiem_tra_toan_ven()
    else:
        chay(a.mot_lan)
