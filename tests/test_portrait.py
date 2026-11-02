"""Prueft Hochformat-Darstellung und die Ausweichlösung fuer die Vorschau."""

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QVideoFrame
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
window._settings = QSettings(str(paths.RESULT_FILE.with_suffix(".ini")), QSettings.IniFormat)
window._start_preview_fallback = lambda: None
window.player.load = lambda *_args, **_kwargs: None
window.resize(1100, 900)
window.show()
app.processEvents()

# --- Echte Geometrie pruefen: ein Breiten-Maximum allein reicht nicht. ---
quadrat = VideoInfo(url="u", title="Quadrat", duration=60, width=1080, height=1080,
                    qualities=[Quality(1080)])
for breite, hoehe in [(1100, 900), (1180, 1385), (1440, 960), (860, 620)]:
    window.resize(breite, hoehe)
    for info in (quer, hoch, quadrat):
        window._on_probe_succeeded(info)
        window.player._stack.setCurrentWidget(window.player._video)
        app.processEvents()
        app.processEvents()
        area = window.player._stage.contentsRect()
        bild = window.player._stack.geometry()
        assert area.contains(bild), "Videoflaeche ragt aus dem sichtbaren Bereich"
        assert abs(bild.width() - bild.height() * info.aspect) <= 1, "Bildformat verzerrt"
        assert bild.width() == area.width() or bild.height() == area.height(), "Bild nutzt den Platz nicht"
        assert abs(bild.center().x() - area.center().x()) <= 1, "Bild nicht waagerecht zentriert"
        assert abs(bild.center().y() - area.center().y()) <= 1, "Bild nicht senkrecht zentriert"
        print(f"{breite}x{hoehe}, {info.title}: Bild {bild.width()}x{bild.height()}, Flaeche {area.width()}x{area.height()}")

# --- Die dekodierte Groesse korrigiert falsche Metadaten, ohne Layoutsprung. ---
window.resize(1100, 900)
window.player.set_aspect(16 / 9)
frame_image = QImage(1080, 1920, QImage.Format_RGB32)
frame_image.fill(0xff445566)
window.player._video.videoSink().setVideoFrame(QVideoFrame(frame_image))
app.processEvents()
app.processEvents()
assert abs(window.player._aspect - 9 / 16) < 0.001, "Dekodiertes Hochformat wurde ignoriert"
assert window.player.height() < window.height(), "Originalaufloesung blaest das Layout auf"

# --- Lade-/Fehlermeldungen bleiben auch nach Hochformat gut lesbar. ---
window.player.show_loading()
app.processEvents()
assert window.player._stack.geometry() == window.player._stage.contentsRect()

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
