import threading
import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .. import db
from ..deps import chu_hoac_quan_tri, nguoi_dung
from ..errors import LoiNghiepVu, khong_tim_thay
from ..security import NguoiDung, hash_mat_khau, kiem_tra_mat_khau, tao_token
from ..services import audit

router = APIRouter(prefix="/api", tags=["Tài khoản"])

# Chống dò mật khẩu: sai SAI_TOI_DA lần trong CUA_SO_GIAY với cùng (tài khoản, địa chỉ IP) thì tạm khóa đăng nhập
# cho cặp đó tới khi lần sai cũ nhất ra khỏi cửa sổ. Khóa theo cặp nên kẻ dò từ một máy không khóa được Chủ ở máy khác.
# Lưu trong bộ nhớ: đủ cho một tiến trình API như cách triển khai hiện tại.
SAI_TOI_DA = 5
CUA_SO_GIAY = 15 * 60
_lan_sai: dict[tuple[str, str], list[float]] = {}
_lan_sai_lock = threading.Lock()


def _giay_con_khoa(khoa: tuple[str, str]) -> int:
    bay_gio = time.monotonic()
    with _lan_sai_lock:
        ds = [t for t in _lan_sai.get(khoa, []) if bay_gio - t < CUA_SO_GIAY]
        if ds:
            _lan_sai[khoa] = ds
        else:
            _lan_sai.pop(khoa, None)
        return int(CUA_SO_GIAY - (bay_gio - ds[0])) + 1 if len(ds) >= SAI_TOI_DA else 0


def _ghi_lan_sai(khoa: tuple[str, str]) -> int:
    with _lan_sai_lock:
        ds = _lan_sai.setdefault(khoa, [])
        ds.append(time.monotonic())
        return len(ds)


class DangNhap(BaseModel):
    ten_dang_nhap: str
    mat_khau: str


class DoiMatKhau(BaseModel):
    mat_khau_cu: str
    mat_khau_moi: str = Field(min_length=8)


class TaoTaiKhoan(BaseModel):
    ten_dang_nhap: str = Field(min_length=3, pattern=r"^[a-z0-9._-]+$")
    ho_ten: str
    vai_tro: str = Field(pattern=r"^(THO|CHU|QUAN_TRI)$")
    mat_khau: str = Field(min_length=8)


class DatLaiMatKhau(BaseModel):
    mat_khau_moi: str = Field(min_length=8)


@router.post("/auth/dang-nhap")
def dang_nhap(body: DangNhap, request: Request):
    ten = body.ten_dang_nhap.strip().lower()
    khoa = (ten, request.client.host if request.client else "?")
    con = _giay_con_khoa(khoa)
    if con:
        raise LoiNghiepVu("THU_SAI_QUA_NHIEU", f"Sai mật khẩu {SAI_TOI_DA} lần liên tiếp. Thử lại sau "
                                               f"{(con + 59) // 60} phút.", 429)
    with db.transaction() as conn:
        tk = conn.execute("SELECT * FROM tai_khoan WHERE ten_dang_nhap = %s", (ten,)).fetchone()
        dung = bool(tk and tk["kich_hoat"] and kiem_tra_mat_khau(tk["mat_khau_hash"], body.mat_khau))
        if dung:
            nguoi = NguoiDung(id=tk["id"], vai_tro=tk["vai_tro"], ho_ten=tk["ho_ten"])
            audit.ghi(conn, nguoi, "DANG_NHAP", "TAI_KHOAN", tk["id"])
        elif _ghi_lan_sai(khoa) == SAI_TOI_DA:
            audit.ghi(conn, None, "TAM_KHOA_DANG_NHAP", "TAI_KHOAN", ten, sau={"ip": khoa[1], "so_lan_sai": SAI_TOI_DA})
    if not dung:
        raise LoiNghiepVu("SAI_DANG_NHAP", "Sai tài khoản hoặc mật khẩu", 401)
    with _lan_sai_lock:
        _lan_sai.pop(khoa, None)
    return {"token": tao_token(nguoi), "nguoi_dung": nguoi.__dict__}


