"""Fehlertypen mit verstaendlichen deutschen Meldungen."""

from __future__ import annotations


class FevError(Exception):
    """Basis fuer alle Fehler, die der Nutzer zu sehen bekommt."""


class ProbeError(FevError):
    """Das Video konnte nicht analysiert werden."""


class DownloadError(FevError):
    """Der Download ist fehlgeschlagen."""


class CancelledError(FevError):
    """Der Nutzer hat abgebrochen."""


def humanize(raw_message: str) -> str:
    """Uebersetzt typische yt-dlp-Meldungen in Klartext."""
    text = (raw_message or "").strip()
    lowered = text.lower()

    if "[tiktok]" in lowered and any(needle in lowered for needle in (
        "unexpected response from webpage request",
        "unable to extract webpage video data",
        "unable to extract universal data",
        "unable to extract challenge data",
        "unable to solve js challenge",
    )):
        return (
            "TikTok liefert gerade keine abrufbaren Videodaten. "
            "Unter Hilfe -> Nach Aktualisierung suchen pruefen. "
            "Bei einer aelteren App den aktuellen Installer verwenden."
        )

    patterns = [
        ("is not a valid url", "Das ist kein gueltiger Link."),
        ("unsupported url", "Diese Seite wird nicht unterstuetzt."),
        ("video unavailable", "Das Video ist nicht verfuegbar."),
        ("private video", "Das Video ist privat."),
        ("members-only", "Das Video ist nur fuer Kanalmitglieder."),
        ("sign in to confirm your age", "Das Video ist altersbeschraenkt und ohne Anmeldung nicht abrufbar."),
        ("age-restricted", "Das Video ist altersbeschraenkt."),
        ("not available in your country", "Das Video ist in deinem Land gesperrt."),
        ("geo restricted", "Das Video ist in deinem Land gesperrt."),
        ("requested format is not available", "Die gewuenschte Qualitaet gibt es bei diesem Video nicht."),
        ("sign in to confirm", "Die Plattform verlangt eine Anmeldung."),
        ("requiring login", "Die Plattform verlangt fuer dieses Video eine Anmeldung."),
        ("removed by the uploader", "Das Video wurde vom Ersteller geloescht."),
        ("copyright", "Das Video wurde aus Urheberrechtsgruenden entfernt."),
        ("urlopen error", "Keine Verbindung zum Internet."),
        ("getaddrinfo failed", "Keine Verbindung zum Internet."),
        ("temporary failure in name resolution", "Keine Verbindung zum Internet."),
        ("timed out", "Zeitueberschreitung - die Seite antwortet nicht."),
        ("ffmpeg", "ffmpeg-Fehler beim Verarbeiten der Datei."),
    ]

    for needle, friendly in patterns:
        if needle in lowered:
            return friendly

    # Das ERROR:-Praefix von yt-dlp entfernen, sonst Originaltext zeigen.
    if text.lower().startswith("error:"):
        text = text[6:].strip()
    return text or "Unbekannter Fehler."
