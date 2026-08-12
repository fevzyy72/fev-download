"""Laedt wirklich zwei Ausschnitte desselben Videos - braucht Internet.

Prueft zwei Dinge, die nur mit echtem Netz sichtbar werden:

1. **Getrennte Dateien.** Beide Auftraege gehen an dieselbe Adresse. Enthielte
   der Dateiname den Zeitbereich nicht, bekaemen sie denselben Namen und yt-dlp
   wuerde die erste Datei stillschweigend wiederverwenden - man haette zweimal
   denselben Ausschnitt und wuerde es nicht merken.

2. **Gleichzeitig ist schneller.** Der Durchsatz je Verbindung ist gedrosselt,
   nicht die Leitung. Zwei Ausschnitte parallel muessen daher deutlich schneller
   sein als die Summe der Einzelzeiten.
"""

import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from fevdl.core.download import probe_duration
from fevdl.core.models import DownloadRequest, Mode
from fevdl.gui.worker import MAX_PARALLEL, DownloadWorker

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"

ziel = Path(tempfile.mkdtemp(prefix="fevsegnetz_"))
bereiche = [(30.0, 45.0), (200.0, 215.0)]
auftraege = [
    DownloadRequest(url=URL, output_dir=ziel, mode=Mode.VIDEO_AUDIO, height=1080,
                    start=anfang, end=ende, prefer_h264=True)
    for anfang, ende in bereiche
]

app = QApplication(sys.argv[:1])

fertige = []
meldungen = []
fehler = []
worker = DownloadWorker(auftraege)
worker.fileReady.connect(lambda pfad: fertige.append(pfad))
worker.progressed.connect(lambda p: meldungen.append((p.percent, p.part, p.parts)))
worker.failed.connect(lambda text: fehler.append(text))
worker.succeeded.connect(lambda _pfad: app.quit())
worker.failed.connect(lambda _text: app.quit())
worker.cancelled.connect(app.quit)

# Notbremse, damit der Test bei haengender Leitung nicht ewig steht.
QTimer.singleShot(8 * 60 * 1000, app.quit)

start = time.perf_counter()
worker.start()
app.exec()
parallel = time.perf_counter() - start
worker.wait(10000)

assert not fehler, f"Download fehlgeschlagen: {fehler[0]}"
print(f"Gleichzeitig (bis zu {MAX_PARALLEL}): {parallel:.1f} s fuer zwei Ausschnitte")

assert len(fertige) == 2, f"Erwartet zwei Dateien, bekommen {len(fertige)}"
assert len(set(fertige)) == 2, "Beide Ausschnitte landeten in derselben Datei"

for datei, (anfang, ende) in zip(sorted(fertige), bereiche):
    laenge = probe_duration(datei)
    soll = ende - anfang
    print(f"   {datei.name[:58]}")
    print(f"      {laenge:.1f} s (erwartet {soll:.1f} s), "
          f"{datei.stat().st_size / 1024:.0f} KB")
    assert datei.is_file() and datei.stat().st_size > 0
    # Der Schnitt sitzt an Keyframes, eine Sekunde Spielraum ist normal.
    assert abs(laenge - soll) <= 2.0, f"{datei.name}: {laenge:.1f} s statt {soll:.1f} s"

groessen = {datei.stat().st_size for datei in fertige}
assert len(groessen) == 2, "Beide Dateien sind gleich gross - da wurde etwas wiederverwendet"

# Die Fortschrittsmeldungen muessen zusammengefasst sein, nicht springen.
assert meldungen, "Es kam ueberhaupt keine Fortschrittsmeldung"
assert all(teile == 2 for _prozent, _fertig, teile in meldungen)
prozente = [prozent for prozent, _fertig, _teile in meldungen]
assert prozente == sorted(prozente), "Der Fortschritt darf nicht zurueckspringen"
print(f"   Fortschritt lief von {prozente[0]:.0f} % auf {prozente[-1]:.0f} %, "
      f"{len(meldungen)} Meldungen, immer steigend")

print("\nMEHRERE-AUSSCHNITTE-NETZTEST OK")
