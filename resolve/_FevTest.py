"""
FevDownloader - Umgebungstest (Phase 0)

Dieses Script wird aus DaVinci Resolve heraus gestartet:
    Workspace -> Scripts -> Utility -> _FevTest

Es prueft, ob Resolve einen Python-Interpreter findet und ob der Zugriff auf die
Resolve-API aus einem internen Script heraus funktioniert (das ist in der
kostenlosen Version der einzige erlaubte Weg).

Alle Ergebnisse landen zusaetzlich in einer Log-Datei auf dem Desktop, damit sie
auch dann lesbar sind, wenn Resolve keine Konsolenausgabe anzeigt.
"""

import os
import sys
import platform
from datetime import datetime

LOG_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "fev_resolve_test.txt")

_lines = []


def log(message):
    """Gibt eine Zeile aus und merkt sie fuer die Log-Datei vor."""
    text = str(message)
    print(text)
    _lines.append(text)


def get_resolve():
    """
    Holt das Resolve-Objekt.

    Resolve legt bei intern gestarteten Scripts meist schon ein globales
    'resolve' bzw. 'app' an. Nur wenn beides fehlt, greifen wir auf das
    offizielle Modul zurueck.
    """
    existing = globals().get("resolve")
    if existing is not None:
        return existing, "globale Variable 'resolve'"

    app_obj = globals().get("app")
    if app_obj is not None and hasattr(app_obj, "GetResolve"):
        obtained = app_obj.GetResolve()
        if obtained is not None:
            return obtained, "app.GetResolve()"

    import DaVinciResolveScript as dvr_script

    return dvr_script.scriptapp("Resolve"), "DaVinciResolveScript-Modul"


def main():
    log("=" * 60)
    log("FevDownloader - Umgebungstest")
    log(datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    log("=" * 60)

    log("")
    log("--- Python ---")
    log("Version    : {}".format(sys.version.split()[0]))
    log("Bitness    : {}".format(platform.architecture()[0]))
    log("Interpreter: {}".format(sys.executable or "(unbekannt)"))

    log("")
    log("--- Resolve ---")
    try:
        resolve_obj, source = get_resolve()
    except Exception as exc:
        log("FEHLER beim Laden der Resolve-API: {}".format(exc))
        log("")
        log("ERGEBNIS: FEHLGESCHLAGEN")
        return

    if resolve_obj is None:
        log("Resolve-Objekt ist None - keine Verbindung zur API.")
        log("")
        log("ERGEBNIS: FEHLGESCHLAGEN")
        return

    log("Bezogen ueber: {}".format(source))
    log("Produkt      : {}".format(resolve_obj.GetProductName()))
    log("Version      : {}".format(resolve_obj.GetVersionString()))

    project_manager = resolve_obj.GetProjectManager()
    project = project_manager.GetCurrentProject() if project_manager else None

    if project is None:
        log("Projekt      : (kein Projekt geoeffnet)")
    else:
        log("Projekt      : {}".format(project.GetName()))
        media_pool = project.GetMediaPool()
        if media_pool is not None:
            root_folder = media_pool.GetRootFolder()
            clip_count = len(root_folder.GetClipList() or []) if root_folder else 0
            log("Media Pool   : erreichbar ({} Clip(s) im Hauptordner)".format(clip_count))
        else:
            log("Media Pool   : NICHT erreichbar")

    log("")
    log("ERGEBNIS: ERFOLGREICH - der Weg ueber Workspace -> Scripts funktioniert.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        log("")
        log("UNERWARTETER FEHLER: {}".format(exc))
        log(traceback.format_exc())
        log("")
        log("ERGEBNIS: FEHLGESCHLAGEN")
    finally:
        try:
            with open(LOG_PATH, "w", encoding="utf-8") as handle:
                handle.write("\n".join(_lines) + "\n")
            print("\nLog geschrieben nach: {}".format(LOG_PATH))
        except Exception as write_error:
            print("Log konnte nicht geschrieben werden: {}".format(write_error))
