"""Startet die Oberflaeche ohne Konsolenfenster.

Ziel der Desktop-Verknuepfung und des Resolve-Scripts. Argumente werden
unveraendert weitergereicht (z. B. --job).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fevdl.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
