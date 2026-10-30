"""Adapter gửi thông báo cho hộp thư đi `thong_bao` (Worker gọi).

Khi chưa cấu hình khóa API, adapter chỉ ghi log (chế độ demo) và coi như đã gửi.
"""
import logging

import httpx

from ..config import settings

log = logging.getLogger("khanhvan.notify")


class LoiGuiThongBao(Exception):
    pass


def gui(kenh: str, nguoi_nhan: str, tieu_de: str, noi_dung: str) -> None:
    if kenh == "EMAIL" and settings.sendgrid_api_key:
        r = httpx.post("https://api.sendgrid.com/v3/mail/send", timeout=15,
                       headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                       json={"personalizations": [{"to": [{"email": nguoi_nhan}]}],
                             "from": {"email": settings.sendgrid_from}, "subject": tieu_de,
                             "content": [{"type": "text/plain", "value": noi_dung}]})
        if r.status_code >= 300:
            raise LoiGuiThongBao(f"SendGrid {r.status_code}: {r.text[:200]}")
        return
    if kenh == "ZALO" and settings.zalo_oa_access_token:
        r = httpx.post("https://openapi.zalo.me/v3.0/oa/message/cs", timeout=15,
                       headers={"access_token": settings.zalo_oa_access_token},
                       json={"recipient": {"user_id": nguoi_nhan},
                             "message": {"text": f"{tieu_de}\n{noi_dung}"}})
        if r.status_code >= 300 or r.json().get("error", 0) != 0:
            raise LoiGuiThongBao(f"Zalo OA lỗi: {r.text[:200]}")
        return
    log.info("[DEMO %s -> %s] %s: %s", kenh, nguoi_nhan, tieu_de, noi_dung)
