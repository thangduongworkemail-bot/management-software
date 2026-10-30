# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Coursework project (Đại học Bách Khoa Hà Nội): POS, multi-workshop inventory, two-way debt and e-invoicing for the "Nội thất Khanh Vân" furniture store. All UI text and identifiers are Vietnamese (no diacritics in code: `don_hang`, `ton_kha_dung`, `nguoi`), and the user communicates in Vietnamese. The root folder is not a git repository.

There are two generations side by side:

- **v2 (current)**: `database/`, `backend/`, `frontend/`, `docker-compose.yml`, `scripts/`, documented in `HUONG_DAN_V2.md`. PostgreSQL 17 + FastAPI + a separate Retry Worker + a Vue 3 PWA.
- **Legacy prototype** at the root: `server.py` (stdlib HTTP + SQLite `khanhvan.db`), `index.html` (static 11-screen mockup), `sw.js`, `tests/`. Built by Antigravity. Leave it alone unless asked. `README_PROTOTYPE_V1.md` describes the legacy version; `README.md` describes the whole repo (v2 first).

## Commands (Windows; PostgreSQL 17 is a local service, superuser `postgres`/`postgres`)

```powershell
scripts\setup.ps1 [-Reset]      # venv + pip, create role/db, migrate, seed, npm install + build
scripts\start.ps1               # API (serves the built PWA) + worker -> http://localhost:8000
scripts\test.ps1                # pytest + vitest
```

- Backend (run from `backend/`, set `PYTHONIOENCODING=utf-8`): `.venv\Scripts\python -m pytest -q`; a single test: `... -m pytest tests/test_business_flows.py::test_lech_tien_va_chap_nhan_giam`. DB tests rebuild a separate `khanhvan_test` database each session. Each `conn`-fixture test runs inside a transaction that is rolled back, while `test_api.py` commits through the real pool.
- `python -m app.bootstrap --reset` rebuilds the dev DB and reseeds; `python -m app.worker --mot-lan` runs each worker job once; `python scripts/smoke.py` runs an end-to-end check against a running server.
- Frontend (from `frontend/`; Node is at `C:\Program Files\nodejs`, which may not be on PATH): `npm run build`, `npm run dev` (Vite on :5173 proxies `/api` and `/ws` to :8000), `npx vitest run`.

## Architecture that spans files

- **Schema is raw SQL** in `database/migrations/*.sql`, applied in name order by `app/migrate.py` (tracked in `schema_migrations`). Add new migrations rather than editing applied ones. Money is BIGINT VNĐ, dimensions are INTEGER mm, and coefficients are INTEGER per-mille (1200 = 1,2).
- **Integrity lives in the database (002_triggers.sql)**:
  - `so_cai_ton` and `nhat_ky` reject UPDATE/DELETE/TRUNCATE (SQLSTATE `KV001`).
  - `gia_hieu_luc` may only have its open row closed; `dong_don` is an immutable price snapshot except `da_xuat` (`KV002`).
  - The audit hash chain is computed by a BEFORE INSERT trigger. The service passes empty hashes, and the trigger takes an advisory lock and assigns the id *after* the lock.
  - `bien_the.tim_kiem` is filled by a trigger (unaccented text plus "1800 1m8" size tokens) for trigram search.
- **Stock is never stored**: `v_ton_kho` sums the ledger. Signs are NHAP/TRA_HANG/GIU_CHO positive and XUAT/NHA_CHO negative. Bundles (`bo_san_pham`) are exploded into their components by `inventory.nhu_cau_cua_don`. Before checking or writing stock, always call `inventory.khoa_bien_the()` (row locks in id order).
- **Services take a `conn` and never commit**. Routers wrap each call in `with db.transaction() as conn:`. Raise `errors.LoiNghiepVu` for business errors, which `main.py` maps to JSON `{loi, thong_bao, chi_tiet}`.
- **Order lifecycle** (`services/orders.py`): `trang_thai` (payment) and `trang_thai_giao` (delivery) are separate columns. `orders.chot_don()` is the single "sale closed" path. In one transaction it exports stock, writes `phieu_ban_hang` and inserts the `hoa_don_dt` queue row. All payment paths (cash, manual confirm, webhook, device, accept-discount, approval) reach it via `payments.ghi_nhan_thanh_toan` or call it directly.
- **Role filtering**: THO must never receive `gia_von`/`gia_san`. Use `catalog.an_gia_noi_bo()` / `NguoiDung.xem_gia_von`, and check new endpoints for this.
- **Realtime**: services call `events.phat()` (pg_notify, delivered only on commit). `realtime.py` LISTENs in a thread and pushes to WebSocket clients filtered by role or user.
- **External integrations** sit behind adapters in `app/adapters/`. Mock e-invoice, VietQR, PayOS signature and S3 SigV4 are tested. The Viettel/VNPT adapters have never been run against real accounts.
- **Offline**: `frontend/src/db.js` (Dexie) caches the catalog from `/api/sync/danh-muc`. Offline orders carry a UUID idempotency key and are pushed to `/api/sync/don-hang`. `frontend/src/lib/dimension.js` and `pricing.js` are JS ports of `backend/app/domain/*.py`, so keep both in sync (the vitest cases mirror the pytest cases).

## Working with Antigravity

The user also runs Antigravity (Google's agent IDE) on this folder. Claude acts as task manager and reviewer through `TASKS.md` (statuses `TODO → ĐANG LÀM → CHỜ DUYỆT → XONG / CẦN SỬA`; only Claude sets the last two). The tasks currently in it target the legacy `index.html`, and `.review/baseline/` holds the snapshot to diff against. Claude cannot send commands to Antigravity, because the installed build has no prompt CLI.

## Folders to leave alone

- `.impeccable_repo/` is a vendored third-party design-skill repo, not part of this project.
- `.gemini/` holds Antigravity/Gemini configuration.
