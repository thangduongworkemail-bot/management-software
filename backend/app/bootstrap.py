"""Khởi tạo trọn gói: tạo role + database (bằng tài khoản superuser), chạy migration, nạp dữ liệu mẫu.

    python -m app.bootstrap            # tạo nếu chưa có, seed nếu CSDL trống
    python -m app.bootstrap --reset    # xóa sạch schema rồi dựng lại + seed
"""
import argparse
import logging
import os
from urllib.parse import urlparse

import psycopg
from psycopg import sql

from . import db, hang_mau_bo_sung, migrate, seed
from .config import settings

log = logging.getLogger("khanhvan.bootstrap")


def _thong_tin(url: str) -> tuple[str, str, str]:
    u = urlparse(url)
    return u.path.lstrip("/"), u.username, u.password or ""


def tao_role_va_csdl(super_url: str, url: str) -> None:
    ten_db, user, mat_khau = _thong_tin(url)
    with psycopg.connect(super_url, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,)).fetchone():
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN CREATEDB PASSWORD {}").format(
                sql.Identifier(user), sql.Literal(mat_khau)))
            log.info("Đã tạo role %s", user)
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (ten_db,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                sql.Identifier(ten_db), sql.Identifier(user)))
            log.info("Đã tạo database %s", ten_db)


def xoa_schema(url: str) -> None:
    _, user, _ = _thong_tin(url)
    with db.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute(sql.SQL("CREATE SCHEMA public AUTHORIZATION {}").format(sql.Identifier(user)))
    log.info("Đã xóa sạch schema public")


def dung(url: str | None = None, reset: bool = False, co_seed: bool = True, super_url: str | None = None,
         hang_bo_sung: bool = False) -> None:
    """hang_bo_sung=True: CSDL mới nạp thêm 30 mặt hàng gỗ của hang_mau_bo_sung sau dữ liệu mẫu. Test để False
    để giữ đúng bộ dữ liệu mẫu bám báo cáo."""
    url = url or settings.database_url
    super_url = super_url or os.environ.get("PG_SUPERUSER_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    try:
        tao_role_va_csdl(super_url, url)
    except psycopg.OperationalError as e:
        log.warning("Bỏ qua bước tạo role/database (không kết nối được superuser): %s", e)
    if reset:
        xoa_schema(url)
    migrate.ap_dung(url)
    if co_seed:
        with db.connect(url) as conn:
            trong = conn.execute("SELECT count(*) AS n FROM tai_khoan").fetchone()["n"] == 0
        if trong:
            seed.nap(url)
            if hang_bo_sung:
                with db.connect(url) as conn:
                    with conn.transaction():
                        so_hang = len(hang_mau_bo_sung.nap(conn)["mat_hang"])
                log.info("Đã nạp thêm %s mặt hàng bổ sung", so_hang)
        else:
            log.info("CSDL đã có dữ liệu, bỏ qua seed (dùng --reset để nạp lại)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true")
    p.add_argument("--khong-seed", action="store_true")
    p.add_argument("--khong-hang-bo-sung", action="store_true", help="chỉ nạp dữ liệu mẫu gốc, không thêm 30 mặt hàng")
    a = p.parse_args()
    dung(reset=a.reset, co_seed=not a.khong_seed, hang_bo_sung=not a.khong_hang_bo_sung)
    print("Xong. CSDL sẵn sàng tại", settings.database_url.rsplit("@", 1)[-1])