@router.get("/auth/toi")
def toi(nguoi: NguoiDung = Depends(nguoi_dung)):
    return nguoi.__dict__


@router.post("/auth/doi-mat-khau")
def doi_mat_khau(body: DoiMatKhau, nguoi: NguoiDung = Depends(nguoi_dung)):
    with db.transaction() as conn:
        tk = conn.execute("SELECT mat_khau_hash FROM tai_khoan WHERE id = %s", (nguoi.id,)).fetchone()
        if not kiem_tra_mat_khau(tk["mat_khau_hash"], body.mat_khau_cu):
            raise LoiNghiepVu("SAI_MAT_KHAU", "Mật khẩu cũ không đúng", 400)
        conn.execute("UPDATE tai_khoan SET mat_khau_hash = %s WHERE id = %s", (hash_mat_khau(body.mat_khau_moi), nguoi.id))
        audit.ghi(conn, nguoi, "DOI_MAT_KHAU", "TAI_KHOAN", nguoi.id)
    return {"ok": True}


@router.get("/tai-khoan")
def danh_sach_tai_khoan(_: NguoiDung = Depends(chu_hoac_quan_tri)):
    with db.transaction() as conn:
        return conn.execute("SELECT id, ten_dang_nhap, ho_ten, vai_tro, kich_hoat, tao_luc FROM tai_khoan ORDER BY id"
                            ).fetchall()


@router.post("/tai-khoan")
def tao_tai_khoan(body: TaoTaiKhoan, nguoi: NguoiDung = Depends(chu_hoac_quan_tri)):
    if body.vai_tro != "THO" and nguoi.vai_tro != "QUAN_TRI":
        raise LoiNghiepVu("KHONG_DU_QUYEN", "Chủ cửa hàng chỉ tạo được tài khoản Thợ / Nhân viên", 403)
    with db.transaction() as conn:
        tk = conn.execute(
            """INSERT INTO tai_khoan (ten_dang_nhap, ho_ten, vai_tro, mat_khau_hash) VALUES (%s, %s, %s, %s)
               RETURNING id, ten_dang_nhap, ho_ten, vai_tro, kich_hoat""",
            (body.ten_dang_nhap, body.ho_ten, body.vai_tro, hash_mat_khau(body.mat_khau))).fetchone()
        audit.ghi(conn, nguoi, "TAO_TAI_KHOAN", "TAI_KHOAN", tk["id"],
                  sau={"ten_dang_nhap": tk["ten_dang_nhap"], "vai_tro": tk["vai_tro"]})
    return tk


@router.post("/tai-khoan/{tk_id}/kich-hoat")
def kich_hoat(tk_id: int, bat: bool, nguoi: NguoiDung = Depends(chu_hoac_quan_tri)):
    if tk_id == nguoi.id:
        raise LoiNghiepVu("KHONG_TU_KHOA", "Không thể tự khóa tài khoản của mình")
    with db.transaction() as conn:
        tk = conn.execute("UPDATE tai_khoan SET kich_hoat = %s WHERE id = %s RETURNING id, ho_ten, kich_hoat",
                          (bat, tk_id)).fetchone()
        if not tk:
            raise khong_tim_thay("tài khoản")
        audit.ghi(conn, nguoi, "MO_TAI_KHOAN" if bat else "KHOA_TAI_KHOAN", "TAI_KHOAN", tk_id)
    return tk


@router.post("/tai-khoan/{tk_id}/dat-lai-mat-khau")
def dat_lai_mat_khau(tk_id: int, body: DatLaiMatKhau, nguoi: NguoiDung = Depends(chu_hoac_quan_tri)):
    with db.transaction() as conn:
        tk = conn.execute("UPDATE tai_khoan SET mat_khau_hash = %s WHERE id = %s RETURNING id",
                          (hash_mat_khau(body.mat_khau_moi), tk_id)).fetchone()
        if not tk:
            raise khong_tim_thay("tài khoản")
        audit.ghi(conn, nguoi, "DAT_LAI_MAT_KHAU", "TAI_KHOAN", tk_id)
    return {"ok": True}
