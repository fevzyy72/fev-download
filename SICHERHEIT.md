# Sicherheitspruefung und Bau-Freigabe

Stand: 02.11.2026, Arbeitsbaum auf `c332e31`, GUI-Umbau abgeschlossen; lokaler Testbau siehe unten.
Geprueft: Regeln in CLAUDE.md 0/2/3/5/6, Quellcode, Installer/Skripte, lokale Rechte, Pakete und erreichbarer Git-Verlauf.
**0 hohe, 6 mittlere, 7 niedrige Funde/Restrisiken; 8 behoben, 5 offen.** Keine nachgewiesene Fern-Codeausfuehrung durch einen gewoehnlichen Video-Link. Die neue Baukette ist lokal erfolgreich durchgelaufen; vor Weitergabe sind vor allem Quellen/Lizenzen zu klaeren. Die urspruenglichen Pruefergebnisse unten beschreiben den Stand vor diesem Bau; der aktuelle Bau-Nachweis steht im letzten Abschnitt.

## Funde

Zeilen beziehen sich auf diesen Arbeitsstand; GUI-Zeilen koennen sich durch den anderen Agenten verschieben. Schwere bewertet die Praxis fuer drei private Nutzer, nicht die maximal denkbare Wirkung.

| Nr. | Schwere | Beleg | Befund, reale Auswirkung und Massnahme | Behoben |
|---|---|---|---|---|
| 1 | mittel | `core/appupdate.py:70`, `core/transport.py:26` (unter `src/fevdl/`) | Die Repository-Praefixpruefung galt nur fuer die erste URL; urllib folgte Redirects auch zu fremden Hosts/HTTP. Jetzt wird **jeder** Folgerequest vorher auf HTTPS, Port 443 und genaue GitHub-/Asset-Hosts begrenzt. PyPI und ffmpeg-Bootstrap verwenden dieselbe Grenze. Ohne kontrollierte Serverantwort war dies kein beliebiger Internetangriff. | Ja |
| 2 | mittel | `src/fevdl/core/update.py:55`, `:165` | Das dauerhaft ausgefuehrte Wheel hatte keine Integritaetspruefung. Jetzt obligatorische SHA-256 aus PyPI-Metadaten, Hash vor Entpacken; fehlender/falscher Hash stoppt. Rueckgezogene und nicht stabile Fassungen werden abgelehnt. | Ja |
| 3 | mittel | `src/fevdl/paths.py:134`, `resolve/FevDownloader.py:110`, `:172`, `src/fevdl/core/appupdate.py:183`, `:243` | Wer in `FevDownloader` schreiben darf, kann nachgeladenen Python-Code, den Programmzeiger in `install.json` oder Importpfade in `result.json` manipulieren. Die Sitzungs-ID ist keine Authentifizierung. Hier haben IPC-Ordner und Temp **zusaetzliche Sandbox-Prinzipale mit Modify**, der installierte Programmordner dagegen nur Nutzer/Admins/SYSTEM. Zufaellige Update-Unterordner verhindern gegenseitiges Ueberschreiben durch App-Laeufe, beseitigen aber kein TOCTOU zwischen Hashpruefung und Start gegen fremde Schreibberechtigte. Normale fremde Benutzer haben bei passenden Profil-ACLs keinen Zugriff; Schadsoftware unter demselben Konto koennte ohnehin die App ersetzen. Rechte gezielt vom Besitzer pruefen/bereinigen, keine pauschale ACL-Aenderung durch diesen Review. | Nein |
| 4 | mittel | `src/fevdl/core/appupdate.py:110`, `:163`, `src/fevdl/core/update.py:55` | GitHub liefert Installer **und** Digest; PyPI liefert Wheel **und** Digest. Das erkennt Uebertragungsfehler bzw. Abweichungen, aber keinen uebernommenen Herausgeberzugang. App-Digest bleibt aus Kompatibilitaetsgruenden optional; ohne Digest/Groessenangabe bleibt nur Transport und Nichtleere. Keine Authenticode-/unabhaengige Signaturpruefung. Fuer drei Freunde zuerst GitHub-2FA/Passkey und gesicherte Recovery; Hashpflicht empfehlen (klein), Signatur mit festem Vertrauensanker als eigene Aenderung (grob 1-3 Tage plus Zertifikat/Schluesselpflege). | Nein |
| 5 | mittel | `installer/LIZENZEN.txt`, `installer/ffmpeg-lock.json`, `installer/licenses/`, `tools/ffmpeg_sources.py` | **Teilweise umgesetzt; Weitergabe weiterhin nicht lizenzseitig freigegeben.** Beide lokalen GPLv3-EXEs sind jetzt gegen das historische gyan-9.0-ZIP bytegenau verifiziert. FFmpeg-9.0-Quelle samt gepruefter Signatur, gyan-Originalhinweisen und vier belegten Bibliotheksquellen begleiten den Installer. Feste SHA-256/Groessen binden Bootstrap und Bau an diese Dateien; fehlende/unpassende Dateien stoppen den Bau. Bibliotheksinventar mit 55 Bibliotheks-/API-Zeilen, belegte Originaltexte von Qt/curl und Quellenhinweis im Ueber-Dialog ergaenzt. **Offen:** weitere exakte Bibliotheksquellen, transitive Teile, Hersteller-Patches/Bauskripte; Qt-Wheel-Abgleich einschliesslich GPLv3/kommerziellem Virtual-Keyboard-Plugin und Multimedia-FFmpeg; curl-Wheel-/BoringSSL-Baunachweis. Kein pauschales "auf Wunsch" und kein als vollstaendig behauptetes GPL-Angebot. Details und konkrete naechste Schritte unten im Lizenz-Nachtrag. | Teilweise / offen |
| 6 | mittel | `build_installer.ps1:130`, Abschnitt Selbsttest; `release.ps1:110`; `installer/FevDownload.iss:17` | Der einzelne Baubefehl pruefte vorher weder Tests noch gepackte Funktion. Jetzt Offline-Tests -> frisches PyInstaller-Verzeichnis samt bin/assets/Lizenzen -> **EXE --selbsttest mit Netz** -> Inno. Isoliertes LOCALAPPDATA verhindert, dass nachgeladenes yt-dlp einen Paketfehler verdeckt. Bei Fehler kein neuer Installer; alte Artefakte werden vor dem Packen entfernt. `bau.json` bindet Hash, Version, Commit, sauberen Arbeitsbaum und Selbsttest; Release prueft ihn auch bei `-OhneBau`, verlangt main und setzt das Tag-Ziel auf den geprueften Commit. Vollstaendiger Ablauf noch zu erproben. | Ja (Code) |
| 7 | niedrig | `src/fevdl/core/urls.py:6`, `core/probe.py:29`, `core/download.py:48`, `core/waveform.py:35` | Keine eigene HTTP-/HTTPS-Grenze im Motor; GUI-Einfuegen war nicht jeder Einstieg. Jetzt explizit vor yt-dlp/ffmpeg abgewiesen: lokale Pfade, file://, FTP und andere Schemata sowie kaputte Hosts/Ports. yt-dlp hatte file:// bereits standardmaessig deaktiviert: keine belegte vorherige lokale Dateiexfiltration. Keine Website-/LAN-Host-Erlaubnisliste; interne HTTP-Ziele bleiben als bewusste Downloader-Funktion moeglich. | Ja |
| 8 | niedrig | `setup.ps1`, `tools/ffmpeg_sources.py`, `installer/ffmpeg-lock.json` | Bootstrap uebernahm EXEs urspruenglich ohne Hash. Jetzt feste historische Version statt beweglichem release-Link, SHA-256/Groesse fuer EXEs, Binaerarchiv und Quellen, eigene Temp-Ordner, HTTPS-/Redirect-Grenzen und Erhalt der Originalhinweise. Die vorhandenen EXEs wurden in dieser Runde zusaetzlich gegen das per Hersteller-Digest verifizierte historische Archiv abgeglichen. FFmpeg-Quellarchiv einmal mit offizieller PGP-Signatur geprueft; kuenftige Einrichtung prueft dessen festen SHA-256. Andere EXEs werden abgewiesen und nicht still ersetzt; `-NurFfmpeg` laesst Python-Pakete unveraendert. Keine unabhaengige Signaturpruefung der gyan-EXEs. | Ja |
| 9 | niedrig | `src/fevdl/ipc.py:89`, `resolve/FevDownloader.py:205`, `installer/FevDownload.iss:150` | Unpassende JSON-Typen konnten Auftrag/Importschleife abbrechen; Inno schrieb Pfade nicht ausdruecklich als UTF-8. Jetzt Job-/Ergebnis-Schema, absolute Importpfade und NUL-Ausschluss; Inno schreibt UTF-8 ohne BOM und escaped Rueckstriche/Anfuehrungszeichen. Keine Shell-Command-Injection gefunden: Startbefehle bleiben Argumentlisten, auch bei Leerzeichen. Das authentifiziert weder Datei noch Pfad (siehe 3). | Ja |
| 10 | niedrig | `setup.ps1:91`, lokale Paket-Metadaten; `fevdl.spec` Ausschluss `setuptools` | setuptools vor dem Bau gezielt von 84.0.0 auf **84.2.1** aktualisiert; Mindestfassung 84.1.0 gegen GHSA-xmj3-9gf7-h52w damit erfuellt. Keine anderen Pakete pauschal aktualisiert. Im gebauten PYZ weiterhin kein setuptools enthalten. | Ja |
| 11 | niedrig | `src/fevdl/core/download.py:276`, `:232` | Titel auf 70 Zeichen begrenzt, Windows-Sanitizing aktiv; Traversal-Titel und reservierte Namen bestehen den Regressionstest. ID und gewaehlter Zielordner sind jedoch nicht insgesamt laengenbegrenzt: sehr lange Pfade koennen Downloads scheitern lassen. Zielordner ist eine Nutzervorgabe, keine Sandbox; relative/UNC-Ziele sind nicht allgemein verboten. Bei Bedarf Laengenpruefung mit guter Fehlermeldung, ca. 1-2 Stunden. | Nein |
| 12 | niedrig | `resolve/FevDownloader.py:241`, `:172`, `src/fevdl/selftest.py` Bericht | Launcher protokolliert Projekt-/Dateinamen und bei Fehlern volle Pfade; regulaere Videolinks/Tokens werden dort nicht protokolliert. Selbsttest kann Links, Pfade und rohe Fehler enthalten. Logs vor Weitergabe pruefen, keine Cookies/Token anhaengen. Eine sparsame Redaktion ist optional, kein belegter Zugangsdatenabfluss. | Nein |
| 13 | niedrig | `src/fevdl/gui/worker.py:51`, `tests/test_thumbnail_limit.py` | Im abgeschlossenen GUI-Umbau behoben: nur HTTP/HTTPS, hoechstens 10 MiB; der Worker liest maximal Grenze + 1 Byte und verwirft zu grosse Antworten. Alle drei Regressionstests fuer kleines Bild, Uebergroesse und fremde Schemata bestehen im aktuellen Offline-Lauf. Keine weitere GUI-Aenderung beim Bau. | Ja |

