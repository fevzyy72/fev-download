"""Prueft den Wellenform-Knopf und rendert den Balken zur Sichtpruefung."""

import math
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from fevdl import paths
from fevdl.core.models import Quality, VideoInfo
from fevdl.gui import typography
from fevdl.gui.main_window import MainWindow

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "fev_wellenform.png"
paths.RESULT_FILE = Path(tempfile.mkdtemp(prefix="fevwave_")) / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())

window = MainWindow(job=None)
window._start_preview_fallback = lambda: None
window.show()

# --- Ohne Tonspur muss der Knopf gesperrt bleiben ---
no_audio = VideoInfo(url="u", title="Ohne Ton", duration=100.0, audio_url="",
                     qualities=[Quality(720, 30)])
window._on_probe_succeeded(no_audio)
print("Ohne Tonspur : Knopf aktiv =", window.waveform_button.isEnabled())
assert not window.waveform_button.isEnabled(), "Ohne Tonspur muss der Knopf gesperrt sein"

# --- Mit Tonspur ---
info = VideoInfo(
    url="https://example.com/v",
    title="Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film",
    duration=635.0,
    uploader="Blender",
    audio_url="https://example.com/audio.m4a",
    qualities=[Quality(2160, 60), Quality(1080, 60), Quality(720, 60)],
    extractor="Youtube",
)
window._on_probe_succeeded(info)
print("Mit Tonspur  : Knopf aktiv =", window.waveform_button.isEnabled())
assert window.waveform_button.isEnabled()

# Berechnete Werte vortaeuschen (ein Lied mit Strophe/Refrain)
peaks = []
for i in range(900):
    t = i / 900
    envelope = 0.25 + 0.7 * abs(math.sin(t * math.pi * 3))
    detail = 0.55 + 0.45 * abs(math.sin(t * 140))
    peaks.append(min(1.0, envelope * detail))
peaks[:40] = [0.02] * 40      # Stille am Anfang
peaks[-60:] = [0.02] * 60     # Stille am Ende

window._on_waveform_ready(peaks)
print("Nach Laden   :", repr(window.waveform_button.text()), "| Balken hat Wellenform =", window.trim_bar.has_waveform())
assert window.trim_bar.has_waveform()
assert window.waveform_button.text() == "Tonspur ausblenden"

# Umschalten aus
window._toggle_waveform()
print("Ausblenden   :", repr(window.waveform_button.text()), "| Balken hat Wellenform =", window.trim_bar.has_waveform())
assert not window.trim_bar.has_waveform()

# Wieder ein - darf NICHT neu berechnen
window._toggle_waveform()
print("Wieder ein   :", repr(window.waveform_button.text()), "| Balken hat Wellenform =", window.trim_bar.has_waveform())
assert window.trim_bar.has_waveform(), "Zwischengespeicherte Werte muessen wiederverwendet werden"

# "Ganzes Video" darf die Wellenform nicht verlieren
window.trim_bar.set_start(120.0)
window.trim_bar.set_end(400.0)
window._reset_trim()
print("Nach Reset   : Wellenform noch da =", window.trim_bar.has_waveform())
assert window.trim_bar.has_waveform(), "Zuruecksetzen darf die Wellenform nicht loeschen"

# Neues Video verwirft sie
window._on_probe_succeeded(no_audio)
print("Neues Video  : Wellenform noch da =", window.trim_bar.has_waveform())
assert not window.trim_bar.has_waveform(), "Neues Video muss die alte Wellenform verwerfen"

# --- Bild zur Sichtpruefung ---
window._on_probe_succeeded(info)
window._on_waveform_ready(peaks)
window.trim_bar.set_start(150.0)
window.trim_bar.set_end(430.0)
window.trim_bar.set_playhead(260.0)
app.processEvents()
window.trim_bar.grab().save(str(OUT))
print("\nBalken gespeichert:", OUT)

window.close()
app.processEvents()
print("\nWELLENFORM-GUI-TEST OK")
