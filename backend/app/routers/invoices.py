from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import db
from ..deps import chi_chu, nguoi_dung, nhan_vien_ban_hang
from ..security import NguoiDung
from ..services import invoices

router = APIRouter(prefix="/api/hoa-don", tags=["Hóa đơn điện tử"])


class NguoiMua(BaseModel):
    ten_nguoi_mua: str | None = None
    ma_so_thue: str | None = Field(default=None, pattern=r"^[0-9]{10}(-?[0-9]{3})?$")
    dia_chi: str | None = None
    email: str | None = None


class GhiSo(BaseModel):
    ky_hieu: str = Field(min_length=1)
    so_hoa_don: str = Field(min_length=1)


@router.get("")
def danh_sach(trang_thai: str | None = None, _: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return invoices.danh_sach(conn, trang_thai)


@router.put("/{hd_id}/nguoi-mua")
def cap_nhat_nguoi_mua(hd_id: int, body: NguoiMua, nguoi: NguoiDung = Depends(nhan_vien_ban_hang)):
    with db.transaction() as conn:
        return invoices.cap_nhat_nguoi_mua(conn, nguoi, hd_id, body.model_dump())


@router.post("/{hd_id}/thu-lai")
def thu_lai(hd_id: int, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return invoices.thu_lai(conn, nguoi, hd_id)


@router.post("/{hd_id}/ghi-so")
def ghi_so(hd_id: int, body: GhiSo, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return invoices.ghi_so_thu_cong(conn, nguoi, hd_id, body.ky_hieu, body.so_hoa_don)


@router.get("/goi-du-lieu")
def goi_du_lieu(dinh_dang: str = "csv", _: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        noi_dung, loai = invoices.goi_du_lieu(conn, "json" if dinh_dang == "json" else "csv")
    duoi = "json" if dinh_dang == "json" else "csv"
    return Response(noi_dung, media_type=loai,
                    headers={"Content-Disposition": f'attachment; filename="hoa-don-cho-xuat.{duoi}"'})
