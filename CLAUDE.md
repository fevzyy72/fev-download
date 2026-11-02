# CLAUDE.md — Arbeitswissen zu diesem Projekt

Diese Datei richtet sich an KI-Assistenten, die an diesem Projekt weiterarbeiten.
Sie erklärt **warum** die Dinge so sind, wie sie sind. Was das Programm kann und
wie man es bedient, steht in [README.md](README.md).

Sprache: Der gesamte Code, alle Kommentare und alle Texte für Nutzer sind auf
Deutsch, ohne Umlaute in Quelltextdateien (`ae`, `oe`, `ue`, `ss`). Markdown-
Dateien dürfen Umlaute enthalten. Bitte beibehalten.

**Nicht alles lesen.** Die Datei ist lang (Fallstricke in Abschnitt 5 sind je Thema
gebündelt): erst Abschnitt 0, dann nur die Stelle, die zur Aufgabe passt.

---

## 0. Aktueller Stand (Stand: 3. Nov. 2026) — zuerst lesen

**Fassung 1.2.0** (Redesign „Sammelmappe“, Sicherheitshärtung, neues Symbol, Schleife/Leertaste)
wird am 3. Nov. 2026 gebaut und auf GitHub veröffentlicht: `fevzyy72/fev-download`
(Branch `main`, Release `v1.2.0` mit `FevDownloadSetup.exe`). Davor war 1.1.0 draußen.
Beim Entwicklungsrechner ist 1.1.0 installiert; `install.json` zeigt auf die installierte
`.exe` (nicht auf den Quelltext – siehe Abschnitt 3). Die Freunde bekommen 1.2.0 per
Installer-Datei bzw. über die App-Aktualisierung.

**Zusätze am 3. Nov. 2026:**
- Klick auf einen gemerkten Ausschnitt spielt ihn **in Schleife** (`PreviewPlayer.loop_range`),
  bis man pausiert (Leertaste) oder selbst springt. Leertaste = Abspielen/Pause am Hauptfenster
  (`action_play`); nur ein per **Tab** fokussiertes Element behält die Leertaste für sich
  (`_Interactive.event` / `TrimBar.event` nehmen `ShortcutOverride` an) – nach einem Mausklick
  gilt sie dem Video.
- Leerer Zettel auf dem Startbildschirm und der Hinweis „laden gleichzeitig“ sind entfernt –
  der Besitzer will keine erklärenden Zusatztexte.
- Programmsymbol: weißes **F, dessen Stamm als Download-Pfeil über einer Ablage endet**
  (`icons.draw_logo` / `draw_logo_small`, `assets/fevdl.ico` via `tools/make_icon.py`); von Codex entworfen.
- `design/` steht in `.gitignore` (nur lokal, enthält Beispielpfade).
- Lizenz-/Quellenprüfung (ffmpeg GPL, Qt, curl) ist **nicht vollständig** – siehe `SICHERHEIT.md`.
- **1.2.0 ist veröffentlicht** (GitHub-Release `v1.2.0`, 112 MB) und lief bei einem Freund und
  in Resolve beim Besitzer. Leerlauf: ~107 MB RAM, 0 % CPU; installiert ~354 MB.
- **Defender-Fehlalarm:** `Trojan:Win32/Bearfoos.A!ml` (ML-Schätzung) nimmt `FevDownload.exe`
  in Quarantäne – auch Startmenü-Symbol und Deinstallationseintrag; Resolve meldet dann
  „Programm nicht zu finden“ (`launcher.log`). Abhilfe: Ordner `%LOCALAPPDATA%\Programs\FevDownload`
  als Ausschluss eintragen und in *Schutzverlauf → Auf Gerät zulassen* (oder Installer erneut).
  Nicht den Scanner abschalten lassen. Die Ursache ist nicht belegt (unsigniert, PyInstaller-Aufbau,
  yt-dlp/curl_cffi, Updater, Start über `fuscript.exe`). Offen: bei Microsoft als Fehlalarm melden,
  Probe mit leerem PyInstaller-Programm, eigener Bootloader, Signatur.
- Aufgeräumt: `build/` und `dist/FevDownload` sind reine Zwischenstände (neu erzeugbar),
  `downloads/` waren Testreste. In `dist/` bleibt nur `FevDownloadSetup.exe` + `bau.json`.

**Diese Runde erledigt** (Details je in Abschnitt 5/6):
- YouTube-Vorschau repariert (`download.PREVIEW_FORMAT`), neueres yt-dlp gewinnt gegen
  einen veralteten Nachlade-Ordner (`paths.bundled_ytdlp_version`).
- Pakete aktuell: yt-dlp 2026.10.26, curl_cffi 0.17, PySide6 6.12, PyInstaller 6.22.3.
- Selbst-Aktualisierung: yt-dlp still beim Start, neue App-Fassungen über GitHub-Releases
  (`core/appupdate.py`, Abschnitt 5 „Aktualisierung der App“).
- `FevDownload.exe --selbsttest` (Abschnitt 5 „Verpacken“), `release.ps1`, `LIZENZEN.txt`.
- Tests: damals 17 ohne Netz, 6 mit `-MitNetz`, alle grün.

**Redesign „D – Sammelmappe“ umgesetzt (2. Nov. 2026), in 1.2.0 enthalten.**
Vorlage: `design/looks2/d-sammelmappe/` (vom Besitzer gewählt). Fotos der echten Qt-Oberfläche:
`design/umsetzung/*.jpg`, neu erzeugen mit `tools/umsetzung_fotos.py` (ohne Netz, BBB-Standbild).
- Aufbau: schmale Leiste (Logo, „Sammeln“, „Dateien“, Menü ☰ = `Strg+K`; **keine Menüleiste mehr**,
  alle `QAction`s hängen per `addAction` am Fenster, sonst greifen I/O/M nicht), links „Deine Quelle“,
  rechts „Sammelmappe“ (Zettel + abgelegte Ausschnitte + Hauptaktion → Lieferliste beim Laden).
  Vor der ersten Analyse nur der Einstieg; das Link-Feld wird danach in die Quelle umgehängt
  (`_place_source_editor`).
- Eigene Bedienelemente in `gui/widgets.py` (QAbstractButton-Basis: Fokusring nur bei Tab,
  Hover 120 ms, Druck 0,97), Symbole + Logo in `gui/icons.py` (eigener SVG-Pfad-Leser – **QtSvg ist
  in `fevdl.spec` ausgeschlossen**). `ChoiceGroup` hat die QComboBox-Schnittstelle (`findData`,
  `currentData` …), daher blieb die Logik zu `Mode.value`/Qualität unverändert.
