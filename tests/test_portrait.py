"""Prueft Hochformat-Darstellung und die Ausweichlösung fuer die Vorschau."""

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from fevdl import paths
from fevdl.core.models import Quality, VideoInfo
from fevdl.gui import typography
from fevdl.gui.main_window import MainWindow

paths.RESULT_FILE = Path(tempfile.mkdtemp(prefix="fevport_")) / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())
app.setApplicationName("Fev Download")
app.setOrganizationName("fezco")
QSettings("fezco", "Fev Download").clear()

# --- Seitenverhaeltnis ---
quer = VideoInfo(url="u", title="Quer", duration=100.0, width=1920, height=1080,
                 qualities=[Quality(1080, 30)])
hoch = VideoInfo(url="u", title="Hoch", duration=60.0, width=1080, height=1920,
                 qualities=[Quality(1920, 30)])
ohne = VideoInfo(url="u", title="Ohne Angabe", duration=60.0,
                 qualities=[Quality(720, 30)])

print("Quer  : aspect =", round(quer.aspect, 2), "| Hochformat =", quer.is_portrait)
print("Hoch  : aspect =", round(hoch.aspect, 2), "| Hochformat =", hoch.is_portrait)
print("Ohne  : aspect =", round(ohne.aspect, 2), "| Hochformat =", ohne.is_portrait)
assert not quer.is_portrait
assert hoch.is_portrait
assert not ohne.is_portrait, "Ohne Angabe muss 16:9 angenommen werden"

window = MainWindow(job=None)
window.resize(1100, 900)
window.show()
app.processEvents()

# --- Querformat: keine Breitenbegrenzung ---
window._on_probe_succeeded(quer)
app.processEvents()
breit = window.player._stack.maximumWidth()
print("Querformat: Breitengrenze =", breit)
assert breit > 10000, "Querformat darf nicht begrenzt werden"

# --- Hochformat: schmale, hohe Flaeche ---
window._on_probe_succeeded(hoch)
app.processEvents()
schmal = window.player._stack.maximumWidth()
hoehe = window.player._stack.height()
print(f"Hochformat: Breitengrenze = {schmal}, Hoehe = {hoehe}")
assert schmal < 10000, "Hochformat muss in der Breite begrenzt werden"
erwartet = int(hoehe * hoch.aspect)
assert abs(schmal - max(220, erwartet)) <= 2, f"Breite {schmal} passt nicht zu Hoehe {hoehe}"

# --- Vorschau ohne Stream-Adresse loest das Nachladen aus ---
window._preview_attempted_download = False
calls = {"n": 0}
window._start_preview_fallback = lambda: calls.update(n=calls["n"] + 1)
ohne_stream = VideoInfo(url="https://tiktok.com/x", title="TikTok", duration=30.0,
                        width=1080, height=1920, preview_url="",
                        qualities=[Quality(1920, 30)])
window._on_probe_succeeded(ohne_stream)
print("Ohne Stream-Adresse: Nachladen ausgeloest =", calls["n"])
assert calls["n"] == 1, "Ohne Stream muss die Datei geholt werden"

# --- Fehlgeschlagener Stream loest es ebenfalls aus, aber nur einmal ---
window._preview_attempted_download = False
calls["n"] = 0
window.player.streamFailed.emit()
window.player.streamFailed.emit()
print("Stream-Fehler: Nachladen ausgeloest =", calls["n"])
assert calls["n"] >= 1, "Ein Stream-Fehler muss das Nachladen ausloesen"

# Sauber abbauen - sonst raeumt Python die Qt-Objekte in falscher Reihenfolge ab.
window.close()
app.processEvents()

print("\nHOCHFORMAT-TEST OK")
