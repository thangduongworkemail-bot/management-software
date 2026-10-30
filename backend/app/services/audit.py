"""Ghi nhật ký thao tác. Mã băm nối chuỗi do trigger trong CSDL tính (xem 002_triggers.sql)."""
import json
from datetime import date, datetime

from psycopg.types.json import Jsonb

from ..security import NguoiDung

HE_THONG = NguoiDung(id=0, vai_tro="HE_THONG", ho_ten="Hệ thống")


def _json_mac_dinh(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def _jsonb(du_lieu):
    if du_lieu is None:
        return None
    return Jsonb(json.loads(json.dumps(du_lieu, default=_json_mac_dinh, ensure_ascii=False)))


def ghi(conn, nguoi: NguoiDung | None, hanh_dong: str, thuc_the: str, thuc_the_id=None,
        truoc=None, sau=None, thiet_bi_id: int | None = None) -> dict:
    nguoi = nguoi or HE_THONG
    return conn.execute(
        """INSERT INTO nhat_ky (nguoi_thuc_hien_id, ten_nguoi_thuc_hien, hanh_dong, thuc_the, thuc_the_id,
                                du_lieu_truoc, du_lieu_sau, thiet_bi_id, prev_hash, current_hash)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '', '')
           RETURNING id, current_hash""",
        (nguoi.id or None, nguoi.ho_ten, hanh_dong, thuc_the,
         None if thuc_the_id is None else str(thuc_the_id), _jsonb(truoc), _jsonb(sau), thiet_bi_id),
    ).fetchone()


def kiem_tra_chuoi(conn) -> list[dict]:
    return conn.execute("SELECT nhat_ky_id, ly_do FROM kiem_tra_chuoi_nhat_ky()").fetchall()
