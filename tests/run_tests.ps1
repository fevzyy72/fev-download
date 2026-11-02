# Fev Download - Tests
#
#   powershell -ExecutionPolicy Bypass -File tests\run_tests.ps1
#   powershell -ExecutionPolicy Bypass -File tests\run_tests.ps1 -MitNetz
#
# Ohne -MitNetz laufen nur die Tests, die kein Internet brauchen. Sie decken
# Oberflaeche, Datenaustausch und das Resolve-Script ab und dauern zusammen
# etwa eine halbe Minute.
#
# Wichtig fuer neue Tests: Jedes MainWindow am Ende schliessen und
# _start_preview_fallback stilllegen. Sonst laufen Hintergrund-Threads beim
# Beenden weiter und Python raeumt die Qt-Objekte in falscher Reihenfolge ab -
# das endet in einem Absturz, obwohl der Test inhaltlich bestanden hat.

param([switch]$MitNetz)

$TestDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $TestDir
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Die Python-Umgebung fehlt. Bitte zuerst setup.ps1 ausfuehren." -ForegroundColor Red
    exit 1
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"

Write-Host ""
Write-Host "==> Syntaxpruefung" -ForegroundColor Cyan
& $Python -m compileall -q (Join-Path $ProjectRoot "src") (Join-Path $ProjectRoot "resolve") (Join-Path $ProjectRoot "tools") (Join-Path $ProjectRoot "launch.pyw")
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Fehler beim Uebersetzen." -ForegroundColor Red
    exit 1
}
Write-Host "    OK" -ForegroundColor Green

# Ohne Netz -------------------------------------------------------------
$Offline = @(
    @{ Datei = "test_security.py"; Was = "Sicherheitsgrenzen: Redirects, Hash, ZIP, Links und Dateinamen" },
    @{ Datei = "test_thumbnail_limit.py"; Was = "Vorschaubild: nur http/https, hoechstens 10 MiB" },
    @{ Datei = "test_tiktok_support.py"; Was = "TikTok ohne FPS, Fehlermeldungen und Aktualisierungen" },
    @{ Datei = "test_preview_format.py"; Was = "Vorschau: Formatwahl fuer YouTube, TikTok und andere" },
    @{ Datei = "test_ytdlp_vorrang.py";  Was = "yt-dlp: die neuere Fassung gewinnt (mitgeliefert/nachgeladen)" },
    @{ Datei = "test_appupdate.py";      Was = "App-Aktualisierung ueber GitHub und stille yt-dlp-Suche" },
    @{ Datei = "test_update_gui.py";     Was = "Aktualisierung im Fenster: Angebot, Download, Installer" },
    @{ Datei = "test_ipc.py";          Was = "Datenaustausch job.json / result.json" },
    @{ Datei = "test_launcher.py";     Was = "Resolve-Script: Installation und Import" },
    @{ Datei = "smoke_gui.py";         Was = "Oberflaeche: Grundfunktionen" },
    @{ Datei = "test_job_gui.py";      Was = "Resolve-Auftrag und Rueckmeldung" },
    @{ Datei = "test_done_button.py";  Was = "Herunterladen -> Fertig -> schliessen" },
    @{ Datei = "test_shortcuts.py";    Was = "Kuerzel I/O stoeren das Tippen nicht" },
    @{ Datei = "test_polish.py";       Was = "Einstellungen, Ablegen, Zwischenablage, Symbol" },
    @{ Datei = "test_library.py";      Was = "Bibliothek: Suche, Filter und Navigation" },
    @{ Datei = "test_segments.py";     Was = "Scrub-Vorschau und mehrere Ausschnitte" },
    @{ Datei = "test_portrait.py";     Was = "Hochformat und Vorschau-Ausweichloesung" },
    @{ Datei = "test_waveform_gui.py"; Was = "Wellenform-Knopf" },
    @{ Datei = "test_sammelmappe.py";  Was = "Sammelmappe: Tastatur, Zoom, Geometrie, Lieferliste" },
    @{ Datei = "test_clean_exit.py";   Was = "Sauberes Beenden" }
)

# Mit Netz --------------------------------------------------------------
$Online = @(
    @{ Datei = "test_tiktok_download.py"; Was = "TikTok: Vorschau, Video, Ausschnitt und Ton wirklich laden" },
    @{ Datei = "test_waveform.py";         Was = "Wellenform aus echter Tonspur" },
    @{ Datei = "test_preview_fallback.py"; Was = "Vorschaudatei wirklich laden" },
    @{ Datei = "test_preview.py";          Was = "Stream im Player abspielen" },
    @{ Datei = "test_segments_netz.py";    Was = "Zwei Ausschnitte wirklich laden" },
    @{ Datei = "test_selbsttest.py";       Was = "Selbsttest: Analyse, Ausschnitt, Vorschau ohne Fenster" }
)

$Liste = $Offline
if ($MitNetz) { $Liste = $Offline + $Online }

Write-Host ""
Write-Host "==> Tests" -ForegroundColor Cyan
$failed = 0
foreach ($eintrag in $Liste) {
    $pfad = Join-Path $TestDir $eintrag.Datei
    # Auch QSettings(org, app) muss isoliert sein: LOCALAPPDATA allein
    # schuetzt unter Windows nicht vor clear() auf den echten Einstellungen.
    $ausgabe = & $Python -u (Join-Path $TestDir "run_isolated.py") $pfad 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host ("    OK      " + $eintrag.Was) -ForegroundColor Green
    } else {
        Write-Host ("    FEHLER  " + $eintrag.Was + "  (" + $eintrag.Datei + ")") -ForegroundColor Red
        $ausgabe | Select-Object -Last 12 | ForEach-Object { Write-Host ("            " + $_) -ForegroundColor DarkGray }
        $failed++
    }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "Alle $($Liste.Count) Tests bestanden." -ForegroundColor Green
    if (-not $MitNetz) {
        Write-Host "(Die Tests mit Internetzugriff laufen nur mit -MitNetz.)" -ForegroundColor DarkGray
    }
} else {
    Write-Host "$failed von $($Liste.Count) Tests fehlgeschlagen." -ForegroundColor Red
    exit 1
}
Write-Host ""
