# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

> Tatsächliche Zielplattform ist ein **Windows-Desktopprogramm (PySide6/Qt)**. „web“ steht hier nur, weil
> die Gestaltungsvorlage als HTML entsteht. Alles, was die Vorlage zeigt, muss später in Qt-Stylesheets
> und eigener Zeichnung (`QPainter`) umsetzbar sein – siehe `CLAUDE.md` (Abschnitt „Qt / PySide6“).

## Users

Der Besitzer und zwei Freunde – Privatpersonen, keine Entwickler. Sie laden Videos von YouTube, TikTok und
über tausend weiteren Plattformen (über yt-dlp), schneiden den gewünschten Ausschnitt heraus und
speichern ihn als Datei. Die App ist ausdrücklich ein **allgemeiner Video-Downloader**; die Übergabe an
DaVinci Resolve (kostenlose Version 21) ist ein zusätzlicher Weg, kein Muss. Sie wird entweder direkt
gestartet oder über Resolve (`Workspace → Scripts → Utility`).

Sie benutzen die App kurz und zielgerichtet: Link einfügen, Stelle finden, laden. Windows, 64 Bit.

## Product Purpose

Von einem Link zu einer fertigen Datei – ohne Kommandozeile, ohne Python, ohne Umweg. Man lädt nur den
gewählten Ausschnitt statt des ganzen Videos; mehrere Ausschnitte desselben Videos laufen gleichzeitig.
Erfolg: Ein Freund ohne Vorkenntnisse findet die richtige Stelle, lädt sie und hat die Datei, ohne
ein Handbuch zu lesen.

## Positioning

Was ein reiner Downloader nicht bietet: Man sieht das Video, **findet die Stelle an der Vorschau und an
der Tonspur (Wellenform)** und lädt nur diesen Ausschnitt, mit mehreren Ausschnitten pro Video. Hinzu
kommen die Medienbibliothek der geladenen Dateien und der direkte Weg in den Media Pool von DaVinci
Resolve.

## Operating Context

- Fenster mit Menüleiste (Datei / Ausschnitt / Hilfe), eine Hauptseite „Download“ und eine
  „Bibliothek“ der geladenen Dateien. Fenstergröße beim Start 1000 × 960, Minimum 860 × 620.
- Videos kommen im Quer-, Hoch- (TikTok, 9:16) und Quadratformat vor. Die Vorschau bekommt bewusst allen
  verfügbaren Platz (keine Höhenbegrenzung) und zeigt das ganze Bild.
- Wird die App aus Resolve gestartet, zeigt sie einen Hinweis mit dem Projektnamen und meldet jede fertige
  Datei dorthin zurück.
- Tastenkürzel: `I` (Anfang setzen), `O` (Ende setzen), `M` (Ausschnitt merken).
- Aktualisierungen: yt-dlp lädt sich still nach, die App bietet neue Fassungen von GitHub an
  (Hilfe → Nach Aktualisierung suchen).
- Alle Texte sind Deutsch.

## Capabilities and Constraints

- Funktionen: Link (Einfügen, Leeren, Drag & Drop), Analyse (Titel, Kanal, Dauer, Plattform, Vorschaubild),
  Vorschau-Player mit Spulleiste, Ausschnitt-Balken mit Wellenform (auf Knopfdruck), Von/Bis-Zeitfelder,
  „Anfang hier“, „Ende hier“, „Ganzes Video“, „Ausschnitt merken“ plus Liste der gemerkten Ausschnitte,
  Inhalt (Video + Ton / nur Ton / nur Video), Qualität, Haken „H.264 für Resolve“, Zielordner,
  Statuszeile, Download-Knopf (wird nach Abschluss zu „Fertig“), Fortschritt auch bei mehreren
  gleichzeitigen Ausschnitten, Bibliothek mit Suche und Filter, Aktualisierungsdialog mit Fortschritt.
- Technische Grenzen der Umsetzung in Qt (verbindlich für die Vorlage):
  - Schriftgrößen und Laufweite nur über `typography.py` (`setFont`), **nicht** im Stylesheet;
    das Stylesheet regelt Farbe, Rahmen, Abstand.
  - Kein `box-shadow`, kein `backdrop-filter`, kein `text-transform`, kein `letter-spacing` im Stylesheet.
    Verläufe nur als `qlineargradient`. Abgerundete Ecken und Rahmen gehen.
  - `QComboBox::down-arrow` nicht anfassen (zerstört die Textdarstellung).
  - Der Ausschnitt-Balken (`trim_bar.py`) ist selbst gezeichnet – dort ist fast alles möglich.
  - Das Videobild kommt von `QVideoWidget` und liegt außerhalb des Layouts; Überlagerungen darüber sind
    heikel.
  - Fenster- und Titelleiste sind die von Windows.
- Quellcodedateien enthalten keine Umlaute; Nutzertexte der App bleiben vorerst, wie sie sind.

## Brand Commitments

- Name: **Fev Download** (bleibt). Herausgeber: fezco.
- Symbol und Schriftzug sind frei neu zu entwerfen – der Besitzer mag das bisherige Programmsymbol nicht.
  Es wird u. a. als Taskleisten- und Verknüpfungssymbol (`assets/fevdl.ico`, 16–256 px) benutzt.
- Der Besitzer findet die heutige Oberfläche **langweilig und veraltet**; Zeitleiste und Knöpfe sollen
  schöner und einfacher werden. Die Vorlage zeigt eine **helle und eine dunkle** Variante.

## Evidence on Hand

- Aktueller Zustand: `assets/screenshot.png` (Big Buck Bunny, YouTube-Link analysiert).
- Quellen der heutigen Gestaltung: `src/fevdl/gui/style.py`, `typography.py`, `trim_bar.py`,
  `preview_player.py`, `main_window.py`, `library_page.py`; Symbol-Generator `tools/make_icon.py`.
- Testmaterial für Bilder: ausschließlich *Big Buck Bunny* (Blender Foundation, CC BY 3.0) in
  `downloads/` bzw. über `bin\ffmpeg.exe` daraus gezogene Einzelbilder. Es gibt **keine** Kundenaussagen,
  Zahlen oder Fremdlogos, die erfunden werden dürften. Fremde Videos (z. B. TikTok-Testclip) dürfen nicht
  in die Vorlage, weil das Projekt öffentlich auf GitHub liegt.

## Product Principles

1. **Der Weg ist kurz:** Link → Stelle finden → laden. Nichts davon darf versteckt oder verschachtelt sein.
2. **Die Vorschau ist die Hauptsache.** Wer eine Stelle sucht, schaut aufs Bild und auf die Tonspur; alles
   andere tritt zurück und bekommt nur den Platz, den es braucht.
3. **Es funktioniert auch ohne Resolve** und ohne Vorwissen; Fehlermeldungen sind deutsch und verständlich.
4. **Gemerkte Ausschnitte gelten:** Ist die Liste gefüllt, wird sie geladen, der Balken ist dann nur das
   Werkzeug, mit dem sie entstand – die Oberfläche darf das nie widersprüchlich anzeigen.
5. **Nichts zeigt mehr, als stimmt:** Fortschritt, Status und Auswahl spiegeln den wahren Zustand.

## Accessibility & Inclusion

Bedienung muss auch ohne Maus möglich bleiben (bestehende Tastenkürzel I, O, M erhalten). Weitere
Anforderungen wurden nicht festgelegt.
