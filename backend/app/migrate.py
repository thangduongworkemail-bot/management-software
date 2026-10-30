"""Áp dụng các file database/migrations/*.sql theo thứ tự tên, mỗi file trong một giao dịch."""
import logging
from pathlib import Path

from . import db
from .config import settings

log = logging.getLogger("khanhvan.migrate")


def ap_dung(url: str | None = None, thu_muc: Path | None = None) -> list[str]:
    thu_muc = thu_muc or settings.migrations_dir
    moi = []
    with db.connect(url, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                     "ten TEXT PRIMARY KEY, ap_dung_luc TIMESTAMPTZ NOT NULL DEFAULT now())")
        da_co = {r["ten"] for r in conn.execute("SELECT ten FROM schema_migrations")}
        for tep in sorted(thu_muc.glob("*.sql")):
            if tep.name in da_co:
                continue
            with conn.transaction():
                conn.execute(tep.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (ten) VALUES (%s)", (tep.name,))
            log.info("Đã áp dụng migration %s", tep.name)
            moi.append(tep.name)
    return moi


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    da_ap_dung = ap_dung()
    print("Migration mới:", ", ".join(da_ap_dung) if da_ap_dung else "không có (CSDL đã cập nhật)")
