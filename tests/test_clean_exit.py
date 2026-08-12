"""Beendet sich die echte App sauber? Startet sie und schliesst das Fenster."""

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from fevdl import paths
from fevdl.core.models import Quality, VideoInfo
from fevdl.gui import typography
from fevdl.gui.main_window import MainWindow

paths.RESULT_FILE = Path(tempfile.mkdtemp(prefix="fevexit_")) / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())
app.setApplicationName("Fev Download")
app.setOrganizationName("fezco")
QSettings("fezco", "Fev Download").clear()

window = MainWindow(job=None)
window.show()

info = VideoInfo(url="u", title="Test", duration=120.0, width=1080, height=1920,
                 preview_url="", qualities=[Quality(1080, 30)])

# Verhindern, dass der Test tatsaechlich etwas aus dem Netz laedt.
window._start_preview_fallback = lambda: None
window._on_probe_succeeded(info)

QTimer.singleShot(700, window.close)
QTimer.singleShot(1400, app.quit)
code = app.exec()

print("Beendet mit Rueckgabewert:", code)
QSettings("fezco", "Fev Download").clear()
print("SAUBERES-BEENDEN-TEST OK")
