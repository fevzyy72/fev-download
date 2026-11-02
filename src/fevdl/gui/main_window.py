"""Das Hauptfenster des FevDownloaders."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QElapsedTimer, QSettings, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import paths
from ..core import appupdate
from ..core.models import (
    DownloadRequest,
    Mode,
    Progress,
    VideoInfo,
    format_timecode,
    parse_timecode,
)
from ..core.probe import pick_height
from ..ipc import Job, ResultWriter
from . import typography
from .library_page import LibraryPage
from .preview_player import PreviewPlayer
from .style import STYLESHEET
from .trim_bar import TrimBar
from .worker import (
    AppUpdateWorker,
    DownloadWorker,
    PreviewWorker,
    ProbeWorker,
    ThumbnailWorker,
    UpdateNotifier,
    WaveformWorker,
    start_startup_check,
)


class MainWindow(QMainWindow):
    def __init__(self, job: Optional[Job] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fev Download")
        self.setMinimumSize(860, 620)
        self.resize(1000, 960)
        self.setStyleSheet(STYLESHEET)

        self._info: Optional[VideoInfo] = None
        self._probe_worker: Optional[ProbeWorker] = None
        self._thumb_worker: Optional[ThumbnailWorker] = None
        self._download_worker: Optional[DownloadWorker] = None
        self._waveform_worker: Optional[WaveformWorker] = None
        self._waveform_peaks: list[float] = []
        self._preview_worker: Optional[PreviewWorker] = None
        self._preview_file: Optional[Path] = None
        self._preview_attempted_download = False
        # Aktualisierung der App selbst (siehe core/appupdate.py)
        self._app_update_worker: Optional[AppUpdateWorker] = None
        self._app_update_dialog: Optional[QProgressDialog] = None
        self._update_notifier: Optional[UpdateNotifier] = None
        # Nach einem fertigen Download wird aus dem Knopf ein Abschluss-Knopf,
        # damit man nicht versehentlich dasselbe noch einmal laedt.
        self._completed = False

        # Gemerkte Stellen desselben Videos, jeweils (Anfang, Ende) in Sekunden.
        # Ist die Liste gefuellt, wird sie geladen und nicht der Balken.
        self._segments: list[tuple[float, float]] = []
        self._finished_files: list[Path] = []
        # Beim Ziehen eines Griffs wird das Spulen gedrosselt - sonst bekommt
        # der Player mehr Sprungbefehle, als er verarbeiten kann.
        self._scrub_clock = QElapsedTimer()
        self._scrub_clock.start()

        # Wurde die Oberflaeche aus Resolve heraus gestartet, meldet sie jede
        # fertige Datei zurueck - das Script dort holt sie in den Media Pool.
        self._job = job
        self._results: Optional[ResultWriter] = None
        if job is not None:
            self._results = ResultWriter(path=paths.RESULT_FILE, job_id=job.job_id)

        self.setAcceptDrops(True)
        if paths.ICON_FILE.is_file():
            self.setWindowIcon(QIcon(str(paths.ICON_FILE)))

        self._settings = QSettings("fezco", "Fev Download")

        self._build_menu()
        self._build_ui()
        self._connect_signals()
        self._restore_settings()
        self._apply_job()
        self._prefill_from_clipboard()
        self._set_state_idle()

    # ------------------------------------------------------------------
    # Gemerkte Einstellungen
    # ------------------------------------------------------------------

    def _restore_settings(self) -> None:
        """Holt die Einstellungen der letzten Sitzung zurueck."""
        # Nur ein selbst gewaehlter Ordner zaehlt als Entscheidung. Wuerde
        # jeder Wert gespeichert, gaelte schon die Vorgabe des allerersten
        # Starts als Wahl und Resolves Vorschlag kaeme nie wieder zum Zug.
        self._output_user_set = self._settings.value("output_user_set", False, type=bool)
        saved_output = self._settings.value("output_dir", "", type=str)
        if saved_output:
            self.output_edit.setText(saved_output)

        saved_mode = self._settings.value("mode", "", type=str)
        index = self.mode_combo.findData(saved_mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)

        self._preferred_height = self._settings.value("height", 1080, type=int)
        self.h264_check.setChecked(self._settings.value("prefer_h264", True, type=bool))

        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self._size_to_screen()

    def _size_to_screen(self) -> None:
        """
        Beim ersten Start das Fenster gross oeffnen.

        Ein festes Mass waere entweder auf grossen Bildschirmen verschenkt oder
        auf kleinen zu gross. Darum richtet es sich nach dem verfuegbaren Platz.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        width = min(1180, int(available.width() * 0.72))
        height = int(available.height() * 0.94)
        self.resize(max(self.minimumWidth(), width), max(self.minimumHeight(), height))
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _store_settings(self) -> None:
        """Sichert die Einstellungen fuer das naechste Mal."""
        self._settings.setValue("output_dir", self.output_edit.text().strip())
        self._settings.setValue("output_user_set", self._output_user_set)
        self._settings.setValue("mode", self._current_mode().value)
        self._settings.setValue("prefer_h264", self.h264_check.isChecked())
        height = self.quality_combo.currentData()
        if height:
            self._settings.setValue("height", int(height))
        self._settings.setValue("geometry", self.saveGeometry())

    def _prefill_from_clipboard(self) -> None:
        """
        Traegt einen Link aus der Zwischenablage schon einmal ein.

        Bewusst ohne Analyse - das Feld ist nur vorbereitet und ausgewaehlt,
        ein Druck auf die Eingabetaste genuegt. Ungefragt Daten nachzuladen
        waere uebergriffig.
        """
        text = (QApplication.clipboard().text() or "").strip()
        if not text or self.url_edit.text().strip():
            return
        if not text.lower().startswith(("http://", "https://")):
            return
        if len(text) > 2000 or "\n" in text:
            return
        self.url_edit.setText(text)
        self.url_edit.selectAll()
        self.url_edit.setFocus()
        self._set_status("Link aus der Zwischenablage uebernommen - Eingabetaste zum Analysieren.")

    def _apply_job(self) -> None:
        """Uebernimmt die Vorgaben aus Resolve, sofern von dort gestartet."""
        if self._job is None:
            self.banner_container.setVisible(False)
            return

        # Ein selbst gewaehlter Zielordner hat Vorrang vor der Vorgabe aus
        # Resolve - sonst wuerde die eigene Wahl bei jedem Start ueberschrieben.
        if self._job.output_dir and not self._output_user_set:
            self.output_edit.setText(str(self._job.output_dir))

        project = self._job.project or "unbenannt"
        self.resolve_banner.setText(
            f"Mit DaVinci Resolve verbunden  ·  Projekt „{project}“  ·  "
            "fertige Clips landen automatisch im Media Pool"
        )
        self.banner_container.setVisible(True)

    # ------------------------------------------------------------------
    # Menue
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&Datei")

        self.action_paste = QAction("Link aus Zwischenablage", self)
        self.action_paste.setShortcut(QKeySequence("Ctrl+V"))
        self.action_paste.triggered.connect(self._paste_from_clipboard)
        file_menu.addAction(self.action_paste)

        self.action_analyse = QAction("Analysieren", self)
        self.action_analyse.setShortcut(QKeySequence("Ctrl+Return"))
        self.action_analyse.triggered.connect(self._start_probe)
        file_menu.addAction(self.action_analyse)

        file_menu.addSeparator()

        self.action_choose_dir = QAction("Zielordner waehlen...", self)
        self.action_choose_dir.setShortcut(QKeySequence("Ctrl+O"))
        self.action_choose_dir.triggered.connect(self._choose_output_dir)
        file_menu.addAction(self.action_choose_dir)

        self.action_open_dir = QAction("Zielordner oeffnen", self)
        self.action_open_dir.triggered.connect(self._open_output_dir)
        file_menu.addAction(self.action_open_dir)

        self.action_library = QAction("Bibliothek", self)
        self.action_library.setShortcut(QKeySequence("Ctrl+L"))
        self.action_library.triggered.connect(self._show_library)
        file_menu.addAction(self.action_library)

        file_menu.addSeparator()

        action_quit = QAction("Beenden", self)
        action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        action_quit.triggered.connect(self.close)
        file_menu.addAction(action_quit)

        edit_menu = menu.addMenu("&Ausschnitt")

        self.action_mark_in = QAction("Anfang auf Abspielposition", self)
        self.action_mark_in.setShortcut(QKeySequence("I"))
        self.action_mark_in.triggered.connect(self._set_start_from_playhead)
        edit_menu.addAction(self.action_mark_in)

        self.action_mark_out = QAction("Ende auf Abspielposition", self)
        self.action_mark_out.setShortcut(QKeySequence("O"))
        self.action_mark_out.triggered.connect(self._set_end_from_playhead)
        edit_menu.addAction(self.action_mark_out)

        edit_menu.addSeparator()

        self.action_add_segment = QAction("Ausschnitt merken", self)
        self.action_add_segment.setShortcut(QKeySequence("M"))
        self.action_add_segment.triggered.connect(self._add_segment)
        edit_menu.addAction(self.action_add_segment)

        self.action_clear_segments = QAction("Gemerkte Ausschnitte verwerfen", self)
        self.action_clear_segments.triggered.connect(self._clear_segments)
        edit_menu.addAction(self.action_clear_segments)

        edit_menu.addSeparator()

        self.action_reset_trim = QAction("Ganzes Video", self)
        self.action_reset_trim.triggered.connect(self._reset_trim)
        edit_menu.addAction(self.action_reset_trim)

        help_menu = menu.addMenu("&Hilfe")

        self.action_update_ytdlp = QAction("Nach Aktualisierung suchen", self)
        self.action_update_ytdlp.triggered.connect(self._check_updates)
        help_menu.addAction(self.action_update_ytdlp)

        help_menu.addSeparator()

        action_about = QAction("Ueber Fev Download", self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Der Inhalt steckt in einem Rollbereich, damit auf kleinen
        # Bildschirmen nichts abgeschnitten wird. Die Fusszeile bleibt
        # bewusst ausserhalb - der Download-Knopf soll immer sichtbar sein,
        # ohne dass man erst scrollen muss.
        content = QWidget()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(44, 26, 44, 22)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addSpacing(14)
        root.addWidget(self._build_rule())
        root.addSpacing(14)
        root.addWidget(self._build_resolve_banner())
        root.addLayout(self._build_link_row())
        root.addSpacing(10)
        root.addWidget(self._build_info_card())
        root.addSpacing(12)
        root.addWidget(self._build_preview_section(), 1)
        root.addSpacing(12)
        root.addWidget(self._build_trim_section())
        root.addSpacing(10)
        root.addWidget(self._build_options_section())

        download_page = QWidget()
        outer = QVBoxLayout(download_page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll, 1)
        outer.addWidget(self._build_footer())

        self.library_page = LibraryPage(
            root_provider=self._library_root,
            import_file=self._import_library_file if self._results is not None else None,
        )

        self.pages = QStackedWidget()
        self.pages.addWidget(download_page)
        self.pages.addWidget(self.library_page)
        self.setCentralWidget(self.pages)

    def _build_header(self) -> QWidget:
        container = QWidget()

        hero = QLabel("Fev Download")
        hero.setObjectName("hero")
        hero.setFont(typography.hero())

        subtitle = QLabel("Laden, zuschneiden, ab nach DaVinci Resolve.")
        subtitle.setObjectName("subtitle")

        self.download_nav_button = QPushButton("Download")
        self.download_nav_button.setObjectName("navActive")
        self.library_nav_button = QPushButton("Bibliothek")
        self.library_nav_button.setObjectName("nav")

        # Nebeneinander statt untereinander: Der Kopf braucht nur eine Zeile,
        # der gewonnene Platz gehoert der Vorschau.
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(hero, 0, Qt.AlignBottom)
        layout.addWidget(subtitle, 0, Qt.AlignBottom)
        layout.addStretch(1)
        layout.addWidget(self.download_nav_button)
        layout.addWidget(self.library_nav_button)
        return container

    def _build_rule(self) -> QFrame:
        rule = QFrame()
        rule.setObjectName("rule")
        rule.setFrameShape(QFrame.HLine)
        rule.setFixedHeight(1)
        return rule

    def _build_resolve_banner(self) -> QWidget:
        # Der Streifen sitzt in einer eigenen Huelle: Wird die ausgeblendet,
        # verschwindet auch ihr Abstand. Ein blosses Ausblenden des Textes
        # wuerde eine Luecke hinterlassen.
        self.banner_container = QWidget()
        self.resolve_banner = QLabel()
        self.resolve_banner.setObjectName("banner")
        self.resolve_banner.setWordWrap(True)

        layout = QVBoxLayout(self.banner_container)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)
        layout.addWidget(self.resolve_banner)

        self.banner_container.setVisible(False)
        return self.banner_container

    def _eyebrow(self, text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("eyebrow")
        label.setFont(typography.eyebrow())
        return label

    def _build_link_row(self) -> QHBoxLayout:
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "Link einfuegen - YouTube, Vimeo, TikTok, Twitch und weitere"
        )
        self.url_edit.setClearButtonEnabled(True)

        self.analyse_button = QPushButton("Analysieren")
        self.analyse_button.setObjectName("primary")
        self.analyse_button.setMinimumWidth(124)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.url_edit, 1)
        row.addWidget(self.analyse_button)
        return row

    def _build_info_card(self) -> QWidget:
        self.info_card = QFrame()
        self.info_card.setObjectName("card")
        self.info_card.setVisible(False)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(80, 45)
        self.thumbnail_label.setObjectName("thumbnail")
        self.thumbnail_label.setAlignment(Qt.AlignCenter)

        self.title_label = QLabel()
        self.title_label.setObjectName("title")
        self.title_label.setFont(typography.title())
        self.title_label.setWordWrap(True)

        self.meta_label = QLabel()
        self.meta_label.setObjectName("muted")

        self.platform_tag = QLabel()
        self.platform_tag.setObjectName("tag")
        self.platform_tag.setFont(typography.tag())
        self.platform_tag.setVisible(False)

        self.live_tag = QLabel("LIVE")
        self.live_tag.setObjectName("tagLive")
        self.live_tag.setFont(typography.tag())
        self.live_tag.setVisible(False)

        tags = QHBoxLayout()
        tags.setSpacing(6)
        tags.addWidget(self.platform_tag)
        tags.addWidget(self.live_tag)
        tags.addStretch(1)

        # Kennzahlen und Markierungen teilen sich eine Zeile - das spart Hoehe,
        # die der Vorschau zugutekommt.
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        meta_row.addWidget(self.meta_label)
        meta_row.addLayout(tags)
        meta_row.addStretch(1)

        text_column = QVBoxLayout()
        text_column.setSpacing(5)
        text_column.addStretch(1)
        text_column.addWidget(self.title_label)
        text_column.addLayout(meta_row)
        text_column.addStretch(1)

        layout = QHBoxLayout(self.info_card)
        layout.setContentsMargins(11, 9, 14, 9)
        layout.setSpacing(12)
        layout.addWidget(self.thumbnail_label)
        layout.addLayout(text_column, 1)
        return self.info_card

    def _build_preview_section(self) -> QWidget:
        self.player = PreviewPlayer()
        # Bewusst ohne Hoehenbegrenzung: Die Vorschau ist der Teil, auf den man
        # schaut, waehrend man den Ausschnitt sucht. Sie bekommt allen Platz,
        # den das Fenster hergibt - wer mehr will, zieht das Fenster groesser.
        return self.player

    def _build_trim_section(self) -> QWidget:
        container = QFrame()
        container.setObjectName("card")

        self.trim_bar = TrimBar()

        self.start_edit = QLineEdit("0:00")
        self.start_edit.setObjectName("timecode")
        self.start_edit.setFixedWidth(82)
        self.start_edit.setAlignment(Qt.AlignCenter)
        self.start_edit.setFont(typography.mono())

        self.end_edit = QLineEdit("0:00")
        self.end_edit.setObjectName("timecode")
        self.end_edit.setFixedWidth(82)
        self.end_edit.setAlignment(Qt.AlignCenter)
        self.end_edit.setFont(typography.mono())

        self.set_start_button = QPushButton("Anfang hier")
        self.set_start_button.setObjectName("trimMark")
        self.set_start_button.setToolTip("Setzt den Anfang auf die Abspielposition  (Taste I)")

        self.set_end_button = QPushButton("Ende hier")
        self.set_end_button.setObjectName("trimMark")
        self.set_end_button.setToolTip("Setzt das Ende auf die Abspielposition  (Taste O)")

        self.add_segment_button = QPushButton("+ Ausschnitt")
        self.add_segment_button.setObjectName("trimAdd")
        self.add_segment_button.setToolTip(
            "Legt den gewaehlten Bereich auf die Liste  (Taste M).\n"
            "So laesst sich aus einem Video mehr als eine Stelle\n"
            "herausschneiden - alle Ausschnitte werden nacheinander geladen."
        )

        self.reset_trim_button = QPushButton("Ganzes Video")
        self.reset_trim_button.setObjectName("trimReset")

        self.waveform_button = QPushButton("Tonspur anzeigen")
        self.waveform_button.setObjectName("waveformAction")
        self.waveform_button.setEnabled(False)
        self.waveform_button.setToolTip(
            "Zeichnet den Lautstaerkeverlauf in den Balken.\n"
            "Damit siehst du genau, wo ein Lied anfaengt und aufhoert."
        )

        self.selection_label = QLabel("-")
        self.selection_label.setObjectName("muted")
        self.selection_label.setFont(typography.mono())

        from_label = QLabel("Von")
        from_label.setObjectName("muted")
        to_label = QLabel("bis")
        to_label.setObjectName("muted")

        # Erste Zeile: alles, was den Ausschnitt festlegt.
        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(from_label)
        controls.addWidget(self.start_edit)
        controls.addWidget(to_label)
        controls.addWidget(self.end_edit)
        controls.addSpacing(6)
        controls.addWidget(self.set_start_button)
        controls.addWidget(self.set_end_button)
        controls.addWidget(self.add_segment_button)
        controls.addStretch(1)
        controls.addWidget(self.selection_label)

        # Zweite Zeile: Ansicht und die Verwaltung der gemerkten Ausschnitte.
        # Die drei rechten Elemente erscheinen erst, wenn es etwas zu
        # verwalten gibt - vorher waeren sie nur Beiwerk.
        self.segment_count_label = QLabel()
        self.segment_count_label.setObjectName("muted")

        self.remove_segment_button = QPushButton("Entfernen")
        self.remove_segment_button.setObjectName("quiet")
        self.remove_segment_button.setEnabled(False)

        self.clear_segments_button = QPushButton("Liste leeren")
        self.clear_segments_button.setObjectName("quiet")

        self.segment_tools = QWidget()
        tools = QHBoxLayout(self.segment_tools)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(8)
        tools.addWidget(self.segment_count_label)
        tools.addWidget(self.remove_segment_button)
        tools.addWidget(self.clear_segments_button)
        self.segment_tools.setVisible(False)

        secondary = QHBoxLayout()
        secondary.setSpacing(8)
        secondary.addWidget(self.reset_trim_button)
        secondary.addWidget(self.waveform_button)
        secondary.addStretch(1)
        secondary.addWidget(self.segment_tools)

        self.segment_list = QListWidget()
        self.segment_list.setObjectName("segmentList")
        self.segment_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.segment_list.setVisible(False)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)
        layout.addWidget(self.trim_bar)
        layout.addLayout(controls)
        layout.addLayout(secondary)
        layout.addWidget(self.segment_list)
        return container

    def _build_options_section(self) -> QWidget:
        # Bewusst eine einzige Zeile statt einer Karte: Jede Zeile hier fehlt
        # der Vorschau, und beim Suchen des Ausschnitts schaut man auf das
        # Video, nicht auf die Einstellungen.
        container = QWidget()

        self.mode_combo = QComboBox()
        for mode in Mode:
            # Qt speichert nur den reinen Text - Mode erbt von str und wuerde
            # sonst als gewoehnliche Zeichenkette zurueckkommen.
            self.mode_combo.addItem(mode.label, mode.value)

        self.quality_combo = QComboBox()
        self.quality_combo.setEnabled(False)
        self.quality_combo.setMinimumWidth(120)

        self.h264_check = QCheckBox("H.264 fuer Resolve")
        self.h264_check.setChecked(True)
        self.h264_check.setToolTip(
            "YouTube liefert 1440p und 4K nur als VP9 oder AV1 aus.\n"
            "DaVinci Resolve kann diese Formate nicht oeffnen.\n"
            "Ist der Haken gesetzt, wird notfalls umgewandelt - das dauert\n"
            "laenger, dafuer laesst sich die Datei sicher importieren."
        )

        self.output_edit = QLineEdit(str(paths.DEFAULT_DOWNLOAD_DIR))
        self.output_edit.setMinimumWidth(180)
        self.browse_button = QPushButton("Ordner")
        self.browse_button.setObjectName("quiet")
        self.browse_button.setToolTip("Zielordner waehlen  (Strg+O)")

        content_label = QLabel("Inhalt")
        content_label.setObjectName("muted")
        quality_label = QLabel("Qualitaet")
        quality_label.setObjectName("muted")

        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(content_label)
        row.addWidget(self.mode_combo, 3)
        row.addWidget(quality_label)
        row.addWidget(self.quality_combo, 2)
        row.addWidget(self.h264_check)
        row.addSpacing(4)
        row.addWidget(self.output_edit, 4)
        row.addWidget(self.browse_button)
        return container

    def _build_footer(self) -> QWidget:
        container = QWidget()
        container.setObjectName("footer")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(2)

        self.status_label = QLabel("Bereit.")
        self.status_label.setObjectName("muted")

        self.download_button = QPushButton("Herunterladen")
        self.download_button.setObjectName("primary")
        self.download_button.setMinimumWidth(160)
        self.download_button.setEnabled(False)

        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.setVisible(False)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self.status_label, 1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.download_button)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(44, 0, 44, 24)
        layout.setSpacing(16)
        layout.addWidget(self.progress_bar)
        layout.addLayout(buttons)
        return container

    def _connect_signals(self) -> None:
        self.analyse_button.clicked.connect(self._start_probe)
        self.url_edit.returnPressed.connect(self._start_probe)

        self.trim_bar.rangeChanged.connect(self._on_range_changed)
        self.trim_bar.seeked.connect(self.player.seek)
        self.trim_bar.scrubbed.connect(self._on_trim_scrub)
        self.trim_bar.scrubFinished.connect(self._on_trim_scrub_finished)
        self.trim_bar.segmentPicked.connect(self._load_segment)
        self.player.positionChanged.connect(self.trim_bar.set_playhead)
        self.player.streamFailed.connect(self._on_stream_failed)

        self.start_edit.editingFinished.connect(self._on_start_edited)
        self.end_edit.editingFinished.connect(self._on_end_edited)
        self.set_start_button.clicked.connect(self._set_start_from_playhead)
        self.set_end_button.clicked.connect(self._set_end_from_playhead)
        self.add_segment_button.clicked.connect(self._add_segment)
        self.remove_segment_button.clicked.connect(self._remove_segment)
        self.clear_segments_button.clicked.connect(self._clear_segments)
        self.segment_list.itemSelectionChanged.connect(self._on_segment_selected)
        self.segment_list.itemDoubleClicked.connect(
            lambda item: self._load_segment(self.segment_list.row(item))
        )
        self.reset_trim_button.clicked.connect(self._reset_trim)
        self.waveform_button.clicked.connect(self._toggle_waveform)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.browse_button.clicked.connect(self._choose_output_dir)

        self.download_button.clicked.connect(self._on_primary_clicked)
        self.cancel_button.clicked.connect(self._cancel_download)
        self.download_nav_button.clicked.connect(self._show_download)
        self.library_nav_button.clicked.connect(self._show_library)
        self.library_page.downloadRequested.connect(self._show_download)
        self.library_page.chooseFolderRequested.connect(self._choose_library_dir)
        # Ein neuer Link hebt den Abschluss wieder auf.
        self.url_edit.textEdited.connect(self._reset_completed)
        # textEdited feuert nur bei Eingaben von Hand, nicht bei setText -
        # genau das soll als eigene Entscheidung gelten.
        self.output_edit.textEdited.connect(self._mark_output_chosen)

    # ------------------------------------------------------------------
    # Menuebefehle
    # ------------------------------------------------------------------

    def _paste_from_clipboard(self) -> None:
        text = (QApplication.clipboard().text() or "").strip()
        if not text:
            self._set_status("In der Zwischenablage steht kein Text.", error=True)
            return
        self.url_edit.setText(text)
        self.url_edit.setFocus()

    def _open_output_dir(self) -> None:
        target = Path(self.output_edit.text().strip())
        try:
            paths.ensure_dir(target)
            os.startfile(str(target))
        except Exception as exc:
            self._set_status(f"Ordner laesst sich nicht oeffnen: {exc}", error=True)

    # ------------------------------------------------------------------
    # Aktualisierungen
    # ------------------------------------------------------------------

    def _check_updates(self) -> None:
        """
        Sucht nach einem neuen yt-dlp UND einer neuen Fassung der App.

        Laeuft bewusst im Vordergrund und nicht in einem eigenen Thread: Es geht
        um wenige Sekunden, der Nutzer hat es selbst angestossen und wartet
        ohnehin auf die Antwort. Ein Thread waere hier nur Maschinerie ohne
        Gewinn. (Der Download des Installers dagegen laeuft im Thread.)
        """
        from ..core.update import update_ytdlp

        self.action_update_ytdlp.setEnabled(False)
        self._set_status("Suche nach Aktualisierungen...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        ytdlp_result = ytdlp_error = release = app_error = None
        try:
            try:
                ytdlp_result = update_ytdlp()
            except Exception as exc:
                ytdlp_error = exc
            try:
                release = appupdate.check()
            except Exception as exc:
                app_error = exc
        finally:
            # Vor der Meldung, sonst steht der Wartezeiger noch im Dialog.
            QApplication.restoreOverrideCursor()
            self.action_update_ytdlp.setEnabled(True)

        lines = []
        if ytdlp_result is not None:
            lines.append("yt-dlp: " + ytdlp_result.message.replace("\n", " "))
        else:
            lines.append("yt-dlp: nicht geprueft ({}).".format(ytdlp_error))
        if release is None and app_error is None:
            lines.append("Fev Download {} ist aktuell.".format(appupdate.current_version()))
        elif app_error is not None:
            lines.append("Fev Download: nicht geprueft ({}).".format(app_error))
        summary = "\n".join(lines)

        if release is not None:
            self._offer_app_update(release, extra=summary)
            return

        failed = ytdlp_error is not None or app_error is not None
        self._set_status(
            "Aktualisierung unvollstaendig." if failed else "Alles auf dem neuesten Stand.",
            error=failed,
        )
        box = QMessageBox.warning if failed else QMessageBox.information
        box(self, "Aktualisierung", summary)

    def _offer_app_update(self, release: "appupdate.AppRelease", extra: str = "") -> None:
        """Fragt, ob die neue Fassung jetzt installiert werden soll."""
        text = "Version {} von Fev Download ist verfuegbar (installiert: {}).".format(
            release.version, appupdate.current_version()
        )
        if release.notes:
            text += "\n\n" + release.notes[:600]
        if extra:
            text += "\n\n" + extra
        text += (
            "\n\nJetzt aktualisieren? Das Fenster schliesst sich kurz "
            "und oeffnet sich danach von selbst wieder."
        )
        answer = QMessageBox.question(
            self, "Neue Fassung verfuegbar", text, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if answer == QMessageBox.Yes:
            self._install_app_update(release)
        else:
            self._set_status(
                "Version {} wartet - Hilfe -> Nach Aktualisierung suchen.".format(release.version)
            )

    def _install_app_update(self, release: "appupdate.AppRelease") -> None:
        """Laedt den Installer, startet ihn und beendet die App."""
        if not paths.IS_FROZEN:
            # Aus dem Quelltext gestartet (Entwicklung): ein Installer waere hier
            # fehl am Platz, er wuerde eine zweite Kopie anlegen.
            QDesktopServices.openUrl(QUrl(release.page))
            self._set_status("Die Seite der neuen Fassung wurde im Browser geoeffnet.")
            return

        if self._download_worker is not None and self._download_worker.isRunning():
            QMessageBox.information(
                self,
                "Download laeuft",
                "Es laeuft noch ein Download. Bitte erst abwarten, dann aktualisieren.",
            )
            return
        if self._app_update_worker is not None and self._app_update_worker.isRunning():
            return

        dialog = QProgressDialog(
            "Version {} wird geladen...".format(release.version), "Abbrechen", 0, 100, self
        )
        dialog.setWindowTitle("Aktualisierung")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        self._app_update_dialog = dialog

        worker = AppUpdateWorker(release, parent=self)
        worker.progress.connect(dialog.setValue)
        worker.succeeded.connect(self._on_app_update_downloaded)
        worker.failed.connect(self._on_app_update_failed)
        dialog.canceled.connect(worker.cancel)
        self._app_update_worker = worker
        dialog.show()
        worker.start()

    def _close_update_dialog(self) -> None:
        dialog = self._app_update_dialog
        self._app_update_dialog = None
        if dialog is not None:
            # Sonst meldet schon das Schliessen "abgebrochen".
            try:
                dialog.canceled.disconnect()
            except (RuntimeError, TypeError):
                pass
            dialog.close()
            dialog.deleteLater()

    def _on_app_update_downloaded(self, installer: Path) -> None:
        self._close_update_dialog()
        try:
            appupdate.launch_installer(installer)
        except Exception as exc:
            self._on_app_update_failed(
                "Der Installer liess sich nicht starten:\n{}\n\nDatei: {}".format(exc, installer)
            )
            return
        self._set_status("Die Aktualisierung laeuft - das Fenster oeffnet sich gleich wieder.")
        # Der Installer wartet nicht auf uns, schliesst die App aber notfalls selbst.
        self.close()

    def _on_app_update_failed(self, message: str) -> None:
        self._close_update_dialog()
        self._set_status("Aktualisierung fehlgeschlagen.", error=True)
        QMessageBox.warning(
            self,
            "Aktualisierung fehlgeschlagen",
            "{}\n\nDas Programm laeuft mit der bisherigen Fassung weiter. "
            "Die neue Fassung gibt es auch von Hand:\n{}".format(message, appupdate.RELEASES_PAGE),
        )

    def start_background_update_check(self) -> None:
        """
        Prueft beim Start im Hintergrund, ohne etwas zu stoeren.

        yt-dlp: still, hoechstens einmal am Tag. App: nur ein Angebot, und jede
        Fassung wird einmal angeboten - wer 'Spaeter' sagt, wird nicht bei jedem
        Start gefragt (der Menuepunkt bleibt).

        Nur im installierten Programm: Aus dem Quelltext (Entwicklung) wuerde das
        mit jedem Commit zum Rauschen. FEVDL_UPDATE_CHECK=1 erzwingt es,
        FEVDL_NO_UPDATE_CHECK=1 unterdrueckt es.
        """
        if os.environ.get("FEVDL_NO_UPDATE_CHECK"):
            return
        if not paths.IS_FROZEN and not os.environ.get("FEVDL_UPDATE_CHECK"):
            return
        notifier = UpdateNotifier(self)
        notifier.ytdlpUpdated.connect(self._on_ytdlp_updated)
        notifier.appUpdateFound.connect(self._on_app_update_found)
        self._update_notifier = notifier
        start_startup_check(notifier)

    def _on_ytdlp_updated(self, version: str) -> None:
        self._set_status("yt-dlp {} wurde geladen und gilt ab dem naechsten Start.".format(version))

    def _on_app_update_found(self, release: "appupdate.AppRelease") -> None:
        busy = self._download_worker is not None and self._download_worker.isRunning()
        already_offered = self._settings.value("offered_version", "", type=str) == release.version
        if busy or already_offered:
            self._set_status(
                "Version {} ist verfuegbar - Hilfe -> Nach Aktualisierung suchen.".format(release.version)
            )
            return
        self._settings.setValue("offered_version", release.version)
        self._offer_app_update(release)

    def _show_about(self) -> None:
        from .. import __version__
        from ..core.update import current_version

        QMessageBox.information(
            self,
            "Ueber Fev Download",
            "Fev Download {}\n\n"
            "Laedt Videos von YouTube und ueber tausend weiteren Plattformen, "
            "schneidet den gewuenschten Ausschnitt heraus und uebergibt ihn an "
            "DaVinci Resolve.\n\n"
            "yt-dlp {}\n"
            "Laesst eine Plattform sich nicht mehr laden, hilft meist\n"
            "Hilfe -> Nach Aktualisierung suchen.\n\n"
            "https://github.com/{}\n"
            "Fremde Bestandteile und ihre Lizenzen (u. a. ffmpeg, GPLv3): "
            "siehe LIZENZEN.txt im Programmordner.\n\n"
            "Bitte nur fuer eigene Inhalte verwenden oder fuer Material, dessen "
            "Lizenz das erlaubt.".format(__version__, current_version(), appupdate.GITHUB_REPO),
        )

    # ------------------------------------------------------------------
    # Seiten und Bibliothek
    # ------------------------------------------------------------------

    def _show_download(self) -> None:
        self.pages.setCurrentIndex(0)

    def _show_library(self) -> None:
        self.library_page.refresh()
        self.pages.setCurrentIndex(1)

    def _library_root(self) -> Path:
        value = self.output_edit.text().strip()
        return Path(value) if value else paths.DEFAULT_DOWNLOAD_DIR

    def _choose_library_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Bibliotheksordner waehlen", str(self._library_root())
        )
        if not chosen:
            return
        self.output_edit.setText(chosen)
        self._output_user_set = True
        self.library_page.refresh()

    def _import_library_file(self, file_path: Path) -> None:
        """Meldet eine vorhandene Datei an das intern laufende Resolve-Script."""
        if self._results is not None:
            self._results.add_file(file_path)

    # ------------------------------------------------------------------
    # Analysieren
    # ------------------------------------------------------------------

    def _start_probe(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self._set_status("Bitte zuerst einen Link einfuegen.", error=True)
            return
        if self._probe_worker is not None and self._probe_worker.isRunning():
            return

        self.analyse_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self._set_status("Analysiere Link...")
        self.progress_bar.setRange(0, 0)  # unbestimmter Fortschritt

        self._probe_worker = ProbeWorker(url, self)
        self._probe_worker.succeeded.connect(self._on_probe_succeeded)
        self._probe_worker.failed.connect(self._on_probe_failed)
        self._probe_worker.start()

    def _on_probe_succeeded(self, info: VideoInfo) -> None:
        self._info = info
        # Die Wellenform des vorherigen Videos ist jetzt gegenstandslos.
        self._waveform_peaks = []
        self.waveform_button.setText("Tonspur anzeigen")
        self.waveform_button.setEnabled(bool(info.audio_url))
        self.analyse_button.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.info_card.setVisible(True)
        self.title_label.setText(info.title)
        # Der Fenstertitel verraet in der Taskleiste, worum es gerade geht.
        short = info.title if len(info.title) <= 60 else info.title[:57] + "..."
        self.setWindowTitle(f"{short} - Fev Download")

        details = []
        if info.uploader:
            details.append(info.uploader)
        details.append(info.duration_text)
        self.meta_label.setText("   ·   ".join(details))

        self.platform_tag.setText(info.extractor.upper() if info.extractor else "")
        self.platform_tag.setVisible(bool(info.extractor))
        self.live_tag.setVisible(info.is_live)

        self.thumbnail_label.clear()
        if info.thumbnail_url:
            self._thumb_worker = ThumbnailWorker(info.thumbnail_url, self)
            self._thumb_worker.loaded.connect(self._on_thumbnail_loaded)
            self._thumb_worker.start()

        self._fill_quality_combo(info)

        # Gemerkte Ausschnitte gehoeren zum vorherigen Video und waeren beim
        # neuen schlicht falsch.
        self._clear_segments(silent=True)
        self.trim_bar.set_duration(info.duration)
        self.player.set_aspect(info.aspect)
        self._preview_attempted_download = False
        self.player.load(info.preview_url, fallback_duration=info.duration)
        if not info.preview_url:
            # Gar keine Stream-Adresse - dann gleich die Datei holen.
            self._start_preview_fallback()

        self._completed = False
        self.download_button.setText("Herunterladen")
        self.download_button.setEnabled(True)
        if info.is_live:
            self._set_status("Achtung: Livestream - der Ausschnitt kann ungenau sein.")
        else:
            self._set_status("Bereit zum Herunterladen.")

    def _on_probe_failed(self, message: str) -> None:
        self.analyse_button.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_status(message, error=True)

    def _on_thumbnail_loaded(self, data: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        self.thumbnail_label.setPixmap(
            pixmap.scaled(
                self.thumbnail_label.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
        )

    def _fill_quality_combo(self, info: VideoInfo) -> None:
        self.quality_combo.clear()
        for quality in info.qualities:
            self.quality_combo.addItem(quality.label, quality.height)

        has_video = bool(info.qualities)
        self.quality_combo.setEnabled(has_video and self._current_mode().needs_video)

        if not has_video:
            self.quality_combo.addItem("kein Video verfuegbar", None)
            self.mode_combo.setCurrentIndex(self.mode_combo.findData(Mode.AUDIO_ONLY.value))
            return

        # Zuletzt gewaehlte Qualitaet, sonst das Beste darunter.
        preferred = pick_height(info, self._preferred_height)
        index = self.quality_combo.findData(preferred)
        self.quality_combo.setCurrentIndex(max(0, index))

    # ------------------------------------------------------------------
    # Ausschnitt
    # ------------------------------------------------------------------

    def _on_range_changed(self, start: float, end: float) -> None:
        self.start_edit.setText(format_timecode(start))
        self.end_edit.setText(format_timecode(end))
        length = max(0.0, end - start)
        if self._segments:
            # Solange etwas auf der Liste steht, wird die geladen. Hier "ganzes
            # Video" zu behaupten, waere schlicht falsch.
            self.selection_label.setText(f"Auswahl · {format_timecode(length)}")
        elif self.trim_bar.is_full_range():
            self.selection_label.setText(f"ganzes Video · {format_timecode(length)}")
        else:
            self.selection_label.setText(f"Ausschnitt · {format_timecode(length)}")

    def _on_start_edited(self) -> None:
        try:
            self.trim_bar.set_start(parse_timecode(self.start_edit.text()))
        except ValueError:
            self.start_edit.setText(format_timecode(self.trim_bar.start()))

    def _on_end_edited(self) -> None:
        try:
            self.trim_bar.set_end(parse_timecode(self.end_edit.text()))
        except ValueError:
            self.end_edit.setText(format_timecode(self.trim_bar.end()))

    def _set_start_from_playhead(self) -> None:
        self.trim_bar.set_start(self.player.position())

    def _set_end_from_playhead(self) -> None:
        self.trim_bar.set_end(self.player.position())

    def _reset_trim(self) -> None:
        if self._info is None:
            return
        # set_duration verwirft die Wellenform - sie gehoert aber weiter zum
        # selben Video, also gleich wieder einsetzen. Ebenso die gemerkten
        # Ausschnitte: Sie gelten weiter, nur der Balken faengt von vorn an.
        peaks = self._waveform_peaks
        self.trim_bar.set_duration(self._info.duration)
        if peaks:
            self.trim_bar.set_waveform(peaks)
        self.trim_bar.set_segments(self._segments)

    # ------------------------------------------------------------------
    # Vorschau folgt dem Griff
    # ------------------------------------------------------------------

    def _on_trim_scrub(self, seconds: float) -> None:
        """
        Waehrend ein Griff gezogen wird, springt die Vorschau mit.

        Ohne das waere der Ausschnitt eine reine Zahlenangabe - man saehe nicht,
        an welchem Bild geschnitten wird. Gedrosselt, weil jede Mausbewegung
        sonst einen eigenen Sprungbefehl ausloest und der Player ins Stocken
        geraet; der genaue Endwert kommt beim Loslassen ueber scrubFinished.
        """
        if self._scrub_clock.elapsed() < 50:
            return
        self._scrub_clock.restart()
        self._seek_preview(seconds)

    def _on_trim_scrub_finished(self, seconds: float) -> None:
        self._scrub_clock.restart()
        self._seek_preview(seconds)

    def _seek_preview(self, seconds: float) -> None:
        # Anhalten, sonst laeuft das Video unter dem Griff sofort weiter.
        self.player.pause()
        self.player.seek(seconds)
        # Die Marke selbst setzen: Gibt es keine abspielbare Vorschau, meldet
        # der Player nichts zurueck - die Marke soll trotzdem stimmen.
        self.trim_bar.set_playhead(seconds)

    # ------------------------------------------------------------------
    # Mehrere Ausschnitte
    # ------------------------------------------------------------------

    def _add_segment(self) -> None:
        """Legt den gerade eingestellten Bereich auf die Liste."""
        if self._info is None or self.trim_bar.duration() <= 0:
            self._set_status("Erst einen Link analysieren.", error=True)
            return

        start = round(self.trim_bar.start(), 2)
        end = round(self.trim_bar.end(), 2)
        if end - start < 1.0:
            self._set_status("Der Ausschnitt ist zu kurz.", error=True)
            return
        if (start, end) in self._segments:
            self._set_status("Dieser Ausschnitt steht schon auf der Liste.")
            return

        self._segments.append((start, end))
        self._segments.sort()
        self._refresh_segments()
        self.segment_list.setCurrentRow(self._segments.index((start, end)))
        self._set_status(
            f"Gemerkt: {format_timecode(start)} bis {format_timecode(end)}  ·  "
            f"{len(self._segments)} auf der Liste"
        )

    def _remove_segment(self) -> None:
        row = self.segment_list.currentRow()
        if not (0 <= row < len(self._segments)):
            return
        start, end = self._segments.pop(row)
        self._refresh_segments()
        self._set_status(
            f"Entfernt: {format_timecode(start)} bis {format_timecode(end)}"
        )

    def _clear_segments(self, silent: bool = False) -> None:
        if not self._segments:
            return
        self._segments = []
        self._refresh_segments()
        if not silent:
            self._set_status("Die Liste der Ausschnitte ist wieder leer.")

    def _load_segment(self, index: int) -> None:
        """Holt einen gemerkten Ausschnitt zurueck in den Balken."""
        if not (0 <= index < len(self._segments)):
            return
        start, end = self._segments[index]
        self.trim_bar.set_range(start, end)
        self.segment_list.setCurrentRow(index)
        self._seek_preview(start)

    def _on_segment_selected(self) -> None:
        self.remove_segment_button.setEnabled(self.segment_list.currentRow() >= 0)

    def _refresh_segments(self) -> None:
        """Bringt Liste, Balken, Zaehler und Knopfbeschriftung auf denselben Stand."""
        self.segment_list.clear()
        for index, (start, end) in enumerate(self._segments, start=1):
            # Feste Spaltenbreite: In der Monospace-Schrift stehen '1:12' und
            # '10:30' sonst versetzt und die Liste wirkt unruhig.
            item = QListWidgetItem(
                f"{index}.  {format_timecode(start):>8}  bis {format_timecode(end):>8}"
                f"     {format_timecode(end - start):>8} lang"
            )
            item.setFont(typography.mono())
            self.segment_list.addItem(item)

        count = len(self._segments)
        self.segment_list.setVisible(count > 0)
        self.segment_tools.setVisible(count > 0)
        if count:
            total = sum(end - start for start, end in self._segments)
            word = "Ausschnitt" if count == 1 else "Ausschnitte"
            self.segment_count_label.setText(
                f"{count} {word}  ·  {format_timecode(total)} gesamt"
            )
            self._size_segment_list()

        self.trim_bar.set_segments(self._segments)
        self._on_segment_selected()
        self._update_download_button()
        # Die Auswahl-Anzeige haengt davon ab, ob die Liste gefuellt ist.
        self._on_range_changed(self.trim_bar.start(), self.trim_bar.end())

    def _size_segment_list(self) -> None:
        """
        Die Liste waechst mit, bis drei Ausschnitte sichtbar sind.

        Eine feste Hoehe waere bei einem Eintrag halb leer und bei fuenfen zu
        klein. Ab dem vierten wird gerollt - mehr Hoehe fehlte der Vorschau.
        """
        row = self.segment_list.sizeHintForRow(0)
        if row <= 0:
            return
        visible = min(len(self._segments), 3)
        frame = 2 * self.segment_list.frameWidth() + 8  # Rahmen und Innenabstand
        self.segment_list.setFixedHeight(visible * row + frame)

    def _update_download_button(self) -> None:
        """Der Knopf sagt, was gleich passiert - ein Clip oder mehrere."""
        if self._completed:
            return
        count = len(self._segments)
        if count > 1:
            self.download_button.setText(f"{count} Ausschnitte laden")
        elif count == 1:
            self.download_button.setText("Ausschnitt laden")
        else:
            self.download_button.setText("Herunterladen")

    # ------------------------------------------------------------------
    # Vorschau
    # ------------------------------------------------------------------

    def _on_stream_failed(self) -> None:
        """
        Der Stream laesst sich nicht abspielen - dann laden wir eben.

        Betrifft vor allem TikTok und aehnliche Seiten, deren Adressen nur mit
        besonderen Kopfdaten funktionieren. Statt einer Fehlermeldung holt die
        App still eine kleine Datei.
        """
        self._start_preview_fallback()

    def _start_preview_fallback(self) -> None:
        if self._info is None or self._preview_attempted_download:
            return
        if self._preview_worker is not None and self._preview_worker.isRunning():
            return

        self._preview_attempted_download = True
        self.player.show_loading("Vorschau wird geladen...")
        self._set_status("Die Vorschau wird geladen - das dauert einen Moment.")

        self._preview_worker = PreviewWorker(
            self._info.url,
            Path(tempfile.gettempdir()) / "FevDownload" / "vorschau",
            parent=self,
        )
        self._preview_worker.succeeded.connect(self._on_preview_ready)
        self._preview_worker.failed.connect(self._on_preview_failed)
        self._preview_worker.start()

    def _on_preview_ready(self, path: Path) -> None:
        self._preview_file = path
        duration = self._info.duration if self._info else 0.0
        self.player.load(path, fallback_duration=duration)
        self._set_status("Bereit zum Herunterladen.")

    def _on_preview_failed(self, message: str) -> None:
        self.player.show_loading(
            "Fuer dieses Video gibt es keine abspielbare Vorschau.\n"
            "Der Ausschnitt laesst sich trotzdem ueber die Zeitfelder waehlen."
        )
        self._set_status(f"Vorschau nicht moeglich: {message}")

    def _toggle_waveform(self) -> None:
        """Ein Knopf fuer drei Faelle: einblenden, ausblenden, erstmals laden."""
        if self.trim_bar.has_waveform():
            self.trim_bar.set_waveform([])
            self.waveform_button.setText("Tonspur anzeigen")
            return

        # Schon einmal berechnet - dann nur wieder einblenden.
        if self._waveform_peaks:
            self.trim_bar.set_waveform(self._waveform_peaks)
            self.waveform_button.setText("Tonspur ausblenden")
            return

        if self._info is None or not self._info.audio_url:
            self._set_status("Zu diesem Video gibt es keine abrufbare Tonspur.", error=True)
            return
        if self._waveform_worker is not None and self._waveform_worker.isRunning():
            return

        self.waveform_button.setEnabled(False)
        self.waveform_button.setText("Lade Tonspur...")

        self._waveform_worker = WaveformWorker(
            self._info.audio_url,
            self._info.duration,
            buckets=max(300, self.trim_bar.width()),
            parent=self,
        )
        self._waveform_worker.succeeded.connect(self._on_waveform_ready)
        self._waveform_worker.failed.connect(self._on_waveform_failed)
        self._waveform_worker.start()

    def _on_waveform_ready(self, peaks: list) -> None:
        self._waveform_peaks = list(peaks)
        self.trim_bar.set_waveform(self._waveform_peaks)
        self.waveform_button.setText("Tonspur ausblenden")
        self.waveform_button.setEnabled(True)

    def _on_waveform_failed(self, message: str) -> None:
        self.waveform_button.setText("Tonspur anzeigen")
        self.waveform_button.setEnabled(True)
        self._set_status(message, error=True)

    # ------------------------------------------------------------------
    # Einstellungen
    # ------------------------------------------------------------------

    def _current_mode(self) -> Mode:
        value = self.mode_combo.currentData()
        try:
            return Mode(value)
        except ValueError:
            return Mode.VIDEO_AUDIO

    def _on_mode_changed(self) -> None:
        needs_video = self._current_mode().needs_video
        has_video = bool(self._info.qualities) if self._info else False
        self.quality_combo.setEnabled(needs_video and has_video)
        self.h264_check.setEnabled(needs_video)

    def _mark_output_chosen(self) -> None:
        self._output_user_set = True

    def _choose_output_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Zielordner waehlen", self.output_edit.text()
        )
        if chosen:
            self.output_edit.setText(chosen)
            self._output_user_set = True

    # ------------------------------------------------------------------
    # Herunterladen
    # ------------------------------------------------------------------

    def _on_primary_clicked(self) -> None:
        """Der grosse Knopf laedt herunter - und schliesst, wenn alles fertig ist."""
        if self._completed:
            self.close()
        else:
            self._start_download()

    def _reset_completed(self) -> None:
        """Zurueck in den Download-Zustand, sobald ein neuer Link kommt."""
        if not self._completed:
            return
        self._completed = False
        self._update_download_button()

    def _build_requests(self) -> list[DownloadRequest]:
        """
        Baut die Auftragsliste fuer den Download.

        Stehen Ausschnitte auf der Liste, gilt ausschliesslich sie - der Balken
        war dann nur das Werkzeug, mit dem sie entstanden sind. Ist die Liste
        leer, zaehlt wie bisher der eingestellte Bereich.
        """
        if self._info is None:
            return []

        mode = self._current_mode()
        height = self.quality_combo.currentData() if mode.needs_video else None
        output_dir = Path(self.output_edit.text().strip())

        if self._segments:
            ranges: list[tuple[Optional[float], Optional[float]]] = list(self._segments)
        elif self.trim_bar.is_full_range():
            ranges = [(None, None)]
        else:
            ranges = [(self.trim_bar.start(), self.trim_bar.end())]

        return [
            DownloadRequest(
                url=self._info.url,
                output_dir=output_dir,
                mode=mode,
                height=height,
                start=start,
                end=end,
                prefer_h264=self.h264_check.isChecked(),
            )
            for start, end in ranges
        ]

    def _start_download(self) -> None:
        if self._info is None:
            return

        try:
            requests = self._build_requests()
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return
        if not requests:
            return

        self._finished_files = []
        self.player.pause()
        self._set_state_busy()
        # Beim Schneiden laedt ffmpeg selbst und meldet dabei nichts - bis zur
        # ersten Zahl vergehen leicht zehn Sekunden. Ein unbestimmter Balken
        # zeigt solange wenigstens, dass ueberhaupt etwas laeuft.
        self.progress_bar.setRange(0, 0)
        if len(requests) > 1:
            self._set_status(
                f"Lade {len(requests)} Ausschnitte gleichzeitig..."
            )
        else:
            self._set_status("Starte Download...")

        self._download_worker = DownloadWorker(requests, self)
        self._download_worker.progressed.connect(self._on_progress)
        self._download_worker.fileReady.connect(self._on_file_ready)
        self._download_worker.succeeded.connect(self._on_download_succeeded)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.cancelled.connect(self._on_download_cancelled)
        self._download_worker.start()

    def _cancel_download(self) -> None:
        if self._download_worker is not None and self._download_worker.isRunning():
            self._set_status("Breche ab...")
            self.cancel_button.setEnabled(False)
            self._download_worker.cancel()

    def _on_progress(self, progress: Progress) -> None:
        # Bei mehreren Ausschnitten steht vorn, wie viele schon fertig sind.
        # Die Prozentzahl ist dann der Mittelwert ueber alle - sie laufen
        # gleichzeitig, ein einzelner Balken je Download waere Unfug.
        prefix = [progress.part_text] if progress.part_text else []

        if progress.status == "downloading":
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(progress.percent))
            bits = prefix + [f"{progress.percent:.0f} %"]
            if progress.speed_text:
                bits.append(progress.speed_text)
            if progress.eta_text:
                bits.append(progress.eta_text)
            self._set_status("   ·   ".join(bits))
        else:
            if progress.status == "processing":
                self.progress_bar.setRange(0, 0)
            bits = prefix + [progress.message or "Wird verarbeitet..."]
            self._set_status("   ·   ".join(bits))

    def _on_file_ready(self, result: Path) -> None:
        """
        Ein Ausschnitt ist fertig.

        Die Meldung geht sofort weiter, nicht erst am Ende: So erscheint bei
        mehreren Ausschnitten jeder einzelne im Media Pool, sobald er da ist.
        """
        if result not in self._finished_files:
            self._finished_files.append(result)
        if self._results is not None:
            self._results.add_file(result)

    def _on_download_succeeded(self, result: Path) -> None:
        self._completed = True
        self._set_state_idle()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

        # Bei einem einzelnen Auftrag hat _on_file_ready dieselbe Datei schon
        # vermerkt; add_file und diese Pruefung halten das auseinander.
        if result not in self._finished_files:
            self._finished_files.append(result)
        if self._results is not None:
            self._results.add_file(result)

        count = len(self._finished_files)
        if count > 1:
            wohin = "liegen im Media Pool" if self._results is not None else "gespeichert"
            self._set_status(f"{count} Ausschnitte {wohin}")
        elif self._results is not None:
            self._set_status(f"{result.name}  ·  liegt im Media Pool")
        else:
            self._set_status(f"Gespeichert: {result.name}")

        self.download_button.setText("Fertig")
        self.download_button.setFocus()

        self.on_download_finished(result)

    def _on_download_failed(self, message: str) -> None:
        self._set_state_idle()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_status(message, error=True)
        QMessageBox.warning(self, "Download fehlgeschlagen", message)

    def _on_download_cancelled(self) -> None:
        self._set_state_idle()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_status("Abgebrochen.")

    def on_download_finished(self, result: Path) -> None:
        """Haken fuer die Resolve-Anbindung - in Phase 3 ueberschrieben."""

    # ------------------------------------------------------------------
    # Zustaende
    # ------------------------------------------------------------------

    def _set_state_busy(self) -> None:
        self.download_button.setVisible(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.analyse_button.setEnabled(False)
        self.url_edit.setEnabled(False)

    def _set_state_idle(self) -> None:
        self.download_button.setVisible(True)
        self.download_button.setEnabled(self._info is not None)
        self.cancel_button.setVisible(False)
        self.analyse_button.setEnabled(True)
        self.url_edit.setEnabled(True)

    def _set_status(self, message: str, error: bool = False) -> None:
        self.status_label.setText(message)
        self.status_label.setObjectName("error" if error else "muted")
        # Damit die geaenderte Farbe auch wirklich gezeichnet wird.
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Ziehen und Ablegen
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        data = event.mimeData()
        if data.hasUrls() or data.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        """Nimmt einen Link entgegen, der auf das Fenster gezogen wird."""
        data = event.mimeData()

        text = ""
        if data.hasUrls():
            urls = data.urls()
            if urls:
                text = urls[0].toString()
        if not text and data.hasText():
            text = data.text().strip()

        if not text.lower().startswith(("http://", "https://")):
            self._set_status("Das war kein Link.", error=True)
            return

        event.acceptProposedAction()
        self.url_edit.setText(text)
        self._reset_completed()
        self._start_probe()

    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._download_worker is not None and self._download_worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Download laeuft",
                "Es laeuft noch ein Download. Wirklich schliessen?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._download_worker.cancel()
            self._download_worker.wait(5000)

        if self._waveform_worker is not None and self._waveform_worker.isRunning():
            self._waveform_worker.cancel()
            self._waveform_worker.wait(3000)

        if self._preview_worker is not None and self._preview_worker.isRunning():
            self._preview_worker.cancel()
            self._preview_worker.wait(3000)

        # Der Bilder-Thread der Bibliothek laeuft dauerhaft und muss ausdruecklich
        # angehalten werden, sonst haengt das Programm beim Beenden.
        self.library_page.shutdown()

        self._store_settings()

        # Dem Resolve-Script sagen, dass nichts mehr nachkommt - sonst wartet
        # es bis zur Zeitgrenze.
        if self._results is not None:
            self._results.mark_finished("ok")

        self.player.stop()
        event.accept()
