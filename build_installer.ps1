# Fev Download - Installer bauen
#
# Erzeugt dist\FevDownloadSetup.exe: eine einzelne Datei zum Weitergeben. Wer
# sie ausfuehrt, braucht weder Python noch sonst etwas vorinstalliert.
#
# Aufruf:  powershell -ExecutionPolicy Bypass -File build_installer.ps1
# Vorpruefung ohne Bau: gleicher Aufruf mit -NurPruefen.
# Standard: Offline-Tests -> PyInstaller -> Selbsttest mit Netz -> Inno Setup.
#
# Voraussetzung: setup.ps1 ist gelaufen (venv, ffmpeg in bin\, Symbol) und
# PyInstaller sowie Inno Setup 6 sind vorhanden. Fehlt eines, sagt das Script
# unten, wie es zu beschaffen ist.

param(
    [switch]$NurPruefen,
    [switch]$OhneTests
)

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

# Vor Tests/Packen abbrechen, wenn die exakten Quellen oder Hinweise fehlen.
# NurPruefen fuehrt dieselbe Offline-Pruefung aus, laedt aber nichts nach.
$FfmpegSourceTool = Join-Path $ProjectRoot "tools\ffmpeg_sources.py"
& $VenvPython $FfmpegSourceTool --check
if ($LASTEXITCODE -ne 0) { throw "ffmpeg-Quellenpaket unvollstaendig oder unpassend. setup.ps1 -NurFfmpeg ausfuehren." }


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
if ($AppVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "Die Fassungsnummer muss aus drei Zahlen bestehen: x.y.z"
}
Write-Ok "Fev Download $AppVersion"

# Eine Vorpruefung darf weder bauen noch vorhandene Artefakte loeschen.
if ($NurPruefen) {
    Write-Ok "Vorpruefung bestanden. Kein Bau und kein Selbsttest ausgefuehrt."
    exit 0
}

if (-not $OhneTests) {
    Write-Step "Tests (ohne Internet)"
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "tests\run_tests.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Tests fehlgeschlagen; es wird kein Installer gebaut." }
}

# ---------------------------------------------------------------------------
# 3. Programm packen
# ---------------------------------------------------------------------------
Write-Step "Programm packen (PyInstaller, dauert ein bis zwei Minuten)"

Set-Location $ProjectRoot

# Bei spaeterem Abbruch darf kein alter Installer als neues Ergebnis aussehen.
foreach ($OldArtifact in @("FevDownloadSetup.exe", "bau.json")) {
    $OldArtifactPath = Join-Path $DistDir $OldArtifact
    if (Test-Path -LiteralPath $OldArtifactPath) { Remove-Item -LiteralPath $OldArtifactPath -Force }
}

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

# PyInstaller schreibt auch INFO auf stderr. PowerShell 5.1 behandelt das bei
# umgeleiteten Bauprotokollen sonst unter "Stop" als NativeCommandError.
# Den echten Erfolg ausschliesslich anhand des Rueckgabewerts entscheiden.
$PreviousErrorAction = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & $VenvPython -m PyInstaller --noconfirm --clean $SpecFile 2>&1 | ForEach-Object { Write-Host $_ }
    $PyInstallerExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $PreviousErrorAction
}
if ($PyInstallerExitCode -ne 0) {
    Write-Host "PyInstaller ist gescheitert." -ForegroundColor Red
    exit 1
}

$AppExe = Join-Path $DistDir "FevDownload\FevDownload.exe"
if (-not (Test-Path $AppExe)) {
    Write-Host "FevDownload.exe wurde nicht erzeugt." -ForegroundColor Red
    exit 1
}
# Dieselben Laufzeitdateien pruefen, die spaeter im Installer landen. Neue
# Logos/Bilder unter assets/ kommen automatisch mit; design/ bleibt draussen.
$PackedBin = Join-Path $PackedDir "bin"
New-Item -ItemType Directory -Path $PackedBin -Force | Out-Null
foreach ($Binary in @("ffmpeg.exe", "ffprobe.exe")) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "bin\$Binary") -Destination $PackedBin -Force
}
foreach ($LegalPart in @("licenses", "HERKUNFT.txt")) {
    $LegalSource = Join-Path $ProjectRoot "bin\$LegalPart"
    if (Test-Path -LiteralPath $LegalSource) {
        Copy-Item -LiteralPath $LegalSource -Destination $PackedBin -Recurse -Force
    }
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot "assets") -Destination $PackedDir -Recurse -Force

# Originallizenzen aus genau der gebauten Umgebung mitnehmen. Keine gesamte
# Entwicklungsumgebung und keine persoenlichen Einstellungen einpacken.
$LicenseScript = @'
import importlib.metadata as md
import json
import pathlib
import shutil
import sys

