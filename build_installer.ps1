# Fev Download - Installer bauen
#
# Erzeugt dist\FevDownloadSetup.exe: eine einzelne Datei zum Weitergeben. Wer
# sie ausfuehrt, braucht weder Python noch sonst etwas vorinstalliert.
#
# Aufruf:  powershell -ExecutionPolicy Bypass -File build_installer.ps1
#
# Voraussetzung: setup.ps1 ist gelaufen (venv, ffmpeg in bin\, Symbol) und
# PyInstaller sowie Inno Setup 6 sind vorhanden. Fehlt eines, sagt das Script
# unten, wie es zu beschaffen ist.

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvPython  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SpecFile    = Join-Path $ProjectRoot "fevdl.spec"
$IssFile     = Join-Path $ProjectRoot "installer\FevDownload.iss"
$DistDir     = Join-Path $ProjectRoot "dist"

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
# 1. Voraussetzungen
# ---------------------------------------------------------------------------
Write-Step "Voraussetzungen pruefen"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Die Python-Umgebung fehlt. Bitte zuerst setup.ps1 ausfuehren." -ForegroundColor Red
    exit 1
}

# ffmpeg wird mitgeliefert, damit beim Empfaenger nichts nachgeladen werden
# muss. Ohne diese Dateien waere der Installer unbrauchbar.
foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
    $file = Join-Path $ProjectRoot "bin\$name"
    if (-not (Test-Path $file)) {
        Write-Host "bin\$name fehlt. Bitte zuerst setup.ps1 ausfuehren." -ForegroundColor Red
        exit 1
    }
}
Write-Ok "ffmpeg und ffprobe liegen bereit."

$IconFile = Join-Path $ProjectRoot "assets\fevdl.ico"
if (-not (Test-Path $IconFile)) {
    Write-Host "assets\fevdl.ico fehlt. Bitte zuerst setup.ps1 ausfuehren." -ForegroundColor Red
    exit 1
}

& $VenvPython -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller fehlt. Nachholen mit:" -ForegroundColor Red
    Write-Host "  .venv\Scripts\python.exe -m pip install pyinstaller" -ForegroundColor Red
    exit 1
}
Write-Ok "PyInstaller vorhanden."

# Sonst liesse sich ein Installer bauen, der zwar startet, aber TikTok nicht
# abrufen kann. Das nachgeladene reine Python-Paket ersetzt curl_cffi nicht.
& $VenvPython -c "from yt_dlp import YoutubeDL; ydl = YoutubeDL({'quiet': True}); assert ydl._get_available_impersonate_targets(), 'Browser-Netzwerkbibliothek fehlt'; ydl.close()"
if ($LASTEXITCODE -ne 0) {
    Write-Host "TikTok-Abhaengigkeiten fehlen. Nachholen mit:" -ForegroundColor Red
    Write-Host "  .venv\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}
Write-Ok "Browser-Netzwerkbibliothek fuer TikTok vorhanden."

# Inno Setup wird sowohl fuer den Benutzer als auch systemweit installiert -
# beide Orte pruefen.
$IsccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$Iscc = $null
foreach ($candidate in $IsccCandidates) {
    if (Test-Path $candidate) {
        $Iscc = $candidate
        break
    }
}
if (-not $Iscc) {
    Write-Host "Inno Setup 6 fehlt. Zu beziehen unter:" -ForegroundColor Red
    Write-Host "  https://jrsoftware.org/isdl.php" -ForegroundColor Red
    exit 1
}
Write-Ok "Inno Setup gefunden."
Write-Info $Iscc

# ---------------------------------------------------------------------------
# 2. Fassung aus dem Quelltext lesen
# ---------------------------------------------------------------------------
Write-Step "Fassung bestimmen"

# Eine einzige Quelle fuer die Fassungsnummer: __init__.py. Der Installer und
# das Ueber-Fenster wuerden sonst mit der Zeit auseinanderlaufen.
$InitFile = Join-Path $ProjectRoot "src\fevdl\__init__.py"
$Match = Select-String -Path $InitFile -Pattern '__version__\s*=\s*"([^"]+)"'
if (-not $Match) {
    Write-Host "In src\fevdl\__init__.py steht keine Fassungsnummer." -ForegroundColor Red
    exit 1
}
$AppVersion = $Match.Matches[0].Groups[1].Value
Write-Ok "Fev Download $AppVersion"

# ---------------------------------------------------------------------------
# 3. Programm packen
# ---------------------------------------------------------------------------
Write-Step "Programm packen (PyInstaller, dauert ein bis zwei Minuten)"

Set-Location $ProjectRoot

# Erst leerraeumen. Sonst blieben Dateien aus einem frueheren Lauf liegen -
# etwa ein von Hand hineinkopiertes bin\ - und der Installer packte ffmpeg
# doppelt ein: einmal aus dist\, einmal aus bin\.
$PackedDir = Join-Path $DistDir "FevDownload"
$ResolvedPackedDir = [System.IO.Path]::GetFullPath($PackedDir)
$ResolvedDistDir = [System.IO.Path]::GetFullPath($DistDir)
if ([System.IO.Path]::GetDirectoryName($ResolvedPackedDir) -ne $ResolvedDistDir) {
    throw "Ungueltiger Zielordner fuer den Build: $ResolvedPackedDir"
}
if (Test-Path -LiteralPath $ResolvedPackedDir) {
    Remove-Item -LiteralPath $ResolvedPackedDir -Recurse -Force
}

& $VenvPython -m PyInstaller --noconfirm --clean $SpecFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller ist gescheitert." -ForegroundColor Red
    exit 1
}

$AppExe = Join-Path $DistDir "FevDownload\FevDownload.exe"
if (-not (Test-Path $AppExe)) {
    Write-Host "FevDownload.exe wurde nicht erzeugt." -ForegroundColor Red
    exit 1
}
$PackedSize = (Get-ChildItem (Join-Path $DistDir "FevDownload") -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Ok ("Gepackt: {0:N0} MB" -f ($PackedSize / 1MB))

# ---------------------------------------------------------------------------
# 4. Installer bauen
# ---------------------------------------------------------------------------
Write-Step "Installer bauen (Inno Setup, hoechste Verdichtung - das dauert)"

& $Iscc "/DAppVersion=$AppVersion" $IssFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "Inno Setup ist gescheitert." -ForegroundColor Red
    exit 1
}

$Setup = Join-Path $DistDir "FevDownloadSetup.exe"
if (-not (Test-Path $Setup)) {
    Write-Host "FevDownloadSetup.exe wurde nicht erzeugt." -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Fertig." -ForegroundColor Green
Write-Host ""
Write-Host ("  {0}" -f $Setup) -ForegroundColor White
Write-Host ("  {0:N0} MB" -f ((Get-Item $Setup).Length / 1MB)) -ForegroundColor White
Write-Host ""
Write-Host "Diese eine Datei ist alles, was weitergegeben werden muss." -ForegroundColor Gray
Write-Host "Hinweis fuer die Empfaenger: Windows zeigt bei unsignierten" -ForegroundColor Gray
Write-Host "Programmen eine Warnung. Dort auf 'Weitere Informationen' und" -ForegroundColor Gray
Write-Host "dann auf 'Trotzdem ausfuehren' klicken." -ForegroundColor Gray
Write-Host ""
