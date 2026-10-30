import json
import secrets
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from .. import db
from ..adapters.payment import GiaoDichVao, xac_thuc_webhook_payos
from ..config import settings
from ..deps import chi_chu, chu_hoac_quan_tri, nhan_vien_ban_hang
from ..errors import LoiNghiepVu
from ..security import NguoiDung
from ..services import devices, orders, payments

router = APIRouter(prefix="/api", tags=["Thanh toán & Đối soát"])


class ThuTienMat(BaseModel):
    so_tien: int = Field(gt=0)
    la_coc: bool = False


class XacNhanTay(BaseModel):
    so_tien: int | None = Field(default=None, gt=0)
    bon_so_cuoi: str | None = Field(default=None, pattern=r"^\d{4}$")
    anh_bien_lai_url: str | None = None


class GhepGiaoDich(BaseModel):
    don_id: int


class GhiChu(BaseModel):
    ghi_chu: str | None = None


class GiaoDichThietBi(BaseModel):
    ma_giao_dich: str = Field(min_length=3)
    so_tien: int = Field(gt=0)
    noi_dung: str = ""
    ngan_hang: str | None = None
    thoi_diem: datetime | None = None


class MoPhongTienVe(BaseModel):
    ma_don: str
    so_tien: int | None = Field(default=None, gt=0)


@router.post("/don-hang/{don_id}/thanh-toan")
def thu_tien_mat(don_id: int, body: ThuTienMat, nguoi: NguoiDung = Depends(nhan_vien_ban_hang)):
    """Thu tiền mặt tại quầy. Chuyển khoản chỉ ghi nhận qua webhook / Máy nhận tiền / xác nhận tay của Chủ."""
    with db.transaction() as conn:
        return payments.ghi_nhan_thanh_toan(conn, nguoi, don_id, body.so_tien, "TIEN_MAT", la_coc=body.la_coc)


@router.post("/don-hang/{don_id}/xac-nhan-tay")
def xac_nhan_tay(don_id: int, body: XacNhanTay, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return payments.xac_nhan_tay(conn, nguoi, don_id, body.so_tien, body.bon_so_cuoi, body.anh_bien_lai_url)


@router.post("/don-hang/{don_id}/chap-nhan-giam")
def chap_nhan_giam(don_id: int, body: GhiChu, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return payments.chap_nhan_giam(conn, nguoi, don_id, body.ghi_chu)


@router.get("/doi-soat")
def doi_soat(_: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return payments.danh_sach_doi_soat(conn)


@router.post("/doi-soat/thanh-toan/{tt_id}/da-khop")
def da_khop(tt_id: int, body: GhiChu, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return payments.danh_dau_da_khop(conn, nguoi, tt_id, body.ghi_chu)


@router.post("/doi-soat/giao-dich/{gd_id}/ghep")
def ghep(gd_id: int, body: GhepGiaoDich, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return payments.ghep_giao_dich(conn, nguoi, gd_id, body.don_id)


@router.get("/chot-ngay")
def tong_ket_ngay(ngay: date | None = None, _: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return payments.tong_ket_ngay(conn, ngay)


@router.post("/chot-ngay")
def chot_so(ngay: date | None = None, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return payments.chot_so_ngay(conn, nguoi, ngay)


# ---------------------------------------------------------------------------
# Tiền về tự động
# ---------------------------------------------------------------------------
@router.post("/webhook/payos", tags=["Webhook"])
async def webhook_payos(request: Request):
    try:
        body = await request.json()
        gd = xac_thuc_webhook_payos(body)
    except (ValueError, KeyError) as e:
        raise LoiNghiepVu("WEBHOOK_KHONG_HOP_LE", str(e), 400)
    with db.transaction() as conn:
        kq = payments.nhan_giao_dich(conn, gd)
    return {"success": True, "ket_qua": kq["ket_qua"]}


async def _thiet_bi_da_ky(request: Request, x_thiet_bi: int, x_thoi_gian: str, x_chu_ky: str) -> tuple[dict, bytes]:
    raw = await request.body()
    with db.transaction() as conn:
        tb = devices.xac_thuc_yeu_cau(conn, x_thiet_bi, x_thoi_gian, x_chu_ky, raw)
        devices.bao_song(conn, tb["id"])
    return tb, raw


@router.post("/thiet-bi/giao-dich", tags=["Máy nhận tiền"])
async def giao_dich_tu_thiet_bi(request: Request, x_thiet_bi: int = Header(), x_thoi_gian: str = Header(),
                                x_chu_ky: str = Header()):
    tb, raw = await _thiet_bi_da_ky(request, x_thiet_bi, x_thoi_gian, x_chu_ky)
    if tb["loai"] != "MAY_NHAN_TIEN":
        raise LoiNghiepVu("KHONG_DU_QUYEN", "Thiết bị này không được báo giao dịch", 403)
    body = GiaoDichThietBi.model_validate(json.loads(raw))
    gd = GiaoDichVao(nguon="MAY_NHAN_TIEN", ma_giao_dich=body.ma_giao_dich, so_tien=body.so_tien,
                     noi_dung=body.noi_dung, ngan_hang=body.ngan_hang, thoi_diem=body.thoi_diem,
                     du_lieu_goc=json.loads(raw))
    with db.transaction() as conn:
        kq = payments.nhan_giao_dich(conn, gd, thiet_bi_id=tb["id"])
    return {"ket_qua": kq["ket_qua"]}


@router.post("/thiet-bi/bao-song", tags=["Máy nhận tiền"])
async def bao_song(request: Request, x_thiet_bi: int = Header(), x_thoi_gian: str = Header(),
                   x_chu_ky: str = Header()):
    await _thiet_bi_da_ky(request, x_thiet_bi, x_thoi_gian, x_chu_ky)
    return {"ok": True}


@router.post("/dev/mo-phong-tien-ve", tags=["Demo"])
def mo_phong_tien_ve(body: MoPhongTienVe, nguoi: NguoiDung = Depends(chu_hoac_quan_tri)):
    """Chỉ bật ở DEV_MODE: giả lập Máy nhận tiền báo một giao dịch chuyển khoản cho đơn."""
    if not settings.dev_mode:
        raise LoiNghiepVu("KHONG_HO_TRO", "Chỉ dùng trong chế độ demo", 404)
    with db.transaction() as conn:
        don = orders.lay_don(conn, orders.id_theo_ma(conn, body.ma_don), nguoi)
        so_tien = body.so_tien or don["con_phai_thu"]
        if so_tien <= 0:
            raise LoiNghiepVu("DA_THU_DU", "Đơn đã thu đủ tiền", 409)
        gd = GiaoDichVao(nguon="MAY_NHAN_TIEN", ma_giao_dich=f"FT{secrets.token_hex(5).upper()}", so_tien=so_tien,
                         noi_dung=f"{don['ma']} chuyen tien mua hang", ngan_hang="Vietcombank",
                         thoi_diem=datetime.now(), du_lieu_goc={"mo_phong": True})
        return payments.nhan_giao_dich(conn, gd)
