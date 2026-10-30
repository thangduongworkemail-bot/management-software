"""Mật khẩu Argon2id, JWT theo vai trò, chữ ký HMAC cho thiết bị ghép nối."""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import settings

_ph = PasswordHasher()  # mặc định là Argon2id


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
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def giai_ma_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def tao_khoa_ky() -> str:
    return secrets.token_urlsafe(32)


def ky_hmac(khoa: str, thong_diep: bytes) -> str:
    return hmac.new(khoa.encode(), thong_diep, hashlib.sha256).hexdigest()


def so_sanh_an_toan(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
