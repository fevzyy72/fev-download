"""Prueft die Wellenform-Berechnung an einem echten Video."""

import sys
import time

from fevdl.core.probe import probe
from fevdl.core.waveform import extract_peaks

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"

print("Analysiere...")
info = probe(URL)
print("Titel     :", info.title)
print("Dauer     :", info.duration_text)
print("Tonspur   :", (info.audio_url[:80] + "...") if info.audio_url else "KEINE")

if not info.audio_url:
    print("\nKeine separate Tonspur verfuegbar.")
    sys.exit(0)

print("\nBerechne Wellenform...")
started = time.time()
peaks = extract_peaks(info.audio_url, info.duration, buckets=900)
elapsed = time.time() - started

print(f"Dauer der Berechnung: {elapsed:.1f} s")
print("Werte     :", len(peaks))
print("Bereich   :", f"min={min(peaks):.3f}  max={max(peaks):.3f}")
print("Mittelwert:", f"{sum(peaks)/len(peaks):.3f}")

assert len(peaks) > 100, "Zu wenige Werte"
assert 0.0 <= min(peaks) and max(peaks) <= 1.0, "Werte ausserhalb 0..1"
assert abs(max(peaks) - 1.0) < 0.001, "Lautester Ausschlag muss auf 1.0 liegen"

# Grobe Textdarstellung zur Sichtpruefung
print("\nVerlauf (jede Spalte = ca. {:.0f} s):".format(info.duration / 60))
levels = " ▁▂▃▄▅▆▇█"
step = max(1, len(peaks) // 60)
line = "".join(levels[min(8, int(peaks[i] * 8))] for i in range(0, len(peaks), step))
print(line)

print("\nWELLENFORM-TEST OK")
