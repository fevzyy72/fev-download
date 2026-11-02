"""
Formatwahl der Ausweich-Vorschau, ohne Netz.

Hintergrund: YouTube bietet keine fertigen Dateien mit Bild UND Ton mehr an.
Der frueher verwendete Ausdruck kannte nur solche Dateien und scheiterte dort
mit "Requested format is not available" - die Vorschau blieb leer. Dieser Test
laesst yt-dlps eigene Auswahl ueber nachgebaute Formatlisten laufen und prueft,
dass fuer jede Art von Seite etwas Abspielbares herauskommt.
"""

import unittest

from yt_dlp import YoutubeDL

from fevdl.core.download import PREVIEW_FORMAT


def _format(format_id, ext, vcodec, acodec, height=None):
    return {
        "format_id": format_id,
        "ext": ext,
        "vcodec": vcodec,
        "acodec": acodec,
        "height": height,
        "width": int(height * 16 / 9) if height else None,
        "url": "https://example.invalid/" + format_id,
        "protocol": "https",
        "tbr": float(height or 64),
    }


def _select(formats):
    """Laesst yt-dlp waehlen und gibt die Kennungen der gewaehlten Formate zurueck."""
    ydl = YoutubeDL({"format": PREVIEW_FORMAT, "quiet": True, "no_warnings": True})
    info = {
        "id": "test",
        "title": "Test",
        "extractor": "test",
        "extractor_key": "Test",
        "webpage_url": "https://example.invalid/test",
        "formats": formats,
    }
    chosen = ydl.process_video_result(info, download=False)
    return [item["format_id"] for item in (chosen.get("requested_formats") or [chosen])]


def _youtube_ohne_fertige_dateien():
    """Nur getrennte Spuren - so liefert YouTube derzeit."""
    video = [
        _format("160", "mp4", "avc1.4d400c", "none", 144),
        _format("133", "mp4", "avc1.4d4015", "none", 240),
        _format("134", "mp4", "avc1.4d401e", "none", 360),
        _format("135", "mp4", "avc1.4d401f", "none", 480),
        _format("136", "mp4", "avc1.4d401f", "none", 720),
        _format("137", "mp4", "avc1.640028", "none", 1080),
        _format("247", "webm", "vp9", "none", 720),
        _format("248", "webm", "vp9", "none", 1080),
    ]
    audio = [
        _format("140", "m4a", "none", "mp4a.40.2"),
        _format("251", "webm", "none", "opus"),
    ]
    return video + audio


class PreviewFormatTests(unittest.TestCase):
    def test_getrennte_spuren_werden_zusammengesetzt(self):
        # Genau der Fall, der frueher scheiterte.
        self.assertEqual(_select(_youtube_ohne_fertige_dateien()), ["135", "140"])

    def test_ohne_avc1_geht_es_mit_anderen_codecs(self):
        formats = [
            _format("247", "webm", "vp9", "none", 480),
            _format("251", "webm", "none", "opus"),
        ]
        self.assertEqual(_select(formats), ["247", "251"])

    def test_fertige_datei_hat_vorrang(self):
        # So liefern TikTok und viele andere Seiten ihre Videos.
        formats = [
            _format("mp4-360", "mp4", "avc1", "mp4a", 360),
            _format("mp4-720", "mp4", "avc1", "mp4a", 720),
        ]
        self.assertEqual(_select(formats), ["mp4-360"])

    def test_fertige_datei_vor_getrennten_spuren(self):
        formats = _youtube_ohne_fertige_dateien() + [
            _format("18", "mp4", "avc1.42001E", "mp4a.40.2", 360),
        ]
        self.assertEqual(_select(formats), ["18"])

    def test_nur_grosse_fertige_datei_wird_genommen(self):
        # Lieber eine grosse Vorschau als gar keine.
        formats = [_format("mp4-1080", "mp4", "avc1", "mp4a", 1080)]
        self.assertEqual(_select(formats), ["mp4-1080"])

    def test_hochformat_ohne_hoehenangabe_unter_540(self):
        # TikTok: 1080 x 1920 zaehlt als Hoehe 1920 und wird als Ganzes genommen.
        formats = [_format("tt", "mp4", "h264", "aac", 1920)]
        self.assertEqual(_select(formats), ["tt"])


if __name__ == "__main__":
    unittest.main()
