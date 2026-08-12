"""Vorschaubilder fuer die Bibliothek.

Zu jeder Mediendatei wird ein kleines Standbild erzeugt und abgelegt, damit man
in der Liste sieht, worum es geht, statt nur Dateinamen zu lesen.

Zwei Entscheidungen dahinter:

* **Zwischenspeicher statt Nebendateien.** Die Bilder liegen unter
  ``%LOCALAPPDATA%\\FevDownloader\\thumbs``. Im Download-Ordner haetten sie
  nichts verloren - dort soll nur liegen, was der Nutzer selbst geladen hat.
* **Schluessel aus Pfad, Zeitstempel und Groesse.** Aendert sich die Datei,
  aendert sich der Schluessel und das Bild wird neu erzeugt. Ein blosser Pfad
  wuerde ein altes Bild einer neuen Datei zuordnen.

Ein Fehlschlag wird als leere ``.none``-Marke vermerkt. Ohne die wuerde bei
jedem Blick in die Bibliothek erneut ffmpeg auf eine Datei losgelassen, die
sowieso kein Bild hergibt.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional

from .. import paths

# Breit genug fuer eine scharfe Darstellung, klein genug, um hunderte davon
# ohne Nachdenken im Speicher zu halten.
THUMB_WIDTH = 176
_TIMEOUT = 30
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def cache_name(path: Path) -> Optional[str]:
    """Eindeutiger Name des Vorschaubildes - None, wenn die Datei fehlt."""
    try:
        stat = path.stat()
    except OSError:
        return None
    key = f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
    return hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:16]


def ensure_thumbnail(path: Path, kind: str = "video") -> Optional[Path]:
    """
    Gibt das Vorschaubild zurueck und erzeugt es beim ersten Mal.

    Laeuft in einem Hintergrund-Thread: ffmpeg braucht je Datei einen
    Sekundenbruchteil, bei einem vollen Ordner summiert sich das.
    """
    if not paths.ffmpeg_available():
        return None

    name = cache_name(path)
    if name is None:
        return None

    target = paths.THUMB_CACHE_DIR / f"{name}.jpg"
    if target.is_file() and target.stat().st_size > 0:
        return target

    marker = paths.THUMB_CACHE_DIR / f"{name}.none"
    if marker.is_file():
        return None

    paths.ensure_dir(paths.THUMB_CACHE_DIR)

    if kind == "audio":
        made = _grab_cover(path, target)
    else:
        made = _grab_frame(path, target)

    if made:
        return target

    try:
        marker.write_bytes(b"")
    except OSError:
        pass
    return None


def _grab_frame(source: Path, target: Path) -> bool:
    """
    Holt ein aussagekraeftiges Einzelbild aus einem Video.

    Der Filter 'thumbnail' sichtet die ersten Sekunden und waehlt daraus das
    typischste Bild. Ein fester Zeitpunkt waere die naheliegende Loesung,
    trifft aber regelmaessig ein schwarzes Bild oder einen Vorspann.
    """
    return _run_ffmpeg(
        [
            "-i", str(source),
            "-vf", f"thumbnail=240,scale={THUMB_WIDTH}:-2",
            "-frames:v", "1",
            "-q:v", "4",
        ],
        target,
    )


def _grab_cover(source: Path, target: Path) -> bool:
    """Holt das eingebettete Titelbild einer Tonspur, falls vorhanden."""
    return _run_ffmpeg(
        [
            "-i", str(source),
            "-an",
            "-vf", f"scale={THUMB_WIDTH}:-2",
            "-frames:v", "1",
            "-q:v", "4",
        ],
        target,
    )


def _run_ffmpeg(arguments: list[str], target: Path) -> bool:
    command = [str(paths.FFMPEG_EXE), "-y", "-loglevel", "error", *arguments, str(target)]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_TIMEOUT,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        target.unlink(missing_ok=True)
        return False

    if completed.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        return False
    return True
