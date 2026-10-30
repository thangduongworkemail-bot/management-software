"""Test dùng CSDL riêng `khanhvan_test`, được dựng lại từ đầu (migration + seed) mỗi phiên chạy."""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "postgresql://khanhvan:khanhvan@localhost:5432/khanhvan_test")
os.environ["DEV_MODE"] = "1"
os.environ["EINVOICE_PROVIDER"] = "MOCK"
os.environ["EINVOICE_MOCK_FAIL_RATE"] = "0"
os.environ["LOCAL_STORAGE_DIR"] = tempfile.mkdtemp(prefix="khanhvan-test-")

import psycopg  # noqa: E402
import pytest  # noqa: E402

from app import bootstrap, db  # noqa: E402
from app.security import NguoiDung  # noqa: E402


@pytest.fixture(scope="session")
def csdl():
    try:
        bootstrap.dung(reset=True, co_seed=True)
    except psycopg.OperationalError as e:
        pytest.skip(f"Không kết nối được PostgreSQL: {e}")
    yield
    db.close_pool()


@pytest.fixture
def conn(csdl):
    """Mỗi test chạy trong một giao dịch và ROLLBACK khi xong, dữ liệu mẫu giữ nguyên."""
    with db.connect() as c:
        yield c
        c.rollback()


def _nguoi(conn, ten_dang_nhap: str) -> NguoiDung:
    r = conn.execute("SELECT id, vai_tro, ho_ten FROM tai_khoan WHERE ten_dang_nhap = %s", (ten_dang_nhap,)).fetchone()
    return NguoiDung(id=r["id"], vai_tro=r["vai_tro"], ho_ten=r["ho_ten"])


@pytest.fixture
def chu(conn):
    return _nguoi(conn, "covan")


@pytest.fixture
def tho(conn):
    return _nguoi(conn, "anhnam")


def id_bien_the(conn, ma: str) -> int:
    return conn.execute("SELECT id FROM bien_the WHERE ma_noi_bo = %s", (ma,)).fetchone()["id"]


def ton(conn, ma: str) -> dict:
    return conn.execute("SELECT t.* FROM v_ton_kho t JOIN bien_the bt ON bt.id = t.bien_the_id WHERE bt.ma_noi_bo = %s",
                        (ma,)).fetchone()
