# Build NetTools.exe tren Windows. Chay trong Terminal cua VS Code:
#   powershell -ExecutionPolicy Bypass -File .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "== Tao moi truong ao .venv ==" -ForegroundColor Cyan
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"

Write-Host "== Cai thu vien ==" -ForegroundColor Cyan
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements-dev.txt --quiet

Write-Host "== Kiem thu ==" -ForegroundColor Cyan
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Kiem thu that bai - dung build." }

Write-Host "== Tao icon + thong tin phien ban ==" -ForegroundColor Cyan
& $py scripts\make_icon.py
& $py scripts\write_version.py

Write-Host "== Dong goi NetTools.exe ==" -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --clean NetTools.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller loi." }

Write-Host ""
Write-Host "XONG: dist\NetTools.exe" -ForegroundColor Green