- Zeitleiste (`trim_bar.py`): Übersicht + Detail ≥ 146 px, zoomt auf Auswahl ± Rand (Lupe schaltet
  um). **Beim Ziehen steht die Skala still**, erst nach dem Loslassen gleitet sie (160 ms); über den
  Rand gezogen erweitert sie sich. Werte rasten auf 0,1 s, Zeitfelder zeigen Zehntel
  (`precise_timecode`). Wellenform jetzt mit 10 Werten/s (max. 36 000), sonst wäre der Zoom grob.
- `worker.DownloadWorker.partReady(index, path)` neu – die Lieferliste hakt jeden Auftrag einzeln ab.
- Einzige Backend-Änderung: Text in `core/errors.py` („Hilfe ->“ → „Menue (unten links) ->“).
- Tests: 19 ohne Netz grün (neu `test_sammelmappe.py`; `test_library.py` prüft jetzt Namen/Tooltips
  statt alter Objektnamen). Mit Netz, in Resolve, bei 125/150 % Skalierung **nicht geprüft**.
- Offen: Abweichungen vom Mockup bewusst (Link-Feld bleibt in der Quelle sichtbar, „Ablegen“ nur
  einmal im Zettel statt doppelt, kein Bildformat-Knopf und kein „Mit BBB ausprobieren“ – waren
  Mockup-Hilfen). Nur helles Thema. Nutzertexte weiter mit ae/oe/ue. Installer/Release erst nach
  Freigabe des Besitzers (Nummer erhöhen!). Bibliotheks-Vorschaubilder brauchen ~3 s je Datei
  (ffmpeg `thumbnail=240`, unverändert) – fiel erst jetzt auf.

**Arbeitsweise mit dem Besitzer:** Er schreibt Deutsch und knapp, will kurze Antworten und
ehrliche Einschätzungen, vor allem vor Veröffentlichungen. Nichts Online-Sichtbares ohne
Freigabe (GitHub-Konto `fevzyy72`, `gh` ist installiert unter
`C:\Program Files\GitHub CLI\gh.exe`). Neue Fassung: Nummer in `src\fevdl\__init__.py`
erhöhen, committen, `release.ps1`.

**Fallen aus der Redesign-Runde:** Ein Kind-Widget, das man ausdrücklich `setEnabled(False)`
setzt, wird beim Freigeben des Elternteils **nicht** wieder aktiv (Qt merkt sich „selbst gesperrt“)
– darum vererbt `ChoiceGroup` den Zustand nur. Ein neuer `objectName` wirkt erst nach
`style().unpolish/polish`. Fokusring nur für `Tab/Backtab/Shortcut`-Gründe, sonst leuchtet er schon
beim Start.

**Fallen aus der Runde davor:** In PowerShell 5.1 nie `Start-Process -Wait` auf den Installer
(wartet auf die neu gestartete App); Installer-Update braucht erzwungenes Schließen
(Abschnitt 5); mehrzeilige Python-Skripte nicht per Heredoc in die Git-Bash, sondern als
Datei schreiben.

---

## 1. Was das ist

Ein Werkzeug, das Videos von YouTube und anderen Plattformen lädt, einen
Ausschnitt herausschneidet und ihn in den Media Pool von DaVinci Resolve legt.
Gestartet wird es aus Resolve heraus über `Workspace → Scripts → Utility`.

Zielumgebung: **Windows**, DaVinci Resolve **21.0.3 (kostenlose Version)**,
Python 3.13.

---

## 2. Die eine Einschränkung, aus der alles folgt

**Seit DaVinci Resolve 19.1 ist Scripting von außen in der kostenlosen Version
gesperrt.** Ein eigenständiges Programm kann die Resolve-Schnittstelle nicht
erreichen. Nur ein Script, das Resolve selbst startet, hat Zugriff.

Daraus folgt der gesamte Aufbau:

```
Resolve: Workspace → Scripts → Utility → FevDownloader
   │  (läuft IN Resolve, hat die Schnittstelle, nur Standardbibliothek)
   │
   ├─ 1. schreibt job.json
   ├─ 2. startet die Oberfläche als eigenen Prozess (.venv\Scripts\pythonw.exe)
   │                                    │
   │                                    │  (eigener Prozess, PySide6 + yt-dlp,
   │                                    │   KEIN Zugriff auf Resolve)
   │                                    ├─ Link, Vorschau, Ausschnitt, Download
   │                                    └─ schreibt result.json nach jedem Download
   │                                    ▼
   └─ 3. pollt result.json → media_pool.ImportMedia() → Clip im Media Pool
```

Austauschordner: `%LOCALAPPDATA%\FevDownloader\`
(`install.json`, `job.json`, `result.json`, `launcher.log`)

**Wichtig:** `resolve/FevDownloader.py` läuft unter Resolves eigenem Python
(`fuscript.exe`), nicht unter `.venv`. Es darf **ausschließlich die
Standardbibliothek** verwenden. Kein `yt_dlp`, kein `PySide6`, keine Typ-
Annotationen aus `__future__` nötig — konservativ halten.

Verifiziert: Resolve bringt Python 3.13.10 (64 Bit) selbst mit; die
Nutzerinstallation wird dafür nicht gebraucht.

---

## 3. Befehle

```powershell
# Einrichtung (venv, yt-dlp, PySide6, ffmpeg nach bin/, Symbol)
powershell -ExecutionPolicy Bypass -File setup.ps1

# Einbindung in Resolve (kopiert das Script, schreibt install.json)
powershell -ExecutionPolicy Bypass -File install_plugin.ps1

# Installer zum Weitergeben bauen -> dist\FevDownloadSetup.exe (~97 MB)
powershell -ExecutionPolicy Bypass -File build_installer.ps1

# Neue Fassung veröffentlichen: Tests, Bau, git push, GitHub-Release (siehe 5., "Aktualisierung der App")
powershell -ExecutionPolicy Bypass -File release.ps1 -Notizen "Was ist neu"

# Oberfläche starten
powershell -ExecutionPolicy Bypass -File run_gui.ps1

# Tests (ohne Internet, ~30 s)
powershell -ExecutionPolicy Bypass -File tests\run_tests.ps1
# Mit den Tests, die wirklich etwas laden
powershell -ExecutionPolicy Bypass -File tests\run_tests.ps1 -MitNetz

