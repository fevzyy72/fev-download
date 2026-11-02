"""Laedt die Ausweich-Vorschaudatei wirklich herunter und prueft sie."""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fevdl import paths
from fevdl.core.download import download_preview, probe_duration, probe_video_codec

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


def stream_types(path):
    """Welche Spuren (video, audio) die Datei wirklich enthaelt."""
    output = subprocess.run(
        [str(paths.FFPROBE_EXE), "-v", "error", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return {line.strip() for line in output.splitlines() if line.strip()}


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
streams = stream_types(result)
print(f"Spuren  : {', '.join(sorted(streams))}")

assert result.is_file(), "Datei fehlt"
assert size_mb > 0.05, "Datei ist verdaechtig klein"
assert probe_duration(result) > 1, "Datei hat keine Laufzeit"
# Getrennt geladene Spuren muessen wirklich zusammengesetzt sein - eine Vorschau
# ohne Ton waere zum Finden einer Schnittstelle kaum zu gebrauchen.
assert "video" in streams, "Die Vorschau hat kein Bild"
assert "audio" in streams, "Die Vorschau hat keinen Ton"

print("\nVORSCHAU-AUSWEICH-TEST OK")
