"""Stoeren die Kuerzel I und O das Tippen im Link-Feld?"""

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from fevdl import paths
from fevdl.core.models import Quality, VideoInfo
from fevdl.gui import typography
from fevdl.gui.main_window import MainWindow

paths.RESULT_FILE = Path(tempfile.mkdtemp(prefix="fevkeys_")) / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())

window = MainWindow(job=None)
window._start_preview_fallback = lambda: None
window.show()
QTest.qWaitForWindowExposed(window)

info = VideoInfo(url="u", title="T", duration=600.0, audio_url="a",
                 qualities=[Quality(1080, 30)])
window._on_probe_succeeded(info)
window.trim_bar.set_playhead(123.0)

start_before = window.trim_bar.start()

window.url_edit.setFocus()
window.url_edit.clear()
QTest.qWait(50)

# Genau das tippt man bei einem echten Link: "video" enthaelt i und o
for char in "video":
    QTest.keyClick(window.url_edit, char)
QTest.qWait(50)

typed = window.url_edit.text()
start_after = window.trim_bar.start()

print("Getippt      :", repr(typed))
print("Ausschnitt-Anfang vorher/nachher:", start_before, "/", start_after)

problems = []
if typed != "video":
    problems.append(f"Im Feld steht {typed!r} statt 'video' - Zeichen gehen verloren")
if start_after != start_before:
    problems.append("Das Tippen hat den Ausschnitt-Anfang verschoben")

if problems:
    print("\nPROBLEM:")
    for p in problems:
        print("  -", p)
    sys.exit(1)

window.close()
QTest.qWait(50)
print("\nTIPPEN OK - die Kuerzel stoeren nicht")
