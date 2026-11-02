"""
Prueft, ob der Nutzer zu einem echten Link eine abspielbare Vorschau bekommt.

Zwei Wege, genau wie in der App:
  1. ein direkter Stream, wenn die Seite einen liefert
  2. sonst die Ausweichdatei, die die App selbst herunterlaedt

Bei YouTube gibt es derzeit keinen direkten Stream mehr (nur getrennte Spuren),
dort zaehlt also der zweite Weg. Frueher endete der Test an dieser Stelle mit
"in Ordnung" - und der Fehler blieb unbemerkt.
"""

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from fevdl.core.download import download_preview
from fevdl.core.probe import probe

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"

print("Analysiere...")
info = probe(URL)
print("Titel        :", info.title)
print("Vorschau-URL :", (info.preview_url[:90] + "...") if info.preview_url else "KEINE")

source = info.preview_url
if source:
    print("Quelle       : direkter Stream")
else:
    print("Quelle       : Ausweichdatei (wie in der App)")
    source = download_preview(URL, Path(tempfile.mkdtemp(prefix="fevprev2_")))
    print("Datei        :", source.name)

app = QApplication(sys.argv)

from fevdl.gui.preview_player import PreviewPlayer

player = PreviewPlayer()
player.resize(640, 400)
player.show()

state = {"positions": [], "error": None, "duration": 0.0}

player.positionChanged.connect(lambda s: state["positions"].append(s))
player.durationResolved.connect(lambda d: state.update(duration=d))

inner = player._player
inner.errorOccurred.connect(lambda e, msg: state.update(error=msg))

player.load(source, fallback_duration=info.duration)
QTimer.singleShot(1200, player.toggle_play)          # abspielen
QTimer.singleShot(4000, lambda: player.seek(120.0))  # springen
QTimer.singleShot(7000, app.quit)

app.exec()

print("\n--- Ergebnis ---")
print("Fehler        :", state["error"] or "keiner")
print("Dauer erkannt :", round(state["duration"], 1), "s")
print("Positionsmeldungen:", len(state["positions"]))
if state["positions"]:
    print("Letzte Position   :", round(state["positions"][-1], 1), "s")

playable = state["error"] is None and len(state["positions"]) > 2
print("\nERGEBNIS:", "VORSCHAU SPIELT" if playable else "VORSCHAU SPIELT NICHT")

player.close()
app.processEvents()
# Ein Test, der nie scheitern kann, prueft nichts.
sys.exit(0 if playable else 1)
