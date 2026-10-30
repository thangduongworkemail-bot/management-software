"""Cấu hình đọc từ biến môi trường (và file backend/.env nếu có)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent


def _nap_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for dong in path.read_text(encoding="utf-8").splitlines():
        dong = dong.strip()
        if not dong or dong.startswith("#") or "=" not in dong:
            continue
        khoa, gia_tri = dong.split("=", 1)
        os.environ.setdefault(khoa.strip(), gia_tri.strip())


_nap_env_file(BACKEND_DIR / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env(
        "DATABASE_URL", "postgresql://khanhvan:khanhvan@localhost:5432/khanhvan"))
    migrations_dir: Path = field(default_factory=lambda: Path(_env(
        "MIGRATIONS_DIR", str(ROOT_DIR / "database" / "migrations"))))
    frontend_dist: Path = field(default_factory=lambda: Path(_env(
        "FRONTEND_DIST", str(ROOT_DIR / "frontend" / "dist"))))
    dev_mode: bool = field(default_factory=lambda: _env("DEV_MODE", "1") == "1")

    jwt_secret: str = field(default_factory=lambda: _env("JWT_SECRET", "khanhvan-dev-secret-doi-khi-trien-khai"))
    jwt_ttl_minutes: int = field(default_factory=lambda: int(_env("JWT_TTL_MINUTES", "720")))

    hold_ttl_minutes: int = field(default_factory=lambda: int(_env("HOLD_TTL_MINUTES", "30")))
    quote_ttl_days: int = field(default_factory=lambda: int(_env("QUOTE_TTL_DAYS", "7")))
    pairing_ttl_minutes: int = 10
    device_clock_skew_seconds: int = 300
    heartbeat_warn_minutes: int = 15

    # Thanh toán: VietQR (Napas 247) & webhook PayOS
    vietqr_bank_bin: str = field(default_factory=lambda: _env("VIETQR_BANK_BIN", "970436"))
    vietqr_account_no: str = field(default_factory=lambda: _env("VIETQR_ACCOUNT_NO", "0011004455667"))
    vietqr_account_name: str = field(default_factory=lambda: _env("VIETQR_ACCOUNT_NAME", "NGUYEN THI VAN"))
    payos_checksum_key: str = field(default_factory=lambda: _env("PAYOS_CHECKSUM_KEY", "payos-checksum-key-demo"))

    # Hóa đơn điện tử
    einvoice_provider: str = field(default_factory=lambda: _env("EINVOICE_PROVIDER", "MOCK"))
    einvoice_mock_fail_rate: float = field(default_factory=lambda: float(_env("EINVOICE_MOCK_FAIL_RATE", "0")))
    einvoice_max_retries: int = field(default_factory=lambda: int(_env("EINVOICE_MAX_RETRIES", "10")))
    einvoice_seller_tax_code: str = field(default_factory=lambda: _env("EINVOICE_SELLER_TAX_CODE", "4600123456"))
    einvoice_template: str = field(default_factory=lambda: _env("EINVOICE_TEMPLATE", "1/001"))
    einvoice_series: str = field(default_factory=lambda: _env("EINVOICE_SERIES", "C26TKV"))
    vnpt_url: str = field(default_factory=lambda: _env("VNPT_URL", ""))
    vnpt_username: str = field(default_factory=lambda: _env("VNPT_USERNAME", ""))
    vnpt_password: str = field(default_factory=lambda: _env("VNPT_PASSWORD", ""))
    viettel_url: str = field(default_factory=lambda: _env("VIETTEL_URL", "https://api-vinvoice.viettel.vn"))
    viettel_username: str = field(default_factory=lambda: _env("VIETTEL_USERNAME", ""))
    viettel_password: str = field(default_factory=lambda: _env("VIETTEL_PASSWORD", ""))

    # Lưu trữ file
    storage_provider: str = field(default_factory=lambda: _env("STORAGE_PROVIDER", "LOCAL"))
    local_storage_dir: Path = field(default_factory=lambda: Path(_env(
        "LOCAL_STORAGE_DIR", str(BACKEND_DIR / "storage"))))
    s3_endpoint: str = field(default_factory=lambda: _env("S3_ENDPOINT", "https://s3.ap-southeast-1.amazonaws.com"))
    s3_region: str = field(default_factory=lambda: _env("S3_REGION", "ap-southeast-1"))
    s3_bucket: str = field(default_factory=lambda: _env("S3_BUCKET", ""))
    s3_access_key: str = field(default_factory=lambda: _env("S3_ACCESS_KEY", ""))
    s3_secret_key: str = field(default_factory=lambda: _env("S3_SECRET_KEY", ""))

    # Thông báo
    notify_owner_phone: str = field(default_factory=lambda: _env("NOTIFY_OWNER_PHONE", "0912345678"))
    zalo_oa_access_token: str = field(default_factory=lambda: _env("ZALO_OA_ACCESS_TOKEN", ""))
    sendgrid_api_key: str = field(default_factory=lambda: _env("SENDGRID_API_KEY", ""))
    sendgrid_from: str = field(default_factory=lambda: _env("SENDGRID_FROM", "no-reply@khanhvan.vn"))

    # Worker
    integrity_check_hour: int = field(default_factory=lambda: int(_env("INTEGRITY_CHECK_HOUR", "2")))


settings = Settings()
