# Fev Download - neue Fassung veroeffentlichen
#
# Ein Befehl: testen, Installer bauen, auf GitHub hochladen. Wer Fev Download
# installiert hat, bekommt die neue Fassung danach beim naechsten Start angeboten
# (siehe src\fevdl\core\appupdate.py).
#
#   1. In src\fevdl\__init__.py die Fassungsnummer erhoehen
#   2. Aenderungen committen
#   3. powershell -ExecutionPolicy Bypass -File release.ps1 -Notizen "Was ist neu"
#
# Optionen:
#   -Notizen      Text, der im Update-Dialog und auf GitHub erscheint
#   -OhneTests    Testlauf ueberspringen (nicht empfohlen)
#   -OhneBau      Den schon gebauten dist\FevDownloadSetup.exe veroeffentlichen,
#                 statt neu zu bauen. Fuer den Fall, dass genau diese Datei vorher
#                 geprueft wurde (z. B. mit --selbsttest). Verweigert sich, wenn
#                 seit dem Bau etwas im Quelltext geaendert wurde.

param(
    [string]$Notizen = "",
    [switch]$OhneTests,
    [switch]$OhneBau
)

# Bewusst nicht "Stop": PowerShell 5.1 wertet jede Ausgabe von git/gh auf dem
# Fehlerkanal (auch reine Statusmeldungen) als Abbruchgrund. Stattdessen wird
# nach jedem Aufruf $LASTEXITCODE geprueft.
$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ProjectRoot

function Write-Step($message) { Write-Host ""; Write-Host "==> $message" -ForegroundColor Cyan }
function Write-Ok($message)   { Write-Host "    $message" -ForegroundColor Green }
function Stop-Release($message) {
    Write-Host ""
    Write-Host "Abgebrochen: $message" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
Write-Step "Voraussetzungen"

# gh liegt nach der Installation nicht in jeder offenen Konsole im PATH.
$Gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $Gh) {
    $Candidate = "C:\Program Files\GitHub CLI\gh.exe"
    if (Test-Path $Candidate) { $Gh = $Candidate }
}
if (-not $Gh) { Stop-Release "GitHub CLI (gh) fehlt. Installieren mit: winget install GitHub.cli" }

& $Gh auth status *> $null
if ($LASTEXITCODE -ne 0) { Stop-Release "Bei GitHub nicht angemeldet. Einmalig: gh auth login" }
Write-Ok "GitHub CLI angemeldet."

$Dirty = git status --porcelain
if ($Dirty) {
    Write-Host $Dirty
    Stop-Release "Es gibt nicht committete Aenderungen. Erst committen, damit die Fassung genau dem Stand auf GitHub entspricht."
}
Write-Ok "Arbeitsbaum sauber."

$InitFile = Join-Path $ProjectRoot "src\fevdl\__init__.py"
$Match = Select-String -Path $InitFile -Pattern '__version__\s*=\s*"([^"]+)"'
if (-not $Match) { Stop-Release "In src\fevdl\__init__.py steht keine Fassungsnummer." }
$Version = $Match.Matches[0].Groups[1].Value
$Tag = "v$Version"
Write-Ok "Fassung $Version (Tag $Tag)"

& $Gh release view $Tag *> $null
if ($LASTEXITCODE -eq 0) {
    Stop-Release "Die Fassung $Version ist schon veroeffentlicht. Bitte in __init__.py erhoehen."
}

# ---------------------------------------------------------------------------
if (-not $OhneTests) {
    Write-Step "Tests (ohne Internet)"
    powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "tests\run_tests.ps1")
    if ($LASTEXITCODE -ne 0) { Stop-Release "Tests fehlgeschlagen." }
}

# ---------------------------------------------------------------------------
$Setup = Join-Path $ProjectRoot "dist\FevDownloadSetup.exe"

if ($OhneBau) {
    Write-Step "Vorhandenen Installer verwenden"
    if (-not (Test-Path $Setup)) { Stop-Release "dist\FevDownloadSetup.exe fehlt. Ohne -OhneBau neu bauen." }
    $Built = (Get-Item $Setup).LastWriteTime
    $Newer = Get-ChildItem (Join-Path $ProjectRoot "src"), (Join-Path $ProjectRoot "resolve"), (Join-Path $ProjectRoot "installer"), (Join-Path $ProjectRoot "assets") -Recurse -File -Exclude *.pyc |
        Where-Object { $_.LastWriteTime -gt $Built }
    $Newer += Get-Item (Join-Path $ProjectRoot "fevdl.spec"), (Join-Path $ProjectRoot "requirements.txt") | Where-Object { $_.LastWriteTime -gt $Built }
    if ($Newer) {
        $Newer | ForEach-Object { Write-Host ("    neuer als der Installer: " + $_.FullName) -ForegroundColor Yellow }
        Stop-Release "Seit dem Bau wurde etwas geaendert. Bitte ohne -OhneBau neu bauen."
    }
    Write-Ok "Installer ist neuer als der gesamte Quelltext."
} else {
    Write-Step "Installer bauen"
    powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "build_installer.ps1")
    if ($LASTEXITCODE -ne 0) { Stop-Release "Der Bau ist fehlgeschlagen." }
    if (-not (Test-Path $Setup)) { Stop-Release "dist\FevDownloadSetup.exe fehlt." }
}
Write-Ok ("{0:N0} MB" -f ((Get-Item $Setup).Length / 1MB))

# ---------------------------------------------------------------------------
Write-Step "Auf GitHub hochladen"

git push origin main
if ($LASTEXITCODE -ne 0) { Stop-Release "git push ist fehlgeschlagen." }

if (-not $Notizen) { $Notizen = "Fev Download $Version" }
& $Gh release create $Tag $Setup --target main --title "Fev Download $Version" --notes $Notizen
if ($LASTEXITCODE -ne 0) { Stop-Release "Das Release liess sich nicht anlegen." }

Write-Host ""
Write-Host "Fertig: Fassung $Version ist veroeffentlicht." -ForegroundColor Green
Write-Host "Installierte Programme bieten sie beim naechsten Start an." -ForegroundColor Gray
Write-Host ""
