"""
Selbsttest ohne Oberflaeche:  FevDownload.exe --selbsttest

Spielt die Strecke durch, auf die es ankommt - Analyse, ein echter kurzer
Download mit Ausschnitt, die Vorschaudatei - und schreibt das Ergebnis nach
%LOCALAPPDATA%\\FevDownloader\\selbsttest.txt (die .exe hat keine Konsole).

Wozu: Dass sich das Fenster oeffnet, beweist nichts darueber, ob yt-dlp, ffmpeg
und die Netzwerkbibliothek im gepackten Programm wirklich arbeiten. Und wenn bei
jemandem etwas nicht laeuft, genuegt es, diese Datei zu schicken.

Rueckgabewert 0 = alles in Ordnung.
"""

from __future__ import annotations

import sys
import tempfile
import time
import traceback
from pathlib import Path

from . import __version__, paths

# Ein frei lizenzierter Kurzfilm, auf den Verlass ist.
TEST_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
REPORT_FILE = paths.IPC_DIR / "selbsttest.txt"


class _Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failed = 0

    def add(self, text: str = "") -> None:
        self.lines.append(text)

    def ok(self, text: str) -> None:
        self.lines.append("  OK       " + text)

    def fail(self, text: str) -> None:
        self.failed += 1
        self.lines.append("  FEHLER   " + text)

    def save(self) -> None:
        try:
            paths.ensure_dir(REPORT_FILE.parent)
            REPORT_FILE.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        except OSError:
            pass


def run() -> int:
    report = _Report()
    report.add("Fev Download - Selbsttest  ({})".format(time.strftime("%d.%m.%Y %H:%M:%S")))
    report.add("")

    # --- Umgebung ---------------------------------------------------------
    report.add("Umgebung")
    report.add("  App          : {}  ({})".format(__version__, "installiert" if paths.IS_FROZEN else "Quelltext"))
    report.add("  Programmordner: {}".format(paths.PROJECT_ROOT))
    if paths.ffmpeg_available():
        report.ok("ffmpeg und ffprobe liegen bereit")
    else:
        report.fail("ffmpeg/ffprobe fehlen in {}".format(paths.BIN_DIR))

    try:
        import yt_dlp
        from yt_dlp import YoutubeDL
        from yt_dlp.version import __version__ as ytdlp_version

        report.add("  yt-dlp       : {}  (aus {})".format(ytdlp_version, Path(yt_dlp.__file__).parent))
        report.add("  mitgeliefert : {}".format(paths.bundled_ytdlp_version() or "unbekannt"))
        report.add("  nachgeladen  : {}".format(paths.installed_ytdlp_version() or "-"))
        ydl = YoutubeDL({"quiet": True})
        targets = ydl._get_available_impersonate_targets()
        ydl.close()
        if targets:
            report.ok("Browser-Netzwerkbibliothek (TikTok): {} Ziele".format(len(targets)))
        else:
            report.fail("Browser-Netzwerkbibliothek fehlt - TikTok geht nicht")
    except Exception as exc:
        report.fail("yt-dlp laesst sich nicht laden: {}".format(exc))
        report.save()
        return 1

    # --- Strecke ----------------------------------------------------------
    from .core.download import download, download_preview, probe_duration
    from .core.models import DownloadRequest, Mode
    from .core.probe import pick_height, probe

    report.add("")
    report.add("Analyse, Download, Vorschau  ({})".format(TEST_URL))
    folder = Path(tempfile.mkdtemp(prefix="fevselbsttest_"))
    try:
        started = time.time()
        info = probe(TEST_URL)
        report.ok("Analyse: '{}' ({:.0f} s) in {:.1f} s".format(info.title[:50], info.duration, time.time() - started))

        height = pick_height(info, 360)
        started = time.time()
        clip = download(DownloadRequest(
            url=info.url, output_dir=folder / "clip", mode=Mode.VIDEO_AUDIO,
            height=height, start=10.0, end=13.0, prefer_h264=True,
        ))
        length = probe_duration(clip)
        verdict = abs(length - 3.0) <= 1.0
        (report.ok if verdict else report.fail)(
            "Ausschnitt 10-13 s: {} MB, Laenge {:.2f} s in {:.1f} s".format(
                round(clip.stat().st_size / 1048576, 2), length, time.time() - started)
        )

        started = time.time()
        preview = download_preview(info.url, folder / "vorschau")
        size = preview.stat().st_size / 1048576
        (report.ok if size > 0.05 else report.fail)(
            "Vorschaudatei: {:.1f} MB in {:.1f} s".format(size, time.time() - started)
        )
    except Exception as exc:
        report.fail("{}".format(exc))
        report.add(traceback.format_exc())

    report.add("")
    report.add("ERGEBNIS: {}".format("alles in Ordnung" if report.failed == 0 else "{} Fehler".format(report.failed)))
    report.save()
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