# Download-Motor ohne Oberfläche prüfen
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m fevdl.cli probe "<link>"
.venv\Scripts\python.exe -m fevdl.cli get "<link>" --mode video_audio --height 1080 --start 1:00 --end 1:30
```

Nach Änderungen an `resolve/FevDownloader.py` muss `install_plugin.ps1` erneut
laufen **und Resolve neu gestartet werden** — Scripts werden nur beim Start
eingelesen. Änderungen unter `src/` wirken sofort, da von dort gelesen wird —
**aber nur, wenn Resolve auch den Quelltext startet.** `install.json` entscheidet
das: Zeigt `project_root` auf den Projektordner (so setzt es `install_plugin.ps1`),
läuft der Quelltext. Spielt man den Installer ein, biegt er den Zeiger auf
`%LOCALAPPDATA%\Programs\FevDownload` um, und Resolve startet die fertige `.exe` —
Änderungen in `src/` bleiben dann unsichtbar, bis man `install_plugin.ps1` erneut
ausführt. Beim Entwickeln zuerst `install.json` prüfen.

---

## 4. Aufbau der Dateien

```
davinciplugin/
├── setup.ps1                 Umgebung, Pakete, ffmpeg, Symbol
├── install_plugin.ps1        Script nach Resolve kopieren, install.json schreiben
├── run_gui.ps1               Oberfläche starten (Entwicklung)
├── build_installer.ps1       Weitergabe: PyInstaller + Inno Setup in einem Lauf
├── release.ps1               Veröffentlichen: Tests + Bau + git push + GitHub-Release
├── fevdl.spec                Bauplan für PyInstaller (Ausschlüsse!)
├── installer/FevDownload.iss Bauplan für Inno Setup (Installer)
├── launch.pyw                Einstieg ohne Konsolenfenster (Verknüpfung + Resolve)
├── requirements.txt          yt-dlp, PySide6
├── bin/                      ffmpeg.exe, ffprobe.exe (lokal, nicht eingecheckt)
├── assets/fevdl.ico          Programmsymbol
├── PRODUCT.md                Produktbeschreibung (Skill impeccable), Basis für Design-Arbeit
├── design/                   Vorlagen (Codex); looks2/d-sammelmappe = gewählt; umsetzung/ = Qt-Fotos
├── tools/make_icon.py        Erzeugt assets/fevdl.ico aus gui/icons.draw_logo (16–256 px)
├── tools/umsetzung_fotos.py  Bildschirmfotos aller Zustände nach design/umsetzung/
├── tests/                    Testreihe + run_tests.ps1
├── resolve/
│   ├── FevDownloader.py      Läuft IN Resolve  ← nur Standardbibliothek!
│   └── _FevTest.py           Diagnose: prüft Resolve-Verbindung und Python
└── src/fevdl/
    ├── __main__.py           Einstieg, Argument --job, Taskleisten-Kennung
    ├── paths.py              Alle Pfade an einer Stelle
    ├── ipc.py                job.json / result.json
    ├── cli.py                Kommandozeile zum Prüfen des Motors
    ├── core/
    │   ├── models.py         Mode, Quality, VideoInfo, DownloadRequest, Progress
    │   ├── probe.py          Metadaten, Qualitäten, Vorschau- und Tonspuradresse
    │   ├── download.py       Download, Ausschnitt, H.264-Umwandlung, Vorschaudatei
    │   ├── waveform.py       Lautstärkeverlauf über ffmpeg
    │   ├── thumbs.py         Standbilder der Bibliothek, mit Zwischenspeicher
    │   ├── update.py         Holt neueres yt-dlp von PyPI nach (auch still beim Start)
    │   ├── appupdate.py      Neue App-Fassung: GitHub-Release abfragen, Installer laden und starten
    │   └── errors.py         Deutsche Fehlermeldungen (humanize)
    └── gui/
        ├── main_window.py    Hauptfenster: Leiste, Quelle, Sammelmappe, Lieferliste
        ├── library_page.py   Medienbibliothek („Dateien“): Suche, Filter, Zeilen per Delegate
        ├── preview_player.py Player, Bildformat (dunkle Bühne), Ausweichmeldung
        ├── trim_bar.py       Zeitleiste: Übersicht + gezoomtes Detail, selbst gezeichnet
        ├── widgets.py        Eigene Bedienelemente (Knöpfe, Karten, Chips, Schalter, Hauptaktion …)
        ├── icons.py          Strichsymbole + Logo als QPainter-Pfade
        ├── worker.py         QThreads: Probe, Thumbnail, Preview, Waveform,
        │                     Download (auch mehrere), LibraryThumb
        ├── typography.py     Schriften  ← Schriftgrößen NUR hier, nie im Stylesheet
        └── style.py          Farben, Rahmen, Abstände
