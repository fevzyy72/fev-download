"""Einstiegspunkt der Oberflaeche:  python -m fevdl [--job PFAD]

Ohne --job laeuft das Programm eigenstaendig. Mit --job wurde es aus DaVinci
Resolve heraus gestartet und meldet fertige Dateien dorthin zurueck.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import paths
from .gui import typography
from .gui.main_window import MainWindow
from .ipc import read_job

APP_ID = "fezco.FevDownload"


def _claim_taskbar_identity() -> None:
    """
    Gibt dem Programm in der Taskleiste eine eigene Kennung.

    Ohne das gruppiert Windows das Fenster unter 'pythonw' und zeigt dessen
    Symbol statt unserem. Betrifft nur Windows und darf ruhig fehlschlagen.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fevdl", add_help=True)
    parser.add_argument(
        "--job",
        default=None,
        help="Pfad zur job.json, die DaVinci Resolve geschrieben hat",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    job = read_job(Path(args.job)) if args.job else None

    _claim_taskbar_identity()

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Fev Download")
    app.setOrganizationName("fezco")
    # Grundschrift zentral setzen statt im Stylesheet - so bleiben die
    # Feineinstellungen aus typography.py wirksam.
    app.setFont(typography.body())

    if paths.ICON_FILE.is_file():
        app.setWindowIcon(QIcon(str(paths.ICON_FILE)))

    window = MainWindow(job=job)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
