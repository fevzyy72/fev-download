"""Prueft die Logik des Resolve-Scripts ohne Resolve."""

import importlib.util
import tempfile
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "resolve" / "FevDownloader.py"

spec = importlib.util.spec_from_file_location("fev_launcher", LAUNCHER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print("Script    : laedt fehlerfrei")

# --- Installation finden ---
# Zwei Bauarten sind zulaessig: die fertige FevDownload.exe (so kommt das
# Programm bei allen an, die es ueber den Installer bekommen) oder der Weg
# ueber die Python-Umgebung des Projekts (beim Entwickeln). Der Test darf
# deshalb keine der beiden voraussetzen - nur, dass der Startbefehl auf etwas
# tatsaechlich Vorhandenes zeigt.
project_root, start_command = mod.find_installation()
print("Projekt   :", project_root)
print("Start     :", " ".join(Path(part).name for part in start_command))

assert start_command, "Es kam gar kein Startbefehl zurueck"
for part in start_command:
    assert Path(part).is_file(), "Der Startbefehl zeigt ins Leere: {}".format(part)

if Path(start_command[0]).name.lower() == "fevdownload.exe":
    print("Bauart    : installiert")
    assert len(start_command) == 1, "Die .exe wird ohne Beiwerk gestartet"
else:
    print("Bauart    : aus dem Quelltext")
    assert len(start_command) == 2, "Erwartet: pythonw.exe und launch.pyw"
    assert Path(start_command[0]).name == "pythonw.exe"
    assert Path(start_command[1]).name == "launch.pyw"


# --- Import in einen nachgebauten Media Pool ---
class FakeMediaPool:
    """Bildet ImportMedia nach: Liste zurueck = Erfolg, None = abgelehnt."""

    def __init__(self, reject=()):
        self.calls = []
        self.reject = set(reject)

    def ImportMedia(self, files):
        self.calls.append(list(files))
        name = Path(files[0]).name
        if name in self.reject:
            return None          # Resolve lehnt ab, z.B. unbekannter Codec
        return ["MediaPoolItem"]


tmp = Path(tempfile.mkdtemp(prefix="fevlaunch_"))
good = tmp / "gut.mp4"
good.write_bytes(b"x")
rejected = tmp / "vp9.webm"
rejected.write_bytes(b"x")
missing = tmp / "gibtsnicht.mp4"

pool = FakeMediaPool(reject={"vp9.webm"})
imported = mod.import_files(pool, [str(good), str(rejected), str(missing)])

print("Importiert:", [Path(p).name for p in imported])
print("Aufrufe   :", len(pool.calls))
assert imported == [str(good)], "Nur die akzeptierte Datei darf zaehlen"
assert len(pool.calls) == 2, "Die fehlende Datei darf gar nicht erst versucht werden"


# --- Ein Fehler beim Import darf das Script nicht abbrechen ---
class ExplodingPool:
    def ImportMedia(self, files):
        raise RuntimeError("Resolve ist beschaeftigt")


result = mod.import_files(ExplodingPool(), [str(good)])
print("Absturz   : abgefangen ->", result)
assert result == [], "Ein Fehler darf nur uebersprungen werden"

print("\nLAUNCHER-TEST OK")
