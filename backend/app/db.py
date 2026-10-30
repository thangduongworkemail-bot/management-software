"""Kết nối PostgreSQL qua psycopg 3 + connection pool.

Mỗi thao tác nghiệp vụ chạy trong đúng một giao dịch:

    with db.transaction() as conn:
        ...   # commit khi thoát khối, rollback nếu có ngoại lệ
"""
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

CONNECT_KWARGS = {
    "row_factory": dict_row,
    "client_encoding": "UTF8",
    "options": "-c timezone=Asia/Ho_Chi_Minh",
}

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=10,
                               kwargs=CONNECT_KWARGS, open=True)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        yield conn


def connect(url: str | None = None, **kwargs) -> psycopg.Connection:
    """Kết nối lẻ (dùng cho migration, LISTEN, script)."""
    return psycopg.connect(url or settings.database_url, **{**CONNECT_KWARGS, **kwargs})
