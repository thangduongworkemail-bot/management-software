"""WebSocket: một luồng LISTEN trên PostgreSQL, sự kiện được phát tới client đúng vai trò."""
import asyncio
import json
import logging
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import db
from .deps import nguoi_tu_token
from .errors import LoiNghiepVu
from .security import NguoiDung
from .services.events import KENH

log = logging.getLogger("khanhvan.realtime")
router = APIRouter()


class QuanLyKetNoi:
    def __init__(self):
        self.ket_noi: dict[WebSocket, NguoiDung] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._dung = threading.Event()
        self._luong: threading.Thread | None = None

    async def phat(self, su_kien: dict) -> None:
        for ws, nguoi in list(self.ket_noi.items()):
            if su_kien.get("vai_tro") and nguoi.vai_tro not in su_kien["vai_tro"]:
                continue
            if su_kien.get("nguoi_nhan_id") and nguoi.id != su_kien["nguoi_nhan_id"]:
                continue
            try:
                await ws.send_json({"loai": su_kien["loai"], "du_lieu": su_kien["du_lieu"]})
            except Exception:
                self.ket_noi.pop(ws, None)

    def bat_dau(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._dung.clear()
        self._luong = threading.Thread(target=self._lang_nghe, name="pg-listen", daemon=True)
        self._luong.start()

    def dung(self) -> None:
        self._dung.set()

    def _lang_nghe(self) -> None:
        while not self._dung.is_set():
            try:
                with db.connect(autocommit=True) as conn:
                    conn.execute(f"LISTEN {KENH}")
                    while not self._dung.is_set():
                        for n in conn.notifies(timeout=1.0):
                            asyncio.run_coroutine_threadsafe(self.phat(json.loads(n.payload)), self.loop)
            except Exception as e:  # mất kết nối CSDL: thử lại sau 3 giây
                log.warning("LISTEN lỗi, kết nối lại: %s", e)
                self._dung.wait(3)


quan_ly = QuanLyKetNoi()


@router.websocket("/ws")
async def ws(websocket: WebSocket, token: str):
    try:
        nguoi = await asyncio.to_thread(nguoi_tu_token, token)
    except LoiNghiepVu:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    quan_ly.ket_noi[websocket] = nguoi
    try:
        while True:
            await websocket.receive_text()  # client gửi "ping" giữ kết nối
    except WebSocketDisconnect:
        pass
    finally:
        quan_ly.ket_noi.pop(websocket, None)
