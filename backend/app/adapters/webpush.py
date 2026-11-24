"""Gửi thông báo đẩy Web Push tới PWA đã cài trên điện thoại hoặc máy tính.

- Mã hóa nội dung theo RFC 8291 (Content-Encoding: aes128gcm): chỉ máy nhận giải mã được,
  dịch vụ đẩy trung gian (Google FCM, Apple, Mozilla, Microsoft WNS) không đọc được nội dung.
- Xác thực máy chủ theo RFC 8292 (VAPID): JWT ký ES256 bằng khóa riêng của cửa hàng.

Chỉ dùng thư viện `cryptography` và PyJWT sẵn có, không cần pywebpush.
"""
import base64
import json
import os
import struct
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

KICH_THUOC_BAN_GHI = 4096          # rs: một bản ghi đủ cho mọi thông báo của hệ thống
NOI_DUNG_TOI_DA = KICH_THUOC_BAN_GHI - 16 - 1 - 86   # trừ tag GCM, byte phân cách, phần đầu


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def tu_b64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _hkdf(salt: bytes, ikm: bytes, info: bytes, do_dai: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=do_dai, salt=salt, info=info).derive(ikm)


def khoa_cong_khai_tho(khoa: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey) -> bytes:
    """Điểm công khai P-256 dạng không nén (65 byte, bắt đầu 0x04)."""
    pub = khoa.public_key() if isinstance(khoa, ec.EllipticCurvePrivateKey) else khoa
    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def khoa_rieng_tu_b64u(s: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(tu_b64u(s), "big"), ec.SECP256R1())


def khoa_rieng_ra_b64u(khoa: ec.EllipticCurvePrivateKey) -> str:
    return b64u(khoa.private_numbers().private_value.to_bytes(32, "big"))


def sinh_khoa() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def ma_hoa(noi_dung: bytes, p256dh: str, auth: str, *,
           khoa_tam: ec.EllipticCurvePrivateKey | None = None, salt: bytes | None = None) -> bytes:
    """Mã hóa aes128gcm (RFC 8291 mục 3–4). `khoa_tam`/`salt` chỉ truyền khi kiểm thử với bộ mẫu của RFC."""
    if len(noi_dung) > NOI_DUNG_TOI_DA:
        raise ValueError(f"Nội dung thông báo quá dài ({len(noi_dung)} byte)")
    khoa_may_nhan = tu_b64u(p256dh)
    pub_may_nhan = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), khoa_may_nhan)
    khoa_tam = khoa_tam or sinh_khoa()
    khoa_tam_cong_khai = khoa_cong_khai_tho(khoa_tam)
    salt = salt or os.urandom(16)

    bi_mat_ecdh = khoa_tam.exchange(ec.ECDH(), pub_may_nhan)
    ikm = _hkdf(tu_b64u(auth), bi_mat_ecdh, b"WebPush: info\x00" + khoa_may_nhan + khoa_tam_cong_khai, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ban_ma = AESGCM(cek).encrypt(nonce, noi_dung + b"\x02", None)   # 0x02: bản ghi cuối cùng
    dau = salt + struct.pack("!IB", KICH_THUOC_BAN_GHI, len(khoa_tam_cong_khai)) + khoa_tam_cong_khai
    return dau + ban_ma


def jwt_vapid(endpoint: str, khoa: ec.EllipticCurvePrivateKey, chu_the: str, song_giay: int = 12 * 3600) -> str:
    u = urlsplit(endpoint)
    return jwt.encode({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + song_giay, "sub": chu_the},
                      khoa, algorithm="ES256", headers={"typ": "JWT"})


@dataclass
class KetQuaGui:
    ma_http: int
    noi_dung: str

    @property
    def thanh_cong(self) -> bool:
        return 200 <= self.ma_http < 300

    @property
    def het_hieu_luc(self) -> bool:
        """Người dùng đã gỡ app / tắt thông báo: dịch vụ đẩy trả 404 hoặc 410, phải xóa đăng ký."""
        return self.ma_http in (404, 410)

    @property
    def nen_thu_lai(self) -> bool:
        return self.ma_http == 429 or self.ma_http >= 500


def gui(dang_ky: dict, du_lieu: dict, khoa: ec.EllipticCurvePrivateKey, chu_the: str, *,
        ttl: int = 24 * 3600, khan: bool = False, timeout: float = 15) -> KetQuaGui:
    """Gửi một thông báo. `dang_ky` có endpoint, p256dh, auth (đúng như trình duyệt cấp)."""
    than = ma_hoa(json.dumps(du_lieu, ensure_ascii=False).encode("utf-8"), dang_ky["p256dh"], dang_ky["auth"])
    headers = {
        "Authorization": f"vapid t={jwt_vapid(dang_ky['endpoint'], khoa, chu_the)}, k={b64u(khoa_cong_khai_tho(khoa))}",
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(ttl),
        "Urgency": "high" if khan else "normal",
    }
    r = httpx.post(dang_ky["endpoint"], content=than, headers=headers, timeout=timeout)
    return KetQuaGui(r.status_code, r.text[:300])
