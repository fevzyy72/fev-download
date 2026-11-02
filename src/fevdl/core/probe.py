"""Metadaten eines Videos abfragen, ohne etwas herunterzuladen."""

from __future__ import annotations

from typing import Any, Optional

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from .errors import ProbeError, humanize
from .models import Quality, VideoInfo
from .urls import web_url

# Fuer die Vorschau reicht wenig Aufloesung - Hauptsache sofort abspielbar.
PREVIEW_MAX_HEIGHT = 480


def _base_options() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        # Bei Playlists nur den ersten Eintrag aufloesen.
        "playlist_items": "1",
    }


def probe(url: str) -> VideoInfo:
    """Fragt Titel, Dauer, Vorschaubild und verfuegbare Qualitaeten ab."""
    url = (url or "").strip()
    if not url:
        raise ProbeError("Bitte zuerst einen Link einfuegen.")
    try:
        url = web_url(url)
    except ValueError as error:
        raise ProbeError(str(error)) from error

    try:
        with YoutubeDL(_base_options()) as ydl:
            info = ydl.extract_info(url, download=False)
    except YtDlpDownloadError as exc:
        raise ProbeError(humanize(str(exc))) from exc
    except Exception as exc:  # Netzwerkabbrueche, kaputte Extractors, ...
        raise ProbeError(humanize(str(exc))) from exc

    if info is None:
        raise ProbeError("Zu diesem Link wurden keine Videodaten gefunden.")

    # Playlists/Kanaele liefern 'entries' - wir nehmen den ersten echten Eintrag.
    info = _first_entry(info)

    formats = info.get("formats") or []
    return VideoInfo(
        url=info.get("webpage_url") or url,
        title=info.get("title") or "Ohne Titel",
        duration=float(info.get("duration") or 0.0),
        uploader=info.get("uploader") or info.get("channel") or "",
        thumbnail_url=info.get("thumbnail") or "",
        preview_url=_pick_preview_url(formats),
        audio_url=_pick_audio_url(formats),
        qualities=_collect_qualities(formats),
        extractor=info.get("extractor_key") or "",
        is_live=bool(info.get("is_live")),
        **_pick_dimensions(info, formats),
    )


def _first_entry(info: dict[str, Any]) -> dict[str, Any]:
    """Steigt in verschachtelte Playlist-Ergebnisse hinab bis zum Video."""
    seen = 0
    while isinstance(info, dict) and info.get("entries") is not None and seen < 5:
        entries = [entry for entry in (info.get("entries") or []) if entry]
        if not entries:
            raise ProbeError("Die Playlist enthaelt kein abspielbares Video.")
        info = entries[0]
        seen += 1
    return info


def _collect_qualities(formats: list[dict[str, Any]]) -> list[Quality]:
    """Sammelt die real verfuegbaren Aufloesungen, hoechste zuerst."""
    best_fps: dict[int, int] = {}

    for fmt in formats:
        if fmt.get("vcodec") in (None, "none"):
            continue
        height = fmt.get("height")
        if not height:
            continue
        height = int(height)
        fps = int(fmt.get("fps") or 0)
        # TikTok nennt oft keine Bildrate. Auch ohne FPS ist das ein Video;
        # vorher fiel 0 > 0 durch und die GUI wechselte faelschlich zu Nur Ton.
        if height not in best_fps or fps > best_fps[height]:
            best_fps[height] = fps

    qualities = [
        Quality(height=height, fps=fps or None)
        for height, fps in best_fps.items()
    ]
    qualities.sort(key=lambda quality: quality.height, reverse=True)
    return qualities


def _pick_preview_url(formats: list[dict[str, Any]]) -> str:
    """
    Sucht einen Stream, der sich sofort abspielen laesst.

    Gebraucht wird ein Format mit Bild UND Ton in einer Datei (progressiv) ueber
    normales HTTPS - getrennte Spuren oder HLS kann der Player nicht direkt
    abspielen. Kleine Aufloesung wird bevorzugt, damit die Vorschau schnell
    startet.
    """
    candidates = []

    for fmt in formats:
        if fmt.get("vcodec") in (None, "none"):
            continue
        if fmt.get("acodec") in (None, "none"):
            continue
        if not fmt.get("url"):
            continue
        protocol = (fmt.get("protocol") or "").lower()
        if protocol not in ("https", "http"):
            continue
        candidates.append(fmt)

    if not candidates:
        return ""

    def sort_key(fmt: dict[str, Any]) -> tuple:
        height = int(fmt.get("height") or 0)
        # Erst alles bis 480p (aufsteigend nach Groesse), danach der Rest.
        within_budget = height <= PREVIEW_MAX_HEIGHT
        mp4_bonus = 0 if (fmt.get("ext") == "mp4") else 1
        return (0 if within_budget else 1, mp4_bonus, -height if within_budget else height)

    candidates.sort(key=sort_key)
    return candidates[0].get("url") or ""


def _pick_dimensions(info: dict[str, Any], formats: list[dict[str, Any]]) -> dict[str, int]:
    """
    Ermittelt Breite und Hoehe der Quelle.

    Wird gebraucht, um Hochformat zu erkennen - ein TikTok-Video in einem
    breiten Fenster waere sonst winzig zwischen zwei schwarzen Balken.
    """
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)

    if width <= 0 or height <= 0:
        # Manche Seiten geben die Masse nur beim einzelnen Format an.
        for fmt in sorted(
            (f for f in formats if f.get("height") and f.get("width")),
            key=lambda f: f.get("height") or 0,
            reverse=True,
        ):
            width = int(fmt.get("width") or 0)
            height = int(fmt.get("height") or 0)
            break

    return {"width": max(0, width), "height": max(0, height)}


def _pick_audio_url(formats: list[dict[str, Any]]) -> str:
    """
    Sucht eine reine Tonspur - moeglichst klein, denn sie wird nur zum
    Zeichnen der Wellenform vollstaendig gelesen.
    """
    candidates = []

    for fmt in formats:
        if fmt.get("acodec") in (None, "none"):
            continue
        if fmt.get("vcodec") not in (None, "none"):
            continue  # Formate mit Bild waeren unnoetig gross
        if not fmt.get("url"):
            continue
        if (fmt.get("protocol") or "").lower() not in ("https", "http"):
            continue
        candidates.append(fmt)

    if not candidates:
        return ""

    # Niedrigste Datenrate genuegt vollauf fuer eine Wellenform.
    candidates.sort(key=lambda fmt: fmt.get("abr") or fmt.get("tbr") or 9999)
    return candidates[0].get("url") or ""


def pick_height(info: VideoInfo, wanted: Optional[int]) -> Optional[int]:
    """
    Waehlt die passende Hoehe: die gewuenschte, sonst die naechstkleinere.

    So fuehrt die Auswahl '1080p' bei einem Video, das nur 720p bietet, nicht zu
    einem Fehler, sondern liefert 720p.
    """
    if not info.qualities:
        return None
    if wanted is None:
        return info.qualities[0].height
    for quality in info.qualities:  # absteigend sortiert
        if quality.height <= wanted:
            return quality.height
    return info.qualities[-1].height
