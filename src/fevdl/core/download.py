"""Der eigentliche Download - mit Qualitaetswahl, Modus und Ausschnitt."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import download_range_func

from .. import paths
from .errors import CancelledError, DownloadError, humanize
from .models import DownloadRequest, Mode, Progress
from .urls import web_url
from .ytdlp_options import shared_options

ProgressCallback = Callable[[Progress], None]
CancelCheck = Callable[[], bool]

# Codecs, die DaVinci Resolve zuverlaessig einliest.
RESOLVE_SAFE_VIDEO_CODECS = ("h264", "avc1", "mpeg4", "prores", "dnxhd")

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Formatwahl der Ausweich-Vorschau, in dieser Reihenfolge:
#
#   1. Eine fertige Datei mit Bild UND Ton bis 540p - so liefern TikTok und
#      viele andere Seiten ihre Videos. 'best' meint bei yt-dlp ausdruecklich
#      eine solche Datei, nicht "das beste Format".
#   2. Getrennte Bild- und Tonspur bis 480p, die ffmpeg zusammensetzt. YouTube
#      bietet fertige Dateien mit Ton nicht mehr an (gemessen an drei Videos,
#      mit alter wie neuer yt-dlp-Fassung); ohne diese Stufe scheiterte die
#      Vorschau dort mit "Requested format is not available".
#   3. Zuletzt irgendeine fertige Datei, auch ueber 540p.
#
# avc1 + m4a wird bevorzugt, weil das ohne Umcodieren in eine mp4 passt, die der
# Player zuverlaessig abspielt.
PREVIEW_FORMAT = (
    "best[height<=540][ext=mp4]/best[height<=540]"
    "/bv*[height<=480][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=480]+ba"
    "/best[ext=mp4]/best"
)


def download(
    request: DownloadRequest,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCheck] = None,
) -> Path:
    """
    Laedt das Video gemaess Auftrag und gibt den Pfad der fertigen Datei zurueck.

    Ist ein Ausschnitt gesetzt, wird er direkt beim Laden geschnitten - bei einem
    zweistuendigen Video fuer 30 Sekunden Ausschnitt wandert also nur ein
    Bruchteil durch die Leitung.
    """
    _check_download_url(request.url)
    if not paths.ffmpeg_available():
        raise DownloadError(
            "ffmpeg fehlt. Bitte setup.ps1 ausfuehren, damit es nach bin/ geladen wird."
        )

    _announce_ffmpeg_location()
    paths.ensure_dir(request.output_dir)
    report = on_progress or (lambda _progress: None)

    options = _build_options(request, report, should_cancel)
    info = _run_with_retries(request, options, report, should_cancel)

    result_path = _extract_result_path(info)
    if result_path is None or not result_path.is_file():
        raise DownloadError("Der Download lief durch, aber die Datei ist nicht auffindbar.")

    if request.prefer_h264 and request.mode.needs_video:
        report(Progress(status="processing", percent=100.0, message="Pruefe Codec fuer Resolve..."))
        result_path = ensure_resolve_compatible(result_path, report, should_cancel)

    report(Progress(status="finished", percent=100.0, message=f"Fertig: {result_path.name}"))
    return result_path


def download_preview(
    url: str,
    target_dir: Path,
    should_cancel: Optional[CancelCheck] = None,
) -> Path:
    """
    Laedt eine kleine, sofort abspielbare Fassung fuer die Vorschau.

    Noetig fuer Seiten wie TikTok: Deren Stream-Adressen lassen sich nur mit
    bestimmten Kopfdaten abrufen, die der Player nicht mitschicken kann. Statt
    dem Nutzer eine Fehlermeldung hinzuwerfen, holen wir die Datei eben selbst.

    Bewusst ohne Ausschnitt und in niedriger Qualitaet - sie dient nur dem
    Anschauen, geladen wird spaeter ohnehin neu.
    """
    url = _check_download_url(url)
    if not paths.ffmpeg_available():
        raise DownloadError("ffmpeg fehlt. Bitte setup.ps1 ausfuehren.")
    _announce_ffmpeg_location()
    paths.ensure_dir(target_dir)

    options: dict[str, Any] = {
        **shared_options(),
        "format": PREVIEW_FORMAT,
        "outtmpl": str(target_dir / "vorschau.%(ext)s"),
        "ffmpeg_location": str(paths.BIN_DIR),
        "windowsfilenames": True,
        "noplaylist": True,
        "playlist_items": "1",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "overwrites": True,
        "retries": 3,
    }

    if should_cancel is not None:
        def hook(_data: dict[str, Any]) -> None:
            if should_cancel():
                raise CancelledError("Abgebrochen.")

        options["progress_hooks"] = [hook]

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except CancelledError:
        raise
    except Exception as exc:
        raise DownloadError(humanize(str(exc))) from exc

    result = _extract_result_path(info)
    if result is None or not result.is_file():
        raise DownloadError("Die Vorschau liess sich nicht laden.")
    return result


def _check_download_url(url: str) -> str:
    try:
        return web_url(url)
    except ValueError as error:
        raise DownloadError(str(error)) from error


def _run_with_retries(
    request: DownloadRequest,
    options: dict[str, Any],
    report: ProgressCallback,
    should_cancel: Optional[CancelCheck],
    attempts: int = 3,
) -> Any:
    """
    Fuehrt den Download aus und wiederholt ihn bei vorruebergehenden Stoerungen.

    Beim Schneiden laedt ffmpeg direkt vom Server der Plattform. Bricht diese
    Verbindung kurz weg, stirbt ffmpeg mit einem Absturzcode - ein erneuter
    Versuch mit frischer Adresse laeuft dann meist problemlos durch. yt-dlps
    eigenes 'retries' greift hier nicht, weil es nur den internen Lader abdeckt.
    """
    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        if should_cancel is not None and should_cancel():
            raise CancelledError("Abgebrochen.")
        try:
            with YoutubeDL(options) as ydl:
                return ydl.extract_info(request.url, download=True)
        except CancelledError:
            raise
        except Exception as exc:
            message = humanize(str(exc))
            if not _is_retryable(str(exc)) or attempt == attempts:
                raise DownloadError(message) from exc
            last_error = exc
            report(
                Progress(
                    status="processing",
                    message=f"Verbindung gestoert - neuer Versuch ({attempt + 1}/{attempts})...",
                )
            )
            time.sleep(2 * attempt)

    raise DownloadError(humanize(str(last_error)))


def _is_retryable(raw_message: str) -> bool:
    """Unterscheidet Stoerungen von endgueltigen Absagen wie 'Video privat'."""
    lowered = raw_message.lower()
    permanent = (
        "unavailable", "private", "members-only", "age", "removed",
        "copyright", "not a valid url", "unsupported url",
        "requested format is not available",
    )
    if any(word in lowered for word in permanent):
        return False

    transient = (
        "ffmpeg exited with code", "http error 5", "timed out", "timeout",
        "connection", "incomplete", "read error", "unable to download",
    )
    return any(word in lowered for word in transient)


def _announce_ffmpeg_location() -> None:
    """
    Macht unser bin/fmpeg fuer yt-dlp ueberall bekannt.

    Die Option 'ffmpeg_location' allein genuegt nicht: Bei der Pruefung, ob ein
    Video teilweise geladen werden kann, ruft yt-dlp FFmpegFD.available() ohne
    Zugriff auf die eigenen Einstellungen auf und sucht dann nur im PATH. Fuer
    genau diesen Fall gibt es die ContextVar - yt-dlp setzt sie in seinem eigenen
    Kommandozeilenprogramm ebenso (siehe yt-dlp Issue #2191).

    Wichtig ist ausserdem, dass das frueh genug passiert: das Ergebnis der
    Suche landet in einem klassenweiten Zwischenspeicher. Lief die Pruefung
    einmal erfolglos, bliebe 'nicht vorhanden' sonst haengen.

    Die ContextVar gilt pro Thread, darum wird sie hier bei jedem Download neu
    gesetzt und nicht einmalig beim Programmstart.
    """
    FFmpegPostProcessor._ffmpeg_location.set(str(paths.BIN_DIR))
    paths.activate_bin_path()


# ---------------------------------------------------------------------------
# Optionen fuer yt-dlp
# ---------------------------------------------------------------------------

def _build_options(
    request: DownloadRequest,
    report: ProgressCallback,
    should_cancel: Optional[CancelCheck],
) -> dict[str, Any]:
    options: dict[str, Any] = {
        **shared_options(),
        "format": _format_selector(request),
        "outtmpl": str(request.output_dir / _output_template(request)),
        "ffmpeg_location": str(paths.BIN_DIR),
        "windowsfilenames": True,
        "noplaylist": True,
        "playlist_items": "1",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [_make_progress_hook(report, should_cancel)],
        "postprocessor_hooks": [_make_postprocessor_hook(report)],
        "retries": 5,
        "fragment_retries": 5,
    }

    if request.mode.needs_video:
        options["merge_output_format"] = "mp4"

    if request.mode is Mode.AUDIO_ONLY:
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "0",
            }
        ]

    if request.is_trimmed:
        start = request.start or 0.0
        end = request.end  # None = bis zum Ende
        options["download_ranges"] = download_range_func(None, [(start, end)])
        # Ohne dieses Flag schneidet ffmpeg nur an Keyframes - der Ausschnitt
        # waere dann bis zu mehrere Sekunden daneben.
        options["force_keyframes_at_cuts"] = True

    return options


def _output_template(request: DownloadRequest) -> str:
    """
    Baut das Namensmuster fuer die Zieldatei.

    Modus, Qualitaet und Ausschnitt gehoeren zwingend in den Namen: Sonst
    bekaemen '720p komplett' und '480p ohne Ton' denselben Dateinamen, und
    yt-dlp wuerde die bereits vorhandene Datei stillschweigend wiederverwenden,
    statt neu zu laden.
    """
    parts: list[str] = []

    if request.mode is Mode.AUDIO_ONLY:
        parts.append("Ton")
    else:
        if request.height:
            parts.append(f"{request.height}p")
        if request.mode is Mode.VIDEO_ONLY:
            parts.append("ohne Ton")

    if request.is_trimmed:
        start = int(request.start or 0)
        if request.end:
            parts.append(f"{start}-{int(request.end)}s")
        else:
            parts.append(f"ab {start}s")

    suffix = f" ({', '.join(parts)})" if parts else ""
    return f"%(title).70s [%(id)s]{suffix}.%(ext)s"


def _format_selector(request: DownloadRequest) -> str:
    """
    Baut den Formatausdruck fuer yt-dlp.

    H.264 (avc1) wird bewusst zuerst versucht: YouTube liefert ab 1440p sonst
    VP9 oder AV1 aus, was Resolve nicht oeffnen kann. Erst wenn es das nicht
    gibt, greifen wir auf das beste verfuegbare Format zurueck.
    """
    if request.mode is Mode.AUDIO_ONLY:
        return "bestaudio/best"

    height_filter = f"[height<={request.height}]" if request.height else ""

    if request.mode is Mode.VIDEO_ONLY:
        return (
            f"bestvideo{height_filter}[vcodec^=avc1]/"
            f"bestvideo{height_filter}/"
            f"best{height_filter}"
        )

    return (
        f"bestvideo{height_filter}[vcodec^=avc1]+bestaudio[ext=m4a]/"
        f"bestvideo{height_filter}[vcodec^=avc1]+bestaudio/"
        f"bestvideo{height_filter}+bestaudio/"
        f"best{height_filter}/best"
    )


# ---------------------------------------------------------------------------
# Fortschritt
# ---------------------------------------------------------------------------

def _make_progress_hook(
    report: ProgressCallback,
    should_cancel: Optional[CancelCheck],
) -> Callable[[dict[str, Any]], None]:
    def hook(data: dict[str, Any]) -> None:
        if should_cancel is not None and should_cancel():
            raise CancelledError("Abgebrochen.")

        status = data.get("status")
        if status == "downloading":
            downloaded = int(data.get("downloaded_bytes") or 0)
            total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            percent = (downloaded / total * 100.0) if total else 0.0
            report(
                Progress(
                    status="downloading",
                    percent=percent,
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    speed=data.get("speed"),
                    eta=data.get("eta"),
                    message="Lade herunter...",
                )
            )
        elif status == "finished":
            report(
                Progress(
                    status="processing",
                    percent=100.0,
                    message="Download fertig, verarbeite...",
                )
            )

    return hook


def _make_postprocessor_hook(report: ProgressCallback) -> Callable[[dict[str, Any]], None]:
    labels = {
        "Merger": "Bild und Ton werden zusammengefuegt...",
        "FFmpegExtractAudio": "Tonspur wird herausgeloest...",
        "FFmpegVideoRemuxer": "Datei wird umgepackt...",
    }

    def hook(data: dict[str, Any]) -> None:
        if data.get("status") != "started":
            return
        name = data.get("postprocessor") or ""
        report(
            Progress(
                status="processing",
                percent=100.0,
                message=labels.get(name, "Wird verarbeitet..."),
            )
        )

    return hook


def _extract_result_path(info: Any) -> Optional[Path]:
    """Holt den Pfad der fertigen Datei aus dem yt-dlp-Ergebnis."""
    if not isinstance(info, dict):
        return None

    entries = info.get("entries")
    if entries:
        info = next((entry for entry in entries if entry), info)

    requested = info.get("requested_downloads") or []
    for item in requested:
        filepath = item.get("filepath") or item.get("_filename")
        if filepath:
            return Path(filepath)

    filepath = info.get("filepath") or info.get("_filename")
    return Path(filepath) if filepath else None


# ---------------------------------------------------------------------------
# Resolve-Kompatibilitaet
# ---------------------------------------------------------------------------

def probe_video_codec(path: Path) -> str:
    """Liest den Videocodec einer Datei mit ffprobe aus."""
    command = [
        str(paths.FFPROBE_EXE),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name",
        "-of", "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=_NO_WINDOW,
        )
        streams = json.loads(completed.stdout or "{}").get("streams") or []
        return (streams[0].get("codec_name") or "").lower() if streams else ""
    except Exception:
        return ""


def probe_duration(path: Path) -> float:
    """Laenge einer Datei in Sekunden - fuer die Kontrolle des Ausschnitts."""
    command = [
        str(paths.FFPROBE_EXE),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=_NO_WINDOW,
        )
        fmt = json.loads(completed.stdout or "{}").get("format") or {}
        return float(fmt.get("duration") or 0.0)
    except Exception:
        return 0.0


def ensure_resolve_compatible(
    path: Path,
    report: ProgressCallback,
    should_cancel: Optional[CancelCheck] = None,
) -> Path:
    """
    Wandelt die Datei nach H.264/mp4 um, falls Resolve sie sonst nicht oeffnen kann.

    Betrifft in der Praxis VP9 und AV1, die YouTube ab 1440p ausliefert. Bei
    bereits passendem Codec passiert nichts.
    """
    codec = probe_video_codec(path)
    if not codec or codec.startswith(RESOLVE_SAFE_VIDEO_CODECS):
        return path

    target = path.with_name(f"{path.stem}_h264.mp4")
    report(
        Progress(
            status="processing",
            percent=100.0,
            message=f"Wandle {codec.upper()} nach H.264 um (kann dauern)...",
        )
    )

    command = [
        str(paths.FFMPEG_EXE),
        "-y",
        "-i", str(path),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        str(target),
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_NO_WINDOW,
    )
    try:
        while process.poll() is None:
            if should_cancel is not None and should_cancel():
                process.terminate()
                raise CancelledError("Abgebrochen.")
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                continue
    except CancelledError:
        target.unlink(missing_ok=True)
        raise

    if process.returncode != 0 or not target.is_file():
        target.unlink(missing_ok=True)
        # Lieber die Originaldatei liefern als gar nichts.
        return path

    path.unlink(missing_ok=True)
    return target
