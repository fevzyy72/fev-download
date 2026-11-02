"""Sicherheitsgrenzen ohne Netz und ohne echte Prozesse pruefen."""

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

from yt_dlp import YoutubeDL

from fevdl import paths
from fevdl.ipc import read_job
from fevdl.core import appupdate, download, probe, transport, update, waveform
from fevdl.core.errors import DownloadError, ProbeError
from fevdl.core.models import DownloadRequest


class IPCTests(unittest.TestCase):
    def test_kaputtes_job_schema_wird_abgewiesen(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "job.json"
            for data in ({"job_id": "x", "output_dir": []}, {"job_id": 42}, {"output_dir": "C:/a"}):
                file.write_text(json.dumps(data), encoding="utf-8")
                self.assertIsNone(read_job(file))

    def test_startbefehl_ist_eine_liste_und_resultat_keine_befehlsquelle(self):
        file = Path(__file__).resolve().parents[1] / "resolve/FevDownloader.py"
        spec = importlib.util.spec_from_file_location("security_launcher", file)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        executable = r"C:\Programme mit Leerzeichen\FevDownload.exe"
        with patch.object(launcher.subprocess, "Popen") as popen:
            launcher.start_interface([executable], r"C:\Programme mit Leerzeichen")
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [executable, "--job", launcher.JOB_FILE])
        self.assertFalse(kwargs.get("shell", False))
        for files in ("C:/a.mp4", [{}], [None], 42):
            self.assertEqual(launcher.pending_files({"job_id": "x", "files": files}, "x", set()), [])
        absolute = str(Path(tempfile.gettempdir()) / "clip.mp4")
        self.assertEqual(launcher.pending_files({"job_id": "x", "files": [absolute]}, "y", set()), [])
        self.assertEqual(launcher.pending_files({"job_id": "x", "files": [absolute]}, "x", set()), [absolute])


class TransportTests(unittest.TestCase):
    def test_weiterleitung_vor_dem_naechsten_request_pruefen(self):
        hosts = appupdate.DOWNLOAD_HOSTS
        handler = transport._CheckedRedirects(hosts)
        request = Request(appupdate.DOWNLOAD_PREFIX + "v2/FevDownloadSetup.exe")
        for url in ("http://github.com/a", "https://evil.example/a",
                    "https://github.com.evil.example/a", "https://github.com:444/a",
                    "https://user:pass@github.com/a", "file:///C:/Windows/test.exe",
                    "https://github.com/a\\b"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, url)
        redirected = handler.redirect_request(
            request, None, 302, "Found", {},
            "https://release-assets.githubusercontent.com/github-production-release-asset/a")
        self.assertEqual(redirected.host, "release-assets.githubusercontent.com")

    def test_startadresse_ohne_netz_abgewiesen(self):
        with patch.object(transport, "build_opener") as opener, self.assertRaises(ValueError):
            transport.open_https(Request("http://pypi.org/a"), 1, frozenset({"pypi.org"}))
        opener.assert_not_called()


