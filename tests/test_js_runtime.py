"""
JavaScript-Laufzeit fuer YouTube (Deno + yt-dlp-ejs). Ohne Netz.

Ohne Laufzeit fragt yt-dlp YouTube nur ueber einen einzigen Zugang an. Sperrt
YouTube den ("Sign in to confirm you're not a bot"), laesst sich kein Video mehr
analysieren - so geschehen bei einem Freund (Nov. 2026). Hier wird geprueft, dass
jeder yt-dlp-Aufruf die Laufzeit bekommt, dass die Loesungsskripte zur
yt-dlp-Fassung passen und dass Deno abgeschottet laeuft.
"""

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fevdl import paths
from fevdl.core import download, probe
from fevdl.core.errors import humanize
from fevdl.core.models import DownloadRequest, Mode
from fevdl.core.ytdlp_options import shared_options

# Genau die Schalter, mit denen yt-dlp Deno fuer die mitgelieferten Skripte startet
# (yt_dlp/extractor/youtube/jsc/_builtin/deno.py).
DENO_SANDBOX = [
    "run", "--ext=js", "--no-code-cache", "--no-prompt", "--no-remote",
    "--no-lock", "--node-modules-dir=none", "--no-config", "--no-npm", "--cached-only", "-",
]


def _run_deno(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(paths.DENO_EXE), *DENO_SANDBOX], input=script, capture_output=True,
        text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class OptionenTests(unittest.TestCase):
    def test_deno_liegt_bereit(self):
        self.assertTrue(paths.DENO_EXE.is_file(), "deno.exe fehlt: {}".format(paths.DENO_EXE))

    def test_jeder_aufruf_bekommt_die_laufzeit(self):
        expected = {"deno": {"path": str(paths.DENO_EXE)}}
        self.assertEqual(probe._base_options()["js_runtimes"], expected)

        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=aqz-KE-bpKQ", output_dir=Path(tempfile.gettempdir()),
            mode=Mode.VIDEO_AUDIO, height=720, start=1.0, end=4.0, prefer_h264=True,
        )
        self.assertEqual(download._build_options(request, lambda _p: None, None)["js_runtimes"], expected)

        # download_preview baut seine Optionen selbst; den yt-dlp-Aufruf abfangen.
        seen = {}

        class _Stop(Exception):
            pass

        class _FakeYdl:
            def __init__(self, options):
                seen.update(options)
                raise _Stop()

        with patch.object(download, "YoutubeDL", _FakeYdl), patch.object(download, "humanize", side_effect=_Stop):
            with self.assertRaises(_Stop):
                download.download_preview("https://www.youtube.com/watch?v=aqz-KE-bpKQ", Path(tempfile.gettempdir()))
        self.assertEqual(seen.get("js_runtimes"), expected)

    def test_ohne_deno_bleibt_alles_beim_alten(self):
        with patch.object(paths, "DENO_EXE", Path(tempfile.gettempdir()) / "gibt-es-nicht" / "deno.exe"):
            self.assertEqual(shared_options(), {})


class SkriptTests(unittest.TestCase):
    def test_loesungsskripte_passen_zu_yt_dlp(self):
        """Genau die Pruefung, die yt-dlp vor dem Benutzen macht (ejs.py: _get_script)."""
        import yt_dlp_ejs
        import yt_dlp_ejs.yt.solver as solver
        from yt_dlp.extractor.youtube.jsc._builtin import vendor

        wanted = vendor.VERSION.split(".")[:2]
        self.assertEqual(
            yt_dlp_ejs.version.split(".")[:2], wanted,
            "requirements.txt: yt-dlp-ejs passt nicht zu yt-dlp (erwartet {})".format(vendor.VERSION),
        )
        for name, code in (("yt.solver.core.min.js", solver.core()), ("yt.solver.lib.min.js", solver.lib())):
            self.assertEqual(hashlib.sha3_512(code.encode()).hexdigest(), vendor.HASHES[name], name)


class DenoTests(unittest.TestCase):
    def test_deno_rechnet(self):
        result = _run_deno("console.log(JSON.stringify({summe: 1 + 1}))")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '{"summe":2}')

    def test_deno_darf_keine_dateien_lesen(self):
        result = _run_deno('console.log(Deno.readTextFileSync("C:/Windows/win.ini").length)')
        self.assertNotEqual(result.returncode, 0, "Deno konnte ohne Erlaubnis eine Datei lesen")

    def test_deno_darf_nicht_ins_netz(self):
        result = _run_deno('const r = await fetch("https://example.com"); console.log(r.status)')
        self.assertNotEqual(result.returncode, 0, "Deno kam ohne Erlaubnis ins Netz")


class MeldungTests(unittest.TestCase):
    def test_bot_sperre_wird_erklaert(self):
        raw = ("ERROR: [youtube] ChfilcOS55M: Sign in to confirm you're not a bot. Use --cookies-from-browser "
               "or --cookies for the authentication.")
        text = humanize(raw)
        self.assertIn("Bot", text)
        self.assertIn("VPN", text)

    def test_altersgrenze_bleibt(self):
        self.assertIn("altersbeschraenkt", humanize("ERROR: Sign in to confirm your age. This video may be"))


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
