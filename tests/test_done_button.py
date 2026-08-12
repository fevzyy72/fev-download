"""Prueft den Wechsel Herunterladen -> Fertig -> schliessen."""

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from fevdl import paths
from fevdl.core.models import Quality, VideoInfo
from fevdl.gui import typography
from fevdl.gui.main_window import MainWindow

tmp = Path(tempfile.mkdtemp(prefix="fevdone_"))
paths.RESULT_FILE = tmp / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())

window = MainWindow(job=None)
window._start_preview_fallback = lambda: None
window.show()

info = VideoInfo(
    url="https://example.com/v",
    title="Testvideo",
    duration=300.0,
    qualities=[Quality(1080, 30), Quality(720, 30)],
    extractor="Youtube",
)
window._on_probe_succeeded(info)
print("Nach Analyse    :", repr(window.download_button.text()), "| completed =", window._completed)
assert window.download_button.text() == "Herunterladen"

# Fertigen Download vortaeuschen
fake = tmp / "clip.mp4"
fake.write_bytes(b"x")
window._on_download_succeeded(fake)
print("Nach Download   :", repr(window.download_button.text()), "| completed =", window._completed)
assert window.download_button.text() == "Fertig", "Knopf muss auf Fertig wechseln"
assert window._completed is True

# Klick auf Fertig muss schliessen, nicht erneut laden
closed = {"value": False}
original_close = window.close


def spy_close():
    closed["value"] = True
    return original_close()


window.close = spy_close
window._on_primary_clicked()
print("Klick auf Fertig: Fenster geschlossen =", closed["value"])
assert closed["value"], "Fertig muss das Fenster schliessen"

# Neuer Link setzt zurueck
window2 = MainWindow(job=None)
window2._start_preview_fallback = lambda: None
window2._on_probe_succeeded(info)
window2._on_download_succeeded(fake)
assert window2.download_button.text() == "Fertig"
window2.url_edit.setText("https://example.com/anderes")
window2.url_edit.textEdited.emit("https://example.com/anderes")
print("Nach neuem Link :", repr(window2.download_button.text()), "| completed =", window2._completed)
assert window2.download_button.text() == "Herunterladen", "Neuer Link muss zuruecksetzen"
assert window2._completed is False

window2.close()
app.processEvents()
print("\nFERTIG-KNOPF-TEST OK")
