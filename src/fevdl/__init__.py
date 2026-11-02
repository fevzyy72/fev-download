"""FevDownloader - Video-Downloader-Plugin fuer DaVinci Resolve."""

from . import paths

__version__ = "1.1.0"

# Muss hier stehen und nirgends sonst: probe.py und download.py binden yt_dlp
# auf Modulebene ein. Sobald irgendein Teil von fevdl geladen wird, ist es also
# zu spaet - der Suchpfad wird dann nicht mehr befragt. __init__.py laeuft vor
# jedem Untermodul, egal ueber welchen Weg das Programm gestartet wurde.
YTDLP_VERSION = paths.activate_ytdlp_update()
