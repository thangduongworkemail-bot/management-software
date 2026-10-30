# Mở hệ thống ra internet qua Cloudflare Quick Tunnel để khách dùng thử.
#   powershell -ExecutionPolicy Bypass -File scripts\demo-public.ps1          # bật (in ra link https)
#   powershell -ExecutionPolicy Bypass -File scripts\demo-public.ps1 -Tat     # tắt API, Worker, tunnel
# API, Worker và tunnel chạy nền độc lập (đóng cửa sổ vẫn chạy). Link đổi mỗi lần bật lại.
param([switch]$Tat)
$goc = Split-Path -Parent $PSScriptRoot
$log = "$goc\.tools\logs"
New-Item -ItemType Directory -Force $log | Out-Null

function Dung-TatCa {
  Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'app\.worker|uvicorn' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
}

Dung-TatCa
if ($Tat) { Write-Host 'Đã tắt demo công khai.' -ForegroundColor Yellow; exit }

$py = "$goc\backend\.venv\Scripts\python.exe"
$env:PYTHONIOENCODING = 'utf-8'
Start-Process -FilePath $py -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--proxy-headers' `
  -WorkingDirectory "$goc\backend" -WindowStyle Hidden -RedirectStandardOutput "$log\api.log" -RedirectStandardError "$log\api.err.log"
Start-Process -FilePath $py -ArgumentList '-m', 'app.worker' -WorkingDirectory "$goc\backend" -WindowStyle Hidden `
  -RedirectStandardOutput "$log\worker.log" -RedirectStandardError "$log\worker.err.log"

for ($i = 0; $i -lt 30; $i++) {
  try { Invoke-RestMethod http://127.0.0.1:8000/api/suc-khoe -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 1 }
}

Remove-Item "$log\tunnel.log" -ErrorAction SilentlyContinue
Start-Process -FilePath "$goc\.tools\cloudflared.exe" -ArgumentList 'tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:8000', '--logfile', "$log\tunnel.log" `
  -WindowStyle Hidden

$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
  Start-Sleep 1
  if (Test-Path "$log\tunnel.log") {
    $m = Select-String -Path "$log\tunnel.log" -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
    if ($m) { $url = $m.Matches[0].Value }
  }
}
if ($url) {
  Set-Content -Path "$log\link.txt" -Value $url -Encoding utf8
  Write-Host "`nLink cho khách dùng thử: $url`n" -ForegroundColor Green
} else {
  Write-Host "Không lấy được link, xem $log\tunnel.log" -ForegroundColor Red
}
