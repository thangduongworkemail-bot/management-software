# Chạy toàn bộ kiểm thử: pytest (dựng CSDL khanhvan_test riêng) + vitest
$goc = Split-Path -Parent $PSScriptRoot
$env:Path = "C:\Program Files\nodejs;$env:Path"
$env:PYTHONIOENCODING = 'utf-8'
$py = if ($env:KHANHVAN_PYTHON) { $env:KHANHVAN_PYTHON } else { "$goc\backend\.venv\Scripts\python.exe" }
Push-Location "$goc\backend"; & $py -m pytest -q; $be = $LASTEXITCODE; Pop-Location
Push-Location "$goc\frontend"; npx vitest run; $fe = $LASTEXITCODE; Pop-Location
exit ([Math]::Max($be, $fe))
