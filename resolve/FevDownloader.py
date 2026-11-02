"""
Fev Download - Start aus DaVinci Resolve
========================================

Aufruf:  Workspace -> Scripts -> Utility -> FevDownloader

Dieses Script laeuft INNERHALB von Resolve und ist damit das einzige Stueck
Code, das die Resolve-Schnittstelle erreicht: Seit Version 19.1 ist Scripting
von aussen in der kostenlosen Version gesperrt.

Ablauf:
  1. Verbindung zu Resolve und zum offenen Projekt herstellen
  2. job.json schreiben und die Oberflaeche als eigenes Programm starten
  3. regelmaessig in result.json schauen
  4. jede neu gemeldete Datei in den Media Pool holen

Es werden ausschliesslich Bausteine der Standardbibliothek verwendet - dieses
Script laeuft unter dem Python, das Resolve mitbringt (fuscript.exe), nicht
unter der Umgebung des Projekts.
"""

import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime

APP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FevDownloader"
)
INSTALL_FILE = os.path.join(APP_DIR, "install.json")
JOB_FILE = os.path.join(APP_DIR, "job.json")
RESULT_FILE = os.path.join(APP_DIR, "result.json")
LOG_FILE = os.path.join(APP_DIR, "launcher.log")

POLL_INTERVAL = 1.0          # Sekunden zwischen zwei Blicken in result.json
TIMEOUT_SECONDS = 8 * 3600   # Notbremse, falls die Oberflaeche haengen bleibt
GRACE_SECONDS = 20           # Anlaufzeit, bevor auf "Programm weg" geprueft wird

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def log(message):
    """Gibt eine Zeile in Resolves Konsole aus und haengt sie ans Protokoll."""
    line = "[Fev Download] {}".format(message)
    print(line)
    try:
        if not os.path.isdir(APP_DIR):
            os.makedirs(APP_DIR)
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write("{}  {}\n".format(datetime.now().strftime("%H:%M:%S"), line))
    except Exception:
        pass


def read_json(path):
    # 'utf-8-sig' statt 'utf-8': Von PowerShell geschriebene Dateien beginnen
    # oft mit einer Byte-Reihenfolge-Marke, an der ein reiner utf-8-Leser
    # scheitert. Fehlt die Marke, verhaelt sich utf-8-sig identisch.
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (IOError, OSError, ValueError):
        return None


def write_json(path, data):
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def get_resolve():
    """
    Holt das Resolve-Objekt.

    Bei intern gestarteten Scripts legt Resolve meist schon ein globales
    'resolve' an. Nur wenn das fehlt, wird das offizielle Modul bemueht.
    """
    existing = globals().get("resolve")
    if existing is not None:
        return existing

    app_object = globals().get("app")
    if app_object is not None and hasattr(app_object, "GetResolve"):
        obtained = app_object.GetResolve()
        if obtained is not None:
            return obtained

    import DaVinciResolveScript as dvr_script

    return dvr_script.scriptapp("Resolve")


# ---------------------------------------------------------------------------
# Oberflaeche finden und starten
# ---------------------------------------------------------------------------

def find_installation():
    """
    Liest, wo das Programm liegt, und stellt den Startbefehl zusammen.

    Es gibt zwei Bauarten, und beide muessen bedient werden:

      1. Fertig installiert - FevDownload.exe bringt Python selbst mit. So
         kommt das Programm bei allen an, die es ueber den Installer bekommen.
      2. Aus dem Quelltext - ueber die Python-Umgebung des Projekts. Nur beim
         Entwickeln, dafuer ohne jedes Mal neu zu bauen.

    Die .exe hat Vorrang: Liegt beides vor, ist das der Entwicklungsrechner,
    und dort soll die gerade gebaute Fassung geprueft werden.

    Rueckgabe: (Ordner, Startbefehl als Liste)
    """
    data = read_json(INSTALL_FILE)
    if not data:
        raise RuntimeError(
            "Die Datei install.json fehlt.\n"
            "Bitte Fev Download neu installieren."
        )

    project_root = data.get("project_root") or ""
    if (not isinstance(project_root, str) or not os.path.isabs(project_root)
            or "\x00" in project_root or not os.path.isdir(project_root)):
        raise RuntimeError(
            "Der eingetragene Programmordner existiert nicht:\n  {}\n"
            "Bitte Fev Download neu installieren.".format(project_root)
        )

    executable = os.path.join(project_root, "FevDownload.exe")
    if os.path.isfile(executable):
        return project_root, [executable]

    pythonw = os.path.join(project_root, ".venv", "Scripts", "pythonw.exe")
    launcher = os.path.join(project_root, "launch.pyw")
    if os.path.isfile(pythonw) and os.path.isfile(launcher):
        return project_root, [pythonw, launcher]

    raise RuntimeError(
        "Im eingetragenen Ordner ist das Programm nicht zu finden:\n  {}\n"
        "Erwartet wurde FevDownload.exe (installiert) oder .venv mit\n"
        "launch.pyw (aus dem Quelltext, nach setup.ps1).".format(project_root)
    )


