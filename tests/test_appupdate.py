"""
Aktualisierung der App ueber GitHub und die stille yt-dlp-Pruefung, ohne Netz.

Die Netzwerkzugriffe werden durch Attrappen ersetzt. Geprueft wird vor allem,
was schiefgehen kann, wenn eine Datei gestartet werden soll, die aus dem Netz
kommt: falsche Herkunft, abgebrochener Download, beschaedigte Datei.
"""

import hashlib
import io
import json
import subprocess
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from fevdl import paths
from fevdl.core import appupdate, update
from fevdl.core.appupdate import AppRelease, UpdateError

GOOD_URL = appupdate.DOWNLOAD_PREFIX + "v1.1.0/FevDownloadSetup.exe"


def release_json(tag="v1.1.0", url=GOOD_URL, name=appupdate.ASSET_NAME, digest=None, size=1234):
    asset = {"name": name, "browser_download_url": url, "size": size}
    if digest:
        asset["digest"] = digest
    return {"tag_name": tag, "body": "Neu: alles.", "html_url": "https://github.com/x/y/releases/tag/" + tag,
            "assets": [asset]}


class FakeResponse(io.BytesIO):
    """Das, was urlopen zurueckgibt: lesbar, als Kontext nutzbar, mit Kopfzeilen."""

    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class ParseTests(unittest.TestCase):
    def test_gueltige_antwort(self):
        digest = "sha256:" + "AB" * 32
        release = appupdate.parse_release(release_json(digest=digest))
        self.assertEqual(release.version, "1.1.0")
        self.assertEqual(release.url, GOOD_URL)
        self.assertEqual(release.sha256, "ab" * 32)
        self.assertEqual(release.size, 1234)

    def test_ohne_pruefsumme(self):
        self.assertIsNone(appupdate.parse_release(release_json()).sha256)

    def test_tag_ohne_v(self):
        self.assertEqual(appupdate.parse_release(release_json(tag="1.2")).version, "1.2")

    def test_unlesbarer_tag(self):
        with self.assertRaises(UpdateError):
            appupdate.parse_release(release_json(tag="neueste"))

    def test_ohne_installer_im_release(self):
        with self.assertRaises(UpdateError) as ctx:
            appupdate.parse_release(release_json(name="README.zip"))
        self.assertIn("Installer", str(ctx.exception))

    def test_fremde_adresse_wird_abgelehnt(self):
        for url in ("https://evil.example/FevDownloadSetup.exe",
                    "http://github.com/fevzyy72/fev-download/releases/download/v1/x.exe",
                    "https://github.com/anderer/repo/releases/download/v1/FevDownloadSetup.exe"):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                appupdate.parse_release(release_json(url=url))


class VersionTests(unittest.TestCase):
    def test_neuer(self):
        self.assertTrue(appupdate.is_newer("1.1.0", "1.0.3"))
        self.assertTrue(appupdate.is_newer("1.0.10", "1.0.9"))   # Zahl fuer Zahl, nicht als Text
        self.assertTrue(appupdate.is_newer("1.10.0", "1.9.0"))

    def test_nicht_neuer(self):
        self.assertFalse(appupdate.is_newer("1.0.3", "1.0.3"))
        self.assertFalse(appupdate.is_newer("1.0.2", "1.0.3"))

    def test_vergleich_mit_laufender_fassung(self):
        from fevdl import __version__
        self.assertFalse(appupdate.is_newer(__version__))


class NetworkTests(unittest.TestCase):
    def _answer(self, payload):
        return patch.object(appupdate, "_open", return_value=FakeResponse(json.dumps(payload).encode()))

    def test_neuere_fassung_wird_gemeldet(self):
        with self._answer(release_json(tag="v9.9.9")), patch.object(appupdate, "current_version", return_value="1.0.3"):
            release = appupdate.check()
        self.assertEqual(release.version, "9.9.9")

    def test_gleiche_fassung_wird_nicht_gemeldet(self):
        with self._answer(release_json(tag="v1.0.3")), patch.object(appupdate, "current_version", return_value="1.0.3"):
            self.assertIsNone(appupdate.check())

    def _fails(self, error):
        with patch.object(appupdate, "_open", side_effect=error):
            with self.assertRaises(UpdateError) as ctx:
                appupdate.latest_release()
        return str(ctx.exception)

    def test_noch_kein_release(self):
        message = self._fails(HTTPError("u", 404, "Not Found", {}, None))
        self.assertIn("noch keine", message)

    def test_anfragelimit(self):
        self.assertIn("keine weiteren Anfragen", self._fails(HTTPError("u", 403, "Forbidden", {}, None)))

    def test_kein_internet(self):
        self.assertIn("Keine Verbindung", self._fails(URLError("getaddrinfo failed")))
        self.assertIn("Keine Verbindung", self._fails(TimeoutError()))

    def test_kaputte_antwort(self):
        with patch.object(appupdate, "_open", return_value=FakeResponse(b"das ist kein json")):
            with self.assertRaises(UpdateError):
                appupdate.latest_release()


