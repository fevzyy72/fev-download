"""Prueft, ob die Oberflaeche einen Resolve-Auftrag uebernimmt und meldet."""

import json
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from fevdl import paths
from fevdl.gui import typography
from fevdl.gui.main_window import MainWindow
from fevdl.ipc import Job, new_job_id

tmp = Path(tempfile.mkdtemp(prefix="fevjob_"))
# Die Rueckmeldung soll in den Testordner, nicht in den echten.
paths.RESULT_FILE = tmp / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())
app.setApplicationName("Fev Download")
app.setOrganizationName("fezco")
# Frueher Zustand aus anderen Testlaeufen darf hier nicht hineinwirken.
QSettings("fezco", "Fev Download").clear()

job = Job(
    job_id=new_job_id(),
    project="newlernen",
    output_dir=tmp / "downloads",
    resolve_version="21.0.3.7",
)

window = MainWindow(job=job)
window.show()

print("Banner sichtbar :", window.resolve_banner.isVisible())
print("Banner Text     :", window.resolve_banner.text()[:70], "...")
print("Zielordner      :", window.output_edit.text())
assert window.resolve_banner.isVisible(), "Der Resolve-Hinweis muss sichtbar sein"
assert window.output_edit.text() == str(tmp / "downloads"), "Zielordner nicht uebernommen"

# Einen fertigen Download vortaeuschen
fake = tmp / "downloads" / "clip.mp4"
fake.parent.mkdir(parents=True, exist_ok=True)
fake.write_bytes(b"nicht wirklich ein video")
window._on_download_succeeded(fake)

data = json.loads((tmp / "result.json").read_text(encoding="utf-8"))
print("Gemeldete Datei :", Path(data["files"][0]).name)
print("Status          :", data["status"])
assert data["files"] == [str(fake)], "Datei wurde nicht gemeldet"
assert data["job_id"] == job.job_id, "job_id stimmt nicht"

# Schliessen muss den Abschluss melden
window.close()
data = json.loads((tmp / "result.json").read_text(encoding="utf-8"))
print("Nach Schliessen :", data["status"])
assert data["status"] == "ok", "Abschluss wurde nicht gemeldet"

# Ohne Auftrag darf kein Banner erscheinen und nichts geschrieben werden
plain = MainWindow(job=None)
print("Ohne Auftrag    : Banner sichtbar =", plain.resolve_banner.isVisible())
assert not plain.resolve_banner.isVisible(), "Ohne Resolve darf kein Banner erscheinen"

# --- Der Vorgabewert darf sich nicht als eigene Wahl festsetzen ---
# Frueher wurde der Zielordner bei jedem Schliessen gespeichert. Dadurch galt
# schon die Vorgabe des ersten Starts als Entscheidung und Resolves Vorschlag
# wurde nie wieder uebernommen.
plain.close()   # speichert die Einstellungen, ohne dass etwas gewaehlt wurde

job2 = Job(job_id=new_job_id(), project="zweitprojekt",
           output_dir=tmp / "aus_resolve", resolve_version="21.0.3.7")
w_after = MainWindow(job=job2)
print("Resolve-Ordner  :", w_after.output_edit.text())
assert w_after.output_edit.text() == str(tmp / "aus_resolve"), \
    "Ohne eigene Wahl muss Resolves Vorschlag greifen"

# Nach einer echten Wahl gilt diese weiter
w_after._mark_output_chosen()
w_after.output_edit.setText(str(tmp / "meine_wahl"))
w_after.close()

w_last = MainWindow(job=job2)
print("Eigene Wahl     :", w_last.output_edit.text())
assert w_last.output_edit.text() == str(tmp / "meine_wahl"), \
    "Eine eigene Wahl muss Vorrang vor Resolve haben"

QSettings("fezco", "Fev Download").clear()
print("\nJOB-GUI-TEST OK")