```

---

## 5. Fallstricke — bitte vor dem Ändern lesen

Jeder Punkt hier hat echte Zeit gekostet und ist im Code kommentiert.

### yt-dlp

**TikTok braucht `curl_cffi`, auch bei aktuellem yt-dlp.** Ohne diese native
Browser-Netzwerkbibliothek antwortete der Beispiel-Link mit nur 537 Bytes und
`Unexpected response from webpage request`. Der bisherige reine Python-Updater
kann sie nicht nachliefern. Deshalb `yt-dlp[curl-cffi]` und `curl_cffi` in den
Abhängigkeiten lassen. `fevdl.spec` sammelt auch `yt_dlp.networking` und das ganze
curl-Paket samt DLL; der Bau prüft, ob Browser-Ziele verfügbar sind.

Die Obergrenze für `curl_cffi` in `requirements.txt` folgt yt-dlp: Jede yt-dlp-Fassung
nennt in ihren Metadaten, welche `curl_cffi`-Fassungen sie verträgt (`<0.18` bei
2026.10.26). Bei einem yt-dlp-Sprung die Grenze mitprüfen, sonst hält sie ein
altes `curl_cffi` fest — so lag es zeitweise auf 0.14.0, obwohl yt-dlp 0.16 empfahl.

**Keine FPS-Angabe bedeutet nicht „kein Video“.** TikTok nennt oft Auflösung und
Codec, aber keine Bildrate. In `_collect_qualities()` muss eine neue Höhe auch
mit FPS 0 aufgenommen werden. Sonst schaltet die Oberfläche fälschlich auf
„Nur Ton“. Abgesichert in `test_tiktok_support.py`; `test_tiktok_download.py`
prüft mit Netz zusätzlich Vorschau, Clip, Ausschnitt und Tonspur.

**PyPI und yt-dlp schreiben Fassungen unterschiedlich:** `2026.8.19` und
`2026.08.19` sind dieselbe Fassung. Der Updater vergleicht numerisch und zeigt
die tatsächlich geladene Fassung, nicht eine erst nach dem Neustart wirksame.

**`ffmpeg_location` allein genügt nicht.** Bei der Prüfung, ob ein Video
teilweise geladen werden kann, ruft yt-dlp `FFmpegFD.available()` ohne Zugriff
auf die eigenen Einstellungen auf und sucht nur im `PATH` (im yt-dlp-Quelltext
steht dort ein `Fixme`). Das Ergebnis landet in einem **klassenweiten**
Zwischenspeicher — lief die Suche einmal erfolglos, bleibt „nicht vorhanden"
hängen. Lösung in `download.py::_announce_ffmpeg_location()`: die dafür
vorgesehene `FFmpegPostProcessor._ffmpeg_location` ContextVar setzen (genau das
tut yt-dlp in seinem eigenen Kommandozeilenprogramm, siehe deren Issue #2191).
Die ContextVar gilt **pro Thread**, deshalb wird sie bei jedem Download neu
gesetzt.

**Dateinamen müssen Modus, Qualität und Zeitbereich enthalten.** Sonst bekommen
„720p komplett" und „480p ohne Ton" denselben Namen, und yt-dlp verwendet
stillschweigend die vorhandene Datei wieder, statt neu zu laden. Das sah im Test
wie ein falscher Ausschnitt aus. Siehe `download.py::_output_template()`.

**VP9 und AV1 kann Resolve nicht öffnen.** YouTube liefert ab 1440p nur diese.
Der Formatausdruck bevorzugt deshalb `avc1`; reicht das nicht, wandelt
`ensure_resolve_compatible()` nach H.264 um. Der Haken in der Oberfläche steuert
das.

**Streamen bricht gelegentlich ab.** Beim Schneiden lädt ffmpeg direkt vom
Server; fällt die Verbindung kurz weg, stirbt es mit einem Absturzcode. yt-dlps
eigenes `retries` deckt das nicht ab, darum `_run_with_retries()` mit
Unterscheidung zwischen vorübergehenden Störungen und endgültigen Absagen.

### Qt / PySide6

**Ein `QPixmap` (oder `QImage`) vor dem Start der Anwendung erzeugen lässt das
Programm abstürzen.** Das gilt auch für Modulebene — ein `_LEER = QPixmap()`
oben in einer Datei bringt schon den Import zum Absturz. Stattdessen
`label.clear()` verwenden.

**Stylesheet-Schriftgrößen überschreiben `setFont()`.** Qt-Stylesheets kennen
weder `letter-spacing` noch `text-transform`. Deshalb: Schriften ausschließlich
über `typography.py` und `app.setFont()`, das Stylesheet regelt nur Farbe,
Rahmen und Abstand. Wer `font-size` ins Stylesheet schreibt, hebelt die
Laufweite aus — die Überschrift war dadurch anfangs winzig.

**`QLabel` erbt den Fensterhintergrund** und zeichnet ihn als sichtbaren Balken
auf weiße Karten. Darum `QLabel { background: transparent; }` als Grundregel,
Ausnahmen nur über ID-Wähler.

**Eigene Regeln für `QComboBox::down-arrow` zerstören die Textdarstellung** — die
Auswahlfelder waren komplett leer. Nicht wieder einbauen.

**`QVideoWidget` erscheint bei `widget.grab()` als weiße Lücke**, weil die
Grafikkarte es getrennt zeichnet. Für Bildschirmfotos ein Einzelbild über
`QVideoSink` holen und einsetzen (siehe `tools/`-Vorgehen im Verlauf).

**`QBuffer(QByteArray())` stürzt ab.** Das temporäre `QByteArray` wird von
Python eingesammelt, während der Puffer auf C++-Seite noch darauf zeigt. Immer
in einer eigenen Variablen halten.

**`Mode` erbt von `str`** — Qt speichert im ComboBox-Datenfeld daher nur den
reinen Text. Immer `mode.value` ablegen und mit `Mode(wert)` zurückwandeln.

**Geprüft, kein Problem:** Die Kürzel `I` und `O` stören das Tippen im Link-Feld
nicht — Qt gibt dem Eingabefeld Vorrang. Abgesichert durch
`tests/test_shortcuts.py`.

### Bildformat der Vorschau

Die Bildfläche sitzt in `preview_player.py::_AspectStage`. Sie berechnet aus
ihrem tatsächlich verfügbaren Platz ein zentriertes Rechteck im Bildformat
und setzt **Breite und Höhe** ausdrücklich. Nur eine maximale Breite plus
seitliche Dehnungen reicht nicht: Das ergab bei TikTok eine 87 Pixel breite
Fläche mit riesigen schwarzen Balken. Bei derselben Fenstergröße passt jetzt
ein rund 422 × 750 Pixel großes Bild hinein.

Das Videowidget liegt bewusst außerhalb eines größenbestimmenden Layouts.
Sonst kann seine native Auflösung (1080 × 1920) zur Mindestgröße werden und
die Bedienelemente aus dem Fenster schieben. `videoSink().videoSizeChanged`
korrigiert das anfängliche Bildformat anhand der tatsächlich dekodierten
Vorschau. Lade- und Fehlermeldungen bekommen weiterhin die ganze Fläche.

`test_portrait.py` prüft die **echte Geometrie**, nicht nur eine Breitenbegrenzung:
Hochformat, Querformat und Quadrat bei vier Fenstergrößen, Dekodierung mit
abweichenden Metadaten und lesbare Ladezustände. Das ganze Bild bleibt sichtbar.

Die Vorschau hat **bewusst keine Höhenbegrenzung**. Sie ist das, worauf man beim
Suchen des Ausschnitts schaut, und bekommt allen Platz des Fensters. Wer Höhe
braucht, muss sie den Bedienelementen abnehmen, nicht der Vorschau.

### Vorschau, die sich nicht streamen lässt

TikTok und andere geben ihre Adressen nur mit besonderen Kopfdaten heraus, die
`QMediaPlayer` nicht mitschicken kann. Bei einem Fehler meldet der Player
`streamFailed`; das Hauptfenster lädt daraufhin über
`download_preview()` eine kleine Datei und spielt diese ab.
`_preview_attempted_download` verhindert Endlosschleifen.

**YouTube liefert keine fertigen Dateien mit Bild und Ton mehr.** Gemessen an drei
Videos, mit alter wie neuer yt-dlp-Fassung: nur getrennte Spuren. Beides ging damit
verloren — `probe._pick_preview_url()` findet keinen Stream (er verlangt eine
fertige Datei), und der frühere Formatausdruck der Ausweichdatei scheiterte mit
„Requested format is not available“. Die Oberfläche zeigte dann „Vorschau nicht
möglich“. Merken: bei yt-dlp heißt `best` ausdrücklich *eine Datei mit Bild und Ton*,
nicht „das beste Format“.

`download.PREVIEW_FORMAT` hat deshalb drei Stufen: fertige Datei bis 540p (TikTok &
Co.), danach getrennte Spuren bis 480p, die ffmpeg zusammensetzt (YouTube), zuletzt
irgendeine fertige Datei. Gemessen: 10:35 min Big Buck Bunny → 37 MB, rund 4 s.
Bei sehr langen Videos wächst die Datei entsprechend (~3,5 MB je Minute); das ist
der Preis dafür, dass YouTube nicht mehr streamen lässt.

Abgesichert zweifach: `test_preview_format.py` (ohne Netz, yt-dlps eigene Auswahl
über nachgebaute Formatlisten) und `test_preview_fallback.py` / `test_preview.py` (mit
Netz; Datei muss Bild **und** Ton haben und im Player laufen).

### PowerShell 5.1

**`Out-File -Encoding utf8` schreibt eine Byte-Markierung (BOM)**, an der
Pythons JSON-Leser scheitert. `install.json` wird deshalb über
`[System.IO.File]::WriteAllText(..., New-Object System.Text.UTF8Encoding($false))`
geschrieben. Zusätzlich lesen beide Seiten mit `utf-8-sig`, das mit und ohne
Markierung zurechtkommt.

**Umgekehrt gilt für `.ps1`-Dateien selbst:** PowerShell 5.1 liest sie ohne
Markierung als ANSI. Deshalb in Scripten **keine Umlaute** verwenden.

**Kein `&&`, kein `?:`** — PowerShell 5.1 kennt beides nicht.

### Mehrere Ausschnitte

Die gemerkten Stellen stehen in `main_window._segments` als Liste von
`(Anfang, Ende)`. Daraus baut `_build_requests()` **einen eigenen
`DownloadRequest` je Stelle**, und `DownloadWorker` lädt bis zu
`MAX_PARALLEL` (3) davon **gleichzeitig**.

**Warum je Stelle ein eigener Auftrag und nicht alles in einem yt-dlp-Aufruf?**
yt-dlp kann mehrere Bereiche auf einmal, aber dann müssten Namensmuster,
H.264-Prüfung und Fortschrittsmeldung für mehrere Zieldateien gleichzeitig
gelten — und ein Fehlversuch würde alle betreffen. So durchläuft jeder
Ausschnitt dieselbe erprobte Strecke, samt `_run_with_retries()`.

**Warum gleichzeitig — und warum das der eigentliche Hebel ist.** Gemessen an
einem 15-Sekunden-Ausschnitt in 1080p:

| | |
|---|---|
| Durchsatz, egal ob 1 oder 3 Downloads | ~0,5 MB/s je Verbindung |
| Feste Grundlast je Ausschnitt | ~9 s (aus 15 s/16,7 s und 60 s/39,5 s) |
| 2 Ausschnitte nacheinander | 27,9 s |
| 2 Ausschnitte gleichzeitig | **16,9 s** |
| 3 Ausschnitte gleichzeitig | **17,0 s** statt ~42 s |

Die Bremse sitzt also **in der einzelnen Verbindung, nicht in der Leitung**.
Darum bringt Parallelität fast das volle Vielfache. Über drei hinaus sank der
Durchsatz je Verbindung sichtbar — daher der Deckel.

**Nicht der Hebel, obwohl es naheliegt:** `force_keyframes_at_cuts` bedeutet
volle Neucodierung (ohne die Option setzt yt-dlp `-c copy`, siehe
`downloader/external.py`). Gemessen kostet das aber nur **0,34 s** von 15,8 s —
die Daten kommen langsamer herein, als der Encoder sie verarbeitet. Ein
schnelleres x264-Preset brachte gar nichts. Die genaue Schnittstelle ist also
praktisch gratis; bitte nicht wieder gegen `-c copy` eintauschen.

Weil sie gleichzeitig laufen, zählt `Progress.part` **fertige** Ausschnitte,
nicht „der wievielte läuft". `DownloadWorker._make_reporter()` fasst die
Meldungen zusammen — ohne das spränge der Balken zwischen drei Downloads hin
und her. Bei einem einzelnen Auftrag wird unverändert durchgereicht.

**Offener Mangel:** Abbrechen greift während des Ladens nicht. `FFmpegFD` meldet
keinen Fortschritt, solange ffmpeg läuft — also wird `should_cancel()` nie
gefragt. Gemessen: Abbruch nach 3 s, Wirkung nach 50 s, und alle Dateien waren
trotzdem vollständig geladen. Das galt vorher genauso, fällt bei mehreren
Ausschnitten nur eher auf. Eine Behebung müsste an den ffmpeg-Prozess herankommen
(`yt_dlp.downloader.external.Popen` ersetzen und die laufenden Prozesse
mitschreiben) — ein Griff in fremde Interna, daher bewusst noch nicht getan.

**Der Zeitbereich im Dateinamen ist hier lebenswichtig** (siehe oben zu
`_output_template()`): Beide Aufträge zeigen auf dieselbe Adresse. Fehlte der
Bereich im Namen, bekämen sie denselben Dateinamen und yt-dlp würde die erste
Datei stillschweigend wiederverwenden — man hätte zweimal denselben Ausschnitt
und würde es nicht merken. Abgesichert durch `tests/test_segments_netz.py`.

`DownloadWorker` meldet jede fertige Datei sofort über `fileReady`, nicht erst
am Ende. So wandert bei drei Ausschnitten jeder einzelne in den Media Pool,
sobald er da ist. `succeeded` kommt zusätzlich für den letzten und schaltet den
Knopf auf „Fertig"; `_on_download_succeeded` prüft deshalb auf Doppelung.

**Ist die Liste gefüllt, gilt ausschließlich sie** — der Balken ist dann nur
noch das Werkzeug, mit dem sie entstanden ist. Darum sagt die Auswahl-Anzeige in
diesem Fall „Auswahl" statt „ganzes Video": Sonst behauptete sie das Gegenteil
dessen, was der Knopf daneben ankündigt.

### Vorschau folgt dem Griff

`TrimBar` meldet beim Ziehen laufend `scrubbed`, beim Loslassen einmalig
`scrubFinished`. Beides landet in `_seek_preview()`.

Zwei Signale und nicht eines, weil während des Ziehens **gedrosselt** wird
(50 ms über `QElapsedTimer`): Ohne Drosselung bekommt `QMediaPlayer` mehr
Sprungbefehle, als er verarbeiten kann. Die Drosselung verwirft aber unter
Umständen die letzte Bewegung — darum die genaue Endstelle beim Loslassen.

`_seek_preview()` setzt die Abspielmarke selbst und wartet nicht auf den Player.
Gibt es keine abspielbare Vorschau, meldet der Player gar nichts zurück; die
Marke soll trotzdem stimmen.

### Vorschaubilder der Bibliothek

`LibraryThumbWorker` ist **ein einziger, dauerhaft laufender Thread mit
Warteschlange**, kein Thread pro Filterwechsel. Bei jedem Tastendruck im
Suchfeld einen neuen zu starten und den alten abzuräumen wäre ein ständiges
Kommen und Gehen — stattdessen wird über `submit()` nur die Liste ausgetauscht.

Er muss ausdrücklich angehalten werden: `library_page.shutdown()` im
`closeEvent`. Sonst wartet er in `QWaitCondition.wait()` und das Programm
beendet sich nicht.

`thumbs.ensure_thumbnail()` merkt sich auch **Fehlschläge** als leere
`.none`-Marke. Ohne die würde bei jedem Blick in die Bibliothek erneut ffmpeg
auf eine Datei losgelassen, die sowieso kein Bild hergibt (Tonspur ohne
Titelbild, kaputte Datei).

Der Schlüssel besteht aus Pfad, Zeitstempel **und** Größe. Ein bloßer Pfad
würde nach dem Überschreiben einer Datei das alte Bild zeigen.

### Verpacken und Weitergeben

Es gibt **zwei Bauarten**, und beide müssen weiterhin laufen:

| | Wie es startet | Für wen |
|---|---|---|
| Aus dem Quelltext | `.venv\Scripts\pythonw.exe launch.pyw` | Entwicklung — Änderungen wirken sofort |
| Installiert | `FevDownload.exe` (bringt Python mit) | alle anderen |

Drei Stellen wissen davon:

1. `paths.py` — `PROJECT_ROOT` zeigt bei `sys.frozen` auf den Ordner der `.exe`,
   sonst wie bisher auf die Projektwurzel. **`bin/` und `assets/` liegen neben
   der `.exe`**, nicht im Paket: 196 MB ffmpeg durch PyInstaller zu schleusen
   wäre nur Umweg und Bauzeit.
2. `resolve/FevDownloader.py::find_installation()` — sucht zuerst
   `FevDownload.exe`, dann das venv. Gibt **`(Ordner, Startbefehl als Liste)`**
   zurück, nicht mehr drei Werte.
3. `installer/FevDownload.iss` — schreibt `install.json` und kopiert das
   Resolve-Script selbst. `install_plugin.ps1` wird beim Empfänger also gar
   nicht gebraucht.

**PyInstaller: ohne `collect_submodules("yt_dlp.extractor")` kennt das fertige
Programm keine einzige Plattform.** yt-dlp sucht seine Extraktoren zur Laufzeit
über `importlib` zusammen; im Quelltext steht kein `import`, also sieht
PyInstaller nichts davon. Kontrolle nach dem Bau: In `build\fevdl\PYZ-00.toc`
müssen ~970 Einträge `yt_dlp.extractor.` stehen.

**Die Ausschlussliste in `fevdl.spec` ist der ganze Größenunterschied.** PySide6
bringt 634 MB mit, gebraucht werden nur QtCore, QtGui, QtWidgets, QtMultimedia
und QtMultimediaWidgets. Mit den Ausschlüssen: 139 MB gepackt, 97 MB als
Installer. Wer dort etwas herausnimmt, sollte vorher messen. **QtWebEngine ist
mit Abstand der dickste Posten (~150 MB).**

Nicht ausschließen: die Erweiterungen unter `_internal\PySide6\plugins\` —
`multimedia` (Vorschau) und `tls` (HTTPS-Streaming) müssen mit, sonst startet
das Fenster zwar, aber die Vorschau bleibt schwarz.

**Inno Setup: `Compression=lzma2/ultra64` bricht mit „Out of memory" ab.** Das
sind 256 MB Wörterbuch, `ISCC.exe` ist aber ein 32-Bit-Programm. Der Abbruch
kommt erst kurz vor Schluss, nach mehreren Minuten Verdichten. `lzma2/max`
läuft durch und liefert praktisch dasselbe Ergebnis.

**Im `.iss` darf keine Zeile mit `#` beginnen** — auch nicht eingerückt und auch
nicht mitten in einem Pascal-Ausdruck. Der Präprozessor liest sie als Direktive
und meldet „Unknown preprocessor directive". Betraf `#13#10` am Zeilenanfang;
Zeilenumbrüche gehören ans Zeilen**ende**.

