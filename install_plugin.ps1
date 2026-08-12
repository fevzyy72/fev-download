# Fev Download - Einbindung in DaVinci Resolve
#
# Kopiert das Startscript in Resolves Scripts-Ordner und hinterlegt, wo dieses
# Projekt liegt. Danach erscheint der Eintrag unter
#   Workspace -> Scripts -> Utility -> FevDownloader
#
# Aufruf:  powershell -ExecutionPolicy Bypass -File install_plugin.ps1

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SourceScript = Join-Path $ProjectRoot "resolve\FevDownloader.py"
$ScriptsDir = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"
$TargetScript = Join-Path $ScriptsDir "FevDownloader.py"
$AppDir = Join-Path $env:LOCALAPPDATA "FevDownloader"
$InstallFile = Join-Path $AppDir "install.json"

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Write-Ok($message) {
    Write-Host "    $message" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 1. Voraussetzungen pruefen
# ---------------------------------------------------------------------------
Write-Step "Voraussetzungen pruefen"

if (-not (Test-Path $SourceScript)) {
    Write-Host "resolve\FevDownloader.py fehlt im Projektordner." -ForegroundColor Red
    exit 1
}

$VenvPythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $VenvPythonw)) {
    Write-Host "Die Python-Umgebung fehlt. Bitte zuerst setup.ps1 ausfuehren." -ForegroundColor Red
    exit 1
}
Write-Ok "Python-Umgebung vorhanden."

$Ffmpeg = Join-Path $ProjectRoot "bin\ffmpeg.exe"
if (-not (Test-Path $Ffmpeg)) {
    Write-Host "ffmpeg fehlt in bin\. Bitte zuerst setup.ps1 ausfuehren." -ForegroundColor Red
    exit 1
}
Write-Ok "ffmpeg vorhanden."

if (-not (Test-Path $ScriptsDir)) {
    Write-Host "Resolves Scripts-Ordner wurde nicht gefunden:" -ForegroundColor Red
    Write-Host "  $ScriptsDir" -ForegroundColor Red
    Write-Host "Ist DaVinci Resolve installiert und mindestens einmal gestartet worden?" -ForegroundColor Red
    exit 1
}
Write-Ok "Resolves Scripts-Ordner gefunden."

# ---------------------------------------------------------------------------
# 2. Projektpfad hinterlegen
# ---------------------------------------------------------------------------
Write-Step "Projektpfad hinterlegen"

if (-not (Test-Path $AppDir)) {
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
}

# Das Script in Resolve laeuft unter einem anderen Python und kennt den
# Projektordner sonst nicht.
$InstallData = [ordered]@{
    project_root = $ProjectRoot
    installed    = (Get-Date).ToString("s")
}
# Bewusst NICHT Out-File -Encoding utf8: PowerShell 5.1 setzt dabei eine
# Byte-Reihenfolge-Marke (BOM) an den Anfang, an der Pythons JSON-Leser
# scheitert. WriteAllText mit UTF8Encoding($false) schreibt ohne Marke.
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($InstallFile, ($InstallData | ConvertTo-Json), $Utf8NoBom)
Write-Ok "$InstallFile"

# ---------------------------------------------------------------------------
# 3. Script kopieren
# ---------------------------------------------------------------------------
Write-Step "Startscript nach Resolve kopieren"

Copy-Item $SourceScript -Destination $TargetScript -Force
Write-Ok "$TargetScript"

# Das Testscript aus der Einrichtungsphase wird nicht mehr gebraucht.
$OldTest = Join-Path $ScriptsDir "_FevTest.py"
if (Test-Path $OldTest) {
    Remove-Item $OldTest -Force
    Write-Ok "Altes Testscript entfernt."
}

# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Einbindung abgeschlossen." -ForegroundColor Green
Write-Host ""
Write-Host "So geht es weiter:" -ForegroundColor White
Write-Host "  1. DaVinci Resolve neu starten (Scripts werden beim Start eingelesen)"
Write-Host "  2. Ein Projekt oeffnen"
Write-Host "  3. Workspace -> Scripts -> Utility -> FevDownloader"
Write-Host ""
