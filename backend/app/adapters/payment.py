"""Adapter thanh toán: xác thực chữ ký webhook PayOS (cổng Napas 247 / VietQR).

PayOS ký `data` bằng HMAC-SHA256 với checksum key trên chuỗi
"khoa1=giatri1&khoa2=giatri2..." đã sắp xếp theo khóa (null -> chuỗi rỗng).
"""
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime

from ..config import settings


@dataclass
class GiaoDichVao:
    nguon: str
    ma_giao_dich: str
    so_tien: int
    noi_dung: str
    ngan_hang: str | None
    thoi_diem: datetime | None
    du_lieu_goc: dict


def _chuoi_ky_payos(data: dict) -> str:
    def gia_tri(v):
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)
    return "&".join(f"{k}={gia_tri(data[k])}" for k in sorted(data))


def ky_payos(data: dict, checksum_key: str | None = None) -> str:
    khoa = (checksum_key or settings.payos_checksum_key).encode()
    return hmac.new(khoa, _chuoi_ky_payos(data).encode("utf-8"), hashlib.sha256).hexdigest()


def xac_thuc_webhook_payos(body: dict, checksum_key: str | None = None) -> GiaoDichVao:
    data = body.get("data")
    chu_ky = body.get("signature")
    if not isinstance(data, dict) or not isinstance(chu_ky, str):
        raise ValueError("Webhook thiếu data/signature")
    if not hmac.compare_digest(ky_payos(data, checksum_key), chu_ky):
        raise ValueError("Chữ ký webhook không hợp lệ")
    thoi_diem = None
    if data.get("transactionDateTime"):
        try:
            thoi_diem = datetime.strptime(data["transactionDateTime"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            thoi_diem = None
    return GiaoDichVao(
        nguon="PAYOS",
        ma_giao_dich=str(data.get("reference") or data.get("paymentLinkId") or data.get("orderCode")),
        so_tien=int(data["amount"]),
        noi_dung=str(data.get("description") or ""),
        ngan_hang=data.get("counterAccountBankName") or None,
        thoi_diem=thoi_diem,
        du_lieu_goc=body,
    )
