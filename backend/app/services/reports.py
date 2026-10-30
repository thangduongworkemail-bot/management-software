"""Số liệu Tổng quan (CN 4.1, 4.2) và Trung tâm sự cố (CN 9.1)."""
from ..config import settings
from ..security import NguoiDung
from . import inventory, orders


def tong_quan(conn, nguoi: NguoiDung) -> dict:
    hom_nay = conn.execute(
        """SELECT COALESCE(sum(tt.so_tien), 0)::bigint AS doanh_thu,
                  count(DISTINCT tt.don_hang_id)::int AS so_don
           FROM thanh_toan tt WHERE tt.thoi_diem::date = current_date""").fetchone()
    theo_ngay = conn.execute(
        """SELECT d::date AS ngay, COALESCE(sum(tt.so_tien), 0)::bigint AS doanh_thu
           FROM generate_series(current_date - 13, current_date, interval '1 day') d
           LEFT JOIN thanh_toan tt ON tt.thoi_diem::date = d::date
           GROUP BY d ORDER BY d""").fetchall()
    thang = conn.execute(
        """SELECT COALESCE(sum(so_tien), 0)::bigint AS doanh_thu FROM thanh_toan
           WHERE date_trunc('month', thoi_diem) = date_trunc('month', now())""").fetchone()
    giu_cho = conn.execute(
        """SELECT id, ma, tong_tien, giu_cho_den FROM don_hang
           WHERE trang_thai = 'CHO_THANH_TOAN' ORDER BY tao_luc DESC""").fetchall()
    kq = {
        "doanh_thu_hom_nay": hom_nay["doanh_thu"],
        "so_don_thu_tien_hom_nay": hom_nay["so_don"],
        "doanh_thu_thang": thang["doanh_thu"],
        "doanh_thu_theo_ngay": theo_ngay,
        "don_cho_thanh_toan": giu_cho,
        "tra_hang_hom_nay": conn.execute(
            "SELECT count(DISTINCT don_hang_id)::int AS n FROM so_cai_ton WHERE loai = 'TRA_HANG' "
            "AND thoi_diem::date = current_date").fetchone()["n"],
        "ton_theo_xuong": inventory.ton_theo_xuong(conn),
        "sap_het": inventory.sap_het(conn),
        "hddt_cho_xuat": conn.execute("SELECT count(*)::int AS n FROM hoa_don_dt WHERE trang_thai = 'CHO_XUAT'")
                             .fetchone()["n"],
        "hddt_loi": conn.execute("SELECT count(*)::int AS n FROM hoa_don_dt WHERE trang_thai = 'LOI'").fetchone()["n"],
    }
    if nguoi.xem_gia_von:
        kq["yeu_cau_cho_duyet"] = orders.yeu_cau_cho_duyet(conn)
        kq["can_doi_soat"] = conn.execute(
            "SELECT count(*)::int AS n FROM thanh_toan WHERE xac_nhan_tay AND NOT da_doi_soat").fetchone()["n"]
        kq["giao_dich_chua_khop"] = conn.execute(
            "SELECT count(*)::int AS n FROM giao_dich_nh WHERE trang_thai IN ('CHUA_KHOP', 'LECH_TIEN')").fetchone()["n"]
        kq["nhat_ky_gan_day"] = conn.execute(
            "SELECT id, thoi_diem, ten_nguoi_thuc_hien, hanh_dong, thuc_the, thuc_the_id FROM nhat_ky "
            "ORDER BY id DESC LIMIT 8").fetchall()
        kq["loi_nhuan_gop_thang"] = conn.execute(
            """SELECT COALESCE(sum(d.thanh_tien - d.gia_von_chup * d.so_luong), 0)::bigint AS n
               FROM dong_don d JOIN don_hang dh ON dh.id = d.don_hang_id
               WHERE dh.trang_thai = 'DA_THANH_TOAN'
                 AND date_trunc('month', dh.cap_nhat_luc) = date_trunc('month', now())""").fetchone()["n"]
    return kq


def trang_thai_he_thong(conn) -> dict:
    may_nhan_tien = conn.execute(
        """SELECT id, ten, lan_bao_song,
                  EXTRACT(EPOCH FROM now() - lan_bao_song)::int / 60 AS so_phut_chua_bao
           FROM thiet_bi WHERE loai = 'MAY_NHAN_TIEN' AND trang_thai = 'HOAT_DONG'
           ORDER BY lan_bao_song DESC NULLS LAST""").fetchall()
    kiem_tra = conn.execute(
        """SELECT thoi_diem, du_lieu_sau FROM nhat_ky WHERE hanh_dong = 'KIEM_TRA_TOAN_VEN'
           ORDER BY id DESC LIMIT 1""").fetchone()
    return {
        "co_so_du_lieu": "TOT",
        "may_nhan_tien": may_nhan_tien,
        "may_nhan_tien_canh_bao": any(m["so_phut_chua_bao"] is None or m["so_phut_chua_bao"] >= settings.heartbeat_warn_minutes
                                      for m in may_nhan_tien) or not may_nhan_tien,
        "hddt": conn.execute(
            """SELECT count(*) FILTER (WHERE trang_thai = 'CHO_XUAT')::int AS cho_xuat,
                      count(*) FILTER (WHERE trang_thai = 'LOI')::int AS loi,
                      max(xuat_luc) AS lan_xuat_cuoi FROM hoa_don_dt""").fetchone(),
        "thong_bao_cho_gui": conn.execute(
            "SELECT count(*)::int AS n FROM thong_bao WHERE trang_thai = 'CHO_GUI'").fetchone()["n"],
        "kiem_tra_toan_ven_cuoi": kiem_tra,
        "huong_dan": [
            "1. Mở app Khanh Vân trên điện thoại của Chủ.",
            "2. Kiểm tra mạng và pin điện thoại.",
            "3. Chưa được? Cứ bán bình thường và bấm xác nhận tay.",
        ],
    }
