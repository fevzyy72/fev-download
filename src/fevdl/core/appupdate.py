"""
Aktualisiert die App selbst - ueber die Releases auf GitHub.

Der Weg: Wer eine neue Fassung veroeffentlicht, laedt den fertigen Installer
(FevDownloadSetup.exe) als Release hoch. Die App fragt dort nach der neuesten
Fassung, laedt den Installer, startet ihn und beendet sich; der Installer legt
sich still ueber die alte Fassung und startet die App wieder (siehe
installer/FevDownload.iss, Flag 'skipifnotsilent').

Warum Releases und nicht der Quelltext des Repos: Wer die App bekommt, hat kein
Python und keine Entwicklungsumgebung - nur die installierte .exe.

Das hier ist von yt-dlp getrennt (core/update.py): yt-dlp kommt von PyPI und
aendert sich oft und klein, die App selbst nur, wenn jemand sie aendert.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .. import paths

GITHUB_REPO = "fevzyy72/fev-download"
RELEASE_API = "https://api.github.com/repos/{}/releases/latest".format(GITHUB_REPO)
RELEASES_PAGE = "https://github.com/{}/releases/latest".format(GITHUB_REPO)
# Der Installer wird nur von hier geladen - sonst koennte ein manipuliertes
# Release-Feld die App dazu bringen, irgendeine Datei zu starten.
DOWNLOAD_PREFIX = "https://github.com/{}/releases/download/".format(GITHUB_REPO)
ASSET_NAME = "FevDownloadSetup.exe"

# Kurz gehalten: Die Pruefung beim Start darf nichts aufhalten.
CHECK_TIMEOUT = 8
DOWNLOAD_TIMEOUT = 30
USER_AGENT = "FevDownload"

ProgressCallback = Callable[[int], None]
CancelCheck = Callable[[], bool]


class UpdateError(Exception):
    """Die Aktualisierung ist gescheitert - die Meldung ist fuer Nutzer gedacht."""


@dataclass(frozen=True)
class AppRelease:
    """Eine auf GitHub veroeffentlichte Fassung."""

    version: str          # ohne fuehrendes 'v', z. B. "1.1.0"
    url: str              # Adresse des Installers
    size: int             # Bytes laut GitHub, 0 wenn unbekannt
    sha256: Optional[str]  # Pruefsumme laut GitHub, falls angegeben
    notes: str            # Beschreibung des Releases
    page: str             # Seite im Browser


def _open(url: str, timeout: float, accept: str = "*/*"):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    return urlopen(request, timeout=timeout)


def _explain(error: Exception) -> str:
    """Macht aus einem Netzwerkfehler einen Satz, den man lesen kann."""
    if isinstance(error, HTTPError):
        if error.code == 404:
            return "Auf GitHub gibt es noch keine veroeffentlichte Fassung."
        if error.code in (403, 429):
            return (
                "GitHub nimmt gerade keine weiteren Anfragen an. "
                "Bitte in einer Stunde noch einmal versuchen."
            )
        return "GitHub antwortet mit einem Fehler ({}).".format(error.code)
    if isinstance(error, (URLError, TimeoutError, OSError)):
        return "Keine Verbindung zu GitHub. Ist das Internet erreichbar?"
    return "Unerwarteter Fehler: {}".format(error)


def parse_release(data: dict) -> AppRelease:
    """Liest die Antwort von GitHub aus. Wirft UpdateError, wenn sie unbrauchbar ist."""
    tag = str(data.get("tag_name") or "").strip()
    version = tag[1:] if tag[:1] in ("v", "V") else tag
    if not re.fullmatch(r"\d+(\.\d+)*", version):
        raise UpdateError("Die Fassungsnummer der Veroeffentlichung ist unlesbar: '{}'.".format(tag))

    asset = next((a for a in (data.get("assets") or []) if a.get("name") == ASSET_NAME), None)
    if asset is None:
        raise UpdateError(
            "Zur Fassung {} gehoert noch kein Installer ({}).".format(version, ASSET_NAME)
        )

    url = str(asset.get("browser_download_url") or "")
    if not url.startswith(DOWNLOAD_PREFIX):
        raise UpdateError("Die Download-Adresse des Installers ist nicht vertrauenswuerdig.")

    digest = str(asset.get("digest") or "")
    sha256 = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else None

    return AppRelease(
        version=version,
        url=url,
        size=int(asset.get("size") or 0),
        sha256=sha256,
        notes=str(data.get("body") or "").strip(),
        page=str(data.get("html_url") or RELEASES_PAGE),
    )


def latest_release() -> AppRelease:
    """Fragt GitHub nach der neuesten Fassung."""
    try:
        with _open(RELEASE_API, CHECK_TIMEOUT, "application/vnd.github+json") as response:
            data = json.loads(response.read().decode("utf-8"))
    except UpdateError:
        raise
    except Exception as error:
        raise UpdateError(_explain(error)) from error
    if not isinstance(data, dict):
        raise UpdateError("GitHub hat eine unerwartete Antwort geschickt.")
    return parse_release(data)


def current_version() -> str:
    from .. import __version__

    return __version__


def is_newer(candidate: str, current: Optional[str] = None) -> bool:
    return paths.version_key(candidate) > paths.version_key(current or current_version())


def check() -> Optional[AppRelease]:
    """Die neuere Fassung, falls es eine gibt - sonst None. Wirft UpdateError."""
    release = latest_release()
    return release if is_newer(release.version) else None


# ---------------------------------------------------------------------------
# Laden und Starten
# ---------------------------------------------------------------------------

def update_dir() -> Path:
    return Path(tempfile.gettempdir()) / "FevDownload" / "update"


def download_installer(
    release: AppRelease,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCheck] = None,
) -> Path:
    """
    Laedt den Installer und prueft ihn.

    Geprueft werden Groesse und - wenn GitHub sie angibt - die SHA-256-Summe. Das
    schuetzt vor einer abgebrochenen oder beschaedigten Datei, bevor sie
    gestartet wird. Eine geladene Datei wird erst danach unter ihrem endgueltigen
    Namen abgelegt.
    """
    if not release.url.startswith(DOWNLOAD_PREFIX):
        raise UpdateError("Die Download-Adresse des Installers ist nicht vertrauenswuerdig.")

    folder = update_dir()
    # Alte Reste weg: sonst sammeln sich mit jeder Fassung 100 MB an.
    shutil.rmtree(folder, ignore_errors=True)
    paths.ensure_dir(folder)
    target = folder / "FevDownloadSetup-{}.exe".format(release.version)
    partial = target.with_suffix(".teil")

    digest = hashlib.sha256()
    received = 0
    try:
        with _open(release.url, DOWNLOAD_TIMEOUT) as response, open(partial, "wb") as out:
            total = release.size or int(response.headers.get("Content-Length") or 0)
            while True:
                if should_cancel is not None and should_cancel():
                    raise UpdateError("Abgebrochen.")
                block = response.read(256 * 1024)
                if not block:
                    break
                out.write(block)
                digest.update(block)
                received += len(block)
                if on_progress is not None and total:
                    on_progress(min(99, int(received * 100 / total)))
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as error:
        partial.unlink(missing_ok=True)
        raise UpdateError(_explain(error)) from error

    if release.size and received != release.size:
        partial.unlink(missing_ok=True)
        raise UpdateError(
            "Der Download ist unvollstaendig ({} von {} Bytes).".format(received, release.size)
        )
    if release.sha256 and digest.hexdigest().lower() != release.sha256:
        partial.unlink(missing_ok=True)
        raise UpdateError("Die geladene Datei ist beschaedigt (Pruefsumme stimmt nicht).")

    partial.replace(target)
    if on_progress is not None:
        on_progress(100)
    return target


# Flags fuer Windows: der Installer soll weiterlaufen, wenn sich die App beendet.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def launch_installer(installer: Path) -> None:
    """
    Startet den Installer still ueber die vorhandene Installation.

    /SILENT zeigt einen kleinen Fortschrittsbalken, aber keine Fragen - so sieht
    man, dass etwas passiert, waehrend die App weg ist. Danach startet der
    Installer die App wieder.

    /FORCECLOSEAPPLICATIONS ist wichtig: Die App beendet sich zwar selbst, aber
    der Installer prueft schon nach einem Sekundenbruchteil, ob noch etwas laeuft.
    Ohne das Erzwingen versucht er, die App ueber den Neustart-Manager zu
    schliessen, scheitert daran und bricht im stillen Modus kommentarlos ab
    ("Some applications could not be shut down. Defaulting to Abort"). Gemessen:
    ohne das Flag wurde nichts installiert, mit Flag in 14 s.
    """
    subprocess.Popen(
        [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
         "/CLOSEAPPLICATIONS", "/FORCECLOSEAPPLICATIONS"],
        creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
