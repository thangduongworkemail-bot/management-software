"""Danh mục hàng hóa, bảng giá nhiều tầng, tìm kiếm tiếng Việt và tính giá đặt riêng."""
import re

from psycopg.types.json import Jsonb

from ..domain import pricing
from ..domain.dimension import LoiKichThuoc, doc_kich_thuoc, doc_mot_kich_thuoc
from ..errors import LoiNghiepVu, khong_tim_thay
from ..security import NguoiDung
from . import audit

TRUONG_NOI_BO = ("gia_von", "gia_san")
_RE_TOKEN_KICH_THUOC = re.compile(r"^(\d+m\d+|\d+(?:[.,]\d+)?(?:m|mm|cm))$")


def an_gia_noi_bo(row: dict, nguoi: NguoiDung) -> dict:
    """Thợ phụ không bao giờ nhận được giá vốn / giá sàn từ API."""
    bo = ("tim_kiem",) if nguoi.xem_gia_von else ("tim_kiem", *TRUONG_NOI_BO)
    return {k: v for k, v in row.items() if k not in bo}


_SELECT_BIEN_THE = """
    SELECT 'BIEN_THE' AS kieu, bt.id, bt.ma_noi_bo AS ma, bt.ten_hien_thi AS ten, m.ten AS mau_hang,
           l.ten AS loai_hang, COALESCE(bt.don_vi_tinh, l.don_vi_tinh) AS don_vi_tinh, bt.loai_go,
           bt.dai_mm, bt.rong_mm, bt.cao_mm, bt.mau_sac,
           bt.dat_theo_kich_thuoc, bt.ton_toi_thieu, COALESCE(bt.anh_url, m.anh_url) AS anh_url,
           bt.mau_hang_id, m.loai_hang_id, bt.hoan_thien, bt.kieu_dang, bt.vat_lieu_phu, bt.xuat_xu,
           bt.khoi_luong_kg, bt.bao_hanh_thang, bt.mo_ta, bt.thuoc_tinh,
           g.gia_niem_yet, g.gia_san, g.gia_von,
           t.ton_hien_co, t.dang_giu_cho, t.ton_kha_dung,
           ct.kieu AS kieu_cong_thuc, bt.tim_kiem, bt.dang_ban
    FROM bien_the bt
    JOIN mau_hang m ON m.id = bt.mau_hang_id
    JOIN loai_hang l ON l.id = m.loai_hang_id
    LEFT JOIN v_gia_hien_hanh g ON g.bien_the_id = bt.id
    LEFT JOIN v_ton_kho t ON t.bien_the_id = bt.id
    LEFT JOIN cong_thuc_gia ct ON ct.bien_the_id = bt.id
"""

_SELECT_BO = """
    SELECT 'BO' AS kieu, b.id, b.ma, b.ten, b.ten AS mau_hang, 'Bộ sản phẩm' AS loai_hang, 'bộ' AS don_vi_tinh,
           NULL::text AS loai_go, NULL::int AS dai_mm, NULL::int AS rong_mm, NULL::int AS cao_mm,
           NULL::text AS mau_sac, FALSE AS dat_theo_kich_thuoc, 0 AS ton_toi_thieu, NULL::text AS anh_url,
           NULL::int AS mau_hang_id, NULL::int AS loai_hang_id, NULL::text AS hoan_thien, NULL::text AS kieu_dang,
           NULL::text AS vat_lieu_phu, NULL::text AS xuat_xu, NULL::int AS khoi_luong_kg,
           NULL::int AS bao_hanh_thang, b.mo_ta, '{}'::jsonb AS thuoc_tinh,
           b.gia_niem_yet, b.gia_san, gv.gia_von,
           t.ton_hien_co, 0 AS dang_giu_cho, t.ton_kha_dung,
           NULL::text AS kieu_cong_thuc, b.tim_kiem, b.dang_ban
    FROM bo_san_pham b
    LEFT JOIN v_ton_bo t ON t.bo_san_pham_id = b.id
    LEFT JOIN v_gia_von_bo gv ON gv.bo_san_pham_id = b.id
"""


