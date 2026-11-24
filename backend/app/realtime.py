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
        # Mỗi luồng một cờ dừng riêng. Dùng chung một cờ rồi clear() khi khởi động lại sẽ "hồi sinh" luồng cũ
        # chưa kịp thoát, và luồng đó tiếp tục đẩy sự kiện vào vòng lặp đã đóng.
        self._dung = threading.Event()
        self._luong = threading.Thread(target=self._lang_nghe, args=(loop, self._dung), name="pg-listen", daemon=True)
        self._luong.start()

    def dung(self) -> None:
        self._dung.set()

    def _lang_nghe(self, loop: asyncio.AbstractEventLoop, dung: threading.Event) -> None:
        while not dung.is_set():
            try:
                with db.connect(autocommit=True) as conn:
                    conn.execute(f"LISTEN {KENH}")
                    while not dung.is_set():
                        for n in conn.notifies(timeout=1.0):
                            if dung.is_set() or loop.is_closed():
                                return
                            coro = self.phat(json.loads(n.payload))
                            try:
                                asyncio.run_coroutine_threadsafe(coro, loop)
                            except RuntimeError:  # vòng lặp vừa đóng (máy chủ đang tắt)
                                coro.close()
                                return
            except Exception as e:  # mất kết nối CSDL: thử lại sau 3 giây
                log.warning("LISTEN lỗi, kết nối lại: %s", e)
                dung.wait(3)


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
