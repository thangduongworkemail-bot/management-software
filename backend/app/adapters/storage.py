"""Adapter lưu trữ file: thư mục cục bộ (mặc định) hoặc S3/Cloudinary qua S3 REST API.

Client không gửi file qua API nghiệp vụ mà xin một URL tải lên có chữ ký (pre-signed),
rồi PUT thẳng file lên đó.
"""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from ..config import settings


@dataclass
class UrlTaiLen:
    khoa: str
    upload_url: str
    file_url: str
    method: str = "PUT"


def tao_khoa_file(muc_dich: str, ten_file: str) -> str:
    duoi = Path(ten_file).suffix.lower()[:10]
    return f"{muc_dich}/{datetime.now():%Y/%m}/{secrets.token_hex(8)}{duoi}"


class LocalStorage:
    ten = "LOCAL"

    def __init__(self, thu_muc: Path | None = None):
        self.thu_muc = thu_muc or settings.local_storage_dir

    def _ky(self, khoa: str, het_han: int) -> str:
        return hmac.new(settings.jwt_secret.encode(), f"{khoa}|{het_han}".encode(), hashlib.sha256).hexdigest()

    def tao_url_tai_len(self, khoa: str, het_han_giay: int = 900) -> UrlTaiLen:
        het_han = int(time.time()) + het_han_giay
        return UrlTaiLen(khoa=khoa,
                         upload_url=f"/api/files/upload/{khoa}?het_han={het_han}&chu_ky={self._ky(khoa, het_han)}",
                         file_url=f"/files/{khoa}")

    def kiem_tra_chu_ky(self, khoa: str, het_han: int, chu_ky: str) -> bool:
        return het_han >= time.time() and hmac.compare_digest(self._ky(khoa, het_han), chu_ky)

    def duong_dan(self, khoa: str) -> Path:
        p = (self.thu_muc / khoa).resolve()
        if self.thu_muc.resolve() not in p.parents:
            raise ValueError("Khóa file không hợp lệ")
        return p

    def luu(self, khoa: str, noi_dung: bytes, content_type: str = "application/octet-stream") -> str:
        p = self.duong_dan(khoa)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(noi_dung)
        return f"/files/{khoa}"


class S3Storage:
    """Ký URL theo AWS Signature V4 (query string) — dùng được với S3, Cloudinary S3 API, MinIO, R2."""
    ten = "S3"

    def __init__(self, endpoint=None, region=None, bucket=None, access_key=None, secret_key=None):
        self.endpoint = (endpoint or settings.s3_endpoint).rstrip("/")
        self.region = region or settings.s3_region
        self.bucket = bucket or settings.s3_bucket
        self.access_key = access_key or settings.s3_access_key
        self.secret_key = secret_key or settings.s3_secret_key

    def presign(self, method: str, khoa: str, het_han_giay: int = 900, now: datetime | None = None,
                virtual_host: bool = False) -> str:
        now = now or datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        ngay = now.strftime("%Y%m%d")
        host = urlparse(self.endpoint).netloc
        if virtual_host:
            host = f"{self.bucket}.{host}"
            canonical_uri = "/" + quote(khoa, safe="/~")
        else:
            canonical_uri = f"/{self.bucket}/" + quote(khoa, safe="/~")
        scope = f"{ngay}/{self.region}/s3/aws4_request"
        query = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key}/{scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(het_han_giay),
            "X-Amz-SignedHeaders": "host",
        }
        canonical_query = "&".join(f"{quote(k, safe='~')}={quote(v, safe='~')}" for k, v in sorted(query.items()))
        canonical_request = "\n".join([method, canonical_uri, canonical_query, f"host:{host}\n", "host",
                                       "UNSIGNED-PAYLOAD"])
        string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                                    hashlib.sha256(canonical_request.encode()).hexdigest()])
        khoa_ky = self._signing_key(ngay)
        chu_ky = hmac.new(khoa_ky, string_to_sign.encode(), hashlib.sha256).hexdigest()
        scheme = urlparse(self.endpoint).scheme
        return f"{scheme}://{host}{canonical_uri}?{canonical_query}&X-Amz-Signature={chu_ky}"

    def _signing_key(self, ngay: str) -> bytes:
        def h(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()
        return h(h(h(h(f"AWS4{self.secret_key}".encode(), ngay), self.region), "s3"), "aws4_request")

    def tao_url_tai_len(self, khoa: str, het_han_giay: int = 900) -> UrlTaiLen:
        return UrlTaiLen(khoa=khoa, upload_url=self.presign("PUT", khoa, het_han_giay),
                         file_url=self.presign("GET", khoa, 7 * 24 * 3600))

    def luu(self, khoa: str, noi_dung: bytes, content_type: str = "application/octet-stream") -> str:
        r = httpx.put(self.presign("PUT", khoa), content=noi_dung, headers={"Content-Type": content_type},
                      timeout=30)
        r.raise_for_status()
        return self.presign("GET", khoa, 7 * 24 * 3600)


def lay_storage():
    return S3Storage() if settings.storage_provider.upper() == "S3" else LocalStorage()
