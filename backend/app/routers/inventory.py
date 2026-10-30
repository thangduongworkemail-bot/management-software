from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from .. import db
from ..deps import chi_chu, nguoi_dung, nhan_vien_ban_hang
from ..errors import LoiNghiepVu, khong_tim_thay
from ..security import NguoiDung
from ..services import audit, inventory

router = APIRouter(prefix="/api/kho", tags=["Kho & Xưởng"])


class DongNhap(BaseModel):
    bien_the_id: int
    so_luong: int = Field(gt=0)
    gia_von_don_vi: int = Field(ge=0)


class PhieuNhap(BaseModel):
    nha_cung_cap_id: int
    dong: list[DongNhap] = Field(min_length=1)
    ghi_chu: str | None = None
    anh_chung_tu_url: str | None = None


class DieuChinh(BaseModel):
    bien_the_id: int
    so_luong: int
    ly_do: str = Field(min_length=3)


class DongKiemKe(BaseModel):
    bien_the_id: int
    so_thuc_te: int = Field(ge=0)


class KiemKe(BaseModel):
    dong: list[DongKiemKe] = Field(min_length=1)
    ly_do: str = Field(min_length=3)


class TaoXuong(BaseModel):
    ten: str = Field(min_length=2, max_length=120)
    lien_he: str | None = None
    so_dien_thoai: str | None = Field(default=None, pattern=r"^[0-9 +().-]{6,20}$")
    dia_chi: str | None = None
    loai_hang: str | None = None
    ma_so_thue: str | None = Field(default=None, pattern=r"^[0-9-]{10,14}$")
    ghi_chu: str | None = None
    han_thanh_toan_ngay: int | None = Field(default=None, ge=0, le=365)

    @field_validator("*", mode="before")
    @classmethod
    def o_trong_la_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class ChiTraXuong(BaseModel):
    so_tien: int = Field(gt=0)
    ghi_chu: str | None = None


@router.get("/so-cai")
def so_cai(bien_the_id: int | None = None, gioi_han: int = 100, _: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return inventory.so_cai(conn, bien_the_id, min(gioi_han, 500))


@router.get("/ton-theo-xuong")
def ton_theo_xuong(_: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return inventory.ton_theo_xuong(conn)


@router.get("/sap-het")
def sap_het(_: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return inventory.sap_het(conn)


@router.get("/giu-cho")
def dang_giu_cho(_: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return conn.execute(
            """SELECT dh.id, dh.ma, dh.tong_tien, dh.giu_cho_den, dh.trang_thai,
                      (SELECT string_agg(mo_ta, ', ') FROM dong_don WHERE don_hang_id = dh.id) AS tom_tat
               FROM don_hang dh
               WHERE EXISTS (SELECT 1 FROM so_cai_ton s WHERE s.don_hang_id = dh.id AND s.loai IN ('GIU_CHO', 'NHA_CHO')
                             GROUP BY s.don_hang_id HAVING sum(s.so_luong) > 0)
               ORDER BY dh.giu_cho_den NULLS LAST""").fetchall()


@router.get("/xuong")
def xuong(nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        rows = conn.execute("SELECT * FROM nha_cung_cap ORDER BY id").fetchall()
    if not nguoi.xem_gia_von:
        rows = [{k: v for k, v in r.items() if k != "so_du_cong_no"} for r in rows]
    return rows


@router.get("/phieu-nhap")
def ds_phieu_nhap(nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        rows = conn.execute(
            """SELECT pn.*, ncc.ten AS xuong, tk.ho_ten AS nguoi_lap,
                      (SELECT sum(so_luong)::int FROM lo_nhap WHERE phieu_nhap_id = pn.id) AS tong_so_luong
               FROM phieu_nhap pn JOIN nha_cung_cap ncc ON ncc.id = pn.nha_cung_cap_id
               JOIN tai_khoan tk ON tk.id = pn.nguoi_lap_id ORDER BY pn.ngay_nhap DESC LIMIT 100""").fetchall()
    if not nguoi.xem_gia_von:
        rows = [{k: v for k, v in r.items() if k != "tong_tien"} for r in rows]
    return rows


@router.post("/phieu-nhap")
def tao_phieu_nhap(body: PhieuNhap, nguoi: NguoiDung = Depends(nhan_vien_ban_hang)):
    with db.transaction() as conn:
        phieu = inventory.tao_phieu_nhap(conn, nguoi, body.nha_cung_cap_id, [d.model_dump() for d in body.dong],
                                         body.ghi_chu, body.anh_chung_tu_url)
    return phieu if nguoi.xem_gia_von else {k: v for k, v in phieu.items() if k != "tong_tien"}


@router.post("/dieu-chinh")
def dieu_chinh(body: DieuChinh, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return inventory.dieu_chinh(conn, nguoi, body.bien_the_id, body.so_luong, body.ly_do)


@router.post("/kiem-ke")
def kiem_ke(body: KiemKe, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return inventory.kiem_ke(conn, nguoi, [d.model_dump() for d in body.dong], body.ly_do)


@router.post("/xuong")
def tao_xuong(body: TaoXuong, nguoi: NguoiDung = Depends(nhan_vien_ban_hang)):
    """Thợ lập phiếu nhập cũng thêm được xưởng mới ngay tại chỗ."""
    with db.transaction() as conn:
        row = inventory.tao_xuong(conn, nguoi, body.model_dump())
    return row if nguoi.xem_gia_von else {k: v for k, v in row.items() if k != "so_du_cong_no"}


@router.post("/xuong/{ncc_id}/chi-tra")
def chi_tra_xuong(ncc_id: int, body: ChiTraXuong, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        ncc = conn.execute("SELECT * FROM nha_cung_cap WHERE id = %s FOR UPDATE", (ncc_id,)).fetchone()
        if not ncc:
            raise khong_tim_thay("xưởng")
        if body.so_tien > ncc["so_du_cong_no"]:
            raise LoiNghiepVu("VUOT_CONG_NO", "Số tiền trả vượt số đang nợ xưởng")
        conn.execute("INSERT INTO chi_tra_xuong (nha_cung_cap_id, so_tien, nguoi_chi_id, ghi_chu) VALUES (%s, %s, %s, %s)",
                     (ncc_id, body.so_tien, nguoi.id, body.ghi_chu))
        moi = conn.execute("UPDATE nha_cung_cap SET so_du_cong_no = so_du_cong_no - %s WHERE id = %s RETURNING *",
                           (body.so_tien, ncc_id)).fetchone()
        audit.ghi(conn, nguoi, "TRA_NO_XUONG", "NHA_CUNG_CAP", ncc_id,
                  truoc={"so_du": ncc["so_du_cong_no"]}, sau={"so_du": moi["so_du_cong_no"], "so_tien": body.so_tien})
        return moi