def _thoat_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def chuan_hoa_truy_van(conn, q: str) -> tuple[str, list[str]]:
    """Bỏ dấu, thay từ đồng nghĩa, đổi token kích thước ("1,8m") về mm."""
    q_cn = conn.execute("SELECT f_chuan_hoa(%s) AS q", (q or "",)).fetchone()["q"].strip()
    if not q_cn:
        return "", []
    dong_nghia = conn.execute(
        "SELECT tu_khoa_cn, tu_chuan_cn FROM tu_dong_nghia ORDER BY length(tu_khoa_cn) DESC").fetchall()
    for r in dong_nghia:
        tk, tc = r["tu_khoa_cn"], r["tu_chuan_cn"]
        if tc in q_cn:
            continue
        q_cn = re.sub(rf"(?<!\w){re.escape(tk)}(?!\w)", tc, q_cn)

    tokens = []
    for tok in q_cn.split():
        if _RE_TOKEN_KICH_THUOC.match(tok):
            try:
                tokens.append(str(doc_mot_kich_thuoc(tok)))
                continue
            except LoiKichThuoc:
                pass
        tokens.append(tok)
    return " ".join(tokens), tokens


_HANG_DANG_BAN = f"({_SELECT_BIEN_THE} UNION ALL {_SELECT_BO}) kq"


def tim_kiem(conn, q: str, nguoi: NguoiDung, gioi_han: int = 20) -> list[dict]:
    q_cn, tokens = chuan_hoa_truy_van(conn, q)
    if not tokens:
        return []
    dieu_kien = " AND ".join(["kq.tim_kiem LIKE %s"] * len(tokens))
    rows = conn.execute(
        f"""SELECT kq.* FROM {_HANG_DANG_BAN}
            WHERE kq.dang_ban AND {dieu_kien}
            ORDER BY similarity(kq.tim_kiem, %s) DESC, kq.ten
            LIMIT %s""",
        (*[f"%{_thoat_like(t)}%" for t in tokens], q_cn, gioi_han),
    ).fetchall()
    if not rows:
        # Không khớp đủ mọi từ (gõ sai chính tả): tìm gần đúng theo trigram
        rows = conn.execute(
            f"""SELECT kq.* FROM {_HANG_DANG_BAN}
                WHERE kq.dang_ban AND %s <%% kq.tim_kiem
                ORDER BY word_similarity(%s, kq.tim_kiem) DESC, kq.ten
                LIMIT %s""",
            (q_cn, q_cn, gioi_han),
        ).fetchall()
    return [an_gia_noi_bo(r, nguoi) for r in rows]


def lay_bien_the(conn, bien_the_id: int) -> dict:
    row = conn.execute(f"{_SELECT_BIEN_THE} WHERE bt.id = %s", (bien_the_id,)).fetchone()
    if not row:
        raise khong_tim_thay("biến thể")
    return row


def lay_bo(conn, bo_id: int) -> dict:
    row = conn.execute(f"{_SELECT_BO} WHERE b.id = %s", (bo_id,)).fetchone()
    if not row:
        raise khong_tim_thay("bộ sản phẩm")
    row["thanh_phan"] = conn.execute(
        """SELECT tp.bien_the_id, bt.ma_noi_bo, bt.ten_hien_thi, tp.so_luong, t.ton_kha_dung
           FROM thanh_phan_bo tp JOIN bien_the bt ON bt.id = tp.bien_the_id
           JOIN v_ton_kho t ON t.bien_the_id = tp.bien_the_id
           WHERE tp.bo_san_pham_id = %s ORDER BY bt.ma_noi_bo""", (bo_id,)).fetchall()
    return row


def tim_theo_ma(conn, ma: str) -> dict:
    r = conn.execute("SELECT id FROM bien_the WHERE ma_noi_bo = %s", (ma,)).fetchone()
    if r:
        return lay_bien_the(conn, r["id"])
    r = conn.execute("SELECT id FROM bo_san_pham WHERE ma = %s", (ma,)).fetchone()
    if r:
        return lay_bo(conn, r["id"])
    raise khong_tim_thay(f"mặt hàng {ma}")


