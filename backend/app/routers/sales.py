from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from .. import db
from ..deps import chi_chu, nguoi_dung, nhan_vien_ban_hang
from ..security import NguoiDung
from ..services import orders

router = APIRouter(prefix="/api", tags=["Bán hàng"])


class KhachHangVao(BaseModel):
    ten: str | None = None
    so_dien_thoai: str | None = None
    ma_so_thue: str | None = Field(default=None, pattern=r"^[0-9]{10}(-?[0-9]{3})?$")
    email: str | None = None
    dia_chi: str | None = None


class DongDonVao(BaseModel):
    ma: str | None = None
    bien_the_id: int | None = None
    bo_san_pham_id: int | None = None
    so_luong: int = Field(default=1, gt=0)
    don_gia_ban: int | None = Field(default=None, ge=0)
    kich_thuoc: str | None = None


class TaoDon(BaseModel):
    dong: list[DongDonVao] = Field(min_length=1)
    khach_hang_id: int | None = None
    khach_hang: KhachHangVao | None = None
    can_hoa_don: bool = False
    ghi_chu: str | None = None
    idempotency_key: str | None = None


class LyDo(BaseModel):
    ly_do: str = Field(min_length=2)


class Duyet(BaseModel):
    dong_y: bool
    ly_do: str | None = None


class XungDot(BaseModel):
    cach: str = Field(pattern=r"^(CHO_XUONG_GIAO|HUY)$")


class BaoGiaVao(BaseModel):
    dong: list[DongDonVao] = Field(min_length=1)
    khach_hang_id: int | None = None
    khach_hang: KhachHangVao | None = None
    ghi_chu: str | None = None


def _du_lieu(body, idempotency_key: str | None) -> dict:
    d = body.model_dump()
    d["idempotency_key"] = idempotency_key or d.get("idempotency_key")
    return d


@router.post("/don-hang")
def tao_don(body: TaoDon, nguoi: NguoiDung = Depends(nhan_vien_ban_hang),
            idempotency_key: str | None = Header(default=None)):
    with db.transaction() as conn:
        return orders.tao_don(conn, nguoi, _du_lieu(body, idempotency_key))


@router.get("/don-hang")
def danh_sach(trang_thai: str | None = None, q: str | None = None, gioi_han: int = 50,
              _: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return orders.danh_sach_don(conn, trang_thai, q, min(gioi_han, 200))


@router.get("/don-hang/ma/{ma}")
def theo_ma(ma: str, nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return orders.lay_don(conn, orders.id_theo_ma(conn, ma), nguoi)


@router.get("/don-hang/{don_id}")
def chi_tiet(don_id: int, nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return orders.lay_don(conn, don_id, nguoi)


@router.post("/don-hang/{don_id}/huy")
def huy(don_id: int, body: LyDo, nguoi: NguoiDung = Depends(nhan_vien_ban_hang)):
    with db.transaction() as conn:
        return orders.huy_don(conn, nguoi, don_id, body.ly_do)


@router.post("/don-hang/{don_id}/ban-chiu")
def ban_chiu(don_id: int, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return orders.ban_chiu(conn, nguoi, don_id)


@router.post("/don-hang/{don_id}/tra-hang")
def tra_hang(don_id: int, body: LyDo, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return orders.tra_hang(conn, nguoi, don_id, body.ly_do)


@router.post("/don-hang/{don_id}/xung-dot")
def xung_dot(don_id: int, body: XungDot, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return orders.giai_quyet_xung_dot(conn, nguoi, don_id, body.cach)


@router.post("/don-hang/{don_id}/giao-hang")
def giao_hang(don_id: int, nguoi: NguoiDung = Depends(nhan_vien_ban_hang)):
    with db.transaction() as conn:
        return orders.giao_hang(conn, nguoi, don_id)


@router.get("/yeu-cau-duyet")
def yeu_cau_duyet(_: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return orders.yeu_cau_cho_duyet(conn)


@router.post("/yeu-cau-duyet/{yc_id}")
def duyet(yc_id: int, body: Duyet, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return orders.duyet_yeu_cau(conn, nguoi, yc_id, body.dong_y, body.ly_do)


@router.post("/bao-gia")
def tao_bao_gia(body: BaoGiaVao, nguoi: NguoiDung = Depends(nhan_vien_ban_hang)):
    with db.transaction() as conn:
        return orders.tao_bao_gia(conn, nguoi, body.model_dump())


@router.get("/bao-gia")
def ds_bao_gia(_: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return conn.execute(
            """SELECT bg.id, bg.ma, bg.tong_tien, bg.tao_luc, bg.het_han_luc, bg.ma_chia_se, kh.ten AS ten_khach,
                      bg.het_han_luc < now() AS da_het_han
               FROM bao_gia bg LEFT JOIN khach_hang kh ON kh.id = bg.khach_hang_id
               ORDER BY bg.tao_luc DESC LIMIT 100""").fetchall()


@router.get("/bao-gia/{bg_id}")
def chi_tiet_bao_gia(bg_id: int, _: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return orders.lay_bao_gia(conn, bg_id)


@router.post("/bao-gia/{bg_id}/tao-don")
def tao_don_tu_bao_gia(bg_id: int, nguoi: NguoiDung = Depends(nhan_vien_ban_hang),
                       idempotency_key: str | None = Header(default=None)):
    with db.transaction() as conn:
        return orders.tao_don_tu_bao_gia(conn, nguoi, bg_id, idempotency_key)


@router.get("/public/bao-gia/{ma_chia_se}", tags=["Công khai"])
def bao_gia_cong_khai(ma_chia_se: str):
    with db.transaction() as conn:
        return orders.bao_gia_cong_khai(conn, ma_chia_se)


@router.get("/khach-hang")
def khach_hang(q: str | None = None, nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        if q:
            rows = conn.execute(
                """SELECT * FROM khach_hang
                   WHERE f_chuan_hoa(ten) LIKE '%%' || f_chuan_hoa(%s) || '%%' OR so_dien_thoai LIKE %s
                   ORDER BY ten LIMIT 20""", (q, f"%{q}%")).fetchall()
        else:
            rows = conn.execute("SELECT * FROM khach_hang ORDER BY du_no DESC, ten LIMIT 100").fetchall()
    return rows
