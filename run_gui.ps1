# Startet die Oberflaeche zum Ausprobieren (Entwicklung).
#
#   powershell -ExecutionPolicy Bypass -File run_gui.ps1

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Die Python-Umgebung fehlt. Bitte zuerst setup.ps1 ausfuehren." -ForegroundColor Red
    exit 1
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
& $Python -m fevdl