def start_interface(command, project_root):
    """Startet die Oberflaeche als eigenstaendiges Programm."""
    return subprocess.Popen(
        command + ["--job", JOB_FILE],
        cwd=project_root,
        creationflags=_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# Import in den Media Pool
# ---------------------------------------------------------------------------

def import_files(media_pool, file_paths):
    """
    Holt die Dateien in den Media Pool und meldet, was tatsaechlich ankam.

    Rueckgabe: Liste der Pfade, die erfolgreich importiert wurden.
    """
    imported = []
    for file_path in file_paths:
        if not isinstance(file_path, str) or not os.path.isabs(file_path) or "\x00" in file_path:
            continue
        if not os.path.isfile(file_path):
            log("Datei nicht gefunden, wird uebersprungen: {}".format(file_path))
            continue
        try:
            items = media_pool.ImportMedia([file_path])
        except Exception as error:
            log("Import fehlgeschlagen ({}): {}".format(os.path.basename(file_path), error))
            continue

        if items:
            log("Im Media Pool: {}".format(os.path.basename(file_path)))
            imported.append(file_path)
        else:
            log(
                "Resolve hat die Datei abgelehnt: {}\n"
                "  Moeglicher Grund: nicht unterstuetzter Codec. In der Oberflaeche\n"
                "  den Haken 'H.264 fuer Resolve' gesetzt lassen.".format(
                    os.path.basename(file_path)
                )
            )
    return imported


def pending_files(result, job_id, imported):
    """Nur vollstaendige Pfadlisten fuer die aktuelle Sitzung annehmen."""
    if not result or result.get("job_id") != job_id:
        return []
    files = result.get("files")
    if not isinstance(files, list):
        return []
    return [path for path in files if isinstance(path, str) and "\x00" not in path
            and os.path.isabs(path) and path not in imported]


# ---------------------------------------------------------------------------
# Hauptablauf
# ---------------------------------------------------------------------------

def main():
    log("=" * 58)
    log("Start " + datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

    resolve = get_resolve()
    if resolve is None:
        log("Keine Verbindung zu DaVinci Resolve.")
        return

    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject() if project_manager else None
    if project is None:
        log("Es ist kein Projekt geoeffnet. Bitte zuerst ein Projekt oeffnen.")
        return

    media_pool = project.GetMediaPool()
    if media_pool is None:
        log("Auf den Media Pool des Projekts ist kein Zugriff moeglich.")
        return

    project_name = project.GetName()
    log("Projekt: {}".format(project_name))

    try:
        project_root, start_command = find_installation()
    except RuntimeError as error:
        log(str(error))
        return

    # Alte Rueckmeldung entfernen, sonst wuerden Dateien der letzten Sitzung
    # sofort noch einmal importiert.
    try:
        if os.path.isfile(RESULT_FILE):
            os.remove(RESULT_FILE)
    except OSError:
        pass

    job_id = time.strftime("%Y%m%d-%H%M%S") + "-{}".format(os.getpid())
    default_output = os.path.join(os.path.expanduser("~"), "Videos", "FevDownloader")
    write_json(
        JOB_FILE,
        {
            "job_id": job_id,
            "project": project_name,
            "output_dir": default_output,
            "resolve_version": resolve.GetVersionString(),
        },
    )

    log("Oeffne das Fenster...")
    process = start_interface(start_command, project_root)

    log("Warte auf Downloads. Dieses Fenster kann offen bleiben.")

    imported = set()
    started_at = time.time()
    deadline = started_at + TIMEOUT_SECONDS
    finished = False

    while time.time() < deadline:
        result = read_json(RESULT_FILE)

        if result and result.get("job_id") == job_id:
            pending = pending_files(result, job_id, imported)
            if pending:
                for path in import_files(media_pool, pending):
                    imported.add(path)
                # Auch abgelehnte Dateien vormerken, sonst laeuft der Import
                # bei jedem Durchgang erneut ins Leere.
                imported.update(pending)

            if result.get("status") in ("ok", "error", "cancelled"):
                finished = True
                break

        # Erst nach der Anlaufzeit pruefen - vorher steht das Fenster oft noch
        # gar nicht.
        if time.time() - started_at > GRACE_SECONDS and process.poll() is not None:
            log("Das Fenster wurde geschlossen.")
            break

        time.sleep(POLL_INTERVAL)
    else:
        log("Zeitgrenze erreicht - der Vorgang wird beendet.")

    # Letzter Blick: Was zwischen dem vorletzten Durchgang und dem Schliessen
    # noch fertig wurde, waere sonst verloren.
    result = read_json(RESULT_FILE)
    if result and result.get("job_id") == job_id:
        pending = pending_files(result, job_id, imported)
        if pending:
            for path in import_files(media_pool, pending):
                imported.add(path)

    if imported:
        log("Fertig - {} Datei(en) im Media Pool von '{}'.".format(len(imported), project_name))
    elif finished:
        log("Fertig - es wurde nichts heruntergeladen.")
    else:
        log("Beendet.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log("Unerwarteter Fehler: {}".format(error))
        log(traceback.format_exc())
