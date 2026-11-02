"""
Welches yt-dlp gilt: das mitgelieferte oder das nachgeladene? Ohne Netz.

Der Nachlade-Ordner ueberlebt den Installer. Frueher stellte
activate_ytdlp_update() ihn immer nach vorn - ein spaeter eingespielter,
neuerer Installer wurde dadurch von der alten nachgeladenen Fassung verdeckt,
ohne dass es jemand merkte. Jetzt gilt die neuere von beiden.

Die Tests arbeiten mit einem Wegwerf-Ordner und fassen das echte
%LOCALAPPDATA% nicht an.
"""

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fevdl import paths


def _fake_update(folder: Path, version: str) -> None:
    """Legt einen Nachlade-Ordner an, der nur eine version.py enthaelt."""
    package = folder / "yt_dlp"
    package.mkdir(parents=True)
    (package / "version.py").write_text(
        "__version__ = '{}'\n_pkg_version = '{}'\n".format(version, version),
        encoding="utf-8",
    )


class VorrangTests(unittest.TestCase):
    def setUp(self):
        self._saved_path = list(sys.path)
        self._tmp = tempfile.TemporaryDirectory(prefix="fevytdlp_")
        self.folder = Path(self._tmp.name) / "ytdlp"

    def tearDown(self):
        sys.path[:] = self._saved_path
        self._tmp.cleanup()

    def _activate(self, bundled):
        with (
            patch.object(paths, "YTDLP_DIR", self.folder),
            patch.object(paths, "bundled_ytdlp_version", return_value=bundled),
        ):
            return paths.activate_ytdlp_update()

    def test_aeltere_nachgeladene_wird_ignoriert(self):
        # Der Fall von Fev: Update vom September, Installer vom Oktober.
        _fake_update(self.folder, "2026.08.19")
        self.assertIsNone(self._activate("2026.10.26"))
        self.assertNotIn(str(self.folder), sys.path)

    def test_gleiche_fassung_in_anderer_schreibweise_ist_nicht_neuer(self):
        # PyPI: 2026.8.19, yt-dlp selbst: 2026.08.19.
        _fake_update(self.folder, "2026.08.19")
        self.assertIsNone(self._activate("2026.8.19"))
        self.assertNotIn(str(self.folder), sys.path)

    def test_neuere_nachgeladene_gilt(self):
        _fake_update(self.folder, "2026.11.05")
        self.assertEqual(self._activate("2026.10.26"), "2026.11.05")
        self.assertEqual(sys.path[0], str(self.folder))

    def test_ohne_bekannte_mitgelieferte_fassung_gilt_die_nachgeladene(self):
        # Rueckfall, wenn sich die mitgelieferte nicht erfragen laesst.
        _fake_update(self.folder, "2026.08.19")
        self.assertEqual(self._activate(None), "2026.08.19")
        self.assertEqual(sys.path[0], str(self.folder))

    def test_ohne_nachlade_ordner_aendert_sich_nichts(self):
        before = list(sys.path)
        self.assertIsNone(self._activate("2026.10.26"))
        self.assertEqual(sys.path, before)

    def test_veralteter_eintrag_im_suchpfad_wird_entfernt(self):
        # Wurde der Ordner frueher schon eingetragen, darf er nicht stehen bleiben.
        _fake_update(self.folder, "2026.08.19")
        sys.path.insert(0, str(self.folder))
        self.assertIsNone(self._activate("2026.10.26"))
        self.assertNotIn(str(self.folder), sys.path)

    def test_wiederholter_aufruf_haeuft_nichts_an(self):
        _fake_update(self.folder, "2026.11.05")
        self._activate("2026.10.26")
        self._activate("2026.10.26")
        self.assertEqual(sys.path.count(str(self.folder)), 1)


class FassungTests(unittest.TestCase):
    def test_vergleich_zahl_fuer_zahl(self):
        key = paths.version_key
        self.assertEqual(key("2026.8.19"), key("2026.08.19"))
        self.assertLess(key("2026.8.19"), key("2026.10.26"))
        # Als Text waere "2026.9.1" groesser als "2026.10.26".
        self.assertLess(key("2026.9.1"), key("2026.10.26"))

    def test_mitgelieferte_fassung_ist_die_des_pakets(self):
        # Im Quelltext-Betrieb muss die Metadaten-Abfrage dieselbe Fassung
        # liefern wie das Paket selbst, das im mitgelieferten Ort liegt.
        bundled = paths.bundled_ytdlp_version()
        if bundled is None:
            self.skipTest("Keine Paket-Metadaten (gepacktes Programm ohne copy_metadata)")

        from importlib.machinery import PathFinder

        search = [entry for entry in sys.path if entry != str(paths.YTDLP_DIR)]
        spec = PathFinder.find_spec("yt_dlp", search)
        self.assertIsNotNone(spec, "yt_dlp ist im Suchpfad nicht auffindbar")
        version_file = Path(spec.origin).parent / "version.py"
        match = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]",
                          version_file.read_text(encoding="utf-8"), re.MULTILINE)
        self.assertEqual(paths.version_key(bundled), paths.version_key(match.group(1)))

    def test_abfrage_bindet_yt_dlp_nicht_ein(self):
        # Die ganze Wahl haengt daran: Ist yt_dlp erst einmal geladen, wird der
        # Suchpfad nicht mehr befragt. Darum in einem frischen Prozess pruefen.
        code = (
            "import sys; from fevdl import paths; "
            "paths.bundled_ytdlp_version(); print('yt_dlp' in sys.modules)"
        )
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        ).stdout.strip()
        self.assertEqual(out, "False")


if __name__ == "__main__":
    unittest.main()
