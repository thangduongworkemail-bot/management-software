"""Kho đa xưởng trên sổ cái chỉ-ghi-thêm.

Mọi thay đổi tồn đều là một dòng mới trong so_cai_ton; tồn hiện có / khả dụng luôn
được tính lại từ sổ cái (view v_ton_kho). Trước khi kiểm tra và giữ/xuất hàng, các
biến thể liên quan được khóa (SELECT ... FOR UPDATE theo thứ tự id) để hai quầy bán
cùng lúc không thể bán vượt tồn.
"""
from collections import defaultdict
from fractions import Fraction

from ..errors import LoiNghiepVu, khong_tim_thay
from ..security import NguoiDung
from . import audit, codes


def khoa_bien_the(conn, ids) -> None:
    ids = sorted(set(ids))
    if ids:
        conn.execute("SELECT id FROM bien_the WHERE id = ANY(%s) ORDER BY id FOR UPDATE", (ids,))


def ton(conn, ids) -> dict[int, dict]:
    ids = sorted(set(ids))
    if not ids:
        return {}
    rows = conn.execute("SELECT * FROM v_ton_kho WHERE bien_the_id = ANY(%s)", (ids,)).fetchall()
    return {r["bien_the_id"]: r for r in rows}


def ghi_so_cai(conn, bien_the_id: int, loai: str, so_luong: int, *, nguoi: NguoiDung | None = None,
               don_hang_id=None, phieu_nhap_id=None, tham_chieu=None, ly_do=None, het_han_luc=None) -> dict:
    return conn.execute(
        """INSERT INTO so_cai_ton (bien_the_id, loai, so_luong, don_hang_id, phieu_nhap_id, tham_chieu, ly_do,
                                   het_han_luc, nguoi_thuc_hien_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (bien_the_id, loai, so_luong, don_hang_id, phieu_nhap_id, tham_chieu, ly_do, het_han_luc,
         (nguoi.id or None) if nguoi else None),
    ).fetchone()


def nhu_cau_cua_don(conn, don_hang_id: int, chi_dong_chua_xuat: bool = True) -> dict[int, int]:
    """Số lượng từng biến thể cần cho đơn — bộ sản phẩm được rã thành thành phần, hàng đặt riêng bỏ qua."""
    rows = conn.execute(
        f"""SELECT COALESCE(tp.bien_the_id, d.bien_the_id) AS bien_the_id,
                   sum(d.so_luong * COALESCE(tp.so_luong, 1))::int AS so_luong
            FROM dong_don d
            LEFT JOIN thanh_phan_bo tp ON tp.bo_san_pham_id = d.bo_san_pham_id
            WHERE d.don_hang_id = %s AND NOT d.dat_rieng {"AND NOT d.da_xuat" if chi_dong_chua_xuat else ""}
            GROUP BY 1""", (don_hang_id,)).fetchall()
    return {r["bien_the_id"]: r["so_luong"] for r in rows}


def thieu_hang(conn, nhu_cau: dict[int, int]) -> list[dict]:
    hien_tai = ton(conn, nhu_cau)
    thieu = []
    for bt_id, can in nhu_cau.items():
        kha_dung = hien_tai.get(bt_id, {}).get("ton_kha_dung", 0)
        if kha_dung < can:
            thieu.append({"bien_the_id": bt_id, "can": can, "kha_dung": kha_dung})
    return thieu


def giu_cho_don(conn, don: dict, het_han_luc, nguoi: NguoiDung | None, bat_buoc: bool = True) -> list[dict]:
    """Ghi GIU_CHO cho toàn bộ hàng có sẵn của đơn. Trả về danh sách thiếu (rỗng = giữ thành công)."""
    nhu_cau = nhu_cau_cua_don(conn, don["id"])
    khoa_bien_the(conn, nhu_cau)
    thieu = thieu_hang(conn, nhu_cau)
    if thieu:
        if bat_buoc:
            ma = {r["id"]: r["ma_noi_bo"] for r in conn.execute(
                "SELECT id, ma_noi_bo FROM bien_the WHERE id = ANY(%s)", ([t["bien_the_id"] for t in thieu],))}
            for t in thieu:
                t["ma_noi_bo"] = ma.get(t["bien_the_id"])
            raise LoiNghiepVu("KHONG_DU_TON", "Không đủ tồn khả dụng để giữ chỗ", 409, chi_tiet=thieu)
        return thieu
    for bt_id, so_luong in nhu_cau.items():
        ghi_so_cai(conn, bt_id, "GIU_CHO", so_luong, nguoi=nguoi, don_hang_id=don["id"],
                   tham_chieu=f"Đơn #{don['ma']}", het_han_luc=het_han_luc)
    return []


def dang_giu_cua_don(conn, don_hang_id: int) -> dict[int, int]:
    rows = conn.execute(
        """SELECT bien_the_id, sum(so_luong)::int AS con_giu FROM so_cai_ton
           WHERE don_hang_id = %s AND loai IN ('GIU_CHO', 'NHA_CHO')
           GROUP BY bien_the_id HAVING sum(so_luong) > 0""", (don_hang_id,)).fetchall()
    return {r["bien_the_id"]: r["con_giu"] for r in rows}


def nha_cho_don(conn, don: dict, ly_do: str, nguoi: NguoiDung | None) -> dict[int, int]:
    dang_giu = dang_giu_cua_don(conn, don["id"])
    khoa_bien_the(conn, dang_giu)
    for bt_id, so_luong in dang_giu.items():
        ghi_so_cai(conn, bt_id, "NHA_CHO", -so_luong, nguoi=nguoi, don_hang_id=don["id"],
                   tham_chieu=f"Đơn #{don['ma']}", ly_do=ly_do)
    return dang_giu


def xuat_kho_don(conn, don: dict, nguoi: NguoiDung | None) -> dict[int, int]:
    """Nhả giữ chỗ của đơn rồi ghi XUAT cho các dòng hàng có sẵn chưa xuất."""
    nhu_cau = nhu_cau_cua_don(conn, don["id"])
    if not nhu_cau:
        return {}
    khoa_bien_the(conn, nhu_cau)
    nha_cho_don(conn, don, "Chuyển giữ chỗ thành xuất bán", nguoi)
    thieu = thieu_hang(conn, nhu_cau)
    if thieu:
        raise LoiNghiepVu("KHONG_DU_TON", "Không đủ tồn để xuất kho cho đơn", 409, chi_tiet=thieu)
    for bt_id, so_luong in nhu_cau.items():
        ghi_so_cai(conn, bt_id, "XUAT", -so_luong, nguoi=nguoi, don_hang_id=don["id"],
                   tham_chieu=f"Đơn #{don['ma']}")
    conn.execute("UPDATE dong_don SET da_xuat = TRUE WHERE don_hang_id = %s AND NOT dat_rieng AND NOT da_xuat",
                 (don["id"],))
    return nhu_cau


def nhap_tra_hang(conn, don: dict, nguoi: NguoiDung, ly_do: str) -> dict[int, int]:
    da_xuat = conn.execute(
        """SELECT bien_the_id, -sum(so_luong)::int AS so_luong FROM so_cai_ton
           WHERE don_hang_id = %s AND loai = 'XUAT' GROUP BY bien_the_id""", (don["id"],)).fetchall()
    for r in da_xuat:
        ghi_so_cai(conn, r["bien_the_id"], "TRA_HANG", r["so_luong"], nguoi=nguoi, don_hang_id=don["id"],
                   tham_chieu=f"Đơn #{don['ma']}", ly_do=ly_do)
    return {r["bien_the_id"]: r["so_luong"] for r in da_xuat}


# ---------------------------------------------------------------------------
# Nhập kho theo xưởng
# ---------------------------------------------------------------------------
def tao_phieu_nhap(conn, nguoi: NguoiDung, nha_cung_cap_id: int, dong: list[dict],
                   ghi_chu: str | None = None, anh_chung_tu_url: str | None = None, ma: str | None = None) -> dict:
    if not dong:
        raise LoiNghiepVu("PHIEU_RONG", "Phiếu nhập phải có ít nhất một dòng")
    ncc = conn.execute("SELECT * FROM nha_cung_cap WHERE id = %s FOR UPDATE", (nha_cung_cap_id,)).fetchone()
    if not ncc:
        raise khong_tim_thay("xưởng cung cấp")
    for d in dong:
        if int(d["so_luong"]) <= 0 or int(d["gia_von_don_vi"]) < 0:
            raise LoiNghiepVu("DONG_NHAP_KHONG_HOP_LE", "Số lượng phải dương và giá vốn không âm")

    tong = sum(int(d["so_luong"]) * int(d["gia_von_don_vi"]) for d in dong)
    ma = ma or codes.ma_tiep_theo(conn, "PN", so_chu_so=2)
    phieu = conn.execute(
        """INSERT INTO phieu_nhap (ma, nha_cung_cap_id, nguoi_lap_id, tong_tien, anh_chung_tu_url, ghi_chu)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
        (ma, nha_cung_cap_id, nguoi.id, tong, anh_chung_tu_url, ghi_chu)).fetchone()

    khoa_bien_the(conn, [d["bien_the_id"] for d in dong])
    gop = defaultdict(lambda: [0, 0])  # bien_the_id -> [so_luong, tong_gia_tri]
    for d in dong:
        conn.execute("INSERT INTO lo_nhap (phieu_nhap_id, bien_the_id, so_luong, gia_von_don_vi) VALUES (%s, %s, %s, %s)",
                     (phieu["id"], d["bien_the_id"], d["so_luong"], d["gia_von_don_vi"]))
        gop[d["bien_the_id"]][0] += int(d["so_luong"])
        gop[d["bien_the_id"]][1] += int(d["so_luong"]) * int(d["gia_von_don_vi"])

    ton_truoc = ton(conn, gop)
    for bt_id, (so_luong, gia_tri) in gop.items():
        _cap_nhat_gia_von_binh_quan(conn, nguoi, bt_id, ton_truoc.get(bt_id, {}).get("ton_hien_co", 0),
                                    so_luong, gia_tri)
        ghi_so_cai(conn, bt_id, "NHAP", so_luong, nguoi=nguoi, phieu_nhap_id=phieu["id"],
                   tham_chieu=f"Phiếu {ma} • {ncc['ten']}")

    conn.execute("UPDATE nha_cung_cap SET so_du_cong_no = so_du_cong_no + %s WHERE id = %s", (tong, nha_cung_cap_id))
    audit.ghi(conn, nguoi, "NHAP_KHO", "PHIEU_NHAP", phieu["id"],
              sau={"ma": ma, "xuong": ncc["ten"], "tong_tien": tong, "so_dong": len(dong)})
    return phieu


