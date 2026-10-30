"""Sự kiện thời gian thực qua PostgreSQL NOTIFY.

pg_notify chỉ được phát khi giao dịch COMMIT, nên client không bao giờ nhận sự kiện
của một thao tác bị rollback. API LISTEN kênh này rồi đẩy xuống WebSocket.
"""
import json

KENH = "khanhvan_su_kien"


def phat(conn, loai: str, du_lieu: dict, vai_tro: list[str] | None = None, nguoi_nhan_id: int | None = None) -> None:
    payload = {"loai": loai, "du_lieu": du_lieu, "vai_tro": vai_tro, "nguoi_nhan_id": nguoi_nhan_id}
    conn.execute("SELECT pg_notify(%s, %s)", (KENH, json.dumps(payload, ensure_ascii=False, default=str)))


def xep_hang_thong_bao(conn, kenh: str, nguoi_nhan: str, tieu_de: str, noi_dung: str) -> None:
    conn.execute("INSERT INTO thong_bao (kenh, nguoi_nhan, tieu_de, noi_dung) VALUES (%s, %s, %s, %s)",
                 (kenh, nguoi_nhan, tieu_de, noi_dung))
