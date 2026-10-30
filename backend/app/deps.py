"""Xác thực JWT và phân quyền endpoint theo vai trò (RBAC)."""
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .errors import LoiNghiepVu, khong_du_quyen
from .security import NguoiDung, giai_ma_token

_bearer = HTTPBearer(auto_error=False)

CHU = "CHU"
THO = "THO"
QUAN_TRI = "QUAN_TRI"


def nguoi_tu_token(token: str) -> NguoiDung:
    try:
        payload = giai_ma_token(token)
    except jwt.ExpiredSignatureError:
        raise LoiNghiepVu("PHIEN_HET_HAN", "Phiên đăng nhập đã hết hạn", 401)
    except jwt.PyJWTError:
        raise LoiNghiepVu("TOKEN_KHONG_HOP_LE", "Token không hợp lệ", 401)
    with db.transaction() as conn:
        tk = conn.execute("SELECT id, vai_tro, ho_ten, kich_hoat FROM tai_khoan WHERE id = %s",
                          (int(payload["sub"]),)).fetchone()
    if not tk or not tk["kich_hoat"]:
        raise LoiNghiepVu("TAI_KHOAN_KHOA", "Tài khoản không tồn tại hoặc đã bị khóa", 401)
    return NguoiDung(id=tk["id"], vai_tro=tk["vai_tro"], ho_ten=tk["ho_ten"])


def nguoi_dung(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> NguoiDung:
    if not cred:
        raise LoiNghiepVu("CHUA_DANG_NHAP", "Cần đăng nhập", 401)
    return nguoi_tu_token(cred.credentials)


def can(*vai_tro: str):
    def kiem_tra(nguoi: NguoiDung = Depends(nguoi_dung)) -> NguoiDung:
        if nguoi.vai_tro not in vai_tro:
            raise khong_du_quyen()
        return nguoi
    return kiem_tra


chi_chu = can(CHU)
chu_hoac_quan_tri = can(CHU, QUAN_TRI)
nhan_vien_ban_hang = can(CHU, THO)