**`install.json` aus Inno heraus: Rückstriche verdoppeln.** JSON kennt `\` als
Fluchtzeichen, `C:\Users` würde Python als Steuerzeichen lesen.
`StringChangeEx(Pfad, '\', '\\', True)` erledigt das. `SaveStringToFile`
schreibt ohne Byte-Markierung, das passt zum bekannten BOM-Problem.

**`build_installer.ps1` räumt `dist\FevDownload` vorher leer.** Sonst bleiben
Dateien aus einem früheren Lauf liegen — etwa ein von Hand hineinkopiertes
`bin\` — und der Installer packt ffmpeg doppelt ein.

**Prüfen, ob der gepackte Zustand wirklich lädt:** Dass das Fenster aufgeht,
beweist nichts über yt-dlp und ffmpeg. Dafür gibt es jetzt
**`FevDownload.exe --selbsttest`** (`src/fevdl/selftest.py`): ohne Fenster, mit
echter Analyse, einem 3-Sekunden-Ausschnitt und der Vorschaudatei. Das Ergebnis
steht in `%LOCALAPPDATA%\FevDownloader\selbsttest.txt` (die .exe hat keine Konsole),
Exit-Code 0 = in Ordnung. **Vor jedem Release gegen die frisch gebaute `.exe`
laufen lassen** — und bei einem Problem eines Freundes bitten, genau diese Datei zu
schicken. Aus dem Quelltext: `python -m fevdl --selbsttest` (`test_selbsttest.py`).

### yt-dlp nachladen

`paths.activate_ytdlp_update()` stellt einen beschreibbaren Ordner
(`%LOCALAPPDATA%\FevDownloader\ytdlp`) im Suchpfad **vor** das mitgelieferte
Paket. `core/update.py` holt das Rad von PyPI und entpackt es dorthin — ohne
pip, das es im gepackten Zustand gar nicht gibt.

**Der Aufruf steht in `src/fevdl/__init__.py` und darf nirgendwo anders hin.**
`probe.py` und `download.py` binden `yt_dlp` auf Modulebene ein; sobald
irgendein Teil von `fevdl` geladen ist, steht der Eintrag in `sys.modules` und
der Suchpfad wird nicht mehr befragt. `__init__.py` läuft vor jedem Untermodul,
egal über welchen Einstieg.

Wirksam wird eine neue Fassung deshalb auch erst **beim nächsten Start** — das
sagt die Meldung im Dialog ausdrücklich.

**Die nachgeladene Fassung gilt nur, wenn sie neuer ist als die mitgelieferte.**
Der Nachlade-Ordner überlebt den Installer. Früher stand er immer vorn: Wer im
September ein Update holte und im Oktober einen neueren Installer einspielte, hatte
weiter die alte Fassung — stillschweigend. Gemessen: 2026.08.19 im Ordner verdeckte
das mitgelieferte 2026.10.26.

`paths.bundled_ytdlp_version()` erfragt die mitgelieferte Fassung über die
Paket-Metadaten (`importlib.metadata`), **ohne `yt_dlp` zu importieren** — danach
ließe sich nichts mehr umentscheiden. Im gepackten Programm gibt es diese Metadaten
nur, weil `fevdl.spec` sie per `copy_metadata("yt-dlp")` mitnimmt. Fehlen sie, gilt
der alte Weg (nachgeladen hat Vorrang) — lieber das, als ein Update zu verlieren.
Getestet in `test_ytdlp_vorrang.py`.

### Aktualisierung der App (GitHub)

Gebaut, weil die App an wenige Freunde geht, die kein Python haben und nicht von
Hand nachladen sollen. Repo: `fevzyy72/fev-download`, **öffentlich** — ein
privates Repo ließe sich ohne Anmeldung nicht abfragen, und einen Zugangsschlüssel
darf die App nicht enthalten.

**Ablauf:** `release.ps1` lädt `FevDownloadSetup.exe` als Release hoch.
`core/appupdate.py` fragt `…/releases/latest` ab, vergleicht mit
`fevdl.__version__` (Zahl für Zahl, `paths.version_key`), lädt den Installer in
`%TEMP%\FevDownload\update`, prüft Größe und SHA-256 und startet ihn mit
`/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS`, abgekoppelt
(`DETACHED_PROCESS`). Danach beendet sich die App.

**Der Installer startet die App wieder:** `FevDownload.iss` hat dafür eine zweite
`[Run]`-Zeile mit `skipifnotsilent` (die erste, mit dem Haken auf der
Abschlussseite, hat `skipifsilent`). Ohne sie verschwände die App nach dem Update
einfach. `RestartApplications=no`, damit nichts doppelt startet.

**Schließen erzwingen — sonst passiert nichts.** Der Installer prüft schon nach
~0,4 s, ob die App noch läuft. Der Neustart-Manager erreicht sie nicht (im Test
„Some applications could not be shut down. Defaulting to Abort“), und im stillen
Modus bricht Setup dann **kommentarlos ab**: kein Update, die App läuft einfach weiter.
Deshalb `/FORCECLOSEAPPLICATIONS` in `launch_installer()` **und** `CloseApplications=force`
im `.iss`. Gemessen: mit Flag 14 s bis „installiert“, alte App beendet, neue gestartet.
Beim Testen **nie** `Start-Process -Wait` auf den Installer anwenden: PowerShell 5.1 wartet
dann auch auf die vom Installer neu gestartete App und hängt ewig.

**Wo das nicht hinfliegen darf:**
- Die Prüfung beim Start steht in `__main__.py` (`window.start_background_update_check()`),
  **nicht** im `MainWindow`-Konstruktor — sonst gingen alle Oberflächen-Tests ins Netz.
- Sie läuft nur im installierten Programm (`paths.IS_FROZEN`). Aus dem Quelltext
  wäre es bei jedem Commit Rauschen, und ein Installer würde dort eine zweite Kopie
  anlegen. `FEVDL_UPDATE_CHECK=1` erzwingt sie, `FEVDL_NO_UPDATE_CHECK=1` unterdrückt sie.
  Aus dem Quelltext öffnet „Jetzt aktualisieren“ nur die Release-Seite.
- Ein normaler `threading.Thread(daemon=True)` statt `QThread`: Hängt das Netz, muss
  das Schließen des Fensters nicht warten. `UpdateNotifier` trägt die Signale.
  Der Download des Installers dagegen ist ein `QThread` (`AppUpdateWorker`), weil
  der Nutzer dabei vor einem Fortschrittsdialog sitzt.

**Sicherheit:** Es wird eine heruntergeladene Datei ausgeführt. Deshalb wird nur von
`https://github.com/fevzyy72/fev-download/releases/download/` geladen (Adresse aus
der API wird gegen dieses Präfix geprüft), und eine zu kurze oder beschädigte Datei
wird nie gestartet. Das schützt vor Pannen, nicht vor einem gekaperten
GitHub-Konto — wer dort Zugriff hat, kann Code ausliefern. Das Konto also mit
Zwei-Faktor-Anmeldung schützen.

