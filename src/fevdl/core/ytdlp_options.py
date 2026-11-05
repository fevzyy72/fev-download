"""Einstellungen, die jeder yt-dlp-Aufruf braucht - Analyse, Vorschau, Download.

Die JavaScript-Laufzeit (Deno). YouTube stellt seinen Abspielern kleine
Rechenaufgaben in JavaScript. Ohne Laufzeit fragt yt-dlp nur ueber einen
einzigen Zugang an, der ohne diese Aufgaben auskommt ('visionos', siehe
_DEFAULT_JSLESS_CLIENTS in yt-dlp). Stuft YouTube eine Verbindung als
verdaechtig ein, antwortet dieser eine Zugang mit "Sign in to confirm you're
not a bot" - und es gibt keinen Ausweg mehr. So geschehen bei einem Freund am
zweiten Tag nach der Installation (Nov. 2026). Mit Deno fragt yt-dlp ueber
mehrere Zugaenge an ('tv_samsung', 'visionos', 'web') und bekommt alle Formate.
Gemessen: Analyse 2,7 s, wie ohne.

Deno wird ausdruecklich mit Pfad angegeben. Gefunden wuerde es sonst nur ueber
den PATH, und bin\\ steht dort erst nach dem ersten Download (activate_bin_path).

'ejs:github' als Notnagel: Die Loesungsskripte stammen aus dem Paket
yt-dlp-ejs, das zur Fassung von yt-dlp passen muss. Holt die stille
Aktualisierung ein neueres yt-dlp, das neuere Skripte verlangt, laedt yt-dlp sie
von GitHub nach - nur dann, und nur wenn die Pruefsumme mit der in yt-dlp
hinterlegten uebereinstimmt. Deno fuehrt sie ohne Datei- und Netzzugriff aus.
"""

from __future__ import annotations

from typing import Any

from .. import paths


def shared_options() -> dict[str, Any]:
    """Gemeinsame Optionen; fehlt Deno, bleibt alles wie in yt-dlp vorgegeben."""
    if not paths.DENO_EXE.is_file():
        return {}
    return {
        "js_runtimes": {"deno": {"path": str(paths.DENO_EXE)}},
        "remote_components": ["ejs:github"],
    }