class WheelTests(unittest.TestCase):
    def test_metadaten_brauchen_eine_gueltige_pruefsumme(self):
        data = {"info": {"version": "2099.1.1"}, "urls": [
            {"packagetype": "bdist_wheel", "url": "https://files.pythonhosted.org/x.whl"}]}
        with patch.object(update, "_fetch", return_value=json.dumps(data).encode()):
            with self.assertRaises(RuntimeError):
                update.latest_version()
        data["urls"][0]["digests"] = {"sha256": "AB" * 32}
        with patch.object(update, "_fetch", return_value=json.dumps(data).encode()):
            self.assertEqual(update.latest_version()[2], "ab" * 32)

    def test_falscher_hash_erreicht_das_entpacken_nicht(self):
        with (patch.object(update, "current_version", return_value="2000.1.1"),
              patch.object(update, "latest_version", return_value=("2099.1.1", "wheel", "00" * 32)),
              patch.object(paths, "installed_ytdlp_version", return_value=None),
              patch.object(update, "_fetch", return_value=b"manipuliert"),
              patch.object(update, "_extract_wheel") as extract):
            with self.assertRaises(RuntimeError):
                update.update_ytdlp()
        extract.assert_not_called()

    def test_nur_paket_und_keine_sonderpfade(self):
        for name in ("yt_dlp/../../ausbruch.py", "yt_dlp/a\\..\\ausbruch.py",
                     "yt_dlp/datei:strom", "yt_dlp/a./datei.py"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / "ytdlp"
                target.mkdir()
                (target / "alt.txt").write_text("unveraendert")
                data = io.BytesIO()
                with zipfile.ZipFile(data, "w") as archive:
                    archive.writestr("yt_dlp/version.py", "__version__ = '2099.1.1'")
                    archive.writestr(name, "ungueltig")
                with self.assertRaises(RuntimeError):
                    update._extract_wheel(data.getvalue(), target)
                self.assertEqual((target / "alt.txt").read_text(), "unveraendert")
                self.assertFalse(target.with_name("ytdlp.neu").exists())

    def test_gueltiges_rad_ersetzt_nur_das_paket(self):
        with tempfile.TemporaryDirectory() as folder:
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as archive:
                archive.writestr("yt_dlp/__init__.py", "")
                archive.writestr("yt_dlp/version.py", "__version__ = '2099.1.1'")
                archive.writestr("anderes_paket/__init__.py", "nicht laden")
            target = Path(folder) / "ytdlp"
            update._extract_wheel(data.getvalue(), target)
            self.assertTrue((target / "yt_dlp/version.py").is_file())
            self.assertFalse((target / "anderes_paket").exists())


class LinkTests(unittest.TestCase):
    def test_fremde_schemata_starten_weder_yt_dlp_noch_ffmpeg(self):
        for url in (r"C:\Videos\a.mp4", "file:///C:/Videos/a.mp4", "ftp://example.com/a",
                    "javascript:alert(1)", "https://", "https://example.com:kaputt/a",
                    "https://example.com/a\nHeader:wert"):
            with self.subTest(url=url), patch.object(probe, "YoutubeDL") as ydl:
                with self.assertRaises(ProbeError):
                    probe.probe(url)
                ydl.assert_not_called()
            with self.subTest(url=url), patch.object(download, "YoutubeDL") as ydl:
                with self.assertRaises(DownloadError):
                    download.download(DownloadRequest(url=url, output_dir=Path("irrelevant")))
                with self.assertRaises(DownloadError):
                    download.download_preview(url, Path("irrelevant"))
                ydl.assert_not_called()
            with patch.object(waveform.subprocess, "Popen") as popen:
                with self.assertRaises(waveform.WaveformError):
                    waveform.extract_peaks(url, 1)
                popen.assert_not_called()

    def test_windows_titel_bleiben_im_zielordner(self):
        with tempfile.TemporaryDirectory() as folder:
            request = DownloadRequest(url="https://example.com/a", output_dir=Path(folder))
            options = download._build_options(request, lambda _: None, None)
            with YoutubeDL(options) as ydl:
                for title in ("../../ausbruch", r"..\..\ausbruch", "CON", "NUL", "a" * 400):
                    filename = Path(ydl.prepare_filename({"title": title, "id": "x", "ext": "mp4"}))
                    self.assertEqual(filename.parent.resolve(), Path(folder).resolve())
                    self.assertLess(len(filename.name), 150)


class InstallerTests(unittest.TestCase):
    def test_parallele_downloads_teilen_keine_datei(self):
        payload = b"MZ-test"
        release = appupdate.AppRelease("2.0.0", appupdate.DOWNLOAD_PREFIX + "v2/x.exe",
                                       len(payload), hashlib.sha256(payload).hexdigest(), "", "")

        class Response(io.BytesIO):
            headers = {}

        with tempfile.TemporaryDirectory() as folder, patch.object(appupdate, "update_dir", return_value=Path(folder)):
            with patch.object(appupdate, "_open", side_effect=lambda *args: Response(payload)):
                first = appupdate.download_installer(release)
                second = appupdate.download_installer(release)
            self.assertNotEqual(first.parent, second.parent)
            self.assertEqual(first.read_bytes(), payload)
            self.assertEqual(second.read_bytes(), payload)
            with patch.object(appupdate, "_open") as opened:
                with self.assertRaises(appupdate.UpdateError):
                    appupdate.download_installer(replace(release, version="../../ausbruch"))
                opened.assert_not_called()

    def test_leere_datei_ist_auch_ohne_hash_kein_installer(self):
        release = appupdate.AppRelease("2.0.0", appupdate.DOWNLOAD_PREFIX + "v2/x.exe", 0, None, "", "")
        with tempfile.TemporaryDirectory() as folder, patch.object(appupdate, "update_dir", return_value=Path(folder)):
            response = io.BytesIO()
            response.headers = {}
            with patch.object(appupdate, "_open", return_value=response), self.assertRaises(appupdate.UpdateError):
                appupdate.download_installer(release)
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