## Weitere Pruefergebnisse

- **ZIP:** `core/update.py:91` nimmt nur `yt_dlp/` mit. Pythons `ZipFile.extract` normalisierte bereits Traversal; ein tatsaechlicher Zip-Slip aus dem alten Code wurde nicht nachgewiesen. Zusaetzlich werden jetzt `..`, Backslashes, Laufwerke/NTFS-Datenstroeme, problematische Pfadenden und Symlink-Eintraege vor jedem Entpacken abgelehnt. Ungueltige Archive lassen das alte Paket unveraendert. Keine Signaturpruefung des installierten Verzeichnisses beim Start; lokale Schreibrechte bleiben entscheidend.
- **Versionen/TLS/Prozesse:** `appupdate.check()` bietet nur numerisch neuere App-Versionen an; yt-dlp vergleicht laufende, vorgemerkte und mitgelieferte Fassung. Kein regulaerer Update-Downgrade gefunden. Ein manuell gestarteter alter Installer kann weiterhin eine neuere Installation ersetzen. Keine deaktivierte TLS-Zertifikatspruefung und kein `shell=True` in der App gefunden. Eigene ffmpeg/ffprobe-Aufrufe verwenden absolute `bin/`-Pfade, yt-dlp bekommt `ffmpeg_location` plus ContextVar; kein belegter PATH-Hijack fuer diese beiden Programme. Weitere installierte yt-dlp-Plugins/JS-Laufzeiten sind eine lokale Vertrauensgrenze, keine zugesicherte Sandbox.
- **Inno:** gleicher AppId fuer Upgrades, `PrivilegesRequired=lowest`, keine aufgeweichten ACLs im Skript. Beide Run-Zeilen starten die absolute App-EXE ohne Shell, normal bzw. nach stillem Update. Deinstallation entfernt Programmdateien, Resolve-Script, IPC und nachgeladenes yt-dlp; neu auch `.neu/.alt/.whl` und Selbsttestbericht. Vorschaubilder optional, Videos bewusst nie; QSettings und Temp-Reste koennen verbleiben. Upgrade, Unicode-Installationspfad, erzwungenes Schliessen und echte Deinstallation noch praktisch pruefen. Zwangsschliessen kann laufende Arbeit abbrechen.
- **GUI/Assets/Spec:** Importanalyse findet nur QtCore/Gui/Widgets/Multimedia/MultimediaWidgets; keine benoetigte Qt-Bibliothek ist ausgeschlossen. Neue `icons.py`/`widgets.py` werden statisch importiert; Icons zeichnen mit QPainter, QtSvg wird aktuell nicht benoetigt. `fevdl.spec` daher unveraendert. Neue Dateien unter `assets/` werden vollstaendig in den geprueften Paketordner und rekursiv in den Installer uebernommen; ICO bleibt Quelle fuer EXE und Setup. Falls spaeter QtSvg eingefuehrt wird: Ausschluss entfernen und Groesse beim naechsten Bau messen. Bisherige Artefakte: Paket ohne externe bin/assets 149.517.080 Bytes, Installer 102.762.497 Bytes; bin zusammen 205.402.112 Bytes. **Keine neue Groessenmessung eines Builds.**
- **Repo/Geheimnisse:** Musterpruefung von Arbeitsdateien und `git log --all -p` ueber 43 damals erreichbare Commits: keine bekannten Token-/Privatschluessel-/Passwortzuweisungen gefunden, keine Vollgarantie fuer verschluesselte/binaere Inhalte. main/origin/main enthalten sechs regulaere Commits; Git-Autoren haben teils Nicht-noreply-E-Mail-Adressen (normale oeffentliche Metadaten, Werte nicht wiederholt). Lokaler T3-Pruefpunkt `0cab378` enthaelt `design/reference/_work/chrome/`; kein Vorfahr von main/origin/main, keine oeffentliche Veroeffentlichung nachgewiesen (GitHub-Abfrage 422). Cookies, Logins und Verlauf der drei geprueften Datenbanken sind leer. Keine Verlaufsbereinigung vorgenommen.
- **Oeffentliche Dateien:** downloads/ (lokal 95 Dateien, ca. 286 MB), bin, venv, build und dist sind ignoriert und nicht auf main versioniert; keine Fremdvideos im Installer-Quellmuster. Design ist derzeit unversioniert: keine Video-/Audio-Dateien oder Browserprofil-Marker im heutigen Baum gefunden. Bildquelle laut `design/README.md:11` nur Big Buck Bunny, Blender Foundation, CC BY 3.0, inklusive Beschnitt-/Attributionshinweis; keine Einzelbild-Forensik. Design-Pruefdateien enthalten lokale Nutzerpfade. Neue Ignore-Regeln schuetzen typische .env/Schluessel/Cookie-Dateien und Arbeitsprofile; nicht blind `git add -f` oder alle lokalen Pruefpunkt-Refs pushen. Spec packt weder tests/ noch design/ noch venv als Verzeichnis; neue EXE-Inhalte nicht inspiziert, da kein Bau. Grobe Klartextsuche im alten EXE findet den Projektpfad nicht.
- **Rechtlicher Hinweis:** README und Ueber-Fenster nennen eigene bzw. erlaubte Inhalte; bitte beim GUI-Umbau erhalten. Oeffentliches Repo allein bedeutet noch keine freie Lizenz fuer den eigenen App-Code; Lizenzwahl bleibt beim Besitzer. SmartScreen-/Virenscanner-Hinweis ist vorhanden. Hinweis an CLAUDE.md-Besitzer: EV-Signierung umgeht SmartScreen heute nicht automatisch; ausserdem liegen bin/assets fuer den Selbsttest nun bereits im Paketordner. Diese gesperrten Dokumente wurden nicht geaendert.

