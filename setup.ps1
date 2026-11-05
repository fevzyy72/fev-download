# FevDownloader - Einrichtung (Phase 0)
#
# Legt eine eigene Python-Umgebung im Projektordner an, installiert yt-dlp und
# PySide6 und laedt ffmpeg nach bin/. Es wird nichts systemweit installiert -
# alles bleibt in diesem Ordner.
#
# Aufruf:  powershell -ExecutionPolicy Bypass -File setup.ps1
# Nur den festgelegten ffmpeg-Build samt Quellen pruefen/nachladen: -NurFfmpeg.

param([switch]$NurFfmpeg)

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

if ($NurFfmpeg) {
    $SourcePython = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $SourcePython)) {
        throw "Python-Umgebung fehlt. Zuerst setup.ps1 ohne -NurFfmpeg ausfuehren."
    }
    & $SourcePython (Join-Path $ProjectRoot "tools\ffmpeg_sources.py") --download --bootstrap
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg samt Quellen konnte nicht bereitgestellt werden." }
    exit 0
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
if ($LASTEXITCODE -ne 0) { throw "pip konnte nicht aktualisiert werden." }
# GHSA-xmj3-9gf7-h52w betrifft alte Windows-Wheel-Installationen.
& $VenvPython -m pip install --upgrade 'setuptools>=84.1.0' --quiet
if ($LASTEXITCODE -ne 0) { throw "setuptools konnte nicht aktualisiert werden." }
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

# Feste Fassung statt beweglichem "release"-Link: Binaerdateien und Quellen
# werden gemeinsam mit installer/ffmpeg-lock.json geprueft. Ein anderer Build
# wird niemals stillschweigend mit den Quellen von 9.0 kombiniert.
$FfmpegExe = Join-Path $BinDir "ffmpeg.exe"
& $VenvPython (Join-Path $ProjectRoot "tools\ffmpeg_sources.py") --download --bootstrap
if ($LASTEXITCODE -ne 0) { throw "ffmpeg samt Quellen konnte nicht bereitgestellt werden." }
Write-Ok "ffmpeg 9.0 samt Quellen und Originalhinweisen liegt bereit."

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

# Kommt ueber das pip-Paket 'deno' (requirements.txt). Ohne sie fragt yt-dlp
# YouTube nur ueber einen Zugang an - siehe src\fevdl\core\ytdlp_options.py.
$DenoExe = Join-Path $VenvDir "Scripts\deno.exe"
if (Test-Path $DenoExe) {
    Write-Ok ((& $DenoExe --version | Select-Object -First 1) + " (JavaScript-Laufzeit fuer YouTube)")
} else {
    Write-Host "    deno.exe fehlt - YouTube laeuft nur eingeschraenkt." -ForegroundColor Yellow
}

& $VenvPython -c "import PySide6; print('PySide6', PySide6.__version__)"

Write-Host ""
Write-Host "Einrichtung abgeschlossen." -ForegroundColor Green
Write-Host ""
