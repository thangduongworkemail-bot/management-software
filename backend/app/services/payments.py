"""Thu tiền, xác nhận tay, nhận giao dịch ngân hàng (webhook / Máy nhận tiền) và đối soát."""
import re
from datetime import date

from ..adapters.payment import GiaoDichVao
from ..config import settings
from ..errors import LoiNghiepVu
from ..security import NguoiDung, sha256_hex
from . import audit, events, orders
from .audit import HE_THONG

_RE_MA_DON = re.compile(r"KV\d{9}")


def ghi_nhan_thanh_toan(conn, nguoi: NguoiDung, don_id: int, so_tien: int, phuong_thuc: str, *,
                        la_coc: bool = False, xac_nhan_tay: bool = False, giao_dich_id: int | None = None,
                        bang_chung: list[tuple[str, str]] | None = None) -> dict:
    if so_tien is None or int(so_tien) <= 0:
        raise LoiNghiepVu("SO_TIEN_KHONG_HOP_LE", "Số tiền phải lớn hơn 0")
    if phuong_thuc not in ("TIEN_MAT", "CHUYEN_KHOAN"):
        raise LoiNghiepVu("PHUONG_THUC_KHONG_HOP_LE", "Phương thức phải là TIEN_MAT hoặc CHUYEN_KHOAN")
    so_tien = int(so_tien)
    don = orders.khoa_don(conn, don_id)
    if don["trang_thai"] == "DA_HUY":
        raise LoiNghiepVu("DON_DA_HUY", "Đơn đã hủy, không thu tiền", 409)
    if don["trang_thai"] == "DA_THANH_TOAN" or orders.con_phai_thu(don) == 0:
        raise LoiNghiepVu("DA_THU_DU", "Đơn đã thu đủ tiền", 409)
    if don["trang_thai"] == "HET_HAN":
        orders.giu_cho_lai(conn, nguoi, don)
        don = orders.khoa_don(conn, don_id)

    can_thu = orders.con_phai_thu(don)
    # Tiền mặt: chỉ ghi phần cần thu, phần dư là tiền thối lại. Chuyển khoản: ghi đúng số tiền về.
    ghi = min(so_tien, can_thu) if phuong_thuc == "TIEN_MAT" else so_tien
    du = ghi >= can_thu
    loai = "THU_NO" if don["trang_thai"] == "CON_NO" else ("THANH_TOAN" if du else "COC")
    tt = conn.execute(
        """INSERT INTO thanh_toan (don_hang_id, loai, phuong_thuc, so_tien, xac_nhan_tay, giao_dich_nh_id,
                                   da_doi_soat, nguoi_ghi_nhan_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (don_id, loai, phuong_thuc, ghi, xac_nhan_tay, giao_dich_id, giao_dich_id is not None,
         nguoi.id or None)).fetchone()
    for kieu, gia_tri in bang_chung or []:
        conn.execute("INSERT INTO bang_chung_tien (thanh_toan_id, kieu, gia_tri, nguoi_tao_id) VALUES (%s, %s, %s, %s)",
                     (tt["id"], kieu, gia_tri, nguoi.id or None))
    conn.execute("UPDATE don_hang SET da_thu = da_thu + %s WHERE id = %s", (ghi, don_id))
    don = orders.khoa_don(conn, don_id)

    if du and don["trang_thai"] != "CHO_DUYET_GIA":
        orders.chot_don(conn, nguoi, don)
    elif la_coc and don["trang_thai"] == "CHO_THANH_TOAN":
        conn.execute("UPDATE don_hang SET trang_thai = 'CON_NO', giu_cho_den = NULL WHERE id = %s", (don_id,))
    orders.cap_nhat_du_no(conn, don["khach_hang_id"])

    audit.ghi(conn, nguoi, "XAC_NHAN_TIEN_TAY" if xac_nhan_tay else "THU_TIEN", "DON_HANG", don["ma"],
              truoc={"da_thu": don["da_thu"] - ghi, "trang_thai": don["trang_thai"]},
              sau={"so_tien": ghi, "phuong_thuc": phuong_thuc, "loai": loai,
                   "bang_chung": [k for k, _ in bang_chung or []], "giao_dich_nh_id": giao_dich_id})
    events.phat(conn, "THANH_TOAN", {"don_id": don_id, "ma": don["ma"], "so_tien": ghi, "du": du})
    return {"thanh_toan": tt, "tien_thoi": so_tien - ghi if phuong_thuc == "TIEN_MAT" else 0,
            "don": orders.lay_don(conn, don_id, nguoi)}


def xac_nhan_tay(conn, nguoi: NguoiDung, don_id: int, so_tien: int | None = None,
                 bon_so_cuoi: str | None = None, anh_bien_lai_url: str | None = None) -> dict:
    """Chủ đã THẤY TIỀN trong app ngân hàng và bấm xác nhận; bắt buộc có bằng chứng."""
    bang_chung = []
    if bon_so_cuoi:
        if not re.fullmatch(r"\d{4}", bon_so_cuoi):
            raise LoiNghiepVu("BANG_CHUNG_KHONG_HOP_LE", "Cần đúng 4 chữ số cuối mã giao dịch")
        bang_chung.append(("BON_SO_CUOI", bon_so_cuoi))
    if anh_bien_lai_url:
        bang_chung.append(("ANH_BIEN_LAI", anh_bien_lai_url))
    if not bang_chung:
        raise LoiNghiepVu("THIEU_BANG_CHUNG", "Xác nhận tay cần 4 số cuối mã giao dịch hoặc ảnh biên lai")
    don = orders.khoa_don(conn, don_id)
    return ghi_nhan_thanh_toan(conn, nguoi, don_id, so_tien or orders.con_phai_thu(don), "CHUYEN_KHOAN",
                               xac_nhan_tay=True, bang_chung=bang_chung)


def nhan_giao_dich(conn, gd: GiaoDichVao, thiet_bi_id: int | None = None) -> dict:
    """Tiếp nhận một giao dịch tiền về. Idempotent: gửi lại cùng mã giao dịch không ghi nhận lần hai."""
    from psycopg.types.json import Jsonb
    ma_bam = sha256_hex(f"{gd.nguon}|{gd.ma_giao_dich}")
    row = conn.execute(
        """INSERT INTO giao_dich_nh (nguon, ma_giao_dich, so_tien, noi_dung, ngan_hang, thoi_diem_nh, ma_bam,
                                     thiet_bi_id, du_lieu_goc)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (ma_bam) DO NOTHING RETURNING *""",
        (gd.nguon, gd.ma_giao_dich, gd.so_tien, gd.noi_dung, gd.ngan_hang, gd.thoi_diem, ma_bam, thiet_bi_id,
         Jsonb(gd.du_lieu_goc))).fetchone()
    if not row:
        return {"ket_qua": "TRUNG_LAP"}

    def cap_nhat(trang_thai, don_id=None, ghi_chu=None):
        conn.execute("UPDATE giao_dich_nh SET trang_thai = %s, don_hang_id = %s, ghi_chu = %s WHERE id = %s",
                     (trang_thai, don_id, ghi_chu, row["id"]))

    m = _RE_MA_DON.search(re.sub(r"\s+", "", gd.noi_dung.upper()))
    don_row = conn.execute("SELECT id FROM don_hang WHERE ma = %s", (m.group(0),)).fetchone() if m else None
    if not don_row:
        cap_nhat("CHUA_KHOP", ghi_chu="Không tìm thấy mã đơn trong nội dung chuyển khoản")
        _bao_chu(conn, "GIAO_DICH_CHUA_KHOP", row, "Có tiền về nhưng không khớp đơn nào")
        return {"ket_qua": "CHUA_KHOP", "giao_dich_id": row["id"]}

    don = orders.khoa_don(conn, don_row["id"])
    if don["trang_thai"] == "DA_HUY":
        cap_nhat("CHUA_KHOP", don["id"], "Đơn đã hủy — cần hoàn tiền cho khách")
        _bao_chu(conn, "GIAO_DICH_CHUA_KHOP", row, f"Tiền về cho đơn đã hủy #{don['ma']}")
        return {"ket_qua": "DON_DA_HUY", "giao_dich_id": row["id"]}

    if orders.con_phai_thu(don) == 0:
        # Đơn đã thu đủ (thường do chủ xác nhận tay trước) -> dùng giao dịch này để đối soát
        tt = conn.execute(
            """SELECT * FROM thanh_toan WHERE don_hang_id = %s AND xac_nhan_tay AND NOT da_doi_soat
               ORDER BY id LIMIT 1 FOR UPDATE""", (don["id"],)).fetchone()
        if tt:
            conn.execute("UPDATE thanh_toan SET giao_dich_nh_id = %s, da_doi_soat = TRUE WHERE id = %s",
                         (row["id"], tt["id"]))
            lech = gd.so_tien - tt["so_tien"]
            cap_nhat("DOI_SOAT", don["id"], None if lech == 0 else f"Lệch {lech:+,} đ so với số xác nhận tay")
            audit.ghi(conn, HE_THONG, "DOI_SOAT_TU_DONG", "DON_HANG", don["ma"],
                      sau={"thanh_toan_id": tt["id"], "giao_dich_nh_id": row["id"], "lech": lech})
            return {"ket_qua": "DOI_SOAT", "giao_dich_id": row["id"], "lech": lech}
        cap_nhat("CHUA_KHOP", don["id"], "Đơn đã thu đủ — khách chuyển thừa, cần kiểm tra/hoàn tiền")
        _bao_chu(conn, "GIAO_DICH_CHUA_KHOP", row, f"Khách chuyển thừa cho đơn #{don['ma']}")
        return {"ket_qua": "THUA_TIEN", "giao_dich_id": row["id"]}

    can_thu = orders.con_phai_thu(don)
    kq = ghi_nhan_thanh_toan(conn, HE_THONG, don["id"], gd.so_tien, "CHUYEN_KHOAN", giao_dich_id=row["id"])
    if gd.so_tien < can_thu:
        cap_nhat("LECH_TIEN", don["id"], f"Khách chuyển thiếu {can_thu - gd.so_tien:,} đ".replace(",", "."))
        _bao_chu(conn, "LECH_TIEN", row, f"Đơn #{don['ma']} chuyển thiếu {can_thu - gd.so_tien:,} đ".replace(",", "."))
        return {"ket_qua": "LECH_TIEN", "giao_dich_id": row["id"], "thieu": can_thu - gd.so_tien, "don": kq["don"]}
    cap_nhat("DA_KHOP", don["id"], None if gd.so_tien == can_thu else f"Chuyển thừa {gd.so_tien - can_thu:,} đ")
    return {"ket_qua": "DA_KHOP", "giao_dich_id": row["id"], "don": kq["don"]}


def _bao_chu(conn, loai: str, gd: dict, noi_dung: str) -> None:
    events.phat(conn, loai, {"giao_dich_id": gd["id"], "so_tien": gd["so_tien"], "noi_dung": gd["noi_dung"],
                             "thong_bao": noi_dung}, vai_tro=["CHU"])
    events.xep_hang_thong_bao(conn, "ZALO", settings.notify_owner_phone, "Cần kiểm tra tiền về", noi_dung)


def chap_nhan_giam(conn, nguoi: NguoiDung, don_id: int, ly_do: str | None = None) -> dict:
    """Khách chuyển thiếu một ít, chủ đồng ý bớt phần còn lại để chốt đơn."""
    don = orders.khoa_don(conn, don_id)
    con = orders.con_phai_thu(don)
    if con == 0 or don["da_thu"] == 0:
        raise LoiNghiepVu("KHONG_LECH_TIEN", "Chỉ áp dụng cho đơn đã thu một phần", 409)
    conn.execute("UPDATE don_hang SET giam_tru = giam_tru + %s WHERE id = %s", (con, don_id))
    audit.ghi(conn, nguoi, "CHAP_NHAN_GIAM", "DON_HANG", don["ma"], sau={"giam_tru": con, "ly_do": ly_do})
    don = orders.khoa_don(conn, don_id)
    if don["trang_thai"] != "CHO_DUYET_GIA":
        orders.chot_don(conn, nguoi, don)
    conn.execute("UPDATE giao_dich_nh SET trang_thai = 'DA_KHOP', "
                 "ghi_chu = concat_ws(' — ', ghi_chu, 'chủ chấp nhận giảm') "
                 "WHERE don_hang_id = %s AND trang_thai = 'LECH_TIEN'", (don_id,))
    return orders.lay_don(conn, don_id, nguoi)


def danh_dau_da_khop(conn, nguoi: NguoiDung, thanh_toan_id: int, ghi_chu: str | None = None) -> dict:
    """Chủ tự đối chiếu với sao kê ngân hàng và đánh dấu khoản xác nhận tay là đã khớp."""
    tt = conn.execute("UPDATE thanh_toan SET da_doi_soat = TRUE WHERE id = %s AND xac_nhan_tay AND NOT da_doi_soat "
                      "RETURNING *", (thanh_toan_id,)).fetchone()
    if not tt:
        raise LoiNghiepVu("KHONG_CAN_DOI_SOAT", "Khoản thu không cần đối soát hoặc đã đối soát", 409)
    audit.ghi(conn, nguoi, "DOI_SOAT_THU_CONG", "THANH_TOAN", thanh_toan_id, sau={"ghi_chu": ghi_chu})
    return tt


def ghep_giao_dich(conn, nguoi: NguoiDung, giao_dich_id: int, don_id: int) -> dict:
    """Ghép tay một giao dịch chưa khớp (khách ghi sai nội dung) vào đơn."""
    gd = conn.execute("SELECT * FROM giao_dich_nh WHERE id = %s FOR UPDATE", (giao_dich_id,)).fetchone()
    if not gd or gd["trang_thai"] != "CHUA_KHOP" or gd["don_hang_id"]:
        raise LoiNghiepVu("KHONG_GHEP_DUOC", "Giao dịch không ở trạng thái chưa khớp", 409)
    don = orders.khoa_don(conn, don_id)
    can_thu = orders.con_phai_thu(don)
    kq = ghi_nhan_thanh_toan(conn, nguoi, don_id, gd["so_tien"], "CHUYEN_KHOAN", giao_dich_id=giao_dich_id)
    conn.execute("UPDATE giao_dich_nh SET trang_thai = %s, don_hang_id = %s WHERE id = %s",
                 ("DA_KHOP" if gd["so_tien"] >= can_thu else "LECH_TIEN", don_id, giao_dich_id))
    audit.ghi(conn, nguoi, "GHEP_GIAO_DICH", "GIAO_DICH_NH", giao_dich_id, sau={"don": don["ma"]})
    return kq


def danh_sach_doi_soat(conn) -> dict:
    return {
        "xac_nhan_tay": conn.execute(
            """SELECT tt.id, tt.so_tien, tt.thoi_diem, dh.ma AS ma_don, dh.id AS don_id, tk.ho_ten AS nguoi_xac_nhan,
                      (SELECT json_agg(json_build_object('kieu', kieu, 'gia_tri', gia_tri)) FROM bang_chung_tien
                       WHERE thanh_toan_id = tt.id) AS bang_chung
               FROM thanh_toan tt JOIN don_hang dh ON dh.id = tt.don_hang_id
               LEFT JOIN tai_khoan tk ON tk.id = tt.nguoi_ghi_nhan_id
               WHERE tt.xac_nhan_tay AND NOT tt.da_doi_soat ORDER BY tt.thoi_diem""").fetchall(),
        "giao_dich_can_xu_ly": conn.execute(
            """SELECT gd.id, gd.nguon, gd.ma_giao_dich, gd.so_tien, gd.noi_dung, gd.trang_thai, gd.ghi_chu,
                      gd.nhan_luc, dh.ma AS ma_don, dh.id AS don_id,
                      CASE WHEN dh.id IS NULL THEN NULL ELSE dh.tong_tien - dh.giam_tru - dh.da_thu END AS con_phai_thu
               FROM giao_dich_nh gd LEFT JOIN don_hang dh ON dh.id = gd.don_hang_id
               WHERE gd.trang_thai IN ('CHUA_KHOP', 'LECH_TIEN')
                 AND (dh.id IS NULL OR dh.tong_tien - dh.giam_tru - dh.da_thu > 0 OR gd.trang_thai = 'CHUA_KHOP')
               ORDER BY gd.nhan_luc DESC""").fetchall(),
    }


def tong_ket_ngay(conn, ngay: date | None = None) -> dict:
    ngay = ngay or date.today()
    r = conn.execute(
        """SELECT COALESCE(sum(so_tien) FILTER (WHERE phuong_thuc = 'TIEN_MAT'), 0)::bigint AS tien_mat,
                  COALESCE(sum(so_tien) FILTER (WHERE phuong_thuc = 'CHUYEN_KHOAN' AND NOT xac_nhan_tay), 0)::bigint
                      AS chuyen_khoan_tu_dong,
                  COALESCE(sum(so_tien) FILTER (WHERE xac_nhan_tay), 0)::bigint AS chuyen_khoan_xac_nhan_tay,
                  count(*) FILTER (WHERE xac_nhan_tay)::int AS so_khoan_xac_nhan_tay,
                  count(*) FILTER (WHERE xac_nhan_tay AND NOT da_doi_soat)::int AS so_xac_nhan_tay_chua_doi_soat,
                  COALESCE(sum(so_tien), 0)::bigint AS tong_thu
           FROM thanh_toan WHERE thoi_diem::date = %s""", (ngay,)).fetchone()
    r["so_don_lech_tien"] = conn.execute(
        "SELECT count(*)::int AS n FROM giao_dich_nh WHERE trang_thai = 'LECH_TIEN' AND nhan_luc::date = %s",
        (ngay,)).fetchone()["n"]
    r["so_don_chot"] = conn.execute(
        """SELECT count(*)::int AS n FROM nhat_ky WHERE hanh_dong = 'CHOT_DON' AND thoi_diem::date = %s""",
        (ngay,)).fetchone()["n"]
    da_chot = conn.execute("SELECT thoi_diem, ten_nguoi_thuc_hien FROM nhat_ky WHERE hanh_dong = 'CHOT_SO_NGAY' "
                           "AND thuc_the_id = %s ORDER BY id DESC LIMIT 1", (ngay.isoformat(),)).fetchone()
    r["ngay"] = ngay
    r["da_chot_so"] = da_chot
    return r


def chot_so_ngay(conn, nguoi: NguoiDung, ngay: date | None = None) -> dict:
    ngay = ngay or date.today()
    tong_ket = tong_ket_ngay(conn, ngay)
    if tong_ket["da_chot_so"]:
        raise LoiNghiepVu("DA_CHOT_SO", "Ngày này đã khóa sổ", 409)
    if tong_ket["so_xac_nhan_tay_chua_doi_soat"]:
        raise LoiNghiepVu("CON_XAC_NHAN_TAY", "Còn khoản xác nhận tay chưa đối soát với sao kê", 409,
                          chi_tiet={"so_khoan": tong_ket["so_xac_nhan_tay_chua_doi_soat"]})
    du_lieu = {k: v for k, v in tong_ket.items() if k not in ("da_chot_so", "ngay")}
    audit.ghi(conn, nguoi, "CHOT_SO_NGAY", "SO_NGAY", ngay.isoformat(), sau=du_lieu)
    return tong_ket_ngay(conn, ngay)
