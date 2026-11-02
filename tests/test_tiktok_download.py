"""TikTok wirklich analysieren, Vorschau, ganzen Clip, Ausschnitt und Ton laden.

Optionaler Link: python tests/test_tiktok_download.py <TikTok-Link>
Dateien entstehen in einem temporaeren Ordner und werden danach entfernt.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from fevdl import paths
from fevdl.core.download import download, download_preview, probe_duration, probe_video_codec
from fevdl.core.models import DownloadRequest, Mode
from fevdl.core.probe import probe

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.tiktok.com/@yavereth/video/7688387323892960534"


def streams(file: Path) -> list[str]:
    result = subprocess.run(
        [str(paths.FFPROBE_EXE), "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "json", str(file)],
        capture_output=True, text=True, check=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return [s["codec_type"] for s in json.loads(result.stdout)["streams"]]


info = probe(URL)
assert info.has_video, "TikTok wurde faelschlich als reine Tonquelle erkannt"
assert info.duration >= 5, "Fuer den Ausschnitt-Test mindestens 5 Sekunden erforderlich"
print(f"Analyse OK: {info.duration:.1f}s, {info.width}x{info.height}, {len(info.qualities)} Qualitaeten")

with tempfile.TemporaryDirectory(prefix="fevtiktok_") as folder:
    target = Path(folder)
    preview = download_preview(info.url, target / "preview")
    assert "video" in streams(preview), "Die Vorschau enthaelt kein Video"
    assert probe_duration(preview) > 0
    print("Vorschau OK")

    whole = download(DownloadRequest(url=info.url, output_dir=target / "whole"))
    assert {"video", "audio"}.issubset(streams(whole)), "Bild oder Ton fehlen"
    assert probe_video_codec(whole) == "h264", "Der Clip ist nicht nach H.264 umgewandelt"
    assert abs(probe_duration(whole) - info.duration) <= 1
    print("Ganzes Video + Ton, H.264 OK")

    trimmed = download(DownloadRequest(
        url=info.url, output_dir=target / "trim", start=1, end=4,
    ))
    assert {"video", "audio"}.issubset(streams(trimmed))
    assert abs(probe_duration(trimmed) - 3) <= 0.5, "Ausschnitt ist ungenau"
    print("Ausschnitt 1-4s OK")

    audio = download(DownloadRequest(
        url=info.url, output_dir=target / "audio", mode=Mode.AUDIO_ONLY,
    ))
    assert streams(audio) == ["audio"], "Nur Ton enthaelt Video oder keine Tonspur"
    print("Nur Ton OK")

print("TIKTOK-DOWNLOAD-TEST OK")
