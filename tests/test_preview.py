"""Prueft, ob Qt einen echten YouTube-Stream abspielen kann."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from fevdl.core.probe import probe

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"

print("Analysiere...")
info = probe(URL)
print("Titel        :", info.title)
print("Vorschau-URL :", (info.preview_url[:90] + "...") if info.preview_url else "KEINE")

if not info.preview_url:
    print("\nERGEBNIS: keine direkt abspielbare Vorschau vorhanden.")
    sys.exit(0)

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

player.load(info.preview_url, fallback_duration=info.duration)
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
