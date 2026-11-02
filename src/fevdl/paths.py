"""Zentrale Pfade des Projekts.

Alles Externe (ffmpeg) liegt bewusst im Projektordner und nicht im System-PATH,
damit die Installation in sich geschlossen bleibt.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# True, wenn das Programm als fertige .exe laeuft (PyInstaller) statt aus dem
# Quelltext. Beide Faelle muessen bedient werden: Entwicklung laeuft weiter aus
# dem Projektordner, die Weitergabe an andere ueber den Installer.
IS_FROZEN = bool(getattr(sys, "frozen", False))

if IS_FROZEN:
    # Gepackt: bin/ und assets/ legt der Installer neben die .exe. Der Umweg
    # ueber __file__ ginge hier ins Leere, da der Quelltext im Paket steckt.
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    # src/fevdl/paths.py -> src/fevdl -> src -> Projektwurzel
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

BIN_DIR = PROJECT_ROOT / "bin"
FFMPEG_EXE = BIN_DIR / "ffmpeg.exe"
FFPROBE_EXE = BIN_DIR / "ffprobe.exe"

ASSETS_DIR = PROJECT_ROOT / "assets"
ICON_FILE = ASSETS_DIR / "fevdl.ico"

VENV_PYTHONW = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

# Austauschordner zwischen Resolve-Launcher und Oberflaeche.
IPC_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "FevDownloader"
JOB_FILE = IPC_DIR / "job.json"
RESULT_FILE = IPC_DIR / "result.json"
# Wird von install_plugin.ps1 geschrieben, damit das Script in Resolve weiss,
# wo dieses Projekt liegt.
INSTALL_FILE = IPC_DIR / "install.json"

# Vorschaubilder der Bibliothek. Bewusst neben den Austauschdateien und nicht
# im Download-Ordner: Dort haben erzeugte Nebendateien nichts zu suchen.
THUMB_CACHE_DIR = IPC_DIR / "thumbs"

# Nachgeladene yt-dlp-Fassung. Bewusst neben den Austauschdateien und nicht im
# Installationsordner: Der gehoert dem Installer und ist unter Umstaenden
# schreibgeschuetzt, dieser hier gehoert dem Nutzer.
YTDLP_DIR = IPC_DIR / "ytdlp"

DEFAULT_DOWNLOAD_DIR = Path.home() / "Videos" / "FevDownloader"


def ffmpeg_available() -> bool:
    """True, wenn ffmpeg und ffprobe im Projekt bereitliegen."""
    return FFMPEG_EXE.is_file() and FFPROBE_EXE.is_file()


def activate_bin_path() -> None:
    """
    Haengt bin/ vorne an den PATH dieses Prozesses.

    Noetig wegen einer Eigenheit von yt-dlp: bei der Pruefung, ob ein Video
    teilweise geladen werden kann, ruft es FFmpegFD.available() ohne Kontext auf
    und ignoriert dabei die Angabe 'ffmpeg_location' - es sucht dann nur im PATH.
    Im yt-dlp-Quelltext steht an der Stelle selbst ein 'Fixme'-Hinweis.

    Betrifft ausschliesslich diesen Prozess, das System bleibt unveraendert.
    """
    bin_dir = str(BIN_DIR)
    current = os.environ.get("PATH", "")
    entries = current.split(os.pathsep)
    if bin_dir not in entries:
        os.environ["PATH"] = bin_dir + os.pathsep + current


def installed_ytdlp_version() -> str | None:
    """Liest die Fassung des nachgeladenen yt-dlp, ohne es einzubinden."""
    version_file = YTDLP_DIR / "yt_dlp" / "version.py"
    try:
        text = version_file.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    return match.group(1) if match else None


def version_key(version: str) -> tuple[int, ...]:
    """
    Macht aus einer Fassung etwas Vergleichbares.

    PyPI schreibt 2026.8.19, yt-dlp selbst 2026.08.19: dieselbe Fassung. Ein
    Vergleich als Text wuerde sie unterscheiden, daher Zahl fuer Zahl.
    """
    return tuple(int(part) for part in re.findall(r"\d+", version))


def bundled_ytdlp_version() -> str | None:
    """
    Fassung des mitgelieferten yt-dlp - ohne es einzubinden.

    Ueber die Paket-Metadaten statt ueber 'import yt_dlp': Sobald das Paket
    einmal geladen ist, laesst sich die Wahl zwischen mitgeliefert und
    nachgeladen nicht mehr treffen (siehe activate_ytdlp_update).

    Der Nachlade-Ordner wird bei der Suche ausgelassen. Er enthaelt zwar nur das
    Paket selbst, aber die Frage lautet ausdruecklich: Was lieferte der
    Installer mit?

    Rueckgabe: None, wenn sich das nicht ermitteln laesst - etwa in einem
    gepackten Programm, bei dem die Metadaten beim Bauen nicht mitgenommen
    wurden (fevdl.spec: copy_metadata).
    """
    from importlib.metadata import distributions

    search = [entry for entry in sys.path if entry != str(YTDLP_DIR)]
    try:
        for dist in distributions(path=search):
            name = re.sub(r"[-_.]+", "-", dist.metadata["Name"] or "").lower()
            if name == "yt-dlp":
                return dist.version
    except Exception:
        return None
    return None


def activate_ytdlp_update() -> str | None:
    """
    Stellt eine nachgeladene yt-dlp-Fassung vor die mitgelieferte - aber nur,
    wenn sie neuer ist.

    YouTube aendert regelmaessig etwas an seinen Seiten; yt-dlp zieht meist
    binnen Tagen nach. Die mitgelieferte Fassung ist aber auf dem Stand des
    Bauens eingefroren - ohne diesen Weg braeuchte es fuer jede Anpassung einen
    neuen Installer.

    yt-dlp ist reines Python, es genuegt also, den Ordner im Suchpfad VOR das
    mitgelieferte Paket zu stellen.

    Der Vergleich ist noetig, weil der Nachlade-Ordner den Installer ueberlebt:
    Wer ein Update holt und spaeter einen neueren Installer einspielt, hat sonst
    eine veraltete nachgeladene Fassung, die die frische mitgelieferte
    stillschweigend verdeckt.

    Muss laufen, BEVOR yt_dlp zum ersten Mal eingebunden wird - danach steht der
    Eintrag in sys.modules und der Suchpfad wird nicht mehr befragt.

    Rueckgabe: die nun geltende nachgeladene Fassung, oder None, wenn die
    mitgelieferte gilt.
    """
    entry = str(YTDLP_DIR)
    if entry in sys.path:
        sys.path.remove(entry)

    version = installed_ytdlp_version()
    if version is None:
        return None

    bundled = bundled_ytdlp_version()
    # Gleich neu genuegt: dann ist die mitgelieferte dieselbe Fassung.
    if bundled is not None and version_key(version) <= version_key(bundled):
        return None

    sys.path.insert(0, entry)
    return version


def ensure_dir(path: Path) -> Path:
    """Legt einen Ordner an, falls er fehlt, und gibt ihn zurueck."""
    path.mkdir(parents=True, exist_ok=True)
    return path
