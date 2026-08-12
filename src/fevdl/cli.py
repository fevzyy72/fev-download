"""
Kommandozeile zum Testen des Download-Motors - ohne Oberflaeche.

    python -m fevdl.cli probe <link>
    python -m fevdl.cli get <link> [--mode video_audio|audio_only|video_only]
                                   [--height 1080] [--start 0:30] [--end 1:00]
                                   [--out ORDNER]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import paths
from .core.download import download, probe_duration
from .core.errors import FevError
from .core.models import DownloadRequest, Mode, format_timecode, parse_timecode
from .core.probe import pick_height, probe


def _cmd_probe(args: argparse.Namespace) -> int:
    info = probe(args.url)
    print(f"Titel     : {info.title}")
    print(f"Kanal     : {info.uploader or '-'}")
    print(f"Dauer     : {info.duration_text} ({info.duration:.0f} s)")
    print(f"Plattform : {info.extractor or '-'}")
    print(f"Live      : {'ja' if info.is_live else 'nein'}")
    print(f"Thumbnail : {'vorhanden' if info.thumbnail_url else 'keins'}")
    print(f"Vorschau  : {'abspielbar' if info.preview_url else 'nicht verfuegbar'}")
    if info.qualities:
        labels = ", ".join(quality.label for quality in info.qualities)
        print(f"Qualitaet : {labels}")
    else:
        print("Qualitaet : (kein Video - reine Tonquelle?)")
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    info = probe(args.url)
    print(f"Titel: {info.title}  ({info.duration_text})")

    mode = Mode(args.mode)
    height = pick_height(info, args.height) if mode.needs_video else None
    if mode.needs_video and args.height and height != args.height:
        print(f"Hinweis: {args.height}p gibt es nicht - nehme {height}p.")

    start = parse_timecode(args.start) if args.start else None
    end = parse_timecode(args.end) if args.end else None

    request = DownloadRequest(
        url=info.url,
        output_dir=Path(args.out) if args.out else paths.DEFAULT_DOWNLOAD_DIR,
        mode=mode,
        height=height,
        start=start,
        end=end,
        prefer_h264=not args.allow_any_codec,
    )

    last_line = {"text": ""}

    def on_progress(progress) -> None:
        if progress.status == "downloading":
            bits = [f"{progress.percent:5.1f}%"]
            if progress.speed_text:
                bits.append(progress.speed_text)
            if progress.eta_text:
                bits.append(progress.eta_text)
            text = "  ".join(bits)
        else:
            text = progress.message
        if text != last_line["text"]:
            print(f"\r{text:<60}", end="", flush=True)
            last_line["text"] = text

    result = download(request, on_progress=on_progress)
    print()

    size_mb = result.stat().st_size / (1024 * 1024)
    print(f"Datei : {result}")
    print(f"Groesse: {size_mb:.1f} MB")

    actual = probe_duration(result)
    print(f"Laenge: {format_timecode(actual)} ({actual:.2f} s)")

    if request.is_trimmed:
        expected = (end or info.duration) - (start or 0.0)
        difference = abs(actual - expected)
        verdict = "OK" if difference <= 1.0 else "ABWEICHUNG"
        print(f"Erwartet: {format_timecode(expected)} ({expected:.2f} s) -> {verdict} (Differenz {difference:.2f} s)")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fevdl", description="FevDownloader - Testwerkzeug")
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe_parser = subparsers.add_parser("probe", help="Metadaten anzeigen")
    probe_parser.add_argument("url")
    probe_parser.set_defaults(func=_cmd_probe)

    get_parser = subparsers.add_parser("get", help="Herunterladen")
    get_parser.add_argument("url")
    get_parser.add_argument("--mode", default=Mode.VIDEO_AUDIO.value,
                            choices=[mode.value for mode in Mode])
    get_parser.add_argument("--height", type=int, default=None)
    get_parser.add_argument("--start", default=None, help="z.B. 0:30")
    get_parser.add_argument("--end", default=None, help="z.B. 1:00")
    get_parser.add_argument("--out", default=None)
    get_parser.add_argument("--allow-any-codec", action="store_true",
                            help="VP9/AV1 zulassen (Resolve kann diese oft nicht oeffnen)")
    get_parser.set_defaults(func=_cmd_get)

    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except FevError as exc:
        print(f"\nFehler: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
