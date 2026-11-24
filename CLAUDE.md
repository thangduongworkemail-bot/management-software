# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Coursework project (Đại học Bách Khoa Hà Nội): POS, multi-workshop inventory, two-way debt and e-invoicing for the "Nội thất Khanh Vân" furniture store. All UI text and identifiers are Vietnamese (no diacritics in code: `don_hang`, `ton_kha_dung`, `nguoi`), and the user communicates in Vietnamese. The folder is a git repo (branch `main`).

There are two generations side by side:

- **v2 (current)**: `database/`, `backend/`, `frontend/`, `docker-compose.yml`, `scripts/`, documented in `HUONG_DAN_V2.md` and `README.md`. PostgreSQL 17 + FastAPI + a separate Retry Worker + a Vue 3 PWA.
- **Legacy prototype** at the root: `server.py` (stdlib HTTP on port 5500 + SQLite `khanhvan.db`), `index.html` (static 11-screen mockup), `sw.js`, `tests/` (stdlib unittest suites that drive a running `server.py`, e.g. `python tests\test_e2e.py`). Built by Antigravity. Leave it alone unless asked. `README_PROTOTYPE_V1.md` describes it.

## Python environment: always use the conda env `ai_signal`

Run every Python command for this project with `C:\ProgramData\miniconda3\envs\ai_signal\python.exe` (Python 3.11), never `backend\.venv` or a bare `python`. `conda` is not on PATH, so call the interpreter by full path (Bash: `/c/ProgramData/miniconda3/envs/ai_signal/python.exe`).

- `start.ps1`, `test.ps1` and `demo-public.ps1` use `$env:KHANHVAN_PYTHON` when it is set, otherwise `backend\.venv`. Set it to the `ai_signal` interpreter before running them. `setup.ps1` still creates and uses `.venv`, so don't run it here.
- `ai_signal` is a shared env whose package versions differ from the pins in `backend/requirements.txt` (FastAPI 0.141 vs 0.165.0 since the Week 13 security upgrade); the suite passed on it before that upgrade. The other backend deps were installed into it at their pinned versions. Ask the user before installing anything else, and don't `pip install -r requirements.txt` into it, since that would downgrade packages. It is Python 3.11, so avoid 3.12-only features (e.g. `f"{Fraction(...):.3f}"`).
- PostgreSQL 17 is installed as the Windows service `postgresql-x64-17` (`C:\Program Files\PostgreSQL\17\bin`).

## Commands

PostgreSQL 17 is expected on `localhost:5432` with superuser `postgres`/`postgres` (`PG_SUPERUSER_URL`); the app role/db is `khanhvan`/`khanhvan`. Config comes from env vars, then `backend/.env` (copy of `.env.example`).

```powershell
$py = 'C:\ProgramData\miniconda3\envs\ai_signal\python.exe'; $env:PYTHONIOENCODING = 'utf-8'
# all from backend/
& $py -m app.bootstrap [--reset]               # create role+db, migrate, seed (+30 extra products unless --khong-hang-bo-sung); --reset wipes and reseeds
& $py -m app.migrate                           # apply new migrations only
& $py -m uvicorn app.main:app --port 8000      # API + built PWA from frontend/dist -> http://localhost:8000 (/docs)
& $py -m app.worker [--mot-lan | --kiem-tra-toan-ven]   # background jobs (once / integrity check now)
& $py -m pytest -q
& $py -m pytest tests/test_business_flows.py::test_lech_tien_va_chap_nhan_giam
& $py scripts/smoke.py                         # end-to-end check against a running server
& $py -m app.nhap_kiotviet <file.csv> [--xem-truoc]   # import a KiotViet product export (preview = rollback)
& $py -m app.hang_mau_bo_sung [--xem-truoc]           # add the 30 extra wood products to an existing DB (idempotent)
& $py -X utf8 -m pytest --noconftest tests/test_kiotviet.py tests/test_dimension_parser.py   # pure tests, no DB
```

- Tests: `conftest.py` forces `DATABASE_URL=.../khanhvan_test`, `DEV_MODE=1` and the mock e-invoice provider, then rebuilds that database each session. If PostgreSQL is unreachable the DB tests are **skipped, not failed**, so check the skip count. Each `conn`-fixture test runs inside a transaction that is rolled back, while `test_api.py` commits through the real pool.
- Frontend (from `frontend/`; Node is at `C:\Program Files\nodejs`): `npm run build`, `npm run dev` (Vite on :5173 proxies `/api` and `/ws` to :8000, override with `API_URL`), `npx vitest run`.
- Mobile (from `frontend/`, Node 22+): `npm run icons` regenerates every PWA/Android/iOS icon and splash from `public/icon.svg`; `npm run app:sync` builds and copies into `android/` and `ios/` (Capacitor 8, iOS via SPM); `npm run app:android` / `app:ios` also open Android Studio / Xcode. `VITE_MAY_CHU=https://…` bakes a default server into native builds. Details in `HUONG_DAN_APP_DI_DONG.md`.
- Docker: `docker compose up -d --build` (build context is the repo root; the image builds the PWA and runs `app.bootstrap` on start).
- Cloudflare Tunnel (the app runs on a local Windows machine, either through a Quick Tunnel from `demo-public.ps1` or a named tunnel with a domain): `HUONG_DAN_DEPLOY_CLOUDFLARE.md`.
- Render: `HUONG_DAN_DEPLOY_RENDER.md`. A single Docker web service runs the API and the worker together, because a Render disk attaches to only one service and the worker writes files. The Docker Command override binds `$PORT`. Set `TZ=ICT-7`, because `codes.py` uses `date.today()`.

## Architecture that spans files

