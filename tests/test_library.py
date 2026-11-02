"""Prueft Bibliothek, Suche, Filter und die neue Seitennavigation."""

import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from fevdl.gui import typography
from fevdl.gui.main_window import MainWindow


root = Path(tempfile.mkdtemp(prefix="fevlibrary_"))
(root / "Unterordner").mkdir()
video = root / "Schnitt Test.mp4"
audio = root / "Unterordner" / "Musik Test.m4a"
ignored = root / "Notiz.txt"
video.write_bytes(b"video")
audio.write_bytes(b"audio")
ignored.write_text("kein Medium", encoding="utf-8")
os.utime(video, (time.time() - 10 * 86400, time.time() - 10 * 86400))

app = QApplication(sys.argv[:1])
app.setFont(typography.body())
QSettings("fezco", "Fev Download").clear()

window = MainWindow(job=None)
window._start_preview_fallback = lambda: None
window.output_edit.setText(str(root))
window._show_library()

page = window.library_page
print("Seite          :", window.pages.currentIndex())
print("Medien         :", page.table.topLevelItemCount())
assert window.pages.currentIndex() == 1
assert page.table.topLevelItemCount() == 2, "Video und Audio muessen erscheinen"
assert page.count_label.text() == "2 Dateien"

page.kind_combo.setCurrentIndex(page.kind_combo.findData("audio"))
print("Nur Audio      :", page.table.topLevelItemCount())
assert page.table.topLevelItemCount() == 1
assert page.table.topLevelItem(0).text(1) == "Audio"

page.kind_combo.setCurrentIndex(page.kind_combo.findData("all"))
page.search_edit.setText("Schnitt")
print("Suche Schnitt  :", page.table.topLevelItemCount())
assert page.table.topLevelItemCount() == 1
assert page.table.topLevelItem(0).text(0) == "Schnitt Test"

page.search_edit.clear()
page.date_combo.setCurrentIndex(page.date_combo.findData("week"))
print("Letzte 7 Tage  :", page.table.topLevelItemCount())
assert page.table.topLevelItemCount() == 1, "Altes Video muss ausgefiltert werden"

page.date_combo.setCurrentIndex(page.date_combo.findData("all"))
page.table.setCurrentItem(page.table.topLevelItem(0))
assert page.selected_path() is not None
assert page.open_button.isEnabled()
assert not page.import_button.isVisible(), "Standalone gibt es keinen Resolve-Import"

# Die Symbolknoepfe tragen ihren Zweck als Name (Bildschirmleser) und Tooltip,
# die Kuerzel stehen im Tooltip.
print("Knopf-Namen    :", window.set_start_button.accessibleName(), "|", window.waveform_button.accessibleName())
assert "Anfang" in window.set_start_button.accessibleName()
assert "Taste I" in window.set_start_button.toolTip()
assert "Taste O" in window.set_end_button.toolTip()
assert window.reset_trim_button.accessibleName() == "Ganzes Video"
assert window.waveform_button.accessibleName().startswith("Tonspur")

# Filter "Ton" ueber die Reiter, wie mit der Maus
page.kind_combo.buttons()[2].click()
assert page.table.topLevelItemCount() == 1 and page.table.topLevelItem(0).text(1) == "Audio"
page.kind_combo.buttons()[0].click()

# Die Leiste zeigt die aktive Seite
assert window.library_nav_button.isChecked()
window._show_download()
assert window.pages.currentIndex() == 0
assert window.download_nav_button.isChecked()
window.close()
app.processEvents()
QSettings("fezco", "Fev Download").clear()
print("\nBIBLIOTHEK-TEST OK")
