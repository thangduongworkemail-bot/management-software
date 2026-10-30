"""Máy chủ API Khanh Vân: REST + WebSocket, phục vụ luôn bản build PWA (frontend/dist)."""
import asyncio
import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import settings
from .errors import LoiNghiepVu
from .realtime import quan_ly
from .realtime import router as ws_router
from .routers import auth, catalog, inventory, invoices, payments, sales, system

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.get_pool()
    quan_ly.bat_dau(asyncio.get_running_loop())
    yield
    quan_ly.dung()
    db.close_pool()


app = FastAPI(title="Hệ thống Quản lý & Bán hàng Nội thất Khanh Vân", version="2.0.0", lifespan=lifespan)


@app.exception_handler(LoiNghiepVu)
async def loi_nghiep_vu(_: Request, e: LoiNghiepVu):
    return JSONResponse({"loi": e.ma, "thong_bao": e.thong_bao, "chi_tiet": e.chi_tiet}, status_code=e.http_status)


@app.exception_handler(RequestValidationError)
async def loi_du_lieu(_: Request, e: RequestValidationError):
    return JSONResponse({"loi": "DU_LIEU_KHONG_HOP_LE", "thong_bao": "Dữ liệu gửi lên không hợp lệ",
                         "chi_tiet": [{"truong": ".".join(str(x) for x in err["loc"]), "loi": err["msg"]}
                                      for err in e.errors()]}, status_code=422)


@app.exception_handler(psycopg.Error)
async def loi_csdl(_: Request, e: psycopg.Error):
    trang_thai = {"KV001": 409, "KV002": 409, "23505": 409, "23514": 400, "23503": 400, "22P02": 400}
    ma = e.sqlstate or ""
    if ma not in trang_thai:
        logging.getLogger("khanhvan").exception("Lỗi CSDL")
        return JSONResponse({"loi": "LOI_HE_THONG", "thong_bao": "Lỗi hệ thống, vui lòng thử lại"}, status_code=500)
    thong_bao = e.diag.message_primary if ma in ("KV001", "KV002") else {
        "23505": "Dữ liệu bị trùng", "23514": "Dữ liệu vi phạm ràng buộc (giá trị âm hoặc không hợp lệ)",
        "23503": "Tham chiếu tới dữ liệu không tồn tại", "22P02": "Định dạng dữ liệu không hợp lệ"}[ma]
    return JSONResponse({"loi": f"CSDL_{ma}", "thong_bao": thong_bao,
                         "chi_tiet": e.diag.constraint_name}, status_code=trang_thai[ma])


for r in (auth.router, catalog.router, inventory.router, sales.router, payments.router, invoices.router,
          system.router, ws_router):
    app.include_router(r)


@app.get("/api/suc-khoe", tags=["Hệ thống"])
def suc_khoe():
    with db.transaction() as conn:
        conn.execute("SELECT 1")
    return {"ok": True}


settings.local_storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.local_storage_dir), name="files")


@app.get("/{duong_dan:path}", include_in_schema=False)
def spa(duong_dan: str):
    """Phục vụ PWA đã build; mọi đường dẫn không phải file trả về index.html (router phía client)."""
    dist = settings.frontend_dist
    if duong_dan.startswith("api/"):
        return JSONResponse({"loi": "KHONG_TIM_THAY", "thong_bao": "Không có API này"}, status_code=404)
    tep = (dist / duong_dan).resolve()
    if duong_dan and tep.is_file() and dist.resolve() in tep.parents:
        headers = {"Cache-Control": "no-cache"} if tep.name in ("sw.js", "index.html", "manifest.webmanifest") else None
        return FileResponse(tep, headers=headers)
    index = dist / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"thong_bao": "Chưa build frontend. Chạy: cd frontend && npm run build"}, status_code=404)
