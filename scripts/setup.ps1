# Cài đặt một lần: dependencies Python + Node, tạo CSDL, migration, seed, build PWA.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 [-Reset]
param([switch]$Reset)
$ErrorActionPreference = 'Stop'
$goc = Split-Path -Parent $PSScriptRoot
$env:Path = "C:\Program Files\nodejs;C:\Program Files\PostgreSQL\17\bin;$env:Path"
$env:PYTHONIOENCODING = 'utf-8'

Write-Host '==> Backend: tạo môi trường ảo & cài thư viện' -ForegroundColor Cyan
Push-Location "$goc\backend"
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q --upgrade pip
.\.venv\Scripts\python -m pip install -q -r requirements.txt

Write-Host '==> CSDL: tạo role/database, chạy migration, nạp dữ liệu mẫu' -ForegroundColor Cyan
if ($Reset) { .\.venv\Scripts\python -m app.bootstrap --reset } else { .\.venv\Scripts\python -m app.bootstrap }
Pop-Location

Write-Host '==> Frontend: cài thư viện & build PWA' -ForegroundColor Cyan
Push-Location "$goc\frontend"
npm install --no-audit --no-fund
npm run build
Pop-Location

Write-Host '==> Xong. Chạy hệ thống: powershell -File scripts\start.ps1' -ForegroundColor Green
