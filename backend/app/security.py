"""Mật khẩu Argon2id, JWT theo vai trò, chữ ký HMAC cho thiết bị ghép nối."""
import hashlib
import hmac
import logging
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import settings

log = logging.getLogger("khanhvan.security")
_ph = PasswordHasher()  # mặc định là Argon2id

# Các giá trị từng nằm trong mã nguồn công khai (mặc định cũ, .env.example, docker-compose): ai cũng ký được token.
KHOA_DA_CONG_KHAI = {"khanhvan-dev-secret-doi-khi-trien-khai", "doi-khoa-bi-mat-nay",
                     "doi-khoa-bi-mat-nay-truoc-khi-trien-khai"}
_khoa_sinh: str | None = None
_khoa_lock = threading.Lock()


def khoa_bi_mat() -> str:
    """Khóa ký JWT và chữ ký URL tải tệp.

    Có JWT_SECRET (và không phải giá trị đã công khai) thì dùng. Không thì mỗi CSDL tự sinh một khóa ngẫu nhiên
    một lần, lưu trong bảng cau_hinh_he_thong (giống khóa VAPID), nên khởi động lại máy chủ không làm mất phiên.
    """
    global _khoa_sinh
    if settings.jwt_secret and settings.jwt_secret not in KHOA_DA_CONG_KHAI:
        return settings.jwt_secret
    if _khoa_sinh is None:
        with _khoa_lock:
            if _khoa_sinh is None:
                if settings.jwt_secret:
                    log.warning("JWT_SECRET đang là giá trị mẫu công khai: bỏ qua, dùng khóa tự sinh lưu trong CSDL")
                from . import db
                with db.transaction() as conn:
                    conn.execute("INSERT INTO cau_hinh_he_thong (khoa, gia_tri) VALUES ('JWT_SECRET', %s) "
                                 "ON CONFLICT (khoa) DO NOTHING", (secrets.token_urlsafe(48),))
                    _khoa_sinh = conn.execute(
                        "SELECT gia_tri FROM cau_hinh_he_thong WHERE khoa = 'JWT_SECRET'").fetchone()["gia_tri"]
    return _khoa_sinh


def hash_mat_khau(mat_khau: str) -> str:
    return _ph.hash(mat_khau)


def kiem_tra_mat_khau(mat_khau_hash: str, mat_khau: str) -> bool:
    try:
        return _ph.verify(mat_khau_hash, mat_khau)
    except (VerificationError, InvalidHashError):
        return False


@dataclass(frozen=True)
class NguoiDung:
    id: int
    vai_tro: str
    ho_ten: str

    @property
    def la_chu(self) -> bool:
        return self.vai_tro == "CHU"

    @property
    def xem_gia_von(self) -> bool:
        return self.vai_tro in ("CHU", "QUAN_TRI")


def tao_token(nguoi: NguoiDung) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(nguoi.id),
        "vai_tro": nguoi.vai_tro,
        "ho_ten": nguoi.ho_ten,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, khoa_bi_mat(), algorithm="HS256")


def giai_ma_token(token: str) -> dict:
    return jwt.decode(token, khoa_bi_mat(), algorithms=["HS256"])


def tao_khoa_ky() -> str:
    return secrets.token_urlsafe(32)


def ky_hmac(khoa: str, thong_diep: bytes) -> str:
    return hmac.new(khoa.encode(), thong_diep, hashlib.sha256).hexdigest()


def so_sanh_an_toan(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