def danh_sach(conn, nguoi: NguoiDung, loai_hang_id: int | None = None, ca_ngung_ban: bool = False) -> list[dict]:
    """Mặc định chỉ hàng đang bán; ca_ngung_ban=True kèm cả hàng đã xóa khỏi danh mục (để khôi phục)."""
    loc_bt, loc_bo = ("TRUE", "TRUE") if ca_ngung_ban else ("bt.dang_ban", "b.dang_ban")
    if loai_hang_id:
        rows = conn.execute(f"{_SELECT_BIEN_THE} WHERE {loc_bt} AND m.loai_hang_id = %s ORDER BY bt.ma_noi_bo",
                            (loai_hang_id,)).fetchall()
    else:
        rows = conn.execute(f"{_SELECT_BIEN_THE} WHERE {loc_bt} ORDER BY bt.ma_noi_bo").fetchall()
        rows += conn.execute(f"{_SELECT_BO} WHERE {loc_bo} ORDER BY b.ma").fetchall()
    return [an_gia_noi_bo(r, nguoi) for r in rows]


def loai_hang(conn) -> list[dict]:
    return conn.execute(
        """SELECT l.id, l.ma, l.ten, l.don_vi_tinh, l.thuoc_tinh_mau, count(bt.id)::int AS so_bien_the
           FROM loai_hang l LEFT JOIN mau_hang m ON m.loai_hang_id = l.id
           LEFT JOIN bien_the bt ON bt.mau_hang_id = m.id AND bt.dang_ban
           GROUP BY l.id ORDER BY l.id""").fetchall()