def _cap_nhat_gia_von_binh_quan(conn, nguoi, bien_the_id: int, ton_hien_co: int, so_luong_nhap: int,
                                gia_tri_nhap: int) -> None:
    from . import catalog
    hien_tai = conn.execute("SELECT gia_von FROM v_gia_hien_hanh WHERE bien_the_id = %s", (bien_the_id,)).fetchone()
    gia_von_cu = hien_tai["gia_von"] if hien_tai else None
    if gia_von_cu is None or ton_hien_co <= 0:
        moi = Fraction(gia_tri_nhap, so_luong_nhap)
    else:
        moi = Fraction(ton_hien_co * gia_von_cu + gia_tri_nhap, ton_hien_co + so_luong_nhap)
    moi = int(moi + Fraction(1, 2))
    if moi != gia_von_cu:
        catalog.dat_gia(conn, nguoi, bien_the_id, "GIA_VON", moi, ghi_chu="Bình quân gia quyền sau nhập kho")


def dieu_chinh(conn, nguoi: NguoiDung, bien_the_id: int, so_luong: int, ly_do: str) -> dict:
    if so_luong == 0:
        raise LoiNghiepVu("SO_LUONG_KHONG_HOP_LE", "Số lượng điều chỉnh phải khác 0")
    if not ly_do or not ly_do.strip():
        raise LoiNghiepVu("THIEU_LY_DO", "Điều chỉnh kho bắt buộc ghi lý do")
    khoa_bien_the(conn, [bien_the_id])
    hien_tai = ton(conn, [bien_the_id]).get(bien_the_id)
    if not hien_tai:
        raise khong_tim_thay("biến thể")
    if hien_tai["ton_hien_co"] + so_luong < hien_tai["dang_giu_cho"]:
        raise LoiNghiepVu("DIEU_CHINH_AM", "Điều chỉnh làm tồn hiện có thấp hơn số đang giữ chỗ", 409)
    dong = ghi_so_cai(conn, bien_the_id, "DIEU_CHINH", so_luong, nguoi=nguoi, ly_do=ly_do.strip(),
                      tham_chieu="Kiểm kê / điều chỉnh")
    audit.ghi(conn, nguoi, "DIEU_CHINH_KHO", "BIEN_THE", bien_the_id,
              truoc={"ton_hien_co": hien_tai["ton_hien_co"]},
              sau={"ton_hien_co": hien_tai["ton_hien_co"] + so_luong, "ly_do": ly_do})
    return dong


