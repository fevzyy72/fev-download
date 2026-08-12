"""Prueft die drei neuen Funktionen am Ausschnitt-Balken.

    1. Beim Ziehen eines Griffs folgt die Vorschau der Stelle
    2. Mehrere Ausschnitte lassen sich merken und wieder entfernen
    3. Aus der Liste werden mehrere Download-Auftraege
"""

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from fevdl import paths
from fevdl.core.models import Quality, VideoInfo
from fevdl.gui import typography
from fevdl.gui.main_window import MainWindow

tmp = Path(tempfile.mkdtemp(prefix="fevseg_"))
paths.RESULT_FILE = tmp / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())
QSettings("fezco", "Fev Download").clear()

window = MainWindow(job=None)
window._start_preview_fallback = lambda: None
window.output_edit.setText(str(tmp))
window.show()
QTest.qWaitForWindowExposed(window)

info = VideoInfo(
    url="https://example.com/v",
    title="Testvideo",
    duration=600.0,
    qualities=[Quality(1080, 30)],
    extractor="Youtube",
)
window._on_probe_succeeded(info)

# -- 1. Vorschau folgt dem Griff -------------------------------------------

gespult = []
window.player.seek = lambda seconds: gespult.append(seconds)
window.player.pause = lambda: None

window.trim_bar.scrubbed.emit(180.0)
window.trim_bar.scrubFinished.emit(184.5)
print("Gespult an     :", gespult)
assert gespult, "Beim Ziehen muss die Vorschau spulen"
assert gespult[-1] == 184.5, "Beim Loslassen muss die genaue Stelle kommen"
assert abs(window.trim_bar._playhead - 184.5) < 0.01, "Die Marke muss mitwandern"

# Der Griff selbst muss den Balken bewegen und dabei melden.
gespult.clear()
balken = window.trim_bar
mitte_y = int(balken.height() / 2)
start_x = int(balken._seconds_to_x(balken.start()))
QTest.mousePress(balken, Qt.LeftButton, Qt.NoModifier, QPoint(start_x, mitte_y))
QTest.mouseMove(balken, QPoint(start_x + 120, mitte_y))
QTest.mouseRelease(balken, Qt.LeftButton, Qt.NoModifier, QPoint(start_x + 120, mitte_y))
print("Anfang nachher :", round(balken.start(), 1), "| Meldungen:", len(gespult))
assert balken.start() > 0, "Das Ziehen muss den Anfang verschieben"
assert gespult, "Das Ziehen muss die Vorschau mitnehmen"

# -- 2. Ausschnitte merken -------------------------------------------------

window.trim_bar.set_range(60.0, 90.0)
window._add_segment()
window.trim_bar.set_range(500.0, 560.0)
window._add_segment()
window.trim_bar.set_range(10.0, 25.0)
window._add_segment()

print("Gemerkt        :", window._segments)
assert len(window._segments) == 3
assert window._segments == sorted(window._segments), "Die Liste muss geordnet sein"
assert window.segment_list.count() == 3
assert window.segment_list.isVisible(), "Die Liste muss sichtbar werden"
assert window.segment_tools.isVisible()
assert window.download_button.text() == "3 Ausschnitte laden"

# Derselbe Bereich darf nicht doppelt hinein.
window.trim_bar.set_range(60.0, 90.0)
window._add_segment()
assert len(window._segments) == 3, "Doppelte Ausschnitte muss er abweisen"

# Ein leerer Ausschnitt kann gar nicht erst entstehen: Der Balken zieht einen
# zu kurzen Bereich auf eine Sekunde auf, genau wie beim Ziehen der Griffe.
window.trim_bar.set_range(300.0, 300.5)
print("Zu kurz gesetzt:", round(window.trim_bar.start(), 1), round(window.trim_bar.end(), 1))
assert window.trim_bar.end() - window.trim_bar.start() >= 1.0
assert len(window._segments) == 3

# -- 3. Zurueckholen und entfernen -----------------------------------------

window._load_segment(1)
print("Zurueckgeholt  :", round(window.trim_bar.start(), 1), round(window.trim_bar.end(), 1))
assert abs(window.trim_bar.start() - 60.0) < 0.01
assert abs(window.trim_bar.end() - 90.0) < 0.01
assert window.segment_list.currentRow() == 1

window.segment_list.setCurrentRow(0)
window._remove_segment()
print("Nach Entfernen :", window._segments)
assert len(window._segments) == 2
assert window.download_button.text() == "2 Ausschnitte laden"

# -- 4. Auftraege bauen ----------------------------------------------------

auftraege = window._build_requests()
print("Auftraege      :", [(a.start, a.end) for a in auftraege])
assert len(auftraege) == 2, "Jeder Ausschnitt braucht einen eigenen Auftrag"
assert auftraege[0].start == 60.0 and auftraege[0].end == 90.0
assert auftraege[1].start == 500.0 and auftraege[1].end == 560.0
assert all(a.url == info.url for a in auftraege)
assert all(a.output_dir == tmp for a in auftraege)

# Ohne Liste bleibt es beim eingestellten Bereich.
window._clear_segments()
print("Nach Leeren    :", window._segments, "|", repr(window.download_button.text()))
assert not window._segments
assert not window.segment_list.isVisible()
assert window.download_button.text() == "Herunterladen"

window._reset_trim()
einzeln = window._build_requests()
assert len(einzeln) == 1
assert einzeln[0].start is None and einzeln[0].end is None, "Ganzes Video: kein Schnitt"

window.trim_bar.set_range(30.0, 45.0)
einzeln = window._build_requests()
assert einzeln[0].start == 30.0 and einzeln[0].end == 45.0

# -- 5. Ein neuer Link verwirft die Liste ----------------------------------

window.trim_bar.set_range(100.0, 130.0)
window._add_segment()
assert len(window._segments) == 1
window._on_probe_succeeded(info)
print("Nach Analyse   :", window._segments)
assert not window._segments, "Ein neues Video darf die alte Liste nicht erben"

# -- 6. Mehrere fertige Dateien werden gemeldet ----------------------------

erste = tmp / "teil1.mp4"
zweite = tmp / "teil2.mp4"
erste.write_bytes(b"x")
zweite.write_bytes(b"y")
window._on_file_ready(erste)
window._on_download_succeeded(zweite)
print("Meldung        :", window.status_label.text())
assert window._finished_files == [erste, zweite]
assert "2 Ausschnitte" in window.status_label.text()
assert window.download_button.text() == "Fertig"

window.close()
app.processEvents()
QSettings("fezco", "Fev Download").clear()
print("\nAUSSCHNITT-TEST OK")