## Abhaengigkeiten und Teststand

Lokal: Python 3.13.10, yt-dlp 2026.10.26, curl_cffi 0.17.0, cffi 2.1.1, certifi 2026.10.23, PySide6/shiboken6 6.12.0, PyInstaller 6.22.3, Hooks 2026.9, ffmpeg/ffprobe 9.0. PyPI-Vulnerabilities der 19 installierten Distributionen abgefragt: nur setuptools-Fund oben. `pip-audit` ist nicht installiert. `pip list --outdated`: pip 26.2.1 -> 26.3, pycparser 3.0 -> 3.12, setuptools 84.0.0 -> 84.2.1. Das ersetzt keinen umfassenden Audit der nativen Qt/curl/ffmpeg-Bibliotheken; keine spezifische offene ffmpeg-CVE fuer diesen Build nachgewiesen. gyan.dev bietet inzwischen 9.0.2; vorhandene EXEs wurden nicht ersetzt.

- `tests/run_tests.ps1`: **19/19 Testdateien gruen**, auch GUI und der inzwischen von Opus ergaenzte Sammelmappe-Test, keine roten Tests. Neue `test_security.py`: 12 Testfaelle; vorhandene Update-Tests klein an Hash-Rueckgabe und isolierte Download-Ordner angepasst. Keine echten Netzwerk-Downloads in dieser Suite.
- PowerShell-AST aller Wurzel-Skripte und `build_installer.ps1 -NurPruefen`: bestanden. Lizenzsammler getrennt im Temp-Ordner ausgefuehrt: 11 Originaldateien, 74.340 Bytes; Qt-Luecke dadurch sichtbar, nicht automatisch geloest.
- Tools vorhanden: venv-Python/PyInstaller; Inno `C:\Users\fevzy\AppData\Local\Programs\Inno Setup 6\ISCC.exe` (Installation 6.7.3); gh `C:\Program Files\GitHub CLI\gh.exe` 2.103.3 (nicht im aktuellen PATH, Fallback vorhanden). gh-Anmeldung nicht geprueft. Python im allgemeinen PATH ist 3.12; Build verwendet korrekt das 3.13-venv.
- **Nicht ausgefuehrt:** vollstaendiger PyInstaller-/Installer-Bau, release.ps1, Signierung, Installation/Upgrade/Deinstallation, echter App-Update-Lauf gegen GitHub, neues Wheel aktivieren, kompletter ffmpeg-Bootstrap oder Online-Medientests. Kein eigener Commit, Push oder Upload; gesperrte GUI/Assets/Design/Dokumentation nicht editiert.

