import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from .. import db
from ..deps import chi_chu, nguoi_dung
from ..domain.dimension import LoiKichThuoc, doc_kich_thuoc
from ..errors import LoiNghiepVu
from ..security import NguoiDung
from ..services import catalog

router = APIRouter(prefix="/api/hang-hoa", tags=["Hàng hóa & Giá"])


class DatGia(BaseModel):
    loai_gia: str = Field(pattern=r"^(GIA_VON|GIA_NIEM_YET|GIA_SAN|GIA_NHOM_KHACH)$")
    so_tien: int = Field(ge=0)
    nhom_khach: str | None = None
    ghi_chu: str | None = None


class TinhGia(BaseModel):
    kich_thuoc: str


class DocKichThuoc(BaseModel):
    text: str
    min_mm: int = 400
    max_mm: int = 3000


class DongNghia(BaseModel):
    tu_khoa: str = Field(min_length=1)
    tu_chuan: str = Field(min_length=1)


class ThongTinBienThe(BaseModel):
    """Mọi thuộc tính mô tả của một mặt hàng; ô để trống gửi lên là null."""
    mau_hang_id: int | None = None
    ten_mau_moi: str | None = None          # tạo mẫu mới trong loai_hang_id thay vì chọn mau_hang_id
    loai_hang_id: int | None = None
    ma_noi_bo: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Za-z0-9-]*$")
    ten_hien_thi: str | None = Field(default=None, min_length=2)
    loai_go: str | None = None
    dai_mm: int | None = Field(default=None, ge=0)
    rong_mm: int | None = Field(default=None, ge=0)
    cao_mm: int | None = Field(default=None, ge=0)
    mau_sac: str | None = None
    hoan_thien: str | None = None
    kieu_dang: str | None = None
    vat_lieu_phu: str | None = None
    xuat_xu: str | None = None
    khoi_luong_kg: int | None = Field(default=None, ge=0)
    bao_hanh_thang: int | None = Field(default=None, ge=0, le=240)
    don_vi_tinh: str | None = None
    mo_ta: str | None = None
    anh_url: str | None = None
    ton_toi_thieu: int | None = Field(default=None, ge=0)
    thuoc_tinh: dict | None = None
    gia_von: int | None = Field(default=None, ge=0)
    gia_san: int | None = Field(default=None, ge=0)
    gia_niem_yet: int | None = Field(default=None, ge=0)

    @field_validator("*", mode="before")
    @classmethod
    def o_trong_la_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class TaoBienThe(ThongTinBienThe):
    ma_noi_bo: str = Field(pattern=r"^[A-Z0-9][A-Za-z0-9-]*$")
    ten_hien_thi: str = Field(min_length=2)
    dat_theo_kich_thuoc: bool = False
    ton_ban_dau: int = Field(default=0, ge=0)     # số đếm được khi thêm hàng phát hiện lúc kiểm kê
    ly_do: str | None = None


class SuaBienThe(ThongTinBienThe):
    pass


class XoaBienThe(BaseModel):
    ly_do: str = Field(min_length=3)


@router.get("/tim-kiem")
def tim_kiem(q: str, gioi_han: int = 20, nguoi: NguoiDung = Depends(nguoi_dung)):
    bat_dau = time.perf_counter()
    with db.transaction() as conn:
        kq = catalog.tim_kiem(conn, q, nguoi, min(gioi_han, 50))
    return {"ket_qua": kq, "thoi_gian_ms": round((time.perf_counter() - bat_dau) * 1000, 1)}