target = pathlib.Path(sys.argv[1]) / "licenses"
target.mkdir(exist_ok=True)
versions = {"Python": sys.version.split()[0]}
for name in ("yt-dlp", "PySide6", "PySide6-Essentials", "PySide6-Addons",
             "shiboken6", "curl_cffi", "cffi", "certifi", "pycparser", "pyinstaller"):
    dist = md.distribution(name)
    versions[name] = dist.version
    found = []
    for item in dist.files or []:
        if any(word in item.name.upper() for word in ("LICENSE", "COPYING", "NOTICE")):
            source = pathlib.Path(dist.locate_file(item))
            if source.is_file():
                destination = target / name / pathlib.Path(str(item))
                if ".." in pathlib.Path(str(item)).parts:
                    raise SystemExit("Ungueltiger Lizenzpfad: " + name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                found.append(str(item))
    if not found:
        raise SystemExit("Originallizenz fehlt: " + name)
python_license = pathlib.Path(sys.base_prefix) / "LICENSE.txt"
shutil.copyfile(python_license, target / "Python-LICENSE.txt")
(target / "PAKETE.json").write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")
'@
$LicenseScript | & $VenvPython - $PackedDir
if ($LASTEXITCODE -ne 0) { throw "Originallizenzen konnten nicht gesammelt werden." }

# Belegte Zusatzhinweise samt unveraenderten Copyright-/Lizenztexten; danach
# ausschliesslich die im Manifest aufgefuehrten Quellen und gyan-Originale.
$PackedLicenses = Join-Path $PackedDir "licenses"
Copy-Item -Path (Join-Path $ProjectRoot "installer\licenses\*") -Destination $PackedLicenses -Recurse -Force
& $VenvPython $FfmpegSourceTool --check --copy-to $PackedLicenses
if ($LASTEXITCODE -ne 0) { throw "ffmpeg-Quellen konnten nicht in das Paket uebernommen werden." }
Copy-Item -LiteralPath (Join-Path $ProjectRoot "installer\LIZENZEN.txt") -Destination $PackedDir -Force


$PackedSize = (Get-ChildItem (Join-Path $DistDir "FevDownload") -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Ok ("Gepackt: {0:N0} MB" -f ($PackedSize / 1MB))

# Die windowed EXE hat keine Konsole. Auf ihren eigenen Prozess warten, nicht
# auf einen Installer, der seinerseits die App neu startet (siehe CLAUDE.md).
Write-Step "Frisch gepackte App pruefen (mit Internet)"
$TestData = Join-Path $env:TEMP ("fevdl-bautest-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TestData | Out-Null
$PreviousLocalAppData = $env:LOCALAPPDATA
$PreviousUpdateCheck = $env:FEVDL_NO_UPDATE_CHECK
try {
    # Ein nachgeladenes yt-dlp darf keinen Fehler des Pakets verdecken; auch
    # die echten IPC-Dateien und Einstellungen sollen unberuehrt bleiben.
    $env:LOCALAPPDATA = $TestData
    $env:FEVDL_NO_UPDATE_CHECK = "1"
    $SelfTest = Start-Process -FilePath $AppExe -ArgumentList "--selbsttest" -WindowStyle Hidden -PassThru
    if (-not $SelfTest.WaitForExit(600000)) {
        $SelfTest.Kill()
        throw "Selbsttest nach zehn Minuten abgebrochen."
    }
    $SelfTest.Refresh()
    $Report = Join-Path $TestData "FevDownloader\selbsttest.txt"
    if (Test-Path -LiteralPath $Report) { Get-Content -LiteralPath $Report }
    if ($SelfTest.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $Report)) {
        throw "Selbsttest fehlgeschlagen. Bericht: $Report"
    }
} finally {
    $env:LOCALAPPDATA = $PreviousLocalAppData
    $env:FEVDL_NO_UPDATE_CHECK = $PreviousUpdateCheck
}

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
# Dieser Nachweis bindet -OhneBau an exakt diesen getesteten Stand.
$Evidence = [ordered]@{
    version = $AppVersion
    commit = (git rev-parse HEAD)
    sha256 = (Get-FileHash -LiteralPath $Setup -Algorithm SHA256).Hash.ToLowerInvariant()
    selbsttest = "bestanden"
    gebaut_utc = (Get-Date).ToUniversalTime().ToString("o")
    signiert = ((Get-AuthenticodeSignature -LiteralPath $Setup).Status -eq "Valid")
    arbeitsbaum_sauber = (-not (git status --porcelain))
    ffmpeg_quellen_manifest_sha256 = (Get-FileHash -LiteralPath (Join-Path $ProjectRoot "installer\ffmpeg-lock.json") -Algorithm SHA256).Hash.ToLowerInvariant()
    lizenzpruefung = "offen: Bibliotheksquellen/Build-Skripte sowie Qt/curl; siehe LIZENZEN.txt"
}
if ($LASTEXITCODE -ne 0) { throw "Git-Stand konnte nicht erfasst werden." }
$Evidence | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $DistDir "bau.json") -Encoding UTF8

# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Fertig." -ForegroundColor Green
Write-Host ""
Write-Host ("  {0}" -f $Setup) -ForegroundColor White
Write-Host ("  {0:N0} MB" -f ((Get-Item $Setup).Length / 1MB)) -ForegroundColor White
Write-Host ""
Write-Host "Vor der Weitergabe die Bau-Freigabe in SICHERHEIT.md pruefen (auch Quellen/Lizenzen)." -ForegroundColor Gray
Write-Host "Windows kann bei unsignierten Programmen warnen; Herausgeber und Download-Quelle pruefen." -ForegroundColor Gray
Write-Host ""