# ---------------------------------------------------------------------------
# Bảng giá
# ---------------------------------------------------------------------------
def dat_gia(conn, nguoi: NguoiDung, bien_the_id: int, loai_gia: str, so_tien: int,
            nhom_khach: str | None = None, ghi_chu: str | None = None, *, kiem_tra: bool = True) -> dict:
    """Đóng mức giá đang mở rồi mở mức mới (không bao giờ ghi đè số tiền cũ)."""
    if so_tien < 0:
        raise LoiNghiepVu("GIA_KHONG_HOP_LE", "Giá không được âm")
    conn.execute("SELECT id FROM bien_the WHERE id = %s FOR UPDATE", (bien_the_id,))
    cu = conn.execute(
        """UPDATE gia_hieu_luc SET den_ngay = now()
           WHERE bien_the_id = %s AND loai_gia = %s AND COALESCE(nhom_khach, '') = COALESCE(%s, '')
             AND den_ngay IS NULL
           RETURNING so_tien""", (bien_the_id, loai_gia, nhom_khach)).fetchone()
    moi = conn.execute(
        """INSERT INTO gia_hieu_luc (bien_the_id, loai_gia, nhom_khach, so_tien, nguoi_dat_id, ghi_chu)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
        (bien_the_id, loai_gia, nhom_khach, so_tien, nguoi.id or None, ghi_chu)).fetchone()
    if kiem_tra:
        _kiem_tra_gia_san(conn, bien_the_id)
    audit.ghi(conn, nguoi, "CAP_NHAT_GIA", "BIEN_THE", bien_the_id,
              truoc={"loai_gia": loai_gia, "so_tien": cu["so_tien"] if cu else None},
              sau={"loai_gia": loai_gia, "so_tien": so_tien, "ghi_chu": ghi_chu})
    return moi


def _kiem_tra_gia_san(conn, bien_the_id: int) -> None:
    gia = conn.execute("SELECT * FROM v_gia_hien_hanh WHERE bien_the_id = %s", (bien_the_id,)).fetchone()
    if gia and gia["gia_san"] is not None and gia["gia_niem_yet"] is not None and gia["gia_san"] > gia["gia_niem_yet"]:
        raise LoiNghiepVu("GIA_SAN_VUOT_NIEM_YET", "Giá sàn không được cao hơn giá niêm yết")


def lich_su_gia(conn, bien_the_id: int) -> list[dict]:
    return conn.execute(
        """SELECT g.*, tk.ho_ten AS nguoi_dat FROM gia_hieu_luc g LEFT JOIN tai_khoan tk ON tk.id = g.nguoi_dat_id
           WHERE g.bien_the_id = %s ORDER BY g.tu_ngay DESC, g.id DESC""", (bien_the_id,)).fetchall()


# ---------------------------------------------------------------------------
# Hàng đặt kích thước riêng
# ---------------------------------------------------------------------------
def lay_cong_thuc(conn, bien_the_id: int) -> tuple[pricing.CongThucGia, dict]:
    row = conn.execute(
        """SELECT ct.*, bt.loai_go, COALESCE(h.he_so_phan_nghin, 1000) AS he_so_phan_nghin
           FROM cong_thuc_gia ct JOIN bien_the bt ON bt.id = ct.bien_the_id
           LEFT JOIN he_so_go h ON h.loai_go = bt.loai_go
           WHERE ct.bien_the_id = %s""", (bien_the_id,)).fetchone()
    if not row:
        raise LoiNghiepVu("KHONG_CO_CONG_THUC", "Mặt hàng này không có công thức tính giá đặt riêng")
    ct = pricing.CongThucGia(
        kieu=row["kieu"], don_gia=row["don_gia"], phu_phi=row["phu_phi"], bac_gia=row["bac_gia"],
        kich_thuoc_min_mm=row["kich_thuoc_min_mm"], kich_thuoc_max_mm=row["kich_thuoc_max_mm"],
        ty_le_gia_von_phan_nghin=row["ty_le_gia_von_phan_nghin"],
        ty_le_gia_san_phan_nghin=row["ty_le_gia_san_phan_nghin"])
    return ct, row


def tinh_gia_dat_rieng(conn, bien_the_id: int, kich_thuoc: str) -> dict:
    ct, row = lay_cong_thuc(conn, bien_the_id)
    try:
        kt = doc_kich_thuoc(kich_thuoc, ct.kich_thuoc_min_mm, ct.kich_thuoc_max_mm)
    except LoiKichThuoc as e:
        raise LoiNghiepVu("KICH_THUOC_KHONG_HOP_LE", str(e)) from e
    if not kt.hop_le:
        raise LoiNghiepVu("KICH_THUOC_NGOAI_DUNG_SAI", "; ".join(kt.canh_bao), chi_tiet={"gia_tri_mm": kt.gia_tri_mm})
    try:
        kq = pricing.tinh_gia(ct, kt.gia_tri_mm, row["loai_go"], row["he_so_phan_nghin"])
    except pricing.LoiCongThuc as e:
        raise LoiNghiepVu("CONG_THUC_LOI", str(e)) from e
    return {
        "kieu_cong_thuc": ct.kieu,
        "kich_thuoc_mm": kt.gia_tri_mm,
        "gia": kq.gia,
        "gia_san": pricing.gia_theo_ty_le(kq.gia, ct.ty_le_gia_san_phan_nghin),
        "gia_von": pricing.gia_theo_ty_le(kq.gia, ct.ty_le_gia_von_phan_nghin),
        "dien_giai": kq.dien_giai,
        "tham_so": {**kq.tham_so, "nhap": kich_thuoc},
    }


# ---------------------------------------------------------------------------
# Từ đồng nghĩa & danh mục mới
# ---------------------------------------------------------------------------
def them_dong_nghia(conn, nguoi: NguoiDung, tu_khoa: str, tu_chuan: str) -> dict:
    row = conn.execute(
        """INSERT INTO tu_dong_nghia (tu_khoa, tu_chuan) VALUES (%s, %s)
           ON CONFLICT (tu_khoa_cn) DO UPDATE SET tu_chuan = EXCLUDED.tu_chuan RETURNING *""",
        (tu_khoa, tu_chuan)).fetchone()
    audit.ghi(conn, nguoi, "THEM_TU_DONG_NGHIA", "TU_DONG_NGHIA", row["id"], sau={"tu_khoa": tu_khoa, "tu_chuan": tu_chuan})
    return row


TRUONG_SUA = ("ma_noi_bo", "ten_hien_thi", "mau_hang_id", "loai_go", "dai_mm", "rong_mm", "cao_mm", "mau_sac",
              "hoan_thien", "kieu_dang", "vat_lieu_phu", "xuat_xu", "khoi_luong_kg", "bao_hanh_thang",
              "don_vi_tinh", "mo_ta", "anh_url", "ton_toi_thieu", "thuoc_tinh")
TRUONG_GIA = (("GIA_NIEM_YET", "gia_niem_yet"), ("GIA_SAN", "gia_san"), ("GIA_VON", "gia_von"))


def _mau_hang_cho(conn, du_lieu: dict) -> int:
    """Dùng mẫu có sẵn, hoặc tạo mẫu mới trong nhóm hàng khi Chủ nhập tên mẫu mới."""
    if du_lieu.get("mau_hang_id"):
        return du_lieu["mau_hang_id"]
    ten, loai_hang_id = (du_lieu.get("ten_mau_moi") or "").strip(), du_lieu.get("loai_hang_id")
    if not ten or not loai_hang_id:
        raise LoiNghiepVu("THIEU_MAU_HANG", "Chọn mẫu hàng có sẵn hoặc nhập tên mẫu mới kèm nhóm hàng")
    co = conn.execute("SELECT id FROM mau_hang WHERE loai_hang_id = %s AND f_chuan_hoa(ten) = f_chuan_hoa(%s)",
                      (loai_hang_id, ten)).fetchone()
    if co:
        return co["id"]
    return conn.execute("INSERT INTO mau_hang (loai_hang_id, ten, mo_ta) VALUES (%s, %s, %s) RETURNING id",
                        (loai_hang_id, ten, ten)).fetchone()["id"]


def _kiem_tra_loai_go(conn, loai_go: str | None) -> None:
    if loai_go and not conn.execute("SELECT 1 FROM he_so_go WHERE loai_go = %s", (loai_go,)).fetchone():
        raise LoiNghiepVu("LOAI_GO_KHONG_CO", f"Loại gỗ '{loai_go}' chưa có trong bảng hệ số gỗ")


def _dat_cac_gia(conn, nguoi: NguoiDung, bien_the_id: int, du_lieu: dict, hien_tai: dict | None) -> dict:
    """Đổi các mức giá được gửi lên (đóng mức cũ, mở mức mới); kiểm tra sàn ≤ niêm yết một lần ở cuối."""
    da_doi = {}
    for loai_gia, khoa in TRUONG_GIA:
        moi = du_lieu.get(khoa)
        if moi is not None and (hien_tai is None or hien_tai.get(khoa) != moi):
            dat_gia(conn, nguoi, bien_the_id, loai_gia, moi, ghi_chu="Sửa thông tin mặt hàng", kiem_tra=False)
            da_doi[khoa] = moi
    if da_doi:
        _kiem_tra_gia_san(conn, bien_the_id)
    return da_doi


def tao_bien_the(conn, nguoi: NguoiDung, du_lieu: dict) -> dict:
    """Thêm mặt hàng (kể cả hàng phát hiện khi kiểm kê): ton_ban_dau > 0 ghi một dòng DIEU_CHINH vào sổ cái."""
    from . import inventory
    dat_rieng = bool(du_lieu.get("dat_theo_kich_thuoc"))
    ton_ban_dau = du_lieu.get("ton_ban_dau") or 0
    if ton_ban_dau and dat_rieng:
        raise LoiNghiepVu("HANG_DAT_RIENG_KHONG_TON", "Hàng đặt theo kích thước không quản lý tồn kho")
    cot = {k: du_lieu.get(k) for k in TRUONG_SUA} | {
        "mau_hang_id": _mau_hang_cho(conn, du_lieu), "thuoc_tinh": Jsonb(du_lieu.get("thuoc_tinh") or {}),
        "ton_toi_thieu": du_lieu.get("ton_toi_thieu") or 0, "dat_theo_kich_thuoc": dat_rieng}
    _kiem_tra_loai_go(conn, cot["loai_go"])
    row = conn.execute(
        f"INSERT INTO bien_the ({', '.join(cot)}) VALUES ({', '.join(f'%({c})s' for c in cot)}) RETURNING id",
        cot).fetchone()
    _dat_cac_gia(conn, nguoi, row["id"], du_lieu, None)
    audit.ghi(conn, nguoi, "TAO_BIEN_THE", "BIEN_THE", row["id"],
              sau={"ma_noi_bo": cot["ma_noi_bo"], "ten_hien_thi": cot["ten_hien_thi"]})
    if ton_ban_dau > 0:
        inventory.dieu_chinh(conn, nguoi, row["id"], ton_ban_dau,
                             du_lieu.get("ly_do") or "Tồn ban đầu khi thêm mặt hàng")
    return lay_bien_the(conn, row["id"])


def sua_bien_the(conn, nguoi: NguoiDung, bien_the_id: int, du_lieu: dict) -> dict:
    """Sửa mọi thuộc tính mô tả của mặt hàng. Số tồn chỉ đổi qua sổ cái (kiểm kê), giá qua lịch sử giá."""
    hien_tai = conn.execute("SELECT * FROM bien_the WHERE id = %s FOR UPDATE", (bien_the_id,)).fetchone()
    if not hien_tai:
        raise khong_tim_thay("biến thể")
    if du_lieu.get("ten_mau_moi"):
        du_lieu = {**du_lieu, "mau_hang_id": _mau_hang_cho(conn, {**du_lieu, "mau_hang_id": None})}
    if "loai_go" in du_lieu:
        _kiem_tra_loai_go(conn, du_lieu["loai_go"])
    doi = {k: du_lieu[k] for k in TRUONG_SUA if k in du_lieu and du_lieu[k] != hien_tai[k]}
    if doi:
        gan = ", ".join(f"{k} = %({k})s" for k in doi)
        tham_so = {**doi, "id": bien_the_id}
        if "thuoc_tinh" in doi:
            tham_so["thuoc_tinh"] = Jsonb(doi["thuoc_tinh"])
        conn.execute(f"UPDATE bien_the SET {gan} WHERE id = %(id)s", tham_so)
    gia_doi = _dat_cac_gia(conn, nguoi, bien_the_id, du_lieu, lay_bien_the(conn, bien_the_id))
    if not doi and not gia_doi:
        raise LoiNghiepVu("KHONG_CO_THAY_DOI", "Không có thông tin nào thay đổi")
    if doi:
        audit.ghi(conn, nguoi, "SUA_BIEN_THE", "BIEN_THE", bien_the_id,
                  truoc={k: hien_tai[k] for k in doi}, sau=doi)
    return lay_bien_the(conn, bien_the_id)


def xoa_bien_the(conn, nguoi: NguoiDung, bien_the_id: int, ly_do: str) -> dict:
    """Xóa khỏi danh mục = ngừng bán: số tồn còn lại ghi điều chỉnh về 0, sổ cái và lịch sử giá giữ nguyên
    (không xóa cứng được vì đơn cũ, phiếu nhập, sổ cái đều tham chiếu). Có thể khôi phục."""
    from . import inventory
    if not ly_do or not ly_do.strip():
        raise LoiNghiepVu("THIEU_LY_DO", "Xóa mặt hàng bắt buộc ghi lý do")
    inventory.khoa_bien_the(conn, [bien_the_id])
    bt = lay_bien_the(conn, bien_the_id)
    if not bt["dang_ban"]:
        raise LoiNghiepVu("DA_XOA", "Mặt hàng đã bị xóa khỏi danh mục trước đó")
    if bt["dang_giu_cho"]:
        raise LoiNghiepVu("DANG_GIU_CHO", f"Đang có đơn giữ {bt['dang_giu_cho']} cái — xử lý đơn trước khi xóa", 409)
    bo = conn.execute(
        """SELECT b.ma FROM thanh_phan_bo tp JOIN bo_san_pham b ON b.id = tp.bo_san_pham_id
           WHERE tp.bien_the_id = %s AND b.dang_ban""", (bien_the_id,)).fetchall()
    if bo:
        raise LoiNghiepVu("THUOC_BO_SAN_PHAM", "Mặt hàng là thành phần của bộ đang bán: "
                          + ", ".join(r["ma"] for r in bo), 409)
    if bt["ton_hien_co"]:
        inventory.dieu_chinh(conn, nguoi, bien_the_id, -bt["ton_hien_co"], f"Xóa khỏi danh mục: {ly_do.strip()}")
    conn.execute("UPDATE bien_the SET dang_ban = FALSE WHERE id = %s", (bien_the_id,))
    audit.ghi(conn, nguoi, "XOA_BIEN_THE", "BIEN_THE", bien_the_id,
              truoc={"dang_ban": True, "ton_hien_co": bt["ton_hien_co"]}, sau={"dang_ban": False, "ly_do": ly_do})
    return lay_bien_the(conn, bien_the_id)


def khoi_phuc_bien_the(conn, nguoi: NguoiDung, bien_the_id: int) -> dict:
    row = conn.execute("UPDATE bien_the SET dang_ban = TRUE WHERE id = %s AND NOT dang_ban RETURNING id",
                       (bien_the_id,)).fetchone()
    if not row:
        raise LoiNghiepVu("KHONG_CAN_KHOI_PHUC", "Mặt hàng không ở trạng thái đã xóa")
    audit.ghi(conn, nguoi, "KHOI_PHUC_BIEN_THE", "BIEN_THE", bien_the_id, truoc={"dang_ban": False},
              sau={"dang_ban": True})
    return lay_bien_the(conn, bien_the_id)
