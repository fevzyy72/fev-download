"""
Aktualisierung im Fenster: Menuepunkt, Angebot, Download, Installer-Start.

Ohne Netz und ohne echten Installer. Alles Modale (QMessageBox) wird durch
Attrappen ersetzt, sonst wuerde der Test auf einen Klick warten.
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Keine Fenster auf dem Bildschirm des Entwicklers.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from fevdl import paths
from fevdl.core import appupdate
from fevdl.core.appupdate import AppRelease, UpdateError
from fevdl.core.update import UpdateResult
from fevdl.gui import typography
from fevdl.gui import main_window as mw
from fevdl.gui.main_window import MainWindow

paths.RESULT_FILE = Path(tempfile.mkdtemp(prefix="fevupdgui_")) / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())
app.setApplicationName("Fev Download")
app.setOrganizationName("fezco")

RELEASE = AppRelease("9.9.9", appupdate.DOWNLOAD_PREFIX + "v9.9.9/FevDownloadSetup.exe",
                     10, None, "Neu: Dinge.", "https://github.com/x/y/releases/tag/v9.9.9")
YTDLP_OK = UpdateResult(False, "2026.10.26", "Bereits auf dem neuesten Stand (2026.10.26).")


def wait_for(condition, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


class UpdateGuiTests(unittest.TestCase):
    def setUp(self):
        QSettings("fezco", "Fev Download").clear()
        self.window = MainWindow(job=None)
        # Erfundene Links duerfen keine echten Downloads ausloesen.
        self.window._start_preview_fallback = lambda: None

    def tearDown(self):
        self.window.close()
        app.processEvents()
        QSettings("fezco", "Fev Download").clear()

    # -- Menuepunkt ----------------------------------------------------

    def test_menuepunkt_heisst_wie_in_den_fehlermeldungen(self):
        # errors.py verweist die Nutzer auf genau diesen Text.
        self.assertEqual(self.window.action_update_ytdlp.text(), "Nach Aktualisierung suchen")

    def test_alles_aktuell(self):
        with (
            patch("fevdl.core.update.update_ytdlp", return_value=YTDLP_OK),
            patch.object(appupdate, "check", return_value=None),
            patch.object(QMessageBox, "information") as info,
            patch.object(QMessageBox, "warning") as warn,
        ):
            self.window._check_updates()
        warn.assert_not_called()
        text = info.call_args.args[2]
        self.assertIn("yt-dlp", text)
        self.assertIn("ist aktuell", text)
        self.assertTrue(self.window.action_update_ytdlp.isEnabled())

    def test_beide_pruefungen_scheitern_ohne_absturz(self):
        with (
            patch("fevdl.core.update.update_ytdlp", side_effect=OSError("kein Netz")),
            patch.object(appupdate, "check", side_effect=UpdateError("GitHub weg")),
            patch.object(QMessageBox, "warning") as warn,
        ):
            self.window._check_updates()
        text = warn.call_args.args[2]
        self.assertIn("kein Netz", text)
        self.assertIn("GitHub weg", text)
        self.assertTrue(self.window.action_update_ytdlp.isEnabled())

    def test_neue_fassung_wird_angeboten_und_abgelehnt(self):
        with (
            patch("fevdl.core.update.update_ytdlp", return_value=YTDLP_OK),
            patch.object(appupdate, "check", return_value=RELEASE),
            patch.object(QMessageBox, "question", return_value=QMessageBox.No) as ask,
            patch.object(self.window, "_install_app_update") as install,
        ):
            self.window._check_updates()
        text = ask.call_args.args[2]
        self.assertIn("9.9.9", text)
        self.assertIn("Neu: Dinge.", text)
        self.assertIn("yt-dlp", text, "Das Ergebnis der yt-dlp-Suche soll im selben Dialog stehen")
        install.assert_not_called()
        self.assertIn("wartet", self.window.status_label.text())

    def test_neue_fassung_wird_angenommen(self):
        with (
            patch("fevdl.core.update.update_ytdlp", return_value=YTDLP_OK),
            patch.object(appupdate, "check", return_value=RELEASE),
            patch.object(QMessageBox, "question", return_value=QMessageBox.Yes),
            patch.object(self.window, "_install_app_update") as install,
        ):
            self.window._check_updates()
        install.assert_called_once_with(RELEASE)

    # -- Installieren --------------------------------------------------

    def test_aus_dem_quelltext_wird_nur_die_seite_geoeffnet(self):
        self.assertFalse(paths.IS_FROZEN, "Der Test setzt Quelltext-Betrieb voraus")
        with patch.object(mw.QDesktopServices, "openUrl") as open_url, \
                patch.object(appupdate, "download_installer") as download:
            self.window._install_app_update(RELEASE)
        self.assertEqual(open_url.call_args.args[0].toString(), RELEASE.page)
        download.assert_not_called()

    def test_laufender_download_haelt_das_update_auf(self):
        running = MagicMock()
        running.isRunning.return_value = True
        self.window._download_worker = running
        with (
            patch.object(paths, "IS_FROZEN", True),
            patch.object(QMessageBox, "information") as info,
            patch.object(appupdate, "download_installer") as download,
        ):
            self.window._install_app_update(RELEASE)
        info.assert_called_once()
        download.assert_not_called()
        self.assertIsNone(self.window._app_update_dialog)
        self.window._download_worker = None

    def test_download_dann_installer_dann_schliessen(self):
        installer = Path(tempfile.mkdtemp(prefix="fevupdinst_")) / "FevDownloadSetup-9.9.9.exe"
        installer.write_bytes(b"MZ")
        with (
            patch.object(paths, "IS_FROZEN", True),
            patch.object(appupdate, "download_installer", return_value=installer) as download,
            patch.object(appupdate, "launch_installer") as launch,
            patch.object(self.window, "close") as close,
        ):
            self.window._install_app_update(RELEASE)
            self.assertTrue(wait_for(lambda: launch.called), "Der Installer wurde nicht gestartet")
        download.assert_called_once()
        launch.assert_called_once_with(installer)
        close.assert_called_once()
        self.assertIsNone(self.window._app_update_dialog, "Der Fortschrittsdialog muss weg sein")

    def test_fehlgeschlagener_download_startet_nichts(self):
        with (
            patch.object(paths, "IS_FROZEN", True),
            patch.object(appupdate, "download_installer", side_effect=UpdateError("Pruefsumme falsch")),
            patch.object(appupdate, "launch_installer") as launch,
            patch.object(QMessageBox, "warning") as warn,
            patch.object(self.window, "close") as close,
        ):
            self.window._install_app_update(RELEASE)
            self.assertTrue(wait_for(lambda: warn.called), "Keine Fehlermeldung")
        launch.assert_not_called()
        close.assert_not_called()
        text = warn.call_args.args[2]
        self.assertIn("Pruefsumme falsch", text)
        self.assertIn(appupdate.RELEASES_PAGE, text, "Der Weg per Hand muss genannt werden")
        self.assertIsNone(self.window._app_update_dialog)

    def test_installer_laesst_sich_nicht_starten(self):
        installer = Path(tempfile.mkdtemp(prefix="fevupdinst_")) / "x.exe"
        installer.write_bytes(b"MZ")
        with (
            patch.object(paths, "IS_FROZEN", True),
            patch.object(appupdate, "download_installer", return_value=installer),
            patch.object(appupdate, "launch_installer", side_effect=OSError("gesperrt")),
            patch.object(QMessageBox, "warning") as warn,
            patch.object(self.window, "close") as close,
        ):
            self.window._install_app_update(RELEASE)
            self.assertTrue(wait_for(lambda: warn.called))
        close.assert_not_called()
        self.assertIn("gesperrt", warn.call_args.args[2])

    # -- Pruefung beim Start -------------------------------------------

    def test_start_pruefung_laeuft_nicht_aus_dem_quelltext(self):
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(mw, "start_startup_check") as start,
        ):
            os.environ.pop("FEVDL_UPDATE_CHECK", None)
            os.environ.pop("FEVDL_NO_UPDATE_CHECK", None)
            self.window.start_background_update_check()
        start.assert_not_called()

    def test_start_pruefung_im_installierten_programm(self):
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(paths, "IS_FROZEN", True),
            patch.object(mw, "start_startup_check") as start,
        ):
            os.environ.pop("FEVDL_NO_UPDATE_CHECK", None)
            self.window.start_background_update_check()
        start.assert_called_once()
        self.assertIs(start.call_args.args[0], self.window._update_notifier)

    def test_start_pruefung_laesst_sich_abschalten(self):
        with (
            patch.dict(os.environ, {"FEVDL_NO_UPDATE_CHECK": "1"}),
            patch.object(paths, "IS_FROZEN", True),
            patch.object(mw, "start_startup_check") as start,
        ):
            self.window.start_background_update_check()
        start.assert_not_called()

    def test_jede_fassung_wird_nur_einmal_angeboten(self):
        with patch.object(self.window, "_offer_app_update") as offer:
            self.window._on_app_update_found(RELEASE)
            self.window._on_app_update_found(RELEASE)
        offer.assert_called_once_with(RELEASE)
        self.assertIn("9.9.9", self.window.status_label.text())

    def test_neuere_fassung_wird_wieder_angeboten(self):
        newer = AppRelease("10.0.0", RELEASE.url, 1, None, "", "p")
        with patch.object(self.window, "_offer_app_update") as offer:
            self.window._on_app_update_found(RELEASE)
            self.window._on_app_update_found(newer)
        self.assertEqual(offer.call_count, 2)

    def test_waehrend_eines_downloads_wird_nicht_gestoert(self):
        running = MagicMock()
        running.isRunning.return_value = True
        self.window._download_worker = running
        with patch.object(self.window, "_offer_app_update") as offer:
            self.window._on_app_update_found(RELEASE)
        offer.assert_not_called()
        self.window._download_worker = None

    def test_ytdlp_meldung_ist_unaufdringlich(self):
        self.window._on_ytdlp_updated("2099.1.1")
        self.assertIn("2099.1.1", self.window.status_label.text())


if __name__ == "__main__":
    unittest.main()
