# FevDownloader - Einrichtung (Phase 0)
#
# Legt eine eigene Python-Umgebung im Projektordner an, installiert yt-dlp und
# PySide6 und laedt ffmpeg nach bin/. Es wird nichts systemweit installiert -
# alles bleibt in diesem Ordner.
#
# Aufruf:  powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvDir     = Join-Path $ProjectRoot ".venv"
$BinDir      = Join-Path $ProjectRoot "bin"
$Requirements = Join-Path $ProjectRoot "requirements.txt"

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Write-Ok($message) {
    Write-Host "    $message" -ForegroundColor Green
}

function Write-Info($message) {
    Write-Host "    $message" -ForegroundColor Gray
}

# ---------------------------------------------------------------------------
# 1. Python finden
# ---------------------------------------------------------------------------
Write-Step "Python suchen"

$PythonExe = $null
$candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "C:\Program Files\Python313\python.exe",
    "C:\Program Files\Python312\python.exe",
    "C:\Program Files\Python311\python.exe"
)

# Zuerst das, was ohnehin im PATH liegt.
$fromPath = Get-Command python -ErrorAction SilentlyContinue
if ($fromPath) {
    $PythonExe = $fromPath.Source
}

if (-not $PythonExe) {
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $PythonExe = $candidate
            break
        }
    }
}

if (-not $PythonExe) {
    Write-Host "Kein Python gefunden. Bitte Python 3.11 oder neuer installieren:" -ForegroundColor Red
    Write-Host "https://www.python.org/downloads/windows/" -ForegroundColor Red
    exit 1
}

$pythonVersion = & $PythonExe --version
Write-Ok "$pythonVersion"
Write-Info $PythonExe

# ---------------------------------------------------------------------------
# 2. Virtuelle Umgebung anlegen
# ---------------------------------------------------------------------------
Write-Step "Python-Umgebung im Projekt anlegen"

if (Test-Path (Join-Path $VenvDir "Scripts\python.exe")) {
    Write-Ok "Bereits vorhanden - wird weiterverwendet."
} else {
    & $PythonExe -m venv $VenvDir
    Write-Ok "Angelegt unter .venv"
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

# ---------------------------------------------------------------------------
# 3. Pakete installieren
# ---------------------------------------------------------------------------
Write-Step "yt-dlp und PySide6 installieren (kann ein paar Minuten dauern)"

& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -r $Requirements --upgrade
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installation der Pakete fehlgeschlagen." -ForegroundColor Red
    exit 1
}
Write-Ok "Pakete installiert."

# ---------------------------------------------------------------------------
# 4. ffmpeg besorgen
# ---------------------------------------------------------------------------
Write-Step "ffmpeg bereitstellen"

$FfmpegExe  = Join-Path $BinDir "ffmpeg.exe"
$FfprobeExe = Join-Path $BinDir "ffprobe.exe"

if ((Test-Path $FfmpegExe) -and (Test-Path $FfprobeExe)) {
    Write-Ok "Bereits vorhanden in bin/"
} else {
    if (-not (Test-Path $BinDir)) {
        New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
    }

    $ZipUrl  = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    $ZipPath = Join-Path $env:TEMP "ffmpeg-fevdl.zip"
    $Extract = Join-Path $env:TEMP "ffmpeg-fevdl-extract"

    Write-Info "Lade herunter von gyan.dev (ca. 30 MB)..."
    $previousProgress = $ProgressPreference
    $ProgressPreference = "SilentlyContinue"   # sonst extrem langsam
    try {
        Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -UseBasicParsing
    } finally {
        $ProgressPreference = $previousProgress
    }

    Write-Info "Entpacke..."
    if (Test-Path $Extract) {
        Remove-Item $Extract -Recurse -Force
    }
    Expand-Archive -Path $ZipPath -DestinationPath $Extract -Force

    foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
        $found = Get-ChildItem -Path $Extract -Filter $name -Recurse -File | Select-Object -First 1
        if (-not $found) {
            Write-Host "$name wurde im Archiv nicht gefunden." -ForegroundColor Red
            exit 1
        }
        Copy-Item $found.FullName -Destination (Join-Path $BinDir $name) -Force
    }

    Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
    Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue
    Write-Ok "ffmpeg.exe und ffprobe.exe liegen nun in bin/"
}

# ---------------------------------------------------------------------------
# 5. Programmsymbol erzeugen
# ---------------------------------------------------------------------------
Write-Step "Programmsymbol erzeugen"

$IconFile = Join-Path $ProjectRoot "assets\fevdl.ico"
if (Test-Path $IconFile) {
    Write-Ok "Bereits vorhanden."
} else {
    & $VenvPython (Join-Path $ProjectRoot "tools\make_icon.py") | Out-Null
    if (Test-Path $IconFile) {
        Write-Ok "assets\fevdl.ico"
    } else {
        Write-Host "    Symbol konnte nicht erzeugt werden - die App laeuft trotzdem." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# 6. Kontrolle
# ---------------------------------------------------------------------------
Write-Step "Kontrolle"

$ffmpegVersion = & $FfmpegExe -version | Select-Object -First 1
Write-Ok $ffmpegVersion

$ytdlpVersion = & $VenvPython -m yt_dlp --version
Write-Ok "yt-dlp $ytdlpVersion"

& $VenvPython -c "import PySide6; print('PySide6', PySide6.__version__)"

Write-Host ""
Write-Host "Einrichtung abgeschlossen." -ForegroundColor Green
Write-Host ""
