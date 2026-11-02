"""Das Hauptfenster des FevDownloaders - Gestaltung "Sammelmappe".

Aufbau:

    Leiste      Logo, Reiter "Sammeln" / "Dateien", Menuesymbol (Strg+K)
    Quelle      Link, Vorschau mit allem freien Platz, Titel, Inhalt, Qualitaet,
                H.264-Schalter, Zielordner
    Mappe       der Zettel mit der aktuellen Auswahl (Zeitleiste, Von/Bis,
                I/O/Ganzes Video, Ablegen), die abgelegten Ausschnitte und unten
                die grosse Hauptaktion. Beim Laden wird daraus die Lieferliste.

Vor der ersten Analyse zeigt die Seite nur den grossen Link-Einstieg.

Die Logik (Analyse, Vorschau-Ausweichdatei, mehrere Ausschnitte parallel,
Resolve-Rueckmeldung, Einstellungen) ist dieselbe wie vorher; neu ist das
Aussehen. Die Bedienelemente stehen in widgets.py und trim_bar.py.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QElapsedTimer, QPoint, QRectF, QSettings, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QScrollArea,
    QSizePolicy,
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
from .icons import draw_logo
from .library_page import LibraryPage
from .preview_player import PreviewPlayer
from .style import STYLESHEET
from .trim_bar import TrimBar, precise_timecode
from .widgets import (
    BusyLine,
    ChoiceGroup,
    DeliveryList,
    IconButton,
    JobRow,
    LogoMark,
    MainAction,
    NavButton,
    Rule,
    SegmentList,
    TextButton,
    ToggleSwitch,
    fade_in,
)
from .worker import (
    MAX_PARALLEL,
    AppUpdateWorker,
    DownloadWorker,
    PreviewWorker,
    ProbeWorker,
    ThumbnailWorker,
    UpdateNotifier,
    WaveformWorker,
    start_startup_check,
)

# Kurze Namen fuer die Medienkarten; der volle Name steht im Tooltip.
MODE_CARDS = (
    (Mode.VIDEO_AUDIO, "Video + Ton", "video"),
    (Mode.AUDIO_ONLY, "Nur Ton", "audio"),
    (Mode.VIDEO_ONLY, "Nur Video", "video"),
)

COLLECTION_WIDE = 420
COLLECTION_NARROW = 380
COMPACT_HEIGHT = 840  # darunter werden die Medienkarten flach


def logo_pixmap(size: int) -> QPixmap:
    """Logo als Bild - nur nach dem Start der Anwendung aufrufen."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    draw_logo(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def _label(text: str = "", name: str = "", font=None, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    if font is not None:
        label.setFont(font)
    label.setWordWrap(wrap)
    return label


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
        self._running = False
        self._job_rows: list[JobRow] = []
        self._parts_done = 0

        # Gemerkte Stellen desselben Videos, jeweils (Anfang, Ende) in Sekunden.
        # Ist die Liste gefuellt, wird sie geladen und nicht der Zettel.
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

        self._build_actions()
        self._build_ui()
        self._connect_signals()
        self._restore_settings()
        self._apply_job()
        self._prefill_from_clipboard()
        self._set_state_idle()
        self._update_plan()

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
        """Beim ersten Start 1000 x 960 - oder so viel, wie der Bildschirm hergibt."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        width = min(1000, available.width() - 40)
        height = min(960, available.height() - 40)
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
            self.resolve_banner.setVisible(False)
            self.resolve_note.setVisible(False)
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
        self.resolve_note.setText(f"Resolve  ·  Projekt „{project}“  ·  fertige Clips landen im Media Pool")
        self.resolve_banner.setVisible(True)
        self.resolve_note.setVisible(True)

    # ------------------------------------------------------------------
    # Befehle (Menue hinter dem Symbol, Tastenkuerzel am Fenster)
    # ------------------------------------------------------------------

    def _action(self, text: str, slot, shortcut: str = "") -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        # Ohne Menueleiste muessen die Aktionen am Fenster haengen, sonst
        # greifen ihre Kuerzel nicht.
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        self.action_paste = self._action("Link aus Zwischenablage", self._paste_from_clipboard, "Ctrl+V")
        self.action_analyse = self._action("Analysieren", self._start_probe, "Ctrl+Return")
        self.action_choose_dir = self._action("Zielordner waehlen...", self._choose_output_dir, "Ctrl+O")
        self.action_open_dir = self._action("Zielordner oeffnen", self._open_output_dir)
        self.action_library = self._action("Bibliothek", self._show_library, "Ctrl+L")
        self.action_quit = self._action("Beenden", self.close, "Ctrl+Q")

        self.action_mark_in = self._action("Anfang auf Abspielposition", self._set_start_from_playhead, "I")
        self.action_mark_out = self._action("Ende auf Abspielposition", self._set_end_from_playhead, "O")
        self.action_play = self._action("Abspielen / Pause", self._toggle_playback, "Space")
        self.action_add_segment = self._action("Ausschnitt ablegen", self._add_segment, "M")
        self.action_clear_segments = self._action("Gemerkte Ausschnitte verwerfen", self._clear_segments)
        self.action_reset_trim = self._action("Ganzes Video", self._reset_trim)

        self.action_update_ytdlp = self._action("Nach Aktualisierung suchen", self._check_updates)
        self.action_about = self._action("Ueber Fev Download", self._show_about)
        self.action_menu = self._action("Menue", self._show_menu, "Ctrl+K")

        menu = QMenu(self)
        for action in (self.action_paste, self.action_analyse):
            menu.addAction(action)
        menu.addSeparator()
        for action in (self.action_choose_dir, self.action_open_dir, self.action_library):
            menu.addAction(action)
        menu.addSeparator()
        for action in (self.action_mark_in, self.action_mark_out, self.action_add_segment,
                       self.action_reset_trim, self.action_clear_segments):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.action_update_ytdlp)
        menu.addAction(self.action_about)
        menu.addSeparator()
        menu.addAction(self.action_quit)
        self.main_menu = menu

    def _show_menu(self) -> None:
        button = self.menu_button
        size = self.main_menu.sizeHint()
        pos = button.mapToGlobal(QPoint(button.width() + 6, button.height() - size.height()))
        self.main_menu.popup(pos)

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("page")
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_nav_rail())

        self._build_source_editor()

        self.download_stack = QStackedWidget()
        self.download_stack.addWidget(self._build_empty_view())
        self.download_stack.addWidget(self._build_work_view())
        self._place_source_editor(compact=False)

        self.library_page = LibraryPage(
            root_provider=self._library_root,
            import_file=self._import_library_file if self._results is not None else None,
        )

        self.pages = QStackedWidget()
        self.pages.addWidget(self.download_stack)
        self.pages.addWidget(self.library_page)
        row.addWidget(self.pages, 1)
        self.setCentralWidget(central)

    def _build_nav_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("navRail")
        rail.setAttribute(Qt.WA_StyledBackground, True)
        rail.setFixedWidth(65)

        self.download_nav_button = NavButton("mark", "Sammeln")
        self.download_nav_button.setToolTip("Video sammeln und laden")
        self.download_nav_button.setChecked(True)
        self.library_nav_button = NavButton("library", "Dateien")
        self.library_nav_button.setToolTip("Bibliothek der geladenen Dateien  ·  Strg+L")
        self.menu_button = IconButton("menu", "Menue", tooltip="Alle Befehle  ·  Strg+K")

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(6, 18, 6, 15)
        layout.setSpacing(12)
        layout.addWidget(LogoMark(32), 0, Qt.AlignHCenter)
        layout.addSpacing(26)
        layout.addWidget(self.download_nav_button, 0, Qt.AlignHCenter)
        layout.addWidget(self.library_nav_button, 0, Qt.AlignHCenter)
        layout.addStretch(1)
        layout.addWidget(self.menu_button, 0, Qt.AlignHCenter)
        return rail

    # -- Link-Eingabe (wandert vom Einstieg in die Quelle) ---------------

    def _build_source_editor(self) -> None:
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Videolink einfuegen oder hier ablegen")
        self.url_edit.setAccessibleName("Videolink")
        self.url_edit.setToolTip("YouTube, Vimeo, TikTok, Twitch und ueber tausend weitere Seiten")

        self.paste_button = IconButton("paste", "Link einfuegen", tooltip="Strg+V")
        self.clear_link_button = IconButton("close", "Link leeren")
        self.analyse_button = TextButton("Analysieren", "arrow", variant="accent", height=44)
        self.analyse_button.setToolTip("Link pruefen und Vorschau laden  ·  Eingabetaste")
        self.analyse_busy = BusyLine()

        self.source_editor = QWidget()
        self._source_grid = QGridLayout(self.source_editor)
        self._source_grid.setContentsMargins(0, 0, 0, 0)
        self._source_grid.setHorizontalSpacing(4)
        self._source_grid.setVerticalSpacing(8)

    def _place_source_editor(self, compact: bool) -> None:
        """Gross im Einstieg, als schmale Zeile ueber der Vorschau."""
        grid = self._source_grid
        for widget in (self.url_edit, self.analyse_busy, self.paste_button,
                       self.clear_link_button, self.analyse_button):
            grid.removeWidget(widget)
        for column in range(5):
            grid.setColumnStretch(column, 0)
        if compact:
            self.url_edit.setObjectName("linkEdit")
            self.analyse_button.setFixedHeight(36)
            # Neben der Vorschau ist Analysieren eine Nebensache - das Blau
            # gehoert dort allein der Hauptaktion.
            self.analyse_button.set_variant("outline")
            grid.addWidget(self.url_edit, 0, 0)
            grid.addWidget(self.paste_button, 0, 1)
            grid.addWidget(self.clear_link_button, 0, 2)
            grid.addWidget(self.analyse_button, 0, 3)
            grid.addWidget(self.analyse_busy, 1, 0, 1, 4)
            grid.setVerticalSpacing(0)
            grid.setColumnStretch(0, 1)
            self._source_slot_work.addWidget(self.source_editor)
        else:
            self.url_edit.setObjectName("linkHero")
            self.analyse_button.setFixedHeight(44)
            self.analyse_button.set_variant("accent")
            grid.addWidget(self.url_edit, 0, 0, 1, 4)
            grid.addWidget(self.analyse_busy, 1, 0, 1, 4)
            grid.addWidget(self.paste_button, 2, 0)
            grid.addWidget(self.clear_link_button, 2, 1)
            grid.addWidget(self.analyse_button, 2, 3)
            grid.setVerticalSpacing(6)
            grid.setColumnStretch(2, 1)
            self._source_slot_empty.addWidget(self.source_editor)
        # Neuer Objektname braucht neues Polieren, sonst bleibt der alte Stil.
        self.url_edit.style().unpolish(self.url_edit)
        self.url_edit.style().polish(self.url_edit)
        self.url_edit.setFont(typography.body(15 if not compact else 13))

    # -- Einstieg (vor der ersten Analyse) -------------------------------

    def _build_empty_view(self) -> QWidget:
        view = QWidget()
        view.setObjectName("emptyView")

        column = QWidget()
        column.setMaximumWidth(560)
        column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(LogoMark(64))
        col.addSpacing(26)
        col.addWidget(_label("Ein Video, mehrere Fundstuecke.", font=typography.hero(30)))
        col.addSpacing(10)
        hint = _label("Lege einen Videolink ab und sammle die Stellen, die du behalten willst.",
                      "muted", typography.body(14), wrap=True)
        col.addWidget(hint)
        col.addSpacing(22)
        self._source_slot_empty = QVBoxLayout()
        self._source_slot_empty.setContentsMargins(0, 0, 0, 0)
        col.addLayout(self._source_slot_empty)
        col.addSpacing(12)
        self.empty_status = _label("", "muted", typography.small(12), wrap=True)
        self.empty_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        col.addWidget(self.empty_status)
        col.addSpacing(6)
        col.addWidget(_label("Link per Drag & Drop  ·  Strg + V zum Einfuegen", "muted", typography.small(12)))
        col.addSpacing(16)
        self.resolve_banner = _label("", "resolveNote", typography.small(12), wrap=True)
        col.addWidget(self.resolve_banner)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(column, 5)
        row.addStretch(1)

        layout = QVBoxLayout(view)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return view

    # -- Arbeitsansicht ---------------------------------------------------

    def _build_work_view(self) -> QWidget:
        view = QWidget()
        view.setObjectName("page")
        row = QHBoxLayout(view)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_source_column(), 1)
        self.collection = self._build_collection()
        row.addWidget(self.collection)
        return view

    def _build_source_column(self) -> QWidget:
        column = QWidget()
        column.setObjectName("sourceColumn")
        column.setAttribute(Qt.WA_StyledBackground, True)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(_label("Deine Quelle", font=typography.heading(24)))
        header.addStretch(1)

        self._source_slot_work = QVBoxLayout()
        self._source_slot_work.setContentsMargins(0, 0, 0, 0)

        body = QWidget()
        body.setObjectName("sourceBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 18)
        layout.setSpacing(0)

        self.player = PreviewPlayer()
        # Bewusst ohne Hoehenbegrenzung: Die Vorschau ist der Teil, auf den man
        # schaut, waehrend man den Ausschnitt sucht. Sie bekommt allen Platz,
        # den das Fenster hergibt - wer mehr will, zieht das Fenster groesser.
        layout.addWidget(self.player, 1)
        layout.addSpacing(14)
        layout.addWidget(self._build_meta())
        layout.addSpacing(14)
        layout.addWidget(Rule())
        layout.addSpacing(14)
        layout.addWidget(self._build_options())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        self.source_scroll = scroll

        outer = QVBoxLayout(column)
        outer.setContentsMargins(24, 22, 16, 0)
        outer.setSpacing(10)
        outer.addLayout(header)
        outer.addLayout(self._source_slot_work)
        outer.addSpacing(4)
        outer.addWidget(scroll, 1)
        return column

    def _build_meta(self) -> QWidget:
        container = QWidget()
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setObjectName("thumbnail")
        self.thumbnail_label.setFixedSize(64, 36)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)

        self.title_label = _label("", font=typography.title(15))
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.meta_label = _label("", "muted", typography.small(12))
        self.live_tag = _label("LIVE", "live", typography.tag(10))
        self.live_tag.setVisible(False)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        meta_row.addWidget(self.meta_label)
        meta_row.addWidget(self.live_tag)
        meta_row.addStretch(1)

        text = QVBoxLayout()
        text.setSpacing(3)
        text.addWidget(self.title_label)
        text.addLayout(meta_row)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.thumbnail_label, 0, Qt.AlignTop)
        layout.addLayout(text, 1)
        return container

    def _build_options(self) -> QWidget:
        container = QWidget()

        self.mode_combo = ChoiceGroup("card", accessible_name="Inhalt")
        for mode, text, icon in MODE_CARDS:
            # Qt-Datenfelder speichern nur den reinen Text - Mode erbt von str
            # und kaeme sonst als gewoehnliche Zeichenkette zurueck.
            self.mode_combo.addItem(text, mode.value, icon=icon, tooltip=mode.label)

        self.quality_combo = ChoiceGroup("chip", accessible_name="Qualitaet")
        self.quality_combo.setEnabled(False)
        self.quality_note = _label("Kein Video verfuegbar - es laesst sich nur der Ton laden.",
                                   "muted", typography.small(12), wrap=True)
        self.quality_note.setVisible(False)

        self.h264_check = ToggleSwitch("H.264 fuer Resolve")
        self.h264_check.setChecked(True)
        self.h264_check.setToolTip(
            "YouTube liefert 1440p und 4K nur als VP9 oder AV1 aus.\n"
            "DaVinci Resolve kann diese Formate nicht oeffnen.\n"
            "Ist der Schalter an, wird notfalls umgewandelt - das dauert\n"
            "laenger, dafuer laesst sich die Datei sicher importieren."
        )

        self.output_edit = QLineEdit(str(paths.DEFAULT_DOWNLOAD_DIR))
        self.output_edit.setObjectName("timecode")
        self.output_edit.setFont(typography.mono(12))
        self.output_edit.setAccessibleName("Zielordner")
        self.browse_button = IconButton("folder", "Zielordner waehlen", tooltip="Strg+O")

        folder_text = QVBoxLayout()
        folder_text.setSpacing(2)
        folder_text.addWidget(_label("Zielordner", "muted", typography.tiny(11)))
        folder_text.addWidget(self.output_edit)
        folder = QHBoxLayout()
        folder.setSpacing(8)
        folder.addLayout(folder_text, 1)
        folder.addWidget(self.browse_button, 0, Qt.AlignBottom)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(_label("Inhalt", "muted", typography.small(12)))
        layout.addSpacing(8)
        layout.addWidget(self.mode_combo)
        layout.addSpacing(14)
        layout.addWidget(_label("Qualitaet", "muted", typography.small(12)))
        layout.addSpacing(8)
        layout.addWidget(self.quality_combo)
        layout.addWidget(self.quality_note)
        layout.addSpacing(10)
        layout.addWidget(self.h264_check)
        layout.addSpacing(12)
        layout.addWidget(Rule())
        layout.addSpacing(10)
        layout.addLayout(folder)
        return container

    # -- Sammelmappe ------------------------------------------------------

    def _build_collection(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("collection")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel.setFixedWidth(COLLECTION_WIDE)

        self.clear_segments_button = IconButton("bin", "Gemerkte Ausschnitte verwerfen")
        self.clear_segments_button.setEnabled(False)
        header = QHBoxLayout()
        header.addWidget(_label("Sammelmappe", font=typography.heading(24)))
        header.addStretch(1)
        header.addWidget(self.clear_segments_button)

        self.collection_stack = QStackedWidget()
        self.collection_stack.addWidget(self._build_editor())
        self.collection_stack.addWidget(self._build_delivery())

        self.plan_label = _label("", font=typography.small(12), wrap=True)
        self.status_label = _label("Bereit.", "muted", typography.small(12), wrap=True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.resolve_note = _label("", "muted", typography.tiny(11), wrap=True)
        self.download_button = MainAction("Herunterladen")
        self.download_button.setEnabled(False)
        self.cancel_button = self.download_button.cancel_button

        send = QVBoxLayout()
        send.setSpacing(5)
        send.addWidget(self.plan_label)
        send.addWidget(self.status_label)
        send.addWidget(self.resolve_note)
        send.addSpacing(8)
        send.addWidget(self.download_button)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 22, 20, 20)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addWidget(self.collection_stack, 1)
        layout.addLayout(send)
        return panel

    def _build_editor(self) -> QWidget:
        body = QWidget()
        body.setObjectName("collectionBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 6, 6)
        layout.setSpacing(0)
        layout.addWidget(self._build_slip())
        layout.addSpacing(18)

        self.segment_tools = QWidget()
        tools = QHBoxLayout(self.segment_tools)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(8)
        tools.addWidget(_label("Gemerkte Ausschnitte", "muted", typography.small(12)))
        tools.addStretch(1)
        self.segment_count_label = _label("", "muted", typography.small(12))
        tools.addWidget(self.segment_count_label)
        self.segment_tools.setVisible(False)
        layout.addWidget(self.segment_tools)
        layout.addSpacing(8)

        self.segment_list = SegmentList()
        self.segment_list.setVisible(False)
        layout.addWidget(self.segment_list)

        self.saved_hint = _label(
            "Noch nichts abgelegt. Stelle waehlen, dann „Ablegen“ (M) - so sammelst du "
            "mehrere Ausschnitte aus einem Video. Ohne Ablage wird die aktuelle Auswahl geladen.",
            "muted", typography.small(12), wrap=True,
        )
        layout.addWidget(self.saved_hint)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        self.editor_scroll = scroll
        return scroll

    def _build_slip(self) -> QWidget:
        slip = QFrame()
        slip.setObjectName("slip")

        self.slip_title = _label("Neue Auswahl", font=typography.strong(14))
        self.add_segment_button = TextButton("Ablegen", "plus", variant="outline", height=36)
        self.add_segment_button.setToolTip(
            "Legt die Auswahl als Ausschnitt in die Mappe  ·  Taste M.\n"
            "So laesst sich aus einem Video mehr als eine Stelle herausschneiden -\n"
            "alle abgelegten Ausschnitte werden gleichzeitig geladen."
        )
        top = QHBoxLayout()
        top.addWidget(self.slip_title)
        top.addStretch(1)
        top.addWidget(self.add_segment_button)

        self.view_label = _label("Auswahl im Detail", "muted", typography.small(12))
        self.zoom_button = IconButton("zoom_out", "Ganzes Video ueberblicken")
        self.waveform_button = IconButton("wave", "Tonspur anzeigen")
        self.waveform_button.setCheckable(True)
        self.waveform_button.setEnabled(False)
        self.waveform_button._tooltip_extra = "Zeichnet den Lautstaerkeverlauf - so siehst du, wo ein Lied anfaengt."
        self.waveform_button.setText("Tonspur anzeigen")
        view_row = QHBoxLayout()
        view_row.setSpacing(2)
        view_row.addWidget(self.view_label)
        view_row.addStretch(1)
        view_row.addWidget(self.zoom_button)
        view_row.addWidget(self.waveform_button)

        self.trim_bar = TrimBar()

        self.start_edit = QLineEdit("0:00")
        self.end_edit = QLineEdit("0:00")
        for edit, name in ((self.start_edit, "Anfang"), (self.end_edit, "Ende")):
            edit.setObjectName("timecode")
            edit.setFont(typography.mono(15))
            edit.setFixedWidth(92)
            edit.setAccessibleName(name)
            edit.setToolTip("Zeit als M:SS, H:MM:SS oder mit Zehnteln (1:36.4)")
        self.selection_label = _label("-", font=typography.mono(15))
        self.selection_label.setToolTip("Laenge der Auswahl")
        times = QHBoxLayout()
        times.setSpacing(8)
        times.addWidget(_label("Von", "muted", typography.small(12)))
        times.addWidget(self.start_edit)
        times.addSpacing(6)
        times.addWidget(_label("Bis", "muted", typography.small(12)))
        times.addWidget(self.end_edit)
        times.addStretch(1)
        times.addWidget(self.selection_label)

        self.set_start_button = IconButton("in", "Anfang auf Abspielposition", key="I", variant="outline")
        self.set_end_button = IconButton("out", "Ende auf Abspielposition", key="O", variant="outline")
        self.reset_trim_button = IconButton("all", "Ganzes Video", variant="outline")
        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(self.set_start_button)
        tools.addWidget(self.set_end_button)
        tools.addWidget(self.reset_trim_button)
        tools.addStretch(1)
        tools.addWidget(_label("M  ablegen", "accentText", typography.mono(11)))

        self.slip_note = _label("", "muted", typography.small(12), wrap=True)
        self.slip_note.setVisible(False)

        layout = QVBoxLayout(slip)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(8)
        layout.addLayout(top)
        layout.addWidget(Rule("slipRule"))
        layout.addLayout(view_row)
        layout.addWidget(self.trim_bar)
        layout.addSpacing(2)
        layout.addLayout(times)
        layout.addSpacing(2)
        layout.addLayout(tools)
        layout.addWidget(self.slip_note)
        return slip

    def _build_delivery(self) -> QWidget:
        view = QWidget()
        view.setObjectName("collectionBody")
        self.delivery_heading = _label("Wird gespeichert.", font=typography.hero(27))
        self.delivery_list = DeliveryList()
        self.back_button = TextButton("Zurueck zur Mappe", "back", variant="ghost")
        self.back_button.setVisible(False)

        layout = QVBoxLayout(view)
        layout.setContentsMargins(10, 20, 6, 6)
        layout.setSpacing(0)
        layout.addWidget(self.delivery_heading)
        layout.addSpacing(28)
        layout.addWidget(self.delivery_list)
        layout.addSpacing(20)
        layout.addWidget(self.back_button)
        layout.addStretch(1)
        return view

    def _connect_signals(self) -> None:
        self.analyse_button.clicked.connect(self._start_probe)
        self.url_edit.returnPressed.connect(self._start_probe)
        self.paste_button.clicked.connect(self._paste_from_clipboard)
        self.clear_link_button.clicked.connect(self._clear_link)

        self.trim_bar.rangeChanged.connect(self._on_range_changed)
        self.trim_bar.seeked.connect(self._on_trim_seeked)
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
        self.clear_segments_button.clicked.connect(self._clear_segments)
        self.segment_list.activated.connect(self._load_segment)
        self.segment_list.removeRequested.connect(self._remove_segment_at)
        self.reset_trim_button.clicked.connect(self._reset_trim)
        self.waveform_button.clicked.connect(self._toggle_waveform)
        self.zoom_button.clicked.connect(self._toggle_zoom)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.browse_button.clicked.connect(self._choose_output_dir)

        self.download_button.clicked.connect(self._on_primary_clicked)
        self.cancel_button.clicked.connect(self._cancel_download)
        self.back_button.clicked.connect(self._back_to_collection)
        self.download_nav_button.clicked.connect(self._show_download)
        self.library_nav_button.clicked.connect(self._show_library)
        self.menu_button.clicked.connect(self._show_menu)
        self.library_page.downloadRequested.connect(self._show_download)
        self.library_page.chooseFolderRequested.connect(self._choose_library_dir)
        # Ein neuer Link hebt den Abschluss wieder auf.
        self.url_edit.textEdited.connect(self._reset_completed)
        # textEdited feuert nur bei Eingaben von Hand, nicht bei setText -
        # genau das soll als eigene Entscheidung gelten.
        self.output_edit.textEdited.connect(self._mark_output_chosen)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Schmale Fenster: Mappe etwas schmaler, damit der Vorschau Platz bleibt.
        self.collection.setFixedWidth(COLLECTION_NARROW if self.width() < 940 else COLLECTION_WIDE)
        # Niedrige Fenster: flache Medienkarten statt Schrift zu verkleinern.
        self.mode_combo.set_compact(self.height() < COMPACT_HEIGHT)

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
        self._reset_completed()

    def _clear_link(self) -> None:
        self.url_edit.clear()
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
                "Version {} wartet - Menue -> Nach Aktualisierung suchen.".format(release.version)
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
        dialog.setMinimumWidth(380)
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
                "Version {} ist verfuegbar - Menue -> Nach Aktualisierung suchen.".format(release.version)
            )
            return
        self._settings.setValue("offered_version", release.version)
        self._offer_app_update(release)

    def _show_about(self) -> None:
        from .. import __version__
        from ..core.update import current_version

        box = QMessageBox(self)
        box.setWindowTitle("Ueber Fev Download")
        box.setIconPixmap(logo_pixmap(56))
        box.setText("<b>Fev Download {}</b>".format(__version__))
        box.setInformativeText(
            "Laedt Videos von YouTube und ueber tausend weiteren Plattformen, "
            "schneidet die gewuenschten Ausschnitte heraus und uebergibt sie an "
            "DaVinci Resolve.\n\n"
            "yt-dlp {}\n"
            "Laesst eine Plattform sich nicht mehr laden, hilft meist\n"
            "Menue -> Nach Aktualisierung suchen.\n\n"
            "https://github.com/{}\n"
            "Fremde Bestandteile und ihre Lizenzen (u. a. ffmpeg, GPLv3): "
            "siehe LIZENZEN.txt im Programmordner; "
            "beigelegte ffmpeg-Quellen unter licenses/ffmpeg.\n\n"
            "Bitte nur fuer eigene Inhalte verwenden oder fuer Material, dessen "
            "Lizenz das erlaubt.".format(current_version(), appupdate.GITHUB_REPO)
        )
        box.exec()

    # ------------------------------------------------------------------
    # Seiten und Bibliothek
    # ------------------------------------------------------------------

    def _show_download(self) -> None:
        self.pages.setCurrentIndex(0)
        self.download_nav_button.setChecked(True)

    def _show_library(self) -> None:
        self.library_page.refresh()
        self.pages.setCurrentIndex(1)
        self.library_nav_button.setChecked(True)

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
            self.url_edit.setFocus()
            return
        if self._probe_worker is not None and self._probe_worker.isRunning():
            return
        if self._running:
            return

        self.analyse_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.analyse_busy.set_running(True)
        self._set_status("Analysiere Link...")

        self._probe_worker = ProbeWorker(url, self)
        self._probe_worker.succeeded.connect(self._on_probe_succeeded)
        self._probe_worker.failed.connect(self._on_probe_failed)
        self._probe_worker.start()

    def _on_probe_succeeded(self, info: VideoInfo) -> None:
        self._info = info
        # Die Wellenform des vorherigen Videos ist jetzt gegenstandslos.
        self._waveform_peaks = []
        self.waveform_button.setText("Tonspur anzeigen")
        self.waveform_button.setChecked(False)
        self.waveform_button.setEnabled(bool(info.audio_url))
        self.analyse_button.setEnabled(True)
        self.analyse_busy.set_running(False)

        if self.download_stack.currentIndex() != 1:
            self._place_source_editor(compact=True)
            self.download_stack.setCurrentIndex(1)
            fade_in(self.collection)

        self.title_label.setText(info.title)
        self.title_label.setToolTip(info.title)
        # Der Fenstertitel verraet in der Taskleiste, worum es gerade geht.
        short = info.title if len(info.title) <= 60 else info.title[:57] + "..."
        self.setWindowTitle(f"{short} - Fev Download")

        details = []
        if info.uploader:
            details.append(info.uploader)
        if info.extractor:
            details.append(info.extractor)
        details.append(info.duration_text)
        self.meta_label.setText("  ·  ".join(details))
        self.live_tag.setVisible(info.is_live)

        self.thumbnail_label.clear()
        self.thumbnail_label.setVisible(bool(info.thumbnail_url))
        if info.thumbnail_url:
            self._thumb_worker = ThumbnailWorker(info.thumbnail_url, self)
            self._thumb_worker.loaded.connect(self._on_thumbnail_loaded)
            self._thumb_worker.start()

        self._fill_quality_combo(info)

        # Gemerkte Ausschnitte gehoeren zum vorherigen Video und waeren beim
        # neuen schlicht falsch.
        self._clear_segments(silent=True)
        self.trim_bar.set_duration(info.duration)
        self.trim_bar.set_hint("" if info.audio_url else "Zu diesem Video gibt es keine abrufbare Tonspur.")
        self.player.set_aspect(info.aspect)
        self._preview_attempted_download = False
        self.player.load(info.preview_url, fallback_duration=info.duration)
        if not info.preview_url:
            # Gar keine Stream-Adresse - dann gleich die Datei holen.
            self._start_preview_fallback()

        self._completed = False
        self._show_editor()
        self.download_button.setEnabled(True)
        self._update_download_button()
        if info.is_live:
            self._set_status("Achtung: Livestream - der Ausschnitt kann ungenau sein.")
        else:
            self._set_status("Bereit zum Herunterladen.")

    def _on_probe_failed(self, message: str) -> None:
        self.analyse_button.setEnabled(True)
        self.analyse_busy.set_running(False)
        self.download_button.setEnabled(self._info is not None)
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
        self.quality_combo.setVisible(has_video)
        self.quality_note.setVisible(not has_video)
        self.quality_combo.setEnabled(has_video and self._current_mode().needs_video)

        if not has_video:
            self.mode_combo.setCurrentIndex(self.mode_combo.findData(Mode.AUDIO_ONLY.value))
            return

        # Zuletzt gewaehlte Qualitaet, sonst das Beste darunter.
        preferred = pick_height(info, self._preferred_height)
        index = self.quality_combo.findData(preferred)
        self.quality_combo.setCurrentIndex(max(0, index))

    # ------------------------------------------------------------------
    # Ausschnitt
    # ------------------------------------------------------------------

    def _saved_index(self, start: float, end: float) -> int:
        for index, (a, b) in enumerate(self._segments):
            if abs(a - start) < 0.05 and abs(b - end) < 0.05:
                return index
        return -1

    def _on_range_changed(self, start: float, end: float) -> None:
        self.start_edit.setText(precise_timecode(start))
        self.end_edit.setText(precise_timecode(end))
        length = max(0.0, end - start)
        self.selection_label.setText(precise_timecode(length))

        saved = self._saved_index(start, end)
        if saved != self.segment_list.currentRow():
            self.segment_list.setCurrentRow(saved)
        has_info = self._info is not None
        if saved >= 0:
            self.slip_title.setText(f"Ausschnitt {saved + 1}  ·  liegt in der Mappe")
            self.add_segment_button.setEnabled(False)
            self.slip_note.setVisible(False)
        else:
            self.slip_title.setText("Ganzes Video" if self.trim_bar.is_full_range() else "Neue Auswahl")
            self.add_segment_button.setEnabled(has_info)
            # Solange etwas in der Mappe liegt, wird nur die geladen. Das muss
            # am Zettel stehen, sonst glaubt man, die Auswahl komme mit.
            if self._segments:
                self.slip_note.setText(
                    "Nicht in der Mappe - geladen wird nur, was abgelegt ist."
                )
            self.slip_note.setVisible(bool(self._segments))
        self._update_plan()

    def _on_start_edited(self) -> None:
        try:
            self.trim_bar.set_start(parse_timecode(self.start_edit.text()))
        except ValueError:
            self.start_edit.setText(precise_timecode(self.trim_bar.start()))

    def _on_end_edited(self) -> None:
        try:
            self.trim_bar.set_end(parse_timecode(self.end_edit.text()))
        except ValueError:
            self.end_edit.setText(precise_timecode(self.trim_bar.end()))

    def _set_start_from_playhead(self) -> None:
        self.trim_bar.set_start(self.player.position())

    def _set_end_from_playhead(self) -> None:
        self.trim_bar.set_end(self.player.position())

    def _reset_trim(self) -> None:
        if self._info is None:
            return
        # set_duration verwirft die Wellenform - sie gehoert aber weiter zum
        # selben Video, also gleich wieder einsetzen. Ebenso die gemerkten
        # Ausschnitte: Sie gelten weiter, nur der Zettel faengt von vorn an.
        peaks = self._waveform_peaks
        shown = self.trim_bar.has_waveform()
        self.trim_bar.set_duration(self._info.duration)
        if peaks and shown:
            self.trim_bar.set_waveform(peaks)
        self.trim_bar.set_segments(self._segments)

    def _toggle_zoom(self) -> None:
        zoomed = not self.trim_bar.is_zoomed()
        self.trim_bar.set_zoomed(zoomed)
        if zoomed:
            self.zoom_button.set_icon("zoom_out")
            self.zoom_button.setText("Ganzes Video ueberblicken")
            self.view_label.setText("Auswahl im Detail")
        else:
            self.zoom_button.set_icon("zoom_in")
            self.zoom_button.setText("Auf die Auswahl zoomen")
            self.view_label.setText("Ganzes Video")

    # ------------------------------------------------------------------
    # Vorschau folgt dem Griff
    # ------------------------------------------------------------------

    def _on_trim_seeked(self, seconds: float) -> None:
        self.player.seek(seconds)
        # Ohne abspielbare Vorschau meldet der Player nichts zurueck.
        self.trim_bar.set_playhead(seconds)

    def _on_trim_scrub(self, seconds: float) -> None:
        """
        Waehrend ein Griff gezogen wird, springt die Vorschau mit.

        Gedrosselt, weil jede Mausbewegung sonst einen eigenen Sprungbefehl
        ausloest und der Player ins Stocken geraet; der genaue Endwert kommt
        beim Loslassen ueber scrubFinished.
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
        """Legt den gerade eingestellten Bereich in die Mappe."""
        if self._info is None or self.trim_bar.duration() <= 0:
            self._set_status("Erst einen Link analysieren.", error=True)
            return
        if self._running:
            return

        start = round(self.trim_bar.start(), 2)
        end = round(self.trim_bar.end(), 2)
        if end - start < 1.0:
            self._set_status("Der Ausschnitt ist zu kurz.", error=True)
            return
        if (start, end) in self._segments or self._saved_index(start, end) >= 0:
            self._set_status("Dieser Ausschnitt liegt schon in der Mappe.")
            return

        self._segments.append((start, end))
        self._segments.sort()
        index = self._segments.index((start, end))
        self._refresh_segments(animate_index=index)
        self.segment_list.setCurrentRow(index)
        self._set_status(
            f"Abgelegt: {precise_timecode(start)} bis {precise_timecode(end)}  ·  "
            f"{len(self._segments)} in der Mappe"
        )

    def _remove_segment(self) -> None:
        self._remove_segment_at(self.segment_list.currentRow())

    def _remove_segment_at(self, row: int) -> None:
        if not (0 <= row < len(self._segments)) or self._running:
            return
        start, end = self._segments.pop(row)
        self._refresh_segments()
        self._set_status(f"Entfernt: {precise_timecode(start)} bis {precise_timecode(end)}")

    def _clear_segments(self, silent: bool = False) -> None:
        if not self._segments or self._running:
            return
        self._segments = []
        self._refresh_segments()
        if not silent:
            self._set_status("Die Mappe ist wieder leer.")

    def _load_segment(self, index: int) -> None:
        """Holt einen gemerkten Ausschnitt zurueck in den Zettel."""
        if not (0 <= index < len(self._segments)):
            return
        start, end = self._segments[index]
        self.trim_bar.set_range(start, end)
        self.segment_list.setCurrentRow(index)
        self._seek_preview(start)
        # Ein Klick auf den gemerkten Ausschnitt spielt genau diesen Teil in
        # Schleife, bis man anhaelt (Leertaste) oder im Video springt.
        self.player.loop_range(start, end)

    def _toggle_playback(self) -> None:
        """Leertaste: Vorschau anhalten bzw. weiterspielen."""
        if self.pages.currentIndex() != 0 or self.download_stack.currentIndex() != 1:
            return
        if self.player.can_play():
            self.player.toggle_play()

    def _refresh_segments(self, animate_index: int = -1) -> None:
        """Bringt Liste, Zeitleiste, Zaehler und Knopf auf denselben Stand."""
        title = self._info.title if self._info else ""
        items = [
            (title, f"{precise_timecode(a)}–{precise_timecode(b)}  ·  {format_timecode(b - a)}")
            for a, b in self._segments
        ]
        self.segment_list.set_items(items, animate_index=animate_index)

        count = len(self._segments)
        self.segment_list.setVisible(count > 0)
        self.segment_tools.setVisible(count > 0)
        self.saved_hint.setVisible(count == 0)
        self.clear_segments_button.setEnabled(count > 0)
        if count:
            total = sum(end - start for start, end in self._segments)
            self.segment_count_label.setText(f"{count}  ·  {format_timecode(total)}")

        self.trim_bar.set_segments(self._segments)
        self._update_download_button()
        # Zettel und Anzeige haengen davon ab, ob die Mappe gefuellt ist.
        self._on_range_changed(self.trim_bar.start(), self.trim_bar.end())

    def _update_plan(self) -> None:
        """Sagt ueber dem Knopf, was er gleich laedt - nie mehr, als stimmt."""
        if self._info is None:
            self.plan_label.setText("")
            self.plan_label.setVisible(False)
            return
        count = len(self._segments)
        if count:
            total = format_timecode(sum(b - a for a, b in self._segments))
            if count == 1:
                text = f"1 abgelegter Ausschnitt wird geladen  ·  {total}"
            else:
                text = f"{count} abgelegte Ausschnitte werden gleichzeitig geladen  ·  {total} gesamt"
        elif self.trim_bar.is_full_range():
            text = f"Das ganze Video wird geladen  ·  {format_timecode(self._info.duration)}"
        else:
            length = precise_timecode(self.trim_bar.end() - self.trim_bar.start())
            text = f"Die aktuelle Auswahl wird geladen  ·  {length}"
        self.plan_label.setText(text)
        self.plan_label.setVisible(True)

    def _download_label(self) -> str:
        count = len(self._segments)
        if count > 1:
            return f"{count} Ausschnitte laden"
        if count == 1:
            return "Ausschnitt laden"
        return "Herunterladen"

    def _update_download_button(self) -> None:
        """Der Knopf sagt, was gleich passiert - ein Clip oder mehrere."""
        if self._completed or self._running:
            return
        self.download_button.set_idle(self._download_label())
        self._update_plan()

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
            self.waveform_button.setChecked(False)
            return

        # Schon einmal berechnet - dann nur wieder einblenden.
        if self._waveform_peaks:
            self.trim_bar.set_waveform(self._waveform_peaks)
            self.waveform_button.setText("Tonspur ausblenden")
            self.waveform_button.setChecked(True)
            return

        self.waveform_button.setChecked(False)
        if self._info is None or not self._info.audio_url:
            self._set_status("Zu diesem Video gibt es keine abrufbare Tonspur.", error=True)
            return
        if self._waveform_worker is not None and self._waveform_worker.isRunning():
            return

        self.waveform_button.setEnabled(False)
        self.waveform_button.setText("Lade Tonspur...")
        self.trim_bar.set_hint("Tonspur wird geladen ...")

        # Mehr Werte als Pixel: Die Detailansicht zoomt hinein und braucht
        # dort noch Aufloesung.
        self._waveform_worker = WaveformWorker(
            self._info.audio_url,
            self._info.duration,
            buckets=min(36000, max(1200, int(self._info.duration * 10))),
            parent=self,
        )
        self._waveform_worker.succeeded.connect(self._on_waveform_ready)
        self._waveform_worker.failed.connect(self._on_waveform_failed)
        self._waveform_worker.start()

    def _on_waveform_ready(self, peaks: list) -> None:
        self._waveform_peaks = list(peaks)
        self.trim_bar.set_waveform(self._waveform_peaks)
        self.trim_bar.set_hint("")
        self.waveform_button.setText("Tonspur ausblenden")
        self.waveform_button.setChecked(True)
        self.waveform_button.setEnabled(True)

    def _on_waveform_failed(self, message: str) -> None:
        self.waveform_button.setText("Tonspur anzeigen")
        self.waveform_button.setChecked(False)
        self.waveform_button.setEnabled(True)
        self.trim_bar.set_hint("Tonspur nicht geladen - erneut ueber das Wellen-Symbol versuchen.")
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
        elif not self._running:
            self._start_download()

    def _reset_completed(self) -> None:
        """Zurueck in den Download-Zustand, sobald ein neuer Link kommt."""
        if not self._completed:
            return
        self._completed = False
        self._show_editor()
        self._update_download_button()

    def _back_to_collection(self) -> None:
        """Aus der Lieferliste zurueck an den Zettel - z. B. fuer weitere Stellen."""
        if self._running:
            return
        self._completed = False
        self._show_editor()
        self._update_download_button()

    def _show_editor(self) -> None:
        if self.collection_stack.currentIndex() != 0:
            self.collection_stack.setCurrentIndex(0)
            fade_in(self.collection_stack.currentWidget())
        self.clear_segments_button.setEnabled(bool(self._segments))

    def _build_requests(self) -> list[DownloadRequest]:
        """
        Baut die Auftragsliste fuer den Download.

        Liegen Ausschnitte in der Mappe, gilt ausschliesslich sie - der Zettel
        war dann nur das Werkzeug, mit dem sie entstanden sind. Ist die Mappe
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
        self._open_delivery(requests)
        self._set_state_busy()
        if len(requests) > 1:
            self._set_status(f"Lade {len(requests)} Ausschnitte gleichzeitig...")
        else:
            self._set_status("Starte Download...")

        self._download_worker = DownloadWorker(requests, self)
        self._download_worker.progressed.connect(self._on_progress)
        self._download_worker.partReady.connect(self._on_part_ready)
        self._download_worker.fileReady.connect(self._on_file_ready)
        self._download_worker.succeeded.connect(self._on_download_succeeded)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.cancelled.connect(self._on_download_cancelled)
        self._download_worker.start()

    def _open_delivery(self, requests: list[DownloadRequest]) -> None:
        """Ersetzt den Zettel durch die Lieferliste - einen Eintrag je Auftrag."""
        title = self._info.title if self._info else ""
        jobs = []
        for number, request in enumerate(requests, start=1):
            name = f"{title}  ·  Ausschnitt {number}" if len(requests) > 1 else title
            if request.start is None:
                span = f"Ganzes Video  ·  {format_timecode(self._info.duration if self._info else 0)}"
            else:
                span = f"{precise_timecode(request.start)}–{precise_timecode(request.end)}"
            jobs.append((name, span))
        self._job_rows = self.delivery_list.set_jobs(jobs)
        for row in self._job_rows:
            row.path = None
            row.folder_button.clicked.connect(lambda _=False, r=row: r.path and self._reveal(r.path))
        self._parts_done = 0
        # Die Auftraege laufen in Reihenfolge an, hoechstens MAX_PARALLEL zugleich.
        for index, row in enumerate(self._job_rows):
            row.set_state(JobRow.RUNNING if index < MAX_PARALLEL else JobRow.WAITING)
        self.delivery_heading.setText("Wird gespeichert.")
        self.back_button.setVisible(False)
        self.collection_stack.setCurrentIndex(1)
        fade_in(self.collection_stack.currentWidget())

    def _cancel_download(self) -> None:
        if self._download_worker is not None and self._download_worker.isRunning():
            self._set_status("Breche ab - der laufende Ausschnitt wird noch fertig geladen...")
            self.cancel_button.setEnabled(False)
            self._download_worker.cancel()

    def _on_progress(self, progress: Progress) -> None:
        # Bei mehreren Ausschnitten steht vorn, wie viele schon fertig sind.
        # Die Prozentzahl ist dann der Mittelwert ueber alle - sie laufen
        # gleichzeitig, ein einzelner Balken je Download waere Unfug.
        prefix = [progress.part_text] if progress.part_text else []

        if progress.status == "downloading" and progress.percent > 0:
            self.download_button.set_progress(progress.percent, f"{progress.percent:.0f} %")
            bits = prefix + [f"{progress.percent:.0f} %"]
            if progress.speed_text:
                bits.append(progress.speed_text)
            if progress.eta_text:
                bits.append(progress.eta_text)
            self._set_status("  ·  ".join(bits))
        else:
            self.download_button.set_progress(None)
            bits = prefix + [progress.message or "Wird verarbeitet..."]
            self._set_status("  ·  ".join(bits))

    def _on_part_ready(self, index: int, path: Path) -> None:
        """Ein Auftrag ist fertig - Zeile abhaken, der naechste wartende rueckt nach."""
        if not (0 <= index < len(self._job_rows)):
            return
        row = self._job_rows[index]
        if row.state() != JobRow.DONE:
            self._parts_done += 1
        row.set_state(JobRow.DONE)
        row.path = path
        row.folder_button.setToolTip(str(path))
        for position, other in enumerate(self._job_rows):
            if other.state() == JobRow.WAITING and position < MAX_PARALLEL + self._parts_done:
                other.set_state(JobRow.RUNNING)

    def _reveal(self, path: Path) -> None:
        try:
            subprocess.Popen(["explorer", "/select,", str(path)])
        except Exception as exc:
            self._set_status(f"Ordner laesst sich nicht oeffnen: {exc}", error=True)

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
        self._running = False
        self._completed = True
        self._set_state_idle()

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

        if self.collection_stack.currentIndex() == 1:
            self.delivery_heading.setText("Abgelegt.")
            self.back_button.setVisible(True)
        # "werden geladen" stimmt jetzt nicht mehr - die Statuszeile sagt, was ist.
        self.plan_label.setVisible(False)
        self.download_button.set_done("Fertig")
        self.download_button.setToolTip("Fenster schliessen")
        self.download_button.setFocus()

        self.on_download_finished(result)

    def _finish_rows(self) -> None:
        for row in self._job_rows:
            if row.state() != JobRow.DONE:
                row.set_state(JobRow.FAILED)
        self.back_button.setVisible(True)

    def _on_download_failed(self, message: str) -> None:
        self._running = False
        self._set_state_idle()
        self._finish_rows()
        self.delivery_heading.setText("Nicht alles geladen.")
        self._set_status(message, error=True)
        QMessageBox.warning(self, "Download fehlgeschlagen", message)

    def _on_download_cancelled(self) -> None:
        self._running = False
        self._set_state_idle()
        self._finish_rows()
        self.delivery_heading.setText("Abgebrochen.")
        self._set_status("Abgebrochen.")

    def on_download_finished(self, result: Path) -> None:
        """Haken fuer die Resolve-Anbindung."""

    # ------------------------------------------------------------------
    # Zustaende
    # ------------------------------------------------------------------

    def _set_state_busy(self) -> None:
        self._running = True
        self.download_button.set_running("Wird geladen")
        self.download_button.setToolTip("")
        self.analyse_button.setEnabled(False)
        self.url_edit.setEnabled(False)
        self.paste_button.setEnabled(False)
        self.clear_link_button.setEnabled(False)
        self.clear_segments_button.setEnabled(False)
        self.add_segment_button.setEnabled(False)

    def _set_state_idle(self) -> None:
        self.download_button.setEnabled(self._info is not None)
        self.download_button.setToolTip("")
        if not self._completed:
            self.download_button.set_idle(self._download_label())
        self.analyse_button.setEnabled(True)
        self.url_edit.setEnabled(True)
        self.paste_button.setEnabled(True)
        self.clear_link_button.setEnabled(True)
        # In der Lieferliste gibt es nichts zu verwerfen.
        self.clear_segments_button.setEnabled(
            bool(self._segments) and self.collection_stack.currentIndex() == 0
        )
        if self._info is not None and not self._completed:
            self._on_range_changed(self.trim_bar.start(), self.trim_bar.end())

    def _set_status(self, message: str, error: bool = False) -> None:
        for label in (self.status_label, self.empty_status):
            label.setText(message)
            label.setObjectName("error" if error else "muted")
            # Damit die geaenderte Farbe auch wirklich gezeichnet wird.
            label.style().unpolish(label)
            label.style().polish(label)

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
