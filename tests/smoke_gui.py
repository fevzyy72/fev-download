"""Baut das Fenster auf, prueft ein paar Grundfunktionen und beendet sich."""

import sys

from PySide6.QtWidgets import QApplication

from fevdl.core.models import Mode, VideoInfo, Quality, format_timecode
from fevdl.gui.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
# Erfundene Links duerfen keine echten Downloads ausloesen.
window._start_preview_fallback = lambda: None
window.show()

# Ergebnis einer Analyse vortaeuschen - ohne Netzwerk.
info = VideoInfo(
    url="https://example.com/video",
    title="Testvideo mit einem ziemlich langen Titel zum Pruefen des Umbruchs",
    duration=635.0,
    uploader="Testkanal",
    thumbnail_url="",
    preview_url="",
    qualities=[
        Quality(2160, 60), Quality(1440, 60), Quality(1080, 60),
        Quality(720, 60), Quality(480, None), Quality(360, None),
    ],
    extractor="Youtube",
)
window._on_probe_succeeded(info)

print("Titel      :", window.title_label.text()[:40], "...")
print("Meta       :", window.meta_label.text())
print("Qualitaeten:", [window.quality_combo.itemText(i) for i in range(window.quality_combo.count())])
print("Vorauswahl :", window.quality_combo.currentText(), "->", window.quality_combo.currentData())
print("Dauer Bar  :", format_timecode(window.trim_bar.duration()))
print("Ganzes Video:", window.trim_bar.is_full_range())

# Ausschnitt setzen
window.trim_bar.set_start(60.0)
window.trim_bar.set_end(80.0)
print("Von/Bis    :", window.start_edit.text(), "-", window.end_edit.text())
print("Auswahl    :", window.selection_label.text())
print("Ganzes Video:", window.trim_bar.is_full_range())

# Zeitfeld-Eingabe
window.start_edit.setText("1:30")
window._on_start_edited()
print("Nach Eingabe 1:30 ->", window.start_edit.text(), "=", window.trim_bar.start(), "s")

# Ungueltige Eingabe darf nicht abstuerzen
window.end_edit.setText("bloedsinn")
window._on_end_edited()
print("Nach Unsinn-Eingabe ->", window.end_edit.text())

# Modus wechseln
window.mode_combo.setCurrentIndex(window.mode_combo.findData(Mode.AUDIO_ONLY.value))
print("Modus      :", window.mode_combo.currentText(), "| Qualitaet aktiv:", window.quality_combo.isEnabled())
window.mode_combo.setCurrentIndex(window.mode_combo.findData(Mode.VIDEO_AUDIO.value))
print("Modus      :", window.mode_combo.currentText(), "| Qualitaet aktiv:", window.quality_combo.isEnabled())

# "Ganzes Video" zuruecksetzen
window.reset_trim_button.click()
print("Nach Reset :", window.start_edit.text(), "-", window.end_edit.text(), "| ganz:", window.trim_bar.is_full_range())

window.close()
app.processEvents()
print("\nSMOKETEST OK")