**Jede Fassung wird nur einmal angeboten** (`offered_version` in den Einstellungen);
der Menüpunkt *Hilfe → Nach Aktualisierung suchen* bleibt, prüft yt-dlp **und** App
und heißt absichtlich weiter so — `errors.py` verweist Nutzer auf diesen Text.

**yt-dlp still beim Start:** `update.auto_update_ytdlp()`, höchstens einmal in 20 Stunden
(`update_check.json`). Schlägt es fehl (kein Netz), wird nichts vermerkt — der nächste
Start versucht es erneut. Stabile Fassungen erscheinen etwa monatlich (gemessen: 14 in
12 Monaten, längste Pause 84 Tage), die Suche ist also billig. Nachtbauten (`.dev0`)
holt der Updater absichtlich nicht.

**Noch nicht gegen das echte GitHub erprobt:** der Ablauf „zweites Release →
Update“ lässt sich erst prüfen, wenn es zwei Fassungen gibt. Getestet sind Antwort,
Download, Prüfsumme, Installer-Start und Fenster einzeln (`test_appupdate.py`,
`test_update_gui.py`) sowie der stille Installer über eine laufende Fassung.

### Einstellungen

Der Zielordner wird nur dann als eigene Entscheidung gewertet, wenn er wirklich
selbst gesetzt wurde (`output_user_set`). Vorher wurde er bei jedem Schließen
gespeichert — dadurch galt schon die Vorgabe des allerersten Starts als Wahl und
Resolves Vorschlag kam nie wieder zum Zug. Abgesichert in
`tests/test_job_gui.py`.

