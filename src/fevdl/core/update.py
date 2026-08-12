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

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from .. import paths

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
    with urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def latest_version() -> tuple[str, str]:
    """
    Fragt PyPI nach der neuesten Fassung.

    Rueckgabe: (Fassung, Adresse des Rads)
    """
    data = json.loads(_fetch(PYPI_URL).decode("utf-8"))
    version = data["info"]["version"]

    for entry in data["urls"]:
        if entry.get("packagetype") == "bdist_wheel":
            return version, entry["url"]

    raise RuntimeError("Auf PyPI liegt kein fertiges Paket fuer yt-dlp bereit.")


def current_version() -> str:
    """
    Die Fassung, die gerade tatsaechlich gilt.

    Bevorzugt die nachgeladene; sonst die mitgelieferte, direkt beim Paket
    erfragt.
    """
    updated = paths.installed_ytdlp_version()
    if updated:
        return updated
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

    archive = target.with_name(target.name + ".whl")
    archive.write_bytes(wheel)
    try:
        with zipfile.ZipFile(archive) as bundle:
            # Nur das Paket selbst; die Metadaten-Ordner (.dist-info) braucht
            # niemand, wenn nicht ueber pip installiert wird.
            for member in bundle.namelist():
                if member.startswith("yt_dlp/"):
                    bundle.extract(member, staging)
    finally:
        archive.unlink(missing_ok=True)

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
    newest, wheel_url = latest_version()

    if newest == running:
        return UpdateResult(
            changed=False,
            version=running,
            message="Bereits auf dem neuesten Stand ({}).".format(running),
        )

    _extract_wheel(_fetch(wheel_url), paths.YTDLP_DIR)

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
