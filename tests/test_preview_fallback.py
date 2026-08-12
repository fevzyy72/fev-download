"""Laedt die Ausweich-Vorschaudatei wirklich herunter und prueft sie."""

import sys
import tempfile
import time
from pathlib import Path

from fevdl.core.download import download_preview, probe_duration, probe_video_codec

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"

target = Path(tempfile.mkdtemp(prefix="fevprev_"))
print("Lade Vorschaudatei...")
started = time.time()
result = download_preview(URL, target)
elapsed = time.time() - started

size_mb = result.stat().st_size / (1024 * 1024)
print(f"Datei   : {result.name}")
print(f"Dauer   : {elapsed:.1f} s")
print(f"Groesse : {size_mb:.1f} MB")
print(f"Codec   : {probe_video_codec(result)}")
print(f"Laenge  : {probe_duration(result):.1f} s")

assert result.is_file(), "Datei fehlt"
assert size_mb > 0.05, "Datei ist verdaechtig klein"
assert probe_duration(result) > 1, "Datei hat keine Laufzeit"

print("\nVORSCHAU-AUSWEICH-TEST OK")