## Bau-Freigabe

1. **Vorher:** GUI/ICO-Umbau abschliessen, Fund 5 (exakte Quellen/Copyrights) klaeren, Rechte aus 3 bewusst bewerten. Rechtlichen Hinweis im Ueber-Fenster erhalten; Fund 13 an Opus geben. App-Version **nur** in `src/fevdl/__init__.py` erhoehen (1.1.0 ist schon veroeffentlicht). Neue Qt-Importe gegen Spec pruefen. `assets/` darf nur fuer die Weitergabe bestimmte Dateien enthalten.
2. Entwicklungswerkzeug aktualisieren, ohne die Laufzeitpakete pauschal auszutauschen:
   ```powershell
   .venv\Scripts\python.exe -m pip install --upgrade "setuptools>=84.1.0"
   powershell -NoProfile -ExecutionPolicy Bypass -File build_installer.ps1 -NurPruefen
   ```
3. Nach Abschluss des Umbaus **ein Befehl** fuer Tests, Bau, isolierten Selbsttest und Installer:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File build_installer.ps1
   ```
   Benoetigt Netz fuer den EXE-Selbsttest. Erfolg: `dist\FevDownloadSetup.exe` und `dist\bau.json`; bei rotem Selbsttest wird Inno nicht gestartet. `-OhneTests` nicht fuer eine Freigabe verwenden. Selbsttestbericht liegt im ausgegebenen Temp-Pruefordner.
4. Im normalen Benutzerkonto/sauberer VM: Erstinstallation ohne Admin; neue Oberflaeche/ICO/Bilder; echter Download und Resolve-Import; Upgrade ueber 1.1.0; anschliessend Deinstallation mit/ohne Thumbnail-Loeschung. Videos muessen bleiben. Installer nicht mit PowerShell `Start-Process -Wait` testen (mitgestartete App kann das Warten offenhalten).
5. Optionales Code-Signing als eigene Arbeit einplanen: App/Installer/Uninstaller korrekt signieren, RFC-3161-Zeitstempel, Verifikation; erst danach den endgueltigen Installer hashen und `bau.json` passend erzeugen. Dateizeitstempel oder `signiert`-Feld sind kein Signaturnachweis. Keine Signierung eingerichtet.
6. **Nur nach eigener ausdruecklicher Veroeffentlichungsfreigabe:** finalen Stand bewusst committen und sauber neu bauen, gh-Anmeldung pruefen; erst dann `release.ps1 -OhneBau -Notizen "..."`. Der Befehl pusht und veroeffentlicht wirklich; er wurde hier nicht gestartet. Neue Build-Metadaten sind Voraussetzung, alte vorhandene Installer haben diesen Nachweis noch nicht.

Quellen fuer die externen Angaben: [PyPI-Hashes/API](https://docs.pypi.org/api/json/), [setuptools-Advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w), [FFmpeg-Lizenzen](https://ffmpeg.org/legal.html), [GPL-FAQ zur Quellenbereitstellung](https://www.gnu.org/licenses/gpl-faq.en.html#SourceAndBinaryOnDifferentSites), [Qt-LGPL-Pflichten](https://www.qt.io/development/open-source-lgpl-obligations), [gyan-Builds](https://www.gyan.dev/ffmpeg/builds/), [FFmpeg-Sicherheitsliste](https://ffmpeg.org/security.html), [Inno UTF8Encode](https://jrsoftware.org/ishelp/topic_isxfunc_utf8encode.htm), [Microsoft SmartScreen](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation). Lizenz-/Quellenabgleich ist noch offen, keine juristische Vollstaendigkeitsbestaetigung.

## Frueherer lokaler Bau-Nachweis vom 02.11.2026 (vor dem Quellenpaket)

- **Gelungen:** Vorpruefung und vollstaendiger Lauf Tests -> PyInstaller -> isolierter EXE-Netzselbsttest -> Inno Setup; Fassung unveraendert **1.1.0**. `dist/bau.json` bindet den Installer-Hash und meldet `selbsttest: bestanden`, `arbeitsbaum_sauber: false`, `signiert: false`. Kein Umgehungsschalter noetig; `release.ps1` lehnt diesen lokalen Stand weiterhin ab und wurde nicht ausgefuehrt.
- **Installer:** `dist/FevDownloadSetup.exe`, **103.334.300 Bytes**, SHA-256 `456db254e8ff01005ca86a1444a03f515bb70fc4d312ce0dd1ff941ab7b20963`. Gegenueber 102.762.497 Bytes: **+571.803 Bytes / +0,556 %**, vor allem das jetzt rekursiv mitgenommene Screenshot (567.454 Bytes) und Originallizenzen sowie geaenderter Python-Code/Verdichtung.
- **Paket:** `dist/FevDownload`, **355.627.609 Bytes** inklusive bin (205.402.112), assets (572.004), Lizenzen (74.340). Mit dem alten Paket vergleichbar ohne diese drei Ordner: **149.579.153 Bytes**, vorher 149.517.080, also **+62.073 Bytes / +0,042 %**. `FevDownload.exe`: 8.696.486 Bytes, SHA-256 `facd96053f644b2c3b5e72300b399475f26fe13778e839442e4d6ea0b799b228`.
- **Tests:** **20/20 Offline-Testdateien** gruen, einschliesslich Fund 13. EXE-Selbsttest: **6 OK, 0 Fehler**, yt-dlp 2026.10.26 ausschliesslich mitgeliefert, ffmpeg/ffprobe vorhanden; YouTube-Analyse 635 s, Ausschnitt 10-13 s exakt 3,00 s / 0,21 MB, Vorschau 37,0 MB; TikTok-Analyse erfolgreich (19 s, 1920p). **47 Browser-Ziele:** chrome 24, edge 2, firefox 7, safari 13, tor 1. Bericht unveraendert gesichert unter `build/local-build-qa/selbsttest.txt` (lokaler Bericht, nicht im Installer).
- **Paketpruefung:** exakt **971** `yt_dlp.extractor.`-Module sowohl in `build/fevdl/PYZ-00.toc` als auch im eingebetteten PYZ; `fevdl.gui.icons`/`widgets`, Multimedia-/TLS-Plugins vorhanden. Alle neun ICO-Bilder stimmen mit den Ressourcen von App und Setup ueberein. Installer nur mit dem [portablen Inno-Unpacker](https://github.com/jrathlev/InnoUnpacker-Windows-GUI/releases) als Archiv entpackt (Download-Hash verifiziert), **281/281 Paketdateien bytegleich**, keine Ausfuehrung/Installation des Setups.
- **Datenschutz:** grobe ASCII-/UTF-16-Klartextsuche in EXE, Setup, allen entpackten Installerdateien sowie dekomprimiertem PYZ/base_library.zip ohne Treffer fuer `C:\Users\fevzy` und ohne eigene Geheimnisse. PEM-Treffer sind nullterminierte Formatmarker ohne Schluesseldaten; eine feste AWS-Kennung in `yt_dlp.extractor.shahid` wurde gegen den [offiziellen yt-dlp-Tag](https://github.com/yt-dlp/yt-dlp/blob/2026.10.26/yt_dlp/extractor/shahid.py) bytegleich als oeffentliche Upstream-Konstante bewertet (Wert nicht ausgegeben). Details: `build/local-build-qa/paketpruefung.json`.
- **Fenster/Bestand:** gepackte EXE mit eigenem LOCALAPPDATA und deaktivierter Update-Suche gestartet; Titel **Fev Download**, Fensterhandle vorhanden, Prozess reagiert. Nur die selbst gestartete PID mit exakt geprueftem `dist/FevDownload/FevDownload.exe`-Pfad beendet, ohne echte Qt-Einstellungen zu speichern. Hashvergleich: installierte App und install.json sowie die 213 geschuetzten Dokument-/Designdateien unveraendert; auch echte Qt-Einstellungen unveraendert.
- **Eigene Aenderungen:** `build_installer.ps1` behandelt PyInstaller-INFO auf stderr unter PowerShell 5.1 korrekt und prueft den Exitcode. `tests/run_tests.ps1` nutzt neu `tests/run_isolated.py`: eigene IPC-Dateien und INI-QSettings statt `clear()` in der echten Registry. setuptools gezielt auf 84.2.1; dieser Bericht. Keine Aenderungen an GUI, Spec, Versionsnummer, design/, CLAUDE.md, README.md oder PRODUCT.md durch diesen Bauauftrag; kein Commit, Push, Release oder Upload.
- **Nicht geprueft/offen:** Installation, Upgrade, Deinstallation, echter Resolve-Import, App-Update und Signierung; App und Installer sind unsigniert. `/DIR` isoliert die Inno-Schreib-/Loeschziele fuer install.json und Resolve nicht, daher auf dem Besitzerrechner bewusst keine Installationstests. Fund 3 (Rechte) und Fund 5 (passende ffmpeg-/Qt-Quellen und Hinweise) bleiben offen. **1.1.0 ist bereits veroeffentlicht:** vor echter Weitergabe/Update-Angebot Version erhoehen, Lizenz-/Quellenfrage klaeren, in sauberer VM testen und aus bewusst committetem Stand neu bauen.

## Lizenz-Nachtrag und neuer lokaler Pruefbau vom 02.11.2026

**Fund 5 ist teilweise bearbeitet, nicht geschlossen.** Keine Rechtsberatung und
keine Vollstaendigkeitsgarantie. Die private Weitergabe an drei Freunde aendert
nichts daran, dass die entsprechenden Lizenzpflichten fuer die mitgegebenen
Fremdprogramme zu erfuellen sind. Der neue Installer ist ein lokaler Pruefbau;
die technische Baupruefung bestaetigt keine lizenzrechtliche Freigabe.

### Exakte Zuordnung und Recherche

- Lokal: `9.0-essentials_build-www.gyan.dev`, GCC 16.1.0 (MSYS2 Rev2),
  `--enable-gpl --enable-version3 --enable-static`. `-version` und `-buildconf`
  sind unveraendert in `installer/licenses/ffmpeg/BUILD.txt` gesichert.
- Das [gyan-Release 9.0 vom 04.08.2026](https://github.com/GyanD/codexffmpeg/releases/tag/9.0)
  ist weiterhin vorhanden. Sein [historisches ZIP](https://github.com/GyanD/codexffmpeg/releases/download/9.0/ffmpeg-9.0-essentials_build.zip)
  hat **111.167.378 Bytes**, SHA-256
  `e6b54767a6065919048f1a098eb27211ca4e12b4348a05d88777a5855d0b6e71`.
  Hash gegen den vom Hersteller/GitHub gezeigten Asset-Digest abgeglichen;
  anschliessend beide EXEs aus diesem Archiv mit den vorhandenen Dateien
  verglichen: **bytegleich**, keine EXE ersetzt.
- `ffmpeg.exe`: SHA-256 `227af0691433b703ffc5725e47f7d06eefc34b4a72e7870e73d30e2cda483ecf`;
  `ffprobe.exe`: `901f0efe4793cbb0f017101e3427f816e8fbf9a407bd585f49df30f4325cfd88`.
- Release und originale `GYAN-README.txt` nennen den FFmpeg-Commit
  `d32b387f2b0a484599d4587d651891f0c63c4238`. Der annotierte Tag `n9.0`
  zeigt auf diesen Commit (Tagobjekt `5b9252abfe2fda0ccb71ed45cd7a954cc45d2b6f`).
  Das [offizielle Quellarchiv](https://ffmpeg.org/releases/ffmpeg-9.0.tar.xz)
  hat **12.032.020 Bytes**, SHA-256
  `7f607a00dd0d28a729d5a4811205812eef01cf6ef6155025febb6f36a9062d52`.
  Die offizielle `.asc`-Signatur wurde mit GnuPG in einem eigenen Pruefverzeichnis
  erfolgreich geprueft; `VALIDSIG` fuer
  `FCF986EA15E6E293A5644F10B4322F04D67658D8`, abgeglichen mit der
  [FFmpeg-Downloadseite](https://ffmpeg.org/download.html). Schluessel und
  Signatur liegen bei. Spaetere Einrichtungen pruefen den festen Archivhash.
- Die [aktuelle gyan-Seite](https://www.gyan.dev/ffmpeg/builds/) liefert inzwischen
  **9.0.2** (FFmpeg-Commit `946fcce07b...`); deren beweglicher Downloadlink und
  aktuelle Bibliotheksliste sind kein Ersatz fuer 9.0. Die automatischen
  GitHub-„Source code“-Archive des Repos **GyanD/codexffmpeg** enthalten nicht
  die gesuchten FFmpeg- und Bibliotheksquellen.
- Das Original der historischen gyan-README enthaelt am Ende eine Liste
  externer Versionen, aber keine komplette per-Bibliothek-Lizenz-/Quellenliste.
  `BIBLIOTHEKEN.tsv` erfasst **55 Bibliotheks-/API-Zeilen**, trennt belegte
  Staende, Einzel-Lizenzbelege, Quellenlinks und offene Zuordnungen. Insbesondere
  wurde der aktuelle Webstand nicht als historischer Buildstand ausgegeben.

### Was unmittelbar mitgeliefert wird und warum

`licenses/ffmpeg/` enthaelt fuenf unveraenderte Quellarchive:

| Quelle | Exakter belegter Stand | Archivgroesse |
|---|---|---:|
| FFmpeg | n9.0 / d32b387f2b0a484599d4587d651891f0c63c4238 | 12.032.020 Bytes |
| x264 | r3223 / 0480cb05fa188d37ae87e8f4fd8f1aea3711f7ee | 1.040.667 Bytes |
| Xvid | 1.3.7 | 820.854 Bytes |
| Rubber Band | v4.0.0 / 1d95888bec3ae0a17c0c4af791810d5a63f6bc35 | 290.593 Bytes |
| vid.stab | 8f5ce5838982804c0869e33ddc4968a3ceeda40c | 154.389 Bytes |

Die x264-Kurzkennung ist zusaetzlich aus der SEI eines **lokal erzeugten**
64x64-Testframes belegt (`core 165 r3223 0480cb0`). Der GitHub-Quellmirror
ist als Mirror gekennzeichnet. Die auf volle Commits festgelegten x264-/vid.stab-
Archiv-URLs wurden erneut geladen und gegen die festgelegten Hashes geprueft.
Archive fuer die anderen Bibliotheken wurden ueber HTTPS bezogen und gehasht;
dafuer ist keine unabhaengige Herstellersignatur nachgewiesen.

Die fuenf Archive umfassen zusammen **14.338.523 Bytes**; mit Signatur,
Schluessel und beiden gyan-Originaltexten sind es **14.417.343 Bytes**.
Vor dem Einbau kommunizierte Schaetzung: zunaechst +12,03 MB fuer FFmpeg,
danach +rund 2,3 MB fuer vier kleine GPL-Bibliotheksquellen, zuzueglich Hinweise.
Fuer einen bisherigen 103,33-MB-Installer ist das praktikabel. Das 111-MB-
Hersteller-ZIP wird nur zur Zuordnung/Einrichtung benoetigt und **nicht**
zusaetzlich eingepackt. Auch die rund 68,69 MB QtBase- und 10,81 MB AviSynth-
Recherchearchive bleiben ausserhalb des Installers: Sie schliessen die offenen
Wheel-/Build-Zuordnungen nicht, AviSynth benoetigt ausserdem eine getrennte
optionale Runtime. Entsprechende belegte Quellenverweise bleiben im Inventar.

Beigefuegt sind ausserdem originale GPL-/LGPL-Texte, FFmpeg-CREDITS,
IJG-Nennung, gyan-README/-Lizenz, lokale Konfiguration, belegte externe
Lizenz-/Copyright-Dateien sowie Originaltexte/Attributionen aus dem QtBase-Tag
v6.12.0 und zusaetzliche curl-Lizenztexte. `licenses/HERKUNFT.json` dokumentiert
**170 Originaldateien** mit Herkunft und SHA-256. Die eigenen Hinweisdateien
sind davon getrennt; Originaltexte wurden nicht uebersetzt oder umgeschrieben.

Weitere Quellen sind, soweit ein Stand belegbar ist, mit festen Tags/Hashes
verlinkt. **Nicht vorhandene Versionsangaben wurden nicht geraten.**
Beispiele: GnuTLS, GMP, libass, FreeType, Fontconfig, FriBidi, HarfBuzz und
weitere Grundbibliotheken fehlen in der Hersteller-Versionsliste; OpenAL steht
nur als „latest“. x265 ist `4.3-2-g5ab552e`; die abgefragte
[Projekt-Archivadresse](https://bitbucket.org/multicoreware/x265_git/get/5ab552e.tar.gz)
lieferte **404**, ebenso abgefragte GitHub-Zuordnungen. Ein beliebiges x265-4.3-
Archiv wurde deshalb nicht als passend ausgegeben. README nennt `libmfx`,
die lokale configure-Zeile dagegen nicht. Transitive Bibliotheken,
Hersteller-Patches und komplette Bau-/Linkskripte sind weiterhin nicht belegt.
Die vorhandenen configure-/Makefiles, README und Compilerangabe allein
schliessen diese Luecke nicht.

**Kein Ersatz durch ein leeres Quellenangebot:** Die vorhandenen Quellen
begleiten das Binaer unmittelbar. Ein Kontaktweg zu den Projekt-Issues ist
angegeben, aber kein vollstaendiges Angebot nach GPLv3 6(b) behauptet.
Solange die fehlenden Daten nicht beschafft sind, waere ein Versprechen auf
deren Lieferung nicht verteidigbar. Ein spaeteres schriftliches Angebot muesste
die vollstaendigen entsprechenden Quellen tatsaechlich liefern koennen und
mindestens drei Jahre sowie solange wie in 6(b) genannter Support/Ersatzteile
angeboten werden gueltig bleiben. Fremde Links haben keine zugesicherte
Gueltigkeitsdauer. Massstab sind der [GPLv3-Volltext](https://www.gnu.org/licenses/gpl-3.0.html)
und die [FFmpeg-Lizenzhinweise](https://ffmpeg.org/legal.html).

### Qt, curl und weitere Pakete

- **Qt/PySide6/Shiboken6 6.12.0:** LGPLv3-/GPLv3-Originaltexte und belegte
  QtBase-Attributionen mit zugehoerigen Lizenzdateien ergaenzt. Austausch
  kompatibler Bibliotheken und Reverse Engineering zum Debuggen geaenderter
  Bibliotheken werden nicht eingeschraenkt. Die vorhandenen kommerziellen
  Wheel-Texte bleiben erhalten, werden aber nicht als Lizenzberechtigung
  ausgegeben. Offen bleiben komplette Quellen-/Baunachweise, weitere Module,
  Multimedia-FFmpeg-DLLs, Mesa und Microsoft-Runtimes.
- **Konkreter Qt-Zusatzfund:** Das unveraendert gepackte Laufzeitpaket enthaelt
  `Qt6VirtualKeyboard.dll` und `platforminputcontexts/qtvirtualkeyboardplugin.dll`.
  Qt nennt dafuer [GPLv3 oder kommerziell](https://doc.qt.io/qt-6/qtvirtualkeyboard-index.html#licenses-and-attributions),
  nicht allgemein LGPLv3. Das direkte App-Importinventar allein war deshalb
  kein vollstaendiger Lizenzabgleich. Die App importiert das Modul nicht selbst.
  Naechster technischer Schritt: unnoetigen Plugin-Pfad gezielt ausschliessen,
  dynamische Abhaengigkeiten und Qt-Tests erneut pruefen; alternativ dessen
  Lizenz-/Quellenpflichten klaeren. In dieser Runde keine Aenderung an der Spec
  oder Qt-Laufzeit-Zusammenstellung.
- **curl_cffi 0.17.0:** `Curl.version()` der tatsaechlich gebauten DLL meldet
  **curl-impersonate 2.3.1 / libcurl 8.23.0**, obwohl die
  [Wrapper-README](https://github.com/lexiforest/curl_cffi/blob/v0.17.0/README.md)
  noch 2.3.0 nennt. Beigefuegt sind Originaltexte von curl, curl-impersonate 2.3.1,
  zlib 1.3.1, Brotli 1.2.1, Zstd 1.5.7, c-ares 1.34.9, nghttp2 1.63.0,
  ngtcp2 1.20.0, nghttp3 1.15.0 sowie BoringSSL. Fuer BoringSSL ist der Commit
  `156c7b75ae9b8c3b3f847acf264f17594c3859fb` aus dem
  [2.3.1-Bauplan](https://github.com/lexiforest/curl-impersonate/blob/v2.3.1/CMakeLists.txt)
  belegt; dessen Identitaet mit dem Wheel ist nicht unabhaengig nachgewiesen.
  Es wird keine pauschale MIT-Lizenz fuer alle nativen Teile behauptet.
- **certifi 2026.10.23:** MPL-2.0-Originaltext wird gesammelt;
  Zertifikatsdaten liegen lesbar unter `_internal/certifi/cacert.pem`, der
  [entsprechende Upstream-Tag](https://github.com/certifi/python-certifi/tree/2026.10.23)
  ist genannt. Python/yt-dlp/cffi/pycparser/PyInstaller und die Wheel-Texte
  werden weiterhin aus der verwendeten Umgebung gesammelt; `PAKETE.json`
  dokumentiert ihre Fassungen. Keine Vollstaendigkeitszusage fuer transitive
  native Komponenten oder eine freie Lizenz des eigenen App-Codes.

### Integration und neuer Bau-Nachweis

- `installer/ffmpeg-lock.json` bindet EXEs, Herstellerarchiv und mitgegebene
  Quellen/Originale an feste URLs, Bytegroessen und SHA-256. Die bezeichneten
  Qt/curl/certifi-Paketfassungen sind ebenfalls festgehalten; andere Fassungen
  verlangen einen bewussten neuen Hinweise-/Quellenabgleich.
- `setup.ps1` verwendet `tools/ffmpeg_sources.py`; beweglicher ffmpeg-Download
  entfernt. Vorhandene passende EXEs bleiben unangetastet; unbekannte werden
  abgewiesen. `setup.ps1 -NurFfmpeg` prueft/laedt nur diese Dateien, ohne
  pip-Updates oder install.json-Aenderung. Netzwerkzugriffe pruefen jede
  Weiterleitung auf erlaubtes HTTPS, Downloads ausserdem auf Groesse/Hash.
- `build_installer.ps1` prueft alle erforderlichen Dateien **vor** Tests/Packen,
  kontrolliert die Originalhinweis-Hashes und kopiert das gepruefte Quellenpaket.
  Inno hat einen expliziten Dateieintrag fuer `licenses/` und eine zusaetzliche
  Pflichtpruefung fuer das FFmpeg-Quellarchiv. Alle Dateien werden regulaer im
  Inno-Deinstallationsprotokoll erfasst; kein pauschales Loeschen fremder Dateien.
  Deinstallation ist damit statisch beruecksichtigt, wurde nicht ausgefuehrt.
- README, Lizenzuebersicht und der vorhandene Ueber-Dialog nennen Quellenort und
  offene Fragen. Der Hinweis auf eigene/erlaubte Inhalte bleibt enthalten;
  keine Qt-Stylesheet-/Schriftgroessenaenderung. Dialog separat mit isolierten
  Einstellungen auf beide Hinweise geprueft.
- **Vollstaendiger Baubefehl:**
  `powershell -NoProfile -ExecutionPolicy Bypass -File build_installer.ps1`,
  Exitcode 0: **20/20 Offline-Testdateien**, PyInstaller, isolierter EXE-Netz-
  selbsttest **6 OK / 0 Fehler**, danach Inno. Zusaetzlich **6/6 Quellen-
  Grenzpruefungen**: Pfadtraversal, Uebergroesse, falscher Downloadhash, echter
  kleiner Quellen-Download, Bauabbruch bei fehlendem Archiv und Abweisung
  manipulierter Signaturdatei. Keine Tests uebersprungen.
- **Netzselbsttest:** 47 Browser-Ziele, YouTube-Analyse 635 s, Ausschnitt
  10-13 s exakt **3,00 s / 0,21 MB**, Vorschau **37,0 MB**, TikTok-Analyse
  **19 s / 1920p** erfolgreich. Bericht: `build/license-qa/selbsttest.txt`;
  Bauprotokoll: `build/license-qa/build.log`. Keine echten Benutzer-IPC-Dateien
  oder Qt-Einstellungen fuer diese Pruefungen verwendet.
- **Installer vorher/nachher:** **103.334.300 -> 117.788.888 Bytes**,
  **+14.454.588 Bytes / +13,988 %**; dezimal **103,33 -> 117,79 MB**
  (neu 112,33 MiB). README rundet auf 118 MB. Neuer SHA-256:
  `418fe9df94c05c6ddbf39f087e6fdbc5edb09358f84b2a149dab3eb0b9b22a60`.
  Paketordner **371.024.341 Bytes**, davon `licenses/` **15.419.290 Bytes**.
- **Inhaltspruefung:** Installer ausschliesslich mit dem bereits vorhandenen
  Inno-Unpacker als Archiv entpackt, niemals gestartet/installiert.
  **470/470 Paketdateien bytegleich**, darunter alle Quellarchive, Original-
  hinweise, Manifest und LIZENZEN.txt; 473 entpackte Dateien insgesamt.
  **971/971** yt-dlp-Extraktormodule, Icons von EXE/Setup in allen neun
  Aufloesungen identisch, GUI-Module vorhanden, kein setuptools im PYZ.
  Klartext-/Tokenmusterpruefung in Paket, EXE, Setup, entpackten Dateien,
  PYZ und base_library.zip ohne neue ungeklärte Funde; bekannte Upstream-
  Konstante und leere PEM-Formatmarker wie zuvor bewertet, Werte nicht ausgegeben.
  Ergebnis: `build/license-qa/paketpruefung.json`. Kein umfassender Secret-Audit
  aller dekomprimierten Fremdquellarchive behauptet.
- **Geschuetzter Bestand:** Hashvergleich aller **505** vorher gesicherten
  Dateien bestanden, darunter installierte App, install.json, design/,
  CLAUDE.md, release.ps1 und Versionsdatei. Fassung unveraendert **1.1.0**.
  Kein Commit, Push, release.ps1-Aufruf, Upload oder sonstige Online-Aenderung.
  `bau.json`: `signiert=false`, `arbeitsbaum_sauber=false`,
  `lizenzpruefung=offen`; Installation/Upgrade/Deinstallation nicht getestet.

### Empfehlung fuer das bereits oeffentliche Release 1.1.0

**Keine Online-Aktion durchgefuehrt.** Empfehlung an den Besitzer: Den alten
Installer bis zur Klaerung nicht weitergeben und dessen oeffentliche
Download-Verfuegbarkeit bewusst pruefen/gegebenenfalls vorlaeufig zuruecknehmen.
Ein Hinweistext allein ersetzt fehlende Quellen nicht. Bereits versorgte
Empfaenger sollten die passenden Quellen und Hinweise zur exakt erhaltenen
Fassung nachgeliefert bekommen, sobald das vollstaendige Paket vorliegt.
Das bestehende Asset nicht still durch diesen weiterhin unvollstaendig
abgeglichenen Pruefbau mit gleicher Versionsnummer austauschen.

Textvorschlag fuer eine vom Besitzer freizugebende Release-Ergaenzung:

> Die Lizenz- und Quellenunterlagen zu den enthaltenen Fremdkomponenten werden
> derzeit vervollstaendigt. Fuer den bisherigen FFmpeg-9.0-Build sind noch nicht
> alle passenden Bibliotheksquellen und Hersteller-Bauunterlagen gesichert.
> Bitte diesen Installer vorerst nicht weiterverteilen. Eine technisch
> erfolgreiche Pruefung ist keine abgeschlossene Lizenzfreigabe. Sobald die
> Unterlagen vollstaendig sind, werden sie zur passenden Fassung bereitgestellt.

**Naechster Schritt:** Beim gyan-Hersteller ueber den auf seiner Buildseite
genannten Kontakt `builds@gyan.dev` das vollstaendige Quellen-/Buildpaket fuer
genau das oben gehashte 9.0-essentials-ZIP anfragen (durch den Besitzer, hier
nicht gesendet). Benoetigt: alle direkten/transitiven Bibliotheksstaende,
Patches, Copyright-/Lizenztexte und Bau-/Linkskripte, insbesondere die bislang
unversionierten Grundbibliotheken und x265 `5ab552e`. Parallel das unnoetige
Qt-Virtual-Keyboard-Plugin und die uebrigen Wheel-Nachweise klaeren. Danach
Quellenpaket vervollstaendigen, in sauberer VM pruefen und erst nach bewusster
Veroeffentlichungsfreigabe eine neue App-Fassung aus sauberem Stand bauen.
