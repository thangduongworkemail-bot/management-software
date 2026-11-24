"""Retry Worker: hàng đợi HĐĐT được xử lý và cam kết, thông báo gửi lỗi được hẹn thử lại, vòng lặp chạy đủ tác vụ,
job kiểm tra toàn vẹn chạy được trên CSDL test sau khi các bộ test khác đã ghi dữ liệu.

Worker tự mở giao dịch và COMMIT vào khanhvan_test (giống test_api). Theo thứ tự tên file, bộ này chạy sau cùng.
Việc gửi thật ra ngoài (Zalo/Email, Web Push) được thay bằng hàm giả.
"""
import logging

import pytest

from app import db, worker
from app.services import events


def _mot(sql: str, *thamso):
    with db.transaction() as conn:
        return conn.execute(sql, thamso).fetchone()


@pytest.fixture
def khong_gui_ra_ngoai(monkeypatch):
    da_gui = []
    monkeypatch.setattr(worker.notify, "gui", lambda kenh, nguoi_nhan, tieu_de, noi_dung: da_gui.append((kenh, tieu_de)))
    monkeypatch.setattr(worker.day, "gui_thong_bao", lambda conn, tb: da_gui.append(("PUSH", tb["tieu_de"])))
    return da_gui


def test_worker_xuat_het_hang_doi_hddt(csdl):
    dem = "SELECT count(*) AS n FROM hoa_don_dt WHERE trang_thai = 'CHO_XUAT' AND lan_thu_tiep <= now()"
    cho = _mot(dem)["n"]
    assert cho >= 1   # dữ liệu mẫu: đơn #KV261026001 đã thu đủ, đang chờ xuất HĐĐT
    assert worker.xu_ly_hddt() == cho
    assert _mot(dem)["n"] == 0
    hd = _mot("SELECT hd.* FROM hoa_don_dt hd JOIN don_hang dh ON dh.id = hd.don_hang_id WHERE dh.ma = 'KV261026001'")
    assert hd["trang_thai"] == "DA_XUAT" and hd["so_hoa_don"] and hd["so_lan_thu"] == 1


def test_thong_bao_gui_loi_duoc_hen_thu_lai_roi_gui_duoc(csdl, monkeypatch, khong_gui_ra_ngoai):
    with db.transaction() as conn:
        events.xep_hang_thong_bao(conn, "ZALO", "0900000000", "Thử worker gửi lại", "nội dung thử")

    def zalo_hong(*_):
        raise RuntimeError("Zalo OA không phản hồi")
    monkeypatch.setattr(worker.notify, "gui", zalo_hong)
    worker.gui_thong_bao(toi_da=1000)
    tb = _mot("SELECT *, lan_thu_tiep > now() AS hen_sau FROM thong_bao WHERE tieu_de = 'Thử worker gửi lại'")
    assert (tb["trang_thai"], tb["so_lan_thu"], tb["hen_sau"]) == ("CHO_GUI", 1, True)
    assert "Zalo OA không phản hồi" in tb["loi_cuoi"]

    # Đến hạn thử lại và kênh gửi đã chạy lại
    monkeypatch.setattr(worker.notify, "gui", lambda *a: None)
    with db.transaction() as conn:
        conn.execute("UPDATE thong_bao SET lan_thu_tiep = now() WHERE id = %s", (tb["id"],))
    worker.gui_thong_bao(toi_da=1000)
    tb = _mot("SELECT * FROM thong_bao WHERE id = %s", tb["id"])
    assert (tb["trang_thai"], tb["so_lan_thu"]) == ("DA_GUI", 2)


def test_chay_mot_lan_khong_tac_vu_nao_loi(csdl, monkeypatch, caplog, khong_gui_ra_ngoai):
    monkeypatch.setattr(worker.signal, "signal", lambda *a: None)   # không đổi xử lý Ctrl+C của pytest
    caplog.set_level(logging.INFO, logger="khanhvan.worker")
    worker.chay(mot_lan=True)
    loi = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert not loi, loi
    assert any("Worker khởi động" in r.getMessage() for r in caplog.records)


def test_kiem_tra_toan_ven_sau_khi_cac_bo_test_da_ghi(csdl):
    kq = worker.kiem_tra_toan_ven()
    assert kq["toan_ven"], kq
    assert _mot("SELECT count(*) AS n FROM nhat_ky WHERE hanh_dong = 'KIEM_TRA_TOAN_VEN'")["n"] >= 1
