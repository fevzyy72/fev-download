"""Regressionspruefungen fuer TikTok-Metadaten und Aktualisierungen, ohne Netz."""

import unittest
from unittest.mock import patch

from fevdl.core.errors import humanize
from fevdl.core.probe import _collect_qualities, probe
from fevdl.core.update import current_version, update_ytdlp


class TikTokMetadataTests(unittest.TestCase):
    def test_video_ohne_fps_bleibt_video(self):
        formats = [
            {"vcodec": "none", "acodec": "mp3"},
            {"vcodec": "h264", "height": 1024, "width": 576},
            {"vcodec": "h265", "height": 1920, "width": 1080},
            {"vcodec": "h265", "height": 1920, "width": 1080},
        ]
        qualities = _collect_qualities(formats)
        self.assertEqual([q.height for q in qualities], [1920, 1024])
        self.assertTrue(all(q.fps is None for q in qualities))

    def test_bekannte_fps_werden_bevorzugt(self):
        qualities = _collect_qualities([
            {"vcodec": "h264", "height": 720},
            {"vcodec": "h264", "height": 720, "fps": 60},
            {"vcodec": "h264", "height": 720, "fps": 30},
            {"vcodec": "h264", "height": 720},
        ])
        self.assertEqual(len(qualities), 1)
        self.assertEqual(qualities[0].fps, 60)

    def test_probe_erkennt_hochformat_ohne_fps(self):
        video = {
            "title": "TikTok-Test", "duration": 19, "extractor_key": "TikTok",
            "formats": [{
                "vcodec": "h264", "acodec": "aac", "height": 1920,
                "width": 1080, "url": "https://example.com/video.mp4",
                "ext": "mp4", "protocol": "https",
            }],
        }
        with patch("fevdl.core.probe.YoutubeDL") as ydl:
            ydl.return_value.__enter__.return_value.extract_info.return_value = video
            info = probe("https://www.tiktok.com/@test/video/123")
        self.assertTrue(info.has_video)
        self.assertTrue(info.is_portrait)
        self.assertEqual(info.best_height, 1920)
        self.assertEqual(info.preview_url, "https://example.com/video.mp4")

    def test_reine_tonquelle_bleibt_tonquelle(self):
        self.assertEqual(_collect_qualities([
            {"vcodec": "none", "height": 1080, "fps": 30},
        ]), [])


class UpdateTests(unittest.TestCase):
    def test_identische_fassung_mit_fuehrenden_nullen(self):
        with (
            patch("fevdl.core.update.current_version", return_value="2026.08.19"),
            patch("fevdl.core.update.latest_version", return_value=("2026.8.19", "unused")),
            patch("fevdl.core.update._fetch") as fetch,
        ):
            result = update_ytdlp()
        self.assertFalse(result.changed)
        fetch.assert_not_called()

    def test_kein_downgrade(self):
        with (
            patch("fevdl.core.update.current_version", return_value="2026.09.30"),
            patch("fevdl.core.update.latest_version", return_value=("2026.8.19", "unused")),
            patch("fevdl.core.update._fetch") as fetch,
        ):
            self.assertFalse(update_ytdlp().changed)
        fetch.assert_not_called()

    def test_neuere_fassung_wird_installiert(self):
        with (
            patch("fevdl.core.update.current_version", return_value="2026.07.04"),
            patch("fevdl.core.update.latest_version", return_value=("2026.8.19", "wheel")),
            patch("fevdl.core.update._fetch", return_value=b"wheel") as fetch,
            patch("fevdl.core.update._extract_wheel") as extract,
            # Sonst hinge der Test davon ab, was auf diesem Rechner schon nachgeladen ist.
            patch("fevdl.paths.installed_ytdlp_version", return_value=None),
        ):
            result = update_ytdlp()
        self.assertTrue(result.changed)
        fetch.assert_called_once_with("wheel")
        extract.assert_called_once()

    def test_fassung_ist_die_geladene(self):
        from yt_dlp.version import __version__
        with patch("fevdl.paths.installed_ytdlp_version", return_value="2099.01.01"):
            self.assertEqual(current_version(), __version__)


class ErrorTests(unittest.TestCase):
    def test_tiktok_blockierung_ist_verstaendlich(self):
        message = humanize("ERROR: [TikTok] 123: Unexpected response from webpage request")
        self.assertIn("TikTok", message)
        self.assertIn("Aktualisierung", message)
        self.assertNotIn("report this issue", message)

    def test_tiktok_anmeldung_ist_verstaendlich(self):
        message = humanize("ERROR: [TikTok] 123: TikTok is requiring login for access to this content")
        self.assertIn("Anmeldung", message)

    def test_private_videos_bleiben_unterscheidbar(self):
        self.assertEqual(humanize("ERROR: [TikTok] 123: Private video"), "Das Video ist privat.")


if __name__ == "__main__":
    unittest.main()
