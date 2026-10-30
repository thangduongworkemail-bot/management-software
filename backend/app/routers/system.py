from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .. import db
from ..adapters.storage import LocalStorage, lay_storage, tao_khoa_file
from ..deps import chi_chu, chu_hoac_quan_tri, nguoi_dung, nhan_vien_ban_hang
from ..errors import LoiNghiepVu
from ..security import NguoiDung
from ..services import audit, devices, reports, sync

router = APIRouter(prefix="/api", tags=["Hệ thống"])


class MaGhep(BaseModel):
    ten: str = Field(min_length=2)
    loai: str = Field(pattern=r"^(MAY_QUAY|DIEN_THOAI|MAY_NHAN_TIEN)$")


class GhepNoi(BaseModel):
    ma_ghep: str = Field(pattern=r"^\d{3}\s?\d{3}$")


class XinUrl(BaseModel):
    ten_file: str
    muc_dich: str = Field(pattern=r"^(bien-lai|chung-tu-nhap|anh-mau)$")


class DayDon(BaseModel):
    don: list[dict] = Field(min_length=1, max_length=200)


@router.get("/tong-quan")
def tong_quan(nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return reports.tong_quan(conn, nguoi)


@router.get("/he-thong/trang-thai")
def trang_thai(_: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return reports.trang_thai_he_thong(conn)


@router.get("/cong-no")
def cong_no(_: NguoiDung = Depends(chi_chu)):
    with db.transaction() as conn:
        return {
            "khach_hang": conn.execute(
                """SELECT kh.id, kh.ten, kh.so_dien_thoai, kh.du_no,
                          (SELECT json_agg(json_build_object('id', id, 'ma', ma, 'con_no', tong_tien - giam_tru - da_thu,
                                                             'tao_luc', tao_luc))
                           FROM don_hang WHERE khach_hang_id = kh.id AND trang_thai = 'CON_NO') AS don
                   FROM khach_hang kh WHERE kh.du_no > 0 ORDER BY kh.du_no DESC""").fetchall(),
            "xuong": conn.execute(
                """SELECT ncc.id, ncc.ten, ncc.so_du_cong_no, ncc.han_thanh_toan_ngay,
                          (SELECT max(ngay_nhap) FROM phieu_nhap WHERE nha_cung_cap_id = ncc.id) AS lan_nhap_cuoi,
                          (SELECT max(ngay_nhap) FROM phieu_nhap WHERE nha_cung_cap_id = ncc.id)
                              + make_interval(days => ncc.han_thanh_toan_ngay) AS han_thanh_toan
                   FROM nha_cung_cap ncc WHERE ncc.so_du_cong_no > 0 ORDER BY ncc.so_du_cong_no DESC""").fetchall(),
        }


# --- Nhật ký -----------------------------------------------------------------
@router.get("/nhat-ky")
def nhat_ky(thuc_the: str | None = None, hanh_dong: str | None = None, gioi_han: int = 100,
            _: NguoiDung = Depends(chu_hoac_quan_tri)):
    dieu_kien, tham_so = [], []
    if thuc_the:
        dieu_kien.append("thuc_the = %s")
        tham_so.append(thuc_the)
    if hanh_dong:
        dieu_kien.append("hanh_dong = %s")
        tham_so.append(hanh_dong)
    where = f"WHERE {' AND '.join(dieu_kien)}" if dieu_kien else ""
    with db.transaction() as conn:
        return conn.execute(
            f"""SELECT nk.*, tb.ten AS ten_thiet_bi FROM nhat_ky nk LEFT JOIN thiet_bi tb ON tb.id = nk.thiet_bi_id
                {where} ORDER BY nk.id DESC LIMIT %s""", (*tham_so, min(gioi_han, 500))).fetchall()


@router.get("/nhat-ky/kiem-tra")
def kiem_tra_nhat_ky(_: NguoiDung = Depends(chu_hoac_quan_tri)):
    with db.transaction() as conn:
        loi = audit.kiem_tra_chuoi(conn)
        tong = conn.execute("SELECT count(*)::int AS n FROM nhat_ky").fetchone()["n"]
    return {"toan_ven": not loi, "so_dong": tong, "loi": loi}


# --- Thiết bị ----------------------------------------------------------------
@router.get("/thiet-bi")
def ds_thiet_bi(_: NguoiDung = Depends(chu_hoac_quan_tri)):
    with db.transaction() as conn:
        return devices.danh_sach(conn)


@router.post("/thiet-bi/ma-ghep")
def tao_ma_ghep(body: MaGhep, nguoi: NguoiDung = Depends(chu_hoac_quan_tri)):
    with db.transaction() as conn:
        return devices.tao_ma_ghep(conn, nguoi, body.ten, body.loai)


@router.post("/thiet-bi/ghep-noi", tags=["Máy nhận tiền"])
def ghep_noi(body: GhepNoi):
    with db.transaction() as conn:
        return devices.ghep_noi(conn, body.ma_ghep)


@router.post("/thiet-bi/{tb_id}/thu-hoi")
def thu_hoi(tb_id: int, nguoi: NguoiDung = Depends(chu_hoac_quan_tri)):
    with db.transaction() as conn:
        return devices.thu_hoi(conn, nguoi, tb_id)


# --- Đồng bộ ngoại tuyến -------------------------------------------------------
@router.get("/sync/danh-muc")
def sync_danh_muc(nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        return sync.danh_muc(conn, nguoi)


@router.post("/sync/don-hang")
def sync_don_hang(body: DayDon, nguoi: NguoiDung = Depends(nhan_vien_ban_hang)):
    return {"ket_qua": sync.day_don_ngoai_tuyen(db.transaction, nguoi, body.don)}


# --- File (ảnh biên lai, chứng từ, ảnh mẫu) -----------------------------------
@router.post("/files/presign")
def xin_url_tai_len(body: XinUrl, _: NguoiDung = Depends(nguoi_dung)):
    url = lay_storage().tao_url_tai_len(tao_khoa_file(body.muc_dich, body.ten_file))
    return url.__dict__


@router.put("/files/upload/{khoa:path}", include_in_schema=False)
async def tai_len_cuc_bo(khoa: str, het_han: int, chu_ky: str, request: Request):
    storage = lay_storage()
    if not isinstance(storage, LocalStorage) or not storage.kiem_tra_chu_ky(khoa, het_han, chu_ky):
        raise LoiNghiepVu("URL_KHONG_HOP_LE", "URL tải lên không hợp lệ hoặc đã hết hạn", 403)
    noi_dung = await request.body()
    if len(noi_dung) > 10 * 1024 * 1024:
        raise LoiNghiepVu("FILE_QUA_LON", "File tối đa 10MB", 413)
    return {"file_url": storage.luu(khoa, noi_dung)}