def kiem_ke(conn, nguoi: NguoiDung, dong: list[dict], ly_do: str) -> list[dict]:
    """Ghi kết quả kiểm kê theo số đếm thực tế: chênh lệch được tính dưới khóa, không tin số client gửi."""
    if not ly_do or not ly_do.strip():
        raise LoiNghiepVu("THIEU_LY_DO", "Kiểm kê bắt buộc ghi lý do")
    thuc_te = {int(d["bien_the_id"]): int(d["so_thuc_te"]) for d in dong}
    if any(v < 0 for v in thuc_te.values()):
        raise LoiNghiepVu("SO_LUONG_KHONG_HOP_LE", "Số đếm thực tế không được âm")
    khoa_bien_the(conn, thuc_te)
    hien_tai = ton(conn, thuc_te)
    ket_qua = []
    for bt_id, so_thuc_te in sorted(thuc_te.items()):
        if bt_id not in hien_tai:
            raise khong_tim_thay("biến thể")
        lech = so_thuc_te - hien_tai[bt_id]["ton_hien_co"]
        if lech:
            dieu_chinh(conn, nguoi, bt_id, lech, ly_do)
            ket_qua.append({"bien_the_id": bt_id, "truoc": hien_tai[bt_id]["ton_hien_co"], "sau": so_thuc_te,
                            "lech": lech})
    return ket_qua