---

## 6. Tests

`tests/run_tests.ps1` — 17 Testdateien ohne Internet, sechs weitere mit `-MitNetz`.

**Ein Test muss scheitern können.** `test_preview.py` meldete früher „in Ordnung“,
wenn keine Vorschau vorhanden war, und beendete sich selbst bei „spielt nicht“ mit
Erfolgscode — so blieb der YouTube-Fehler unbemerkt. Bei neuen Tests mit Netz:
fehlt das Erwartete, muss der Exit-Code ungleich 0 sein.

**Regeln für neue Tests mit Oberfläche:**

1. `window._start_preview_fallback = lambda: None` setzen, sonst lösen erfundene
   Links echte Downloads aus.
2. Am Ende `window.close()` und `app.processEvents()`.
3. `QSettings("fezco", "Fev Download").clear()` am Anfang, wenn der Test von
   Vorgabewerten ausgeht.

Ohne 1 und 2 laufen Hintergrund-Threads beim Beenden weiter, Python räumt die
Qt-Objekte in falscher Reihenfolge ab, und der Test **stürzt nach dem bestandenen
Durchlauf ab** — er meldet „OK" und liefert trotzdem einen Fehlercode.

Ein Test prüft ausdrücklich, dass die echte App sich sauber beendet
(`test_clean_exit.py`). Wenn Tests abstürzen, dieser aber nicht, liegt es an der
Testumgebung und nicht an der App.