- **Schema is raw SQL** in `database/migrations/*.sql`, applied in name order by `app/migrate.py` (tracked in `schema_migrations`). Add new migrations rather than editing applied ones. Money is BIGINT VNĐ, dimensions are INTEGER mm, and coefficients are INTEGER per-mille (1200 = 1,2).
- **Integrity lives in the database (002_triggers.sql)**:
  - `so_cai_ton` and `nhat_ky` reject UPDATE/DELETE/TRUNCATE (SQLSTATE `KV001`).
  - `gia_hieu_luc` may only have its open row closed; `dong_don` is an immutable price snapshot except `da_xuat` (`KV002`).
  - The audit hash chain is computed by a BEFORE INSERT trigger. The service passes empty hashes, and the trigger takes an advisory lock and assigns the id *after* the lock.
  - `bien_the.tim_kiem` is filled by a trigger (unaccented text plus "1800 1m8" size tokens) for trigram search. Since 006 the trigger also appends the canonical form of any synonym found in the row (`f_mo_rong_dong_nghia`), because the query side replaces colloquial words with canonical ones; `catalog.them_dong_nghia` re-indexes matching rows. `frontend/src/lib/search.js` mirrors this offline.
- **Stock is never stored**: `v_ton_kho` sums the ledger. Signs are NHAP/TRA_HANG/GIU_CHO positive and XUAT/NHA_CHO negative. Bundles (`bo_san_pham`) are exploded into their components by `inventory.nhu_cau_cua_don`. Before checking or writing stock, always call `inventory.khoa_bien_the()` (row locks in id order).
- **Services take a `conn` and never commit**. Routers wrap each call in `with db.transaction() as conn:`. Raise `errors.LoiNghiepVu` for business errors, which `main.py` maps to JSON `{loi, thong_bao, chi_tiet}`.
- **Order lifecycle** (`services/orders.py`): `trang_thai` (payment) and `trang_thai_giao` (delivery) are separate columns. `orders.chot_don()` is the single "sale closed" path. In one transaction it exports stock, writes `phieu_ban_hang` and inserts the `hoa_don_dt` queue row. All payment paths (cash, manual confirm, webhook, device, accept-discount, approval) reach it via `payments.ghi_nhan_thanh_toan` or call it directly.
- **Role filtering**: THO must never receive `gia_von`/`gia_san`. Use `catalog.an_gia_noi_bo()` / `NguoiDung.xem_gia_von`, and check new endpoints for this.
- **Realtime**: services call `events.phat()` (pg_notify, delivered only on commit). `realtime.py` LISTENs in a thread and pushes to WebSocket clients filtered by role or user.
- **Mobile app**: the same Vue build runs as a web page, an installed PWA, and a Capacitor native app. Native shells serve the UI from `capacitor://localhost` / `https://localhost`, so every server URL (`/api`, `/files`, `/ws`, public quote links) must go through `urlMayChu()` / `urlCongKhai()` / `urlRealtime()` in `frontend/src/nen-tang.js`; a bare `fetch('/api/…')` or `:src="x.anh_url"` breaks the native app. The backend allows those origins via `CORS_ORIGINS`. The service worker is registered only on web (`main.js`), and `public/day-thong-bao.js` is imported into it for push.
- **Web Push**: `events.phat()` also calls `services/day.xep_hang_theo_su_kien`, which queues one `thong_bao` row (kenh `PUSH`) per subscribed device for event types in `day.SU_KIEN_DAY`. The Worker sends them through `adapters/webpush.py` (RFC 8291 aes128gcm + RFC 8292 VAPID, `cryptography` only); 404/410 deletes the subscription. The VAPID key is auto-generated into `cau_hinh_he_thong` unless `VAPID_PRIVATE_KEY` is set. Low-stock alerts (`inventory.canh_bao_ton_thap`, deduped 24 h via `canh_bao_ton`) run from the Worker.
- **External integrations** sit behind adapters in `app/adapters/`. Mock e-invoice, VietQR, PayOS signature and S3 SigV4 are tested. The Viettel/VNPT adapters have never been run against real accounts.
- **Offline**: `frontend/src/db.js` (Dexie) caches the catalog from `/api/sync/danh-muc`. Offline orders carry a UUID idempotency key and are pushed to `/api/sync/don-hang`. `frontend/src/lib/dimension.js` and `pricing.js` are JS ports of `backend/app/domain/*.py`, so keep both in sync (the vitest cases mirror the pytest cases).

## Working with Antigravity

The user also runs Antigravity (Google's agent IDE) on this folder. Claude acts as task manager and reviewer through `TASKS.md` (statuses `TODO → ĐANG LÀM → CHỜ DUYỆT → XONG / CẦN SỬA`; only Claude sets the last two). The tasks currently in it target the legacy `index.html`, and `.review/baseline/` holds the snapshot to diff against. Claude cannot send commands to Antigravity, because the installed build has no prompt CLI.

## Real store data

`data_bo_sung/` holds the store's KiotViet product export. The original CSV was re-saved as Latin-1 and lost its Vietnamese characters (each became `?`); `khoi_phuc_dau.py` rebuilt `*_khoi_phuc.csv` (UTF-8 BOM) from a word dictionary, checked byte-for-byte against the original. Import the restored file, never the original; `domain/kiotviet.py` rejects files with lost accents. Products are imported via `catalog.tao_bien_the`, so prices go through price history and stock becomes a `DIEU_CHINH` ledger row.

## Local-only folders (gitignored, may be absent in a fresh clone)

- `.review/` is the review baseline above; don't modify it.
- `.tools/` holds `cloudflared.exe` and the logs for `scripts\demo-public.ps1` (Cloudflare quick-tunnel demo).
- `.impeccable_repo/` is a vendored third-party design-skill repo and `.gemini/` holds Antigravity/Gemini configuration; leave both alone.
