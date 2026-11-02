"""Holt eine neuere yt-dlp-Fassung nach.

Warum das noetig ist: Die Plattformen aendern regelmaessig etwas an ihren
Seiten, yt-dlp zieht meist binnen Tagen nach. Im fertig gepackten Programm ist
die Fassung aber auf den Stand des Bauens eingefroren. Ohne diesen Weg braeuchte
jede Anpassung einen neuen Installer fuer alle.

Der Trick ist unspektakulaer: yt-dlp ist reines Python, ohne uebersetzte
Bestandteile. Ein Rad (.whl) von PyPI ist ein gewoehnliches ZIP-Archiv - es
genuegt, den Inhalt in einen beschreibbaren Ordner zu entpacken und diesen im
Suchpfad vor das mitgelieferte Paket zu stellen (siehe
paths.activate_ytdlp_update).

Bewusst ohne pip: Im gepackten Zustand gibt es keines, und selbst wenn - es
wuerde in den Installationsordner schreiben wollen.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request

from .. import paths
from .transport import open_https

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
TIMEOUT = 30
# PyPI beantwortet Anfragen ohne Kennung mit 403.
USER_AGENT = "FevDownload"


@dataclass(frozen=True)
class UpdateResult:
    """Ergebnis eines Aktualisierungsversuchs."""

    changed: bool
    version: str
    message: str


def _fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with open_https(request, TIMEOUT, frozenset({"pypi.org", "files.pythonhosted.org"})) as response:
        return response.read()


def latest_version() -> tuple[str, str, str]:
    """
    Fragt PyPI nach der neuesten Fassung.

    Rueckgabe: (Fassung, Adresse des Rads, SHA-256 aus den PyPI-Metadaten).
    """
    data = json.loads(_fetch(PYPI_URL).decode("utf-8"))
    version = data["info"]["version"]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version):
        raise RuntimeError("Auf PyPI liegt keine stabile yt-dlp-Fassung bereit.")

    for entry in data["urls"]:
        if entry.get("packagetype") == "bdist_wheel" and not entry.get("yanked"):
            digest = entry.get("digests", {}).get("sha256", "")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                raise RuntimeError("Die PyPI-Pruefsumme fuer yt-dlp fehlt oder ist unlesbar.")
            return version, entry["url"], digest.lower()

    raise RuntimeError("Auf PyPI liegt kein fertiges Paket fuer yt-dlp bereit.")


def current_version() -> str:
    """
    Die Fassung, die gerade tatsaechlich gilt.

    Wird direkt beim geladenen Paket erfragt. Eine gerade erst nachgeladene
    Fassung gilt noch nicht im laufenden Prozess.
    """
    try:
        from yt_dlp.version import __version__ as bundled

        return bundled
    except Exception:
        return "unbekannt"


def _extract_wheel(wheel: bytes, target: Path) -> None:
    """
    Entpackt das Rad nach target - erst danach wird das Alte ersetzt.

    Ueber einen Nebenordner, damit ein Abbruch mittendrin nicht eine halb
    entpackte und damit unbrauchbare Fassung hinterlaesst.
    """
    staging = target.with_name(target.name + ".neu")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(wheel)) as bundle:
            # Nur das Paket selbst; die Metadaten-Ordner (.dist-info) braucht
            # niemand, wenn nicht ueber pip installiert wird.
            members = [m for m in bundle.infolist() if m.filename.startswith("yt_dlp/")]
            for member in members:
                name = member.filename
                # ZIP-Namen sind POSIX-Pfade. Unter Windows waeren ausserdem
                # Rueckstriche, Laufwerke und NTFS-Datenstroeme gefaehrlich.
                if ("\\" in name or ":" in name or "\x00" in name
                        or any(p in (".", "..") or p.endswith((".", " "))
                               for p in name.rstrip("/").split("/"))
                        or (member.external_attr >> 16) & 0o170000 == 0o120000):
                    raise RuntimeError("Das yt-dlp-Paket enthaelt einen ungueltigen Dateipfad.")
            for member in members:
                bundle.extract(member, staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if not (staging / "yt_dlp" / "version.py").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError("Das geladene Paket sieht nicht wie yt-dlp aus.")

    previous = target.with_name(target.name + ".alt")
    shutil.rmtree(previous, ignore_errors=True)
    if target.exists():
        target.rename(previous)
    staging.rename(target)
    shutil.rmtree(previous, ignore_errors=True)


def update_ytdlp() -> UpdateResult:
    """
    Holt die neueste yt-dlp-Fassung, falls es eine neuere gibt.

    Die neue Fassung wirkt erst nach einem Neustart des Programms: yt_dlp ist
    zu diesem Zeitpunkt laengst eingebunden und laesst sich nicht im laufenden
    Betrieb austauschen.
    """
    running = current_version()
    newest, wheel_url, expected_hash = latest_version()

    if paths.version_key(newest) <= paths.version_key(running):
        return UpdateResult(
            changed=False,
            version=running,
            message="Bereits auf dem neuesten Stand ({}).".format(running),
        )

    # Schon geholt, wartet aber auf den Neustart: nicht noch einmal laden.
    waiting = paths.installed_ytdlp_version()
    if waiting is not None and paths.version_key(waiting) >= paths.version_key(newest):
        return UpdateResult(
            changed=False,
            version=waiting,
            message=(
                "Die neueste Fassung ({}) ist bereits geladen.\n"
                "Wirksam wird sie beim naechsten Start von Fev Download.".format(waiting)
            ),
        )

    wheel = _fetch(wheel_url)
    if hashlib.sha256(wheel).hexdigest() != expected_hash:
        raise RuntimeError("Die Pruefsumme des yt-dlp-Pakets stimmt nicht.")
    _extract_wheel(wheel, paths.YTDLP_DIR)

    return UpdateResult(
        changed=True,
        version=newest,
        message=(
            "Aktualisiert: {} statt {}.\n"
            "Wirksam wird das beim naechsten Start von Fev Download.".format(
                newest, running
            )
        ),
    )


# ---------------------------------------------------------------------------
# Stille Pruefung beim Start
# ---------------------------------------------------------------------------

# Einmal am Tag genuegt: stabile Fassungen erscheinen etwa monatlich. Etwas unter
# 24 Stunden, damit ein Start zur gleichen Uhrzeit am Folgetag nicht knapp
# durchfaellt.
CHECK_INTERVAL_SECONDS = 20 * 3600


def due_for_check(now: float | None = None) -> bool:
    """True, wenn die letzte Suche lange genug her ist (oder es keine gab)."""
    moment = time.time() if now is None else now
    try:
        data = json.loads(paths.UPDATE_CHECK_FILE.read_text(encoding="utf-8-sig"))
        last = float(data.get("ytdlp_checked", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return True
    # Eine Uhrzeit in der Zukunft (Uhr umgestellt) zaehlt als abgelaufen.
    return last > moment or moment - last >= CHECK_INTERVAL_SECONDS


def mark_checked(now: float | None = None) -> None:
    """Haelt fest, dass gerade gesucht wurde. Darf nie den Start stoeren."""
    try:
        paths.ensure_dir(paths.UPDATE_CHECK_FILE.parent)
        paths.UPDATE_CHECK_FILE.write_text(
            json.dumps({"ytdlp_checked": time.time() if now is None else now}),
            encoding="utf-8",
        )
    except OSError:
        pass


def auto_update_ytdlp() -> UpdateResult | None:
    """
    Die Suche beim Start: still, hoechstens einmal am Tag, nie mit Fehlermeldung.

    Rueckgabe: das Ergebnis, wenn gesucht wurde - sonst None. Schlaegt die Suche
    fehl (kein Netz, PyPI nicht erreichbar), wird NICHT als erledigt vermerkt:
    Beim naechsten Start wird erneut versucht, statt einen Tag zu verlieren.
    """
    if not due_for_check():
        return None
    try:
        result = update_ytdlp()
    except Exception:
        return None
    mark_checked()
    return result