**Wenn die Resolve-Seite klemmt:** `resolve/_FevTest.py` in Resolves Scripts-
Ordner kopieren und über `Workspace → Scripts → Utility → _FevTest` starten. Es
meldet Python-Version, Resolve-Version, offenes Projekt und ob der Media Pool
erreichbar ist — und schreibt alles nach `Desktop\fev_resolve_test.txt`. Damit
lässt sich sofort trennen, ob das Problem bei Resolve oder bei der App liegt.
Das eigentliche Protokoll steht in `%LOCALAPPDATA%\FevDownloader\launcher.log`.

---

## 7. Getroffene Entscheidungen

| Thema | Entscheidung | Grund |
|---|---|---|
| Oberfläche | PySide6, eigener Prozess | Resolves UIManager fehlt in der kostenlosen Version seit 19.1 |
| Verständigung | JSON-Dateien | Einziger Weg bei gesperrtem externem Scripting |
| Schnitt | `download_ranges` + `force_keyframes_at_cuts` | Lädt nur den gewählten Bereich statt alles |
| ffmpeg | lokal in `bin/` | Keine Systemänderung, Projekt bleibt in sich geschlossen |
| Import | nur Media Pool | Kein ungefragter Eingriff in die Timeline |
| Gestaltung | warmes Monochrom, flach | Nach dem Skill `minimalist-ui`, auf Qt übertragen |
| Wellenform | auf Knopfdruck | Gemessen 0,9 s für 10 Minuten — automatisch wäre vertretbar |
| Mehrere Ausschnitte | ein Auftrag je Stelle, bis zu 3 gleichzeitig | Jeder durchläuft dieselbe erprobte Strecke; die Drosselung sitzt je Verbindung, also bringt Parallelität fast das volle Vielfache |
| Vorschaubilder | automatisch, im Zwischenspeicher | Einmal erzeugt, danach sofort da — ein Knopf dafür wäre nur eine Hürde |
| Bildquelle | ffmpeg-Filter `thumbnail` | Ein fester Zeitpunkt trifft regelmäßig Schwarzbild oder Vorspann |
| Weitergabe | PyInstaller + Inno Setup, eine `.exe` | Ein venv lässt sich nicht verschieben, und niemand installiert erst Python |
| Installationsort | `%LOCALAPPDATA%\Programs`, ohne Admin | Kein UAC-Fenster; Resolves Scripts-Ordner liegt ohnehin beim Benutzer |
| ffmpeg im Installer | mitgeliefert statt nachgeladen | Funktioniert sicher, auch wenn gyan.dev einmal nicht erreichbar ist |
| yt-dlp aktuell halten | Nachladen von PyPI in einen eigenen Ordner, still beim Start (1×/Tag) | Sonst bräuchte jede YouTube-Änderung einen neuen Installer für alle; die Suche ist billig |
| App aktuell halten | GitHub-Releases, Angebot beim Start, Installer läuft still drüber | Zielgruppe sind wenige Freunde ohne Python; öffentliches Repo, weil die App sonst nichts abfragen kann |

---

## 8. Was noch offen ist

- **Redesign „Sammelmappe“** umgesetzt, wartet auf Freigabe/Commit – Stand in Abschnitt 0.
- Der Ablauf „zweites Release → Aktualisierung in der App“ wurde noch nicht mit zwei
  echten GitHub-Fassungen durchgespielt (Einzelteile sind getestet).
- Gepackte App meldet 33 statt 47 Browser-Ziele für TikTok (Quelltext: 47), ohne erkannten
  Grund; die TikTok-Analyse im Selbsttest klappt trotzdem.
- `tests/test_launcher.py` schreibt bei jedem Lauf in das echte `launcher.log`.
- Die Wellenform könnte automatisch nach der Analyse laden (0,9 s gemessen).
  Der Nutzer hat sich zunächst für den Knopf entschieden.
- Mehrere **Videos** gleichzeitig sind nicht vorgesehen; es läuft immer eines.
  Mehrere Ausschnitte desselben Videos laufen dagegen parallel (siehe oben).
- Abbrechen wirkt erst, wenn ffmpeg den laufenden Ausschnitt fertig hat — der
  Mangel ist oben unter „Mehrere Ausschnitte" beschrieben.
- Ein einzelner langer Ausschnitt lässt sich nicht beschleunigen. Man könnte ihn
  in Teilstücke zerlegen, parallel holen und wieder zusammensetzen — das würde
  bei der gemessenen Drosselung je Verbindung wirken, ist aber deutlich mehr
  Maschinerie (Nahtstellen, Zusammenfügen ohne Neucodierung).
- Die gemerkten Ausschnitte überleben das Schließen des Fensters nicht. Sie
  gehören zu einem Link, und der wird beim nächsten Start ohnehin neu analysiert.
- Vorschaubilder werden nur für die gerade angezeigten Dateien erzeugt, höchstens
  400 (`library_page.THUMB_LIMIT`). Der Zwischenspeicher unter
  `%LOCALAPPDATA%\FevDownloader\thumbs` wird nie aufgeräumt — bei sehr vielen
  Dateien wäre eine Altersgrenze sinnvoll.
- Nur Windows. Für macOS und Linux müssten die `.ps1`-Scripte, die Pfade in
  `paths.py` und `CREATE_NO_WINDOW` angepasst werden.
- **Der Installer ist nicht signiert.** Windows zeigt beim Ausführen die
  SmartScreen-Warnung („Der Computer wurde durch Windows geschützt" → *Weitere
  Informationen* → *Trotzdem ausführen*), und manche Virenscanner melden bei
  PyInstaller-Paketen mit yt-dlp Fehlalarm. Dagegen hilft nur ein
  Code-Signing-Zertifikat (200–400 € im Jahr), und selbst dann baut sich der
  Ruf erst über Downloads auf — es sei denn, es ist ein EV-Zertifikat.
- Der Installer ersetzt eine vorhandene Fassung, ohne zu fragen. Eine
  Rückfrage bei gleicher oder neuerer Fassung wäre freundlicher.
- Playlists: Es wird immer nur der erste Eintrag verarbeitet
  (`playlist_items: "1"`).

---

## 9. Rechtlicher Rahmen

Das Werkzeug lädt Videos herunter. Es ist für eigene Inhalte gedacht oder für
Material, dessen Lizenz das erlaubt. Diesen Hinweis in `README.md` und im
Über-Fenster bitte stehen lassen.
