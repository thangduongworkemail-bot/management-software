# Khởi chạy API (phục vụ luôn PWA) + Retry Worker.  Mở http://localhost:8000
$goc = Split-Path -Parent $PSScriptRoot
$py = "$goc\backend\.venv\Scripts\python.exe"
$env:PYTHONIOENCODING = 'utf-8'
$api = Start-Process -FilePath $py -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000' `
  -WorkingDirectory "$goc\backend" -PassThru -NoNewWindow
$worker = Start-Process -FilePath $py -ArgumentList '-m', 'app.worker' -WorkingDirectory "$goc\backend" -PassThru -NoNewWindow
Write-Host "API pid $($api.Id), Worker pid $($worker.Id). Mở http://localhost:8000  (Ctrl+C để dừng)" -ForegroundColor Green
try { Wait-Process -Id $api.Id } finally {
  Stop-Process -Id $worker.Id -ErrorAction SilentlyContinue
  Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
}
