"""Prueft den Austausch job.json / result.json ohne Resolve und ohne Fenster."""

import sys
import tempfile
from pathlib import Path

from fevdl.ipc import Job, ResultWriter, new_job_id, read_job, write_job

tmp = Path(tempfile.mkdtemp(prefix="fevipc_"))
job_file = tmp / "job.json"
result_file = tmp / "result.json"

# --- Auftrag schreiben und zurueckgelesen bekommen ---
job_id = new_job_id()
write_job(job_file, Job(
    job_id=job_id,
    project="Testprojekt",
    output_dir=Path(r"C:\Users\Beispiel\Videos\FevDownloader"),
    resolve_version="21.0.3.7",
))

loaded = read_job(job_file)
assert loaded is not None, "job.json konnte nicht gelesen werden"
assert loaded.job_id == job_id, "job_id stimmt nicht"
assert loaded.project == "Testprojekt", "Projektname stimmt nicht"
assert str(loaded.output_dir).endswith("FevDownloader"), "Zielordner stimmt nicht"
print("Auftrag  : geschrieben und gelesen  ->", loaded.project, "|", loaded.job_id)

# --- Ergebnisse melden ---
writer = ResultWriter(path=result_file, job_id=job_id)
writer.add_file(Path(r"C:\clips\eins.mp4"))
writer.add_file(Path(r"C:\clips\zwei.m4a"))
writer.add_file(Path(r"C:\clips\eins.mp4"))  # Dublette darf nicht doppelt landen

import json
data = json.loads(result_file.read_text(encoding="utf-8"))
assert data["status"] == "running", "Status muss waehrend des Laufens 'running' sein"
assert len(data["files"]) == 2, f"Erwartet 2 Dateien, sind {len(data['files'])}"
print("Ergebnis : 2 Dateien gemeldet, Dublette gefiltert ->", data["status"])

writer.mark_finished("ok")
data = json.loads(result_file.read_text(encoding="utf-8"))
assert data["status"] == "ok", "Abschluss-Status stimmt nicht"
print("Abschluss: Status ->", data["status"])

# --- Kaputte Datei darf nicht abstuerzen ---
broken = tmp / "kaputt.json"
broken.write_text("{ das ist kein JSON", encoding="utf-8")
assert read_job(broken) is None, "Kaputte Datei muss None ergeben"
assert read_job(tmp / "gibtsnicht.json") is None, "Fehlende Datei muss None ergeben"
print("Robust   : kaputte und fehlende Datei sauber abgefangen")

print("\nIPC-TEST OK")
