"""Prueft Einstellungen merken, Ziehen-und-Ablegen, Zwischenablage, Symbol."""

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QSettings, Qt, QUrl
from PySide6.QtGui import QDropEvent, QIcon
from PySide6.QtWidgets import QApplication

from fevdl import paths
from fevdl.core.models import Mode, Quality, VideoInfo
from fevdl.gui import typography
from fevdl.gui.main_window import MainWindow

paths.RESULT_FILE = Path(tempfile.mkdtemp(prefix="fevpolish_")) / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())
app.setApplicationName("Fev Download TEST")
app.setOrganizationName("fezco")

# Testeinstellungen isoliert halten
QSettings("fezco", "Fev Download").clear()

# --- Symbol ---
assert paths.ICON_FILE.is_file(), "Symboldatei fehlt"
icon = QIcon(str(paths.ICON_FILE))
print("Symbol       :", len(icon.availableSizes()), "Groessen, nicht leer =", not icon.isNull())
assert not icon.isNull()

info = VideoInfo(
    url="https://example.com/v",
    title="Ein sehr langer Videotitel der auf jeden Fall gekuerzt werden muss weil er viel zu lang ist",
    duration=600.0,
    audio_url="a",
    qualities=[Quality(2160, 60), Quality(1080, 60), Quality(720, 30)],
    extractor="Youtube",
)

# --- Erste Sitzung: Einstellungen aendern ---
w1 = MainWindow(job=None)
w1._start_preview_fallback = lambda: None
target = str(Path(tempfile.mkdtemp(prefix="fevout_")))
w1.output_edit.setText(target)
w1.mode_combo.setCurrentIndex(w1.mode_combo.findData(Mode.AUDIO_ONLY.value))
w1.h264_check.setChecked(False)
w1._on_probe_succeeded(info)
w1.quality_combo.setCurrentIndex(w1.quality_combo.findData(720))
w1.resize(1111, 777)

print("Fenstertitel :", w1.windowTitle())
assert w1.windowTitle().endswith("- Fev Download")
assert len(w1.windowTitle()) < 90, "Titel muss gekuerzt werden"

w1.close()
print("Sitzung 1    : gespeichert")

# --- Zweite Sitzung: alles wieder da? ---
w2 = MainWindow(job=None)
w2._start_preview_fallback = lambda: None
print("Zielordner   :", w2.output_edit.text() == target)
print("Modus        :", w2._current_mode().label)
print("H.264-Haken  :", w2.h264_check.isChecked())
assert w2.output_edit.text() == target, "Zielordner nicht gemerkt"
assert w2._current_mode() is Mode.AUDIO_ONLY, "Modus nicht gemerkt"
assert w2.h264_check.isChecked() is False, "Haken nicht gemerkt"

w2._on_probe_succeeded(info)
print("Qualitaet    :", w2.quality_combo.currentText(), "->", w2.quality_combo.currentData())
assert w2.quality_combo.currentData() == 720, "Qualitaet nicht gemerkt"

# --- Ziehen und Ablegen ---
mime = QMimeData()
mime.setUrls([QUrl("https://www.youtube.com/watch?v=abc123")])
event = QDropEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
w2._start_probe = lambda: print("             (Analyse wuerde jetzt starten)")
w2.dropEvent(event)
print("Abgelegt     :", w2.url_edit.text())
assert w2.url_edit.text() == "https://www.youtube.com/watch?v=abc123", "Link nicht uebernommen"

# Kein Link -> saubere Meldung statt Absturz
mime2 = QMimeData()
mime2.setText("nur irgendein Text")
event2 = QDropEvent(QPoint(10, 10), Qt.CopyAction, mime2, Qt.LeftButton, Qt.NoModifier)
w2.dropEvent(event2)
print("Kein Link    :", w2.status_label.text())
assert "kein Link" in w2.status_label.text()

# --- Zwischenablage ---
QApplication.clipboard().setText("https://vimeo.com/123456")
w3 = MainWindow(job=None)
print("Zwischenabl. :", w3.url_edit.text())
assert w3.url_edit.text() == "https://vimeo.com/123456", "Link nicht aus Zwischenablage uebernommen"

QApplication.clipboard().setText("das ist kein link")
w4 = MainWindow(job=None)
print("Kein Link    : Feld leer =", w4.url_edit.text() == "")
assert w4.url_edit.text() == "", "Nur echte Links duerfen uebernommen werden"

for window in (w2, w3, w4):
    window.close()
app.processEvents()

QSettings("fezco", "Fev Download").clear()
print("\nFEINSCHLIFF-TEST OK")
