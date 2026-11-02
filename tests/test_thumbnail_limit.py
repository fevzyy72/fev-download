"""Vorschaubild: nur http/https und hoechstens MAX_BYTES (ohne Internet, lokaler Server)."""

import http.server
import threading
import unittest

from fevdl.gui.worker import ThumbnailWorker


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/klein":
            body = b"x" * 1000
        elif self.path == "/gross":
            body = b"x" * (ThumbnailWorker.MAX_BYTES + 5)
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass  # Client hat nach der Grenze abgebrochen

    def log_message(self, *args):
        pass


def _lade(url):
    """run() direkt aufrufen - kein Thread noetig, Signal geht an eine Liste."""
    ergebnis = []
    worker = ThumbnailWorker(url)
    worker.loaded.connect(ergebnis.append)
    worker.run()
    return ergebnis


class ThumbnailLimitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_kleines_bild_kommt_an(self):
        self.assertEqual(len(_lade(f"http://127.0.0.1:{self.port}/klein")), 1)

    def test_zu_grosses_bild_wird_verworfen(self):
        self.assertEqual(_lade(f"http://127.0.0.1:{self.port}/gross"), [])

    def test_fremde_schemata_werden_nicht_geoeffnet(self):
        for url in ("file:///C:/Windows/win.ini", "ftp://127.0.0.1/x", "C:\\Windows\\win.ini"):
            self.assertEqual(_lade(url), [], url)


if __name__ == "__main__":
    unittest.main()