class DownloadTests(unittest.TestCase):
    PAYLOAD = b"MZ" + bytes(range(256)) * 1000

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fevupd_")
        self.folder = Path(self._tmp.name) / "update"
        patcher = patch.object(appupdate, "update_dir", return_value=self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _release(self, payload=None, **changes):
        payload = self.PAYLOAD if payload is None else payload
        values = dict(version="1.1.0", url=GOOD_URL, size=len(payload),
                      sha256=hashlib.sha256(payload).hexdigest(), notes="", page="p")
        values.update(changes)
        return AppRelease(**values)

    def _serve(self, payload=None):
        payload = self.PAYLOAD if payload is None else payload
        return patch.object(appupdate, "_open", side_effect=lambda *a, **k: FakeResponse(payload))

    def test_guter_download(self):
        seen = []
        with self._serve():
            path = appupdate.download_installer(self._release(), on_progress=seen.append)
        self.assertEqual(path.read_bytes(), self.PAYLOAD)
        self.assertEqual(path.name, "FevDownloadSetup-1.1.0.exe")
        self.assertEqual(seen[-1], 100)
        self.assertEqual(seen, sorted(seen), "Der Fortschritt darf nicht zurueckspringen")
        self.assertEqual(list(self.folder.glob("*.teil")), [], "Zwischendatei muss weg sein")

    def test_falsche_pruefsumme(self):
        with self._serve(), self.assertRaises(UpdateError) as ctx:
            appupdate.download_installer(self._release(sha256="00" * 32))
        self.assertIn("Pruefsumme", str(ctx.exception))
        self.assertEqual(list(self.folder.glob("*")), [], "Eine beschaedigte Datei darf nicht liegen bleiben")

    def test_abgeschnittener_download(self):
        release = self._release()
        with self._serve(self.PAYLOAD[:5000]), self.assertRaises(UpdateError) as ctx:
            appupdate.download_installer(release)
        self.assertIn("unvollstaendig", str(ctx.exception))
        self.assertEqual(list(self.folder.glob("*")), [])

    def test_abbruch(self):
        with self._serve(), self.assertRaises(UpdateError):
            appupdate.download_installer(self._release(), should_cancel=lambda: True)
        self.assertEqual(list(self.folder.glob("*")), [])

    def test_fremde_adresse_wird_nicht_einmal_geoeffnet(self):
        with patch.object(appupdate, "_open") as opened, self.assertRaises(UpdateError):
            appupdate.download_installer(self._release(url="https://evil.example/x.exe"))
        opened.assert_not_called()

    def test_ohne_pruefsumme_zaehlt_die_groesse(self):
        with self._serve():
            path = appupdate.download_installer(self._release(sha256=None))
        self.assertTrue(path.is_file())

    def test_anderer_download_bleibt_unberuehrt(self):
        self.folder.mkdir(parents=True)
        (self.folder / "FevDownloadSetup-0.9.exe").write_bytes(b"alt")
        with self._serve():
            appupdate.download_installer(self._release())
        self.assertTrue((self.folder / "FevDownloadSetup-0.9.exe").exists())

    def test_netzfehler_beim_laden(self):
        with patch.object(appupdate, "_open", side_effect=URLError("weg")), self.assertRaises(UpdateError):
            appupdate.download_installer(self._release())


class LaunchTests(unittest.TestCase):
    def test_installer_startet_still_und_abgekoppelt(self):
        with patch.object(subprocess, "Popen") as popen:
            appupdate.launch_installer(Path(r"C:\x\FevDownloadSetup-1.1.0.exe"))
        args, kwargs = popen.call_args
        command = args[0]
        self.assertEqual(command[0], r"C:\x\FevDownloadSetup-1.1.0.exe")
        for flag in ("/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"):
            self.assertIn(flag, command)
        # Ohne Erzwingen bricht der Installer ab, wenn die App beim Pruefen noch
        # laeuft - gemessen, siehe launch_installer.
        self.assertIn("/FORCECLOSEAPPLICATIONS", command)
        # Ohne DETACHED_PROCESS wuerde der Installer mit der App sterben.
        self.assertTrue(kwargs["creationflags"] & 0x00000008)
        self.assertNotIn("/VERYSILENT", command, "Der Fortschrittsbalken soll sichtbar sein")


class YtdlpCheckThrottleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fevchk_")
        patcher = patch.object(paths, "UPDATE_CHECK_FILE", Path(self._tmp.name) / "update_check.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_ohne_vermerk_ist_es_faellig(self):
        self.assertTrue(update.due_for_check())

    def test_direkt_nach_der_suche_nicht(self):
        update.mark_checked()
        self.assertFalse(update.due_for_check())

    def test_nach_einem_tag_wieder(self):
        update.mark_checked(now=1_000_000)
        self.assertFalse(update.due_for_check(now=1_000_000 + 3600))
        self.assertTrue(update.due_for_check(now=1_000_000 + 24 * 3600))

    def test_uhr_zurueckgestellt_zaehlt_als_faellig(self):
        update.mark_checked(now=time.time() + 10 * 86400)
        self.assertTrue(update.due_for_check())

    def test_kaputte_datei_ist_faellig(self):
        paths.UPDATE_CHECK_FILE.write_text("{kaputt", encoding="utf-8")
        self.assertTrue(update.due_for_check())

    def test_nicht_faellig_fragt_gar_nicht_erst_an(self):
        update.mark_checked()
        with patch.object(update, "update_ytdlp") as ask:
            self.assertIsNone(update.auto_update_ytdlp())
        ask.assert_not_called()

    def test_erfolg_wird_vermerkt(self):
        result = update.UpdateResult(changed=True, version="2099.1.1", message="m")
        with patch.object(update, "update_ytdlp", return_value=result):
            self.assertIs(update.auto_update_ytdlp(), result)
        self.assertFalse(update.due_for_check())

    def test_fehler_ist_still_und_wird_nicht_vermerkt(self):
        # Ohne Netz soll beim naechsten Start erneut versucht werden.
        with patch.object(update, "update_ytdlp", side_effect=URLError("offline")):
            self.assertIsNone(update.auto_update_ytdlp())
        self.assertTrue(update.due_for_check())

    def test_schon_geladene_fassung_wird_nicht_nochmal_geholt(self):
        with (
            patch.object(update, "current_version", return_value="2026.08.19"),
            patch.object(update, "latest_version", return_value=("2026.11.5", "wheel", "00" * 32)),
            patch.object(paths, "installed_ytdlp_version", return_value="2026.11.05"),
            patch.object(update, "_fetch") as fetch,
        ):
            result = update.update_ytdlp()
        self.assertFalse(result.changed)
        self.assertIn("naechsten Start", result.message)
        fetch.assert_not_called()


class StartupCheckTests(unittest.TestCase):
    """run_startup_checks aus gui/worker.py, mit Attrappen statt Qt-Signalen."""

    def setUp(self):
        from fevdl.gui import worker

        self.worker = worker
        self.notifier = types.SimpleNamespace(ytdlpUpdated=MagicMock(), appUpdateFound=MagicMock())

    def _run(self, ytdlp=None, app=None, **kwargs):
        with (
            patch.object(self.worker, "auto_update_ytdlp", side_effect=ytdlp if isinstance(ytdlp, Exception) else None,
                         return_value=None if isinstance(ytdlp, Exception) else ytdlp),
            patch.object(self.worker.appupdate, "check", side_effect=app if isinstance(app, Exception) else None,
                         return_value=None if isinstance(app, Exception) else app),
        ):
            self.worker.run_startup_checks(self.notifier, **kwargs)

    def test_meldet_neues_ytdlp_und_neue_app(self):
        release = AppRelease("9.9.9", GOOD_URL, 1, None, "", "p")
        self._run(ytdlp=update.UpdateResult(True, "2099.1.1", "m"), app=release)
        self.notifier.ytdlpUpdated.emit.assert_called_once_with("2099.1.1")
        self.notifier.appUpdateFound.emit.assert_called_once_with(release)

    def test_schweigt_wenn_nichts_neu_ist(self):
        self._run(ytdlp=update.UpdateResult(False, "x", "m"), app=None)
        self.notifier.ytdlpUpdated.emit.assert_not_called()
        self.notifier.appUpdateFound.emit.assert_not_called()

    def test_fehler_bleiben_still(self):
        self._run(ytdlp=URLError("offline"))
        self._run(app=UpdateError("kein Netz"))
        self.notifier.appUpdateFound.emit.assert_not_called()

    def test_geschlossenes_fenster_stoert_nicht(self):
        self.notifier.appUpdateFound.emit.side_effect = RuntimeError("Signal source has been deleted")
        release = AppRelease("9.9.9", GOOD_URL, 1, None, "", "p")
        self._run(app=release)   # darf keine Ausnahme werfen


if __name__ == "__main__":
    unittest.main()