@router.get("")
def danh_sach(loai_hang_id: int | None = None, ca_ngung_ban: bool = False, nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return catalog.danh_sach(conn, nguoi, loai_hang_id, ca_ngung_ban)


@router.get("/loai-hang")
def loai_hang(_: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return catalog.loai_hang(conn)


@router.get("/mau-hang")
def mau_hang(_: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return conn.execute("SELECT m.id, m.ten, m.loai_hang_id, l.ten AS loai_hang FROM mau_hang m "
                            "JOIN loai_hang l ON l.id = m.loai_hang_id ORDER BY m.ten").fetchall()


@router.get("/he-so-go")
def he_so_go(_: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return conn.execute("SELECT * FROM he_so_go ORDER BY loai_go").fetchall()


@router.get("/bien-the/{bien_the_id}")
def bien_the(bien_the_id: int, nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        row = catalog.lay_bien_the(conn, bien_the_id)
        row["xuong"] = conn.execute(
            """SELECT ncc.ten, mx.ma_hang_xuong, mx.so_ngay_giao, mx.uu_tien
                      {gia}
               FROM ma_xuong mx JOIN nha_cung_cap ncc ON ncc.id = mx.nha_cung_cap_id
               WHERE mx.bien_the_id = %s ORDER BY mx.uu_tien""".format(
                gia=", mx.gia_nhap" if nguoi.xem_gia_von else ""), (bien_the_id,)).fetchall()
        return catalog.an_gia_noi_bo(row, nguoi)


@router.get("/bo/{bo_id}")
def bo_san_pham(bo_id: int, nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return catalog.an_gia_noi_bo(catalog.lay_bo(conn, bo_id), nguoi)


@router.post("/bien-the")
def tao_bien_the(body: TaoBienThe, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return catalog.an_gia_noi_bo(catalog.tao_bien_the(conn, nguoi, body.model_dump()), nguoi)


@router.patch("/bien-the/{bien_the_id}")
def sua_bien_the(bien_the_id: int, body: SuaBienThe, nguoi: NguoiDung = Depends(chi_chu)):
    """Chỉ các trường có trong body được sửa; gửi null để xóa trắng một thuộc tính."""
    du_lieu = body.model_dump(exclude_unset=True)
    for khoa in ("ma_noi_bo", "ten_hien_thi", "mau_hang_id"):
        if khoa in du_lieu and du_lieu[khoa] is None:
            del du_lieu[khoa]
    if du_lieu.get("ton_toi_thieu", 0) is None:
        du_lieu["ton_toi_thieu"] = 0
    if du_lieu.get("thuoc_tinh", {}) is None:
        du_lieu["thuoc_tinh"] = {}
    with db.transaction() as conn:
        return catalog.an_gia_noi_bo(catalog.sua_bien_the(conn, nguoi, bien_the_id, du_lieu), nguoi)


@router.post("/bien-the/{bien_the_id}/xoa")
def xoa_bien_the(bien_the_id: int, body: XoaBienThe, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return catalog.an_gia_noi_bo(catalog.xoa_bien_the(conn, nguoi, bien_the_id, body.ly_do), nguoi)


@router.post("/bien-the/{bien_the_id}/khoi-phuc")
def khoi_phuc_bien_the(bien_the_id: int, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return catalog.an_gia_noi_bo(catalog.khoi_phuc_bien_the(conn, nguoi, bien_the_id), nguoi)


@router.post("/bien-the/{bien_the_id}/gia")
def dat_gia(bien_the_id: int, body: DatGia, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        catalog.dat_gia(conn, nguoi, bien_the_id, body.loai_gia, body.so_tien, body.nhom_khach, body.ghi_chu)
        return catalog.an_gia_noi_bo(catalog.lay_bien_the(conn, bien_the_id), nguoi)


@router.get("/bien-the/{bien_the_id}/lich-su-gia")
def lich_su_gia(bien_the_id: int, _: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return catalog.lich_su_gia(conn, bien_the_id)


@router.post("/bien-the/{bien_the_id}/tinh-gia")
def tinh_gia(bien_the_id: int, body: TinhGia, nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        kq = catalog.tinh_gia_dat_rieng(conn, bien_the_id, body.kich_thuoc)
    return catalog.an_gia_noi_bo(kq, nguoi)


@router.post("/kich-thuoc/doc")
def doc(body: DocKichThuoc, _: NguoiDung = Depends(nguoi_dung)):
    try:
        kq = doc_kich_thuoc(body.text, body.min_mm, body.max_mm)
    except LoiKichThuoc as e:
        raise LoiNghiepVu("KICH_THUOC_KHONG_HOP_LE", str(e))
    return {"gia_tri_mm": kq.gia_tri_mm, "canh_bao": kq.canh_bao, "hop_le": kq.hop_le}


@router.get("/tu-dong-nghia")
def ds_dong_nghia(_: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return conn.execute("SELECT id, tu_khoa, tu_chuan FROM tu_dong_nghia ORDER BY tu_khoa").fetchall()


@router.post("/tu-dong-nghia")
def them_dong_nghia(body: DongNghia, nguoi: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return catalog.them_dong_nghia(conn, nguoi, body.tu_khoa, body.tu_chuan)