# ---------------------------------------------------------------------------
# Xưởng cung cấp
# ---------------------------------------------------------------------------
def tao_xuong(conn, nguoi: NguoiDung, du_lieu: dict) -> dict:
    ten = (du_lieu.get("ten") or "").strip()
    if not ten:
        raise LoiNghiepVu("THIEU_TEN_XUONG", "Nhập tên xưởng")
    if conn.execute("SELECT 1 FROM nha_cung_cap WHERE f_chuan_hoa(ten) = f_chuan_hoa(%s)", (ten,)).fetchone():
        raise LoiNghiepVu("XUONG_DA_CO", f"Đã có xưởng tên '{ten}'", 409)
    goc = conn.execute("SELECT upper(trim(both '_' FROM regexp_replace(f_chuan_hoa(%s), '[^a-z0-9]+', '_', 'g'))) AS ma",
                       (ten,)).fetchone()["ma"][:30] or "XUONG"
    ma, i = goc, 1
    while conn.execute("SELECT 1 FROM nha_cung_cap WHERE ma = %s", (ma,)).fetchone():
        i += 1
        ma = f"{goc}_{i}"
    row = conn.execute(
        """INSERT INTO nha_cung_cap (ma, ten, lien_he, so_dien_thoai, dia_chi, loai_hang, ma_so_thue, ghi_chu,
                                     han_thanh_toan_ngay)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (ma, ten, du_lieu.get("lien_he"), du_lieu.get("so_dien_thoai"), du_lieu.get("dia_chi"),
         du_lieu.get("loai_hang"), du_lieu.get("ma_so_thue"), du_lieu.get("ghi_chu"),
         30 if du_lieu.get("han_thanh_toan_ngay") is None else du_lieu["han_thanh_toan_ngay"])).fetchone()
    audit.ghi(conn, nguoi, "TAO_XUONG", "NHA_CUNG_CAP", row["id"], sau={"ma": ma, "ten": ten})
    return row


def so_cai(conn, bien_the_id: int | None = None, gioi_han: int = 100) -> list[dict]:
    dieu_kien = "WHERE s.bien_the_id = %s" if bien_the_id else ""
    tham_so = (bien_the_id, gioi_han) if bien_the_id else (gioi_han,)
    return conn.execute(
        f"""SELECT s.*, bt.ma_noi_bo, bt.ten_hien_thi, tk.ho_ten AS nguoi_thuc_hien, dh.ma AS ma_don
            FROM so_cai_ton s JOIN bien_the bt ON bt.id = s.bien_the_id
            LEFT JOIN tai_khoan tk ON tk.id = s.nguoi_thuc_hien_id
            LEFT JOIN don_hang dh ON dh.id = s.don_hang_id
            {dieu_kien} ORDER BY s.id DESC LIMIT %s""", tham_so).fetchall()


def ton_theo_xuong(conn) -> list[dict]:
    return conn.execute(
        """SELECT ncc.id, ncc.ten, count(DISTINCT mx.bien_the_id)::int AS so_mau,
                  COALESCE(sum(t.ton_hien_co), 0)::int AS ton_hien_co,
                  count(*) FILTER (WHERE t.ton_kha_dung <= bt.ton_toi_thieu AND NOT bt.dat_theo_kich_thuoc)::int
                      AS so_mau_sap_het
           FROM nha_cung_cap ncc
           LEFT JOIN ma_xuong mx ON mx.nha_cung_cap_id = ncc.id AND mx.uu_tien = 1
           LEFT JOIN bien_the bt ON bt.id = mx.bien_the_id
           LEFT JOIN v_ton_kho t ON t.bien_the_id = mx.bien_the_id
           GROUP BY ncc.id ORDER BY ncc.id""").fetchall()


def sap_het(conn) -> list[dict]:
    return conn.execute(
        """SELECT bt.id, bt.ma_noi_bo, bt.ten_hien_thi, bt.ton_toi_thieu, t.ton_hien_co, t.ton_kha_dung
           FROM bien_the bt JOIN v_ton_kho t ON t.bien_the_id = bt.id
           WHERE bt.dang_ban AND NOT bt.dat_theo_kich_thuoc AND t.ton_kha_dung <= bt.ton_toi_thieu
           ORDER BY t.ton_kha_dung, bt.ma_noi_bo""").fetchall()
