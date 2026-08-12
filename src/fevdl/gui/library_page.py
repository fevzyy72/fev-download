"""Bibliothek fuer bereits heruntergeladene Medien."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import typography
from .worker import LibraryThumbWorker

# Grosse genug, um den Inhalt zu erkennen, klein genug fuer eine ruhige Liste.
THUMB_SIZE = QSize(72, 41)
# Obergrenze fuer eine Ansicht: Bei einem Ordner mit tausenden Dateien waere es
# sinnlos, fuer alle ffmpeg zu bemuehen - sichtbar sind ohnehin nur wenige.
THUMB_LIMIT = 400


VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}

AUDIO_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}


@dataclass(frozen=True)
class LibraryEntry:
    """Eine Mediendatei mit den Angaben fuer Suche und Sortierung."""

    path: Path
    kind: str
    modified: float
    size: int

    @property
    def format_label(self) -> str:
        return self.path.suffix.lstrip(".").upper()


def scan_media(root: Path) -> list[LibraryEntry]:
    """Liest alle unterstuetzten Medien unterhalb eines Ordners ein."""
    if not root.is_dir():
        return []

    entries: list[LibraryEntry] = []
    try:
        candidates = root.rglob("*")
        for candidate in candidates:
            suffix = candidate.suffix.lower()
            if suffix in VIDEO_EXTENSIONS:
                kind = "video"
            elif suffix in AUDIO_EXTENSIONS:
                kind = "audio"
            else:
                continue

            try:
                stat = candidate.stat()
            except OSError:
                continue
            if candidate.is_file():
                entries.append(
                    LibraryEntry(
                        path=candidate,
                        kind=kind,
                        modified=stat.st_mtime,
                        size=stat.st_size,
                    )
                )
    except OSError:
        return entries
    return entries


def format_size(size: int) -> str:
    """Dateigroesse in einer kurzen, gut lesbaren Form."""
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


class LibraryPage(QWidget):
    """Durchsuchbare Liste der Dateien im aktuellen Download-Ordner."""

    downloadRequested = Signal()
    chooseFolderRequested = Signal()

    def __init__(
        self,
        root_provider: Callable[[], Path],
        import_file: Optional[Callable[[Path], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._root_provider = root_provider
        self._import_file = import_file
        self._entries: list[LibraryEntry] = []
        # Fertige Vorschaubilder: Quelldatei -> Bilddatei. Damit erscheinen sie
        # beim naechsten Filterwechsel sofort statt erst nach ffmpeg.
        self._thumbs: dict[str, str] = {}
        self._rows: dict[str, QTreeWidgetItem] = {}
        self._placeholder: Optional[QPixmap] = None
        self._thumb_worker = LibraryThumbWorker(self)
        self._thumb_worker.ready.connect(self._on_thumb_ready)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(44, 26, 44, 28)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addSpacing(14)

        rule = QFrame()
        rule.setObjectName("rule")
        rule.setFrameShape(QFrame.HLine)
        rule.setFixedHeight(1)
        root.addWidget(rule)
        root.addSpacing(20)

        controls = QFrame()
        controls.setObjectName("card")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(16, 14, 16, 14)
        controls_layout.setSpacing(10)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("librarySearch")
        self.search_edit.setPlaceholderText("Nach Dateiname oder Ordner suchen")
        self.search_edit.setClearButtonEnabled(True)

        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Alle Medien", "all")
        self.kind_combo.addItem("Nur Videos", "video")
        self.kind_combo.addItem("Nur Audio", "audio")

        self.date_combo = QComboBox()
        self.date_combo.addItem("Jedes Datum", "all")
        self.date_combo.addItem("Heute", "today")
        self.date_combo.addItem("Letzte 7 Tage", "week")
        self.date_combo.addItem("Letzte 30 Tage", "month")
        self.date_combo.addItem("Dieses Jahr", "year")

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Neueste zuerst", "newest")
        self.sort_combo.addItem("Aelteste zuerst", "oldest")
        self.sort_combo.addItem("Name A-Z", "name")
        self.sort_combo.addItem("Groesste zuerst", "size")

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(self.search_edit, 5)
        filter_row.addWidget(self.kind_combo, 2)
        filter_row.addWidget(self.date_combo, 2)
        filter_row.addWidget(self.sort_combo, 2)
        controls_layout.addLayout(filter_row)

        root.addWidget(controls)
        root.addSpacing(14)

        info_row = QHBoxLayout()
        info_row.setSpacing(10)
        self.count_label = QLabel("0 Dateien")
        self.count_label.setObjectName("libraryCount")
        self.count_label.setFont(typography.title(10))
        self.folder_label = QLabel()
        self.folder_label.setObjectName("muted")
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.choose_folder_button = QPushButton("Ordner wechseln")
        self.choose_folder_button.setObjectName("quiet")
        self.refresh_button = QPushButton("Aktualisieren")
        self.refresh_button.setObjectName("softAction")

        info_row.addWidget(self.count_label)
        info_row.addWidget(self.folder_label, 1)
        info_row.addWidget(self.choose_folder_button)
        info_row.addWidget(self.refresh_button)
        root.addLayout(info_row)
        root.addSpacing(10)

        self.table = QTreeWidget()
        self.table.setObjectName("libraryTable")
        self.table.setColumnCount(5)
        self.table.setHeaderLabels(["Name", "Typ", "Format", "Datum", "Groesse"])
        self.table.setIconSize(THUMB_SIZE)
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAllColumnsShowFocus(True)
        self.table.setSortingEnabled(False)

        header = self.table.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        empty = QFrame()
        empty.setObjectName("libraryEmpty")
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(32, 32, 32, 32)
        empty_layout.addStretch(1)
        self.empty_title = QLabel("Noch keine Medien gefunden")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_title.setFont(typography.hero(16))
        self.empty_hint = QLabel(
            "Downloads aus diesem Ordner erscheinen automatisch hier."
        )
        self.empty_hint.setObjectName("muted")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addSpacing(5)
        empty_layout.addWidget(self.empty_hint)
        empty_layout.addStretch(1)

        self.result_stack = QStackedWidget()
        self.result_stack.addWidget(self.table)
        self.result_stack.addWidget(empty)
        root.addWidget(self.result_stack, 1)
        root.addSpacing(14)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.status_label = QLabel("Bereit.")
        self.status_label.setObjectName("muted")
        self.open_folder_button = QPushButton("Im Ordner zeigen")
        self.open_folder_button.setEnabled(False)
        self.open_button = QPushButton("Oeffnen")
        self.open_button.setObjectName("primary")
        self.open_button.setEnabled(False)
        self.import_button = QPushButton("In Media Pool")
        self.import_button.setObjectName("resolveAction")
        self.import_button.setVisible(self._import_file is not None)
        self.import_button.setEnabled(False)

        actions.addWidget(self.status_label, 1)
        actions.addWidget(self.open_folder_button)
        actions.addWidget(self.import_button)
        actions.addWidget(self.open_button)
        root.addLayout(actions)

    def _build_header(self) -> QWidget:
        container = QWidget()

        title = QLabel("Bibliothek")
        title.setObjectName("hero")
        title.setFont(typography.hero())

        subtitle = QLabel("Deine Downloads, sofort griffbereit.")
        subtitle.setObjectName("subtitle")

        self.download_nav_button = QPushButton("Download")
        self.download_nav_button.setObjectName("nav")
        self.library_nav_button = QPushButton("Bibliothek")
        self.library_nav_button.setObjectName("navActive")

        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title, 0, Qt.AlignBottom)
        layout.addWidget(subtitle, 0, Qt.AlignBottom)
        layout.addStretch(1)
        layout.addWidget(self.download_nav_button)
        layout.addWidget(self.library_nav_button)
        return container

    def _connect_signals(self) -> None:
        self.download_nav_button.clicked.connect(self.downloadRequested.emit)
        self.choose_folder_button.clicked.connect(self.chooseFolderRequested.emit)
        self.refresh_button.clicked.connect(self.refresh)
        self.search_edit.textChanged.connect(self._apply_filters)
        self.kind_combo.currentIndexChanged.connect(self._apply_filters)
        self.date_combo.currentIndexChanged.connect(self._apply_filters)
        self.sort_combo.currentIndexChanged.connect(self._apply_filters)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(lambda _item, _column: self._open_selected())
        self.open_button.clicked.connect(self._open_selected)
        self.open_folder_button.clicked.connect(self._show_selected_in_folder)
        self.import_button.clicked.connect(self._import_selected)

    def refresh(self) -> None:
        """Liest den aktuellen Download-Ordner neu ein."""
        root = self._root_provider()
        self.folder_label.setText(str(root))
        self.folder_label.setToolTip(str(root))
        self._entries = scan_media(root)
        self._apply_filters()

    def _filtered_entries(self) -> list[LibraryEntry]:
        query = self.search_edit.text().strip().casefold()
        kind = self.kind_combo.currentData()
        period = self.date_combo.currentData()
        now = datetime.now()
        now_timestamp = now.timestamp()

        result = []
        for entry in self._entries:
            if kind != "all" and entry.kind != kind:
                continue
            searchable = f"{entry.path.name} {entry.path.parent}".casefold()
            if query and query not in searchable:
                continue

            age = now_timestamp - entry.modified
            modified = datetime.fromtimestamp(entry.modified)
            if period == "today" and modified.date() != now.date():
                continue
            if period == "week" and age > 7 * 86400:
                continue
            if period == "month" and age > 30 * 86400:
                continue
            if period == "year" and modified.year != now.year:
                continue
            result.append(entry)

        sort_mode = self.sort_combo.currentData()
        if sort_mode == "oldest":
            result.sort(key=lambda item: item.modified)
        elif sort_mode == "name":
            result.sort(key=lambda item: item.path.name.casefold())
        elif sort_mode == "size":
            result.sort(key=lambda item: item.size, reverse=True)
        else:
            result.sort(key=lambda item: item.modified, reverse=True)
        return result

    def _apply_filters(self) -> None:
        entries = self._filtered_entries()
        self.table.clear()
        self._rows.clear()

        missing: list[tuple[str, str]] = []
        for entry in entries:
            modified = datetime.fromtimestamp(entry.modified).strftime("%d.%m.%Y  %H:%M")
            kind_label = "Video" if entry.kind == "video" else "Audio"
            item = QTreeWidgetItem(
                [
                    entry.path.stem,
                    kind_label,
                    entry.format_label,
                    modified,
                    format_size(entry.size),
                ]
            )
            key = str(entry.path)
            item.setData(0, Qt.UserRole, key)
            item.setToolTip(0, key)
            item.setTextAlignment(1, Qt.AlignCenter)
            item.setTextAlignment(2, Qt.AlignCenter)
            item.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)

            cached = self._thumbs.get(key)
            if cached:
                item.setIcon(0, QIcon(cached))
            else:
                # Der Platzhalter haelt die Zeilenhoehe von Anfang an gleich -
                # sonst wuerde die Liste beim Eintreffen der Bilder springen.
                item.setIcon(0, QIcon(self._placeholder_pixmap()))
                if len(missing) < THUMB_LIMIT:
                    missing.append((key, entry.kind))

            self._rows[key] = item
            self.table.addTopLevelItem(item)

        self._thumb_worker.submit(missing)

        total = len(self._entries)
        shown = len(entries)
        if shown == total:
            self.count_label.setText(f"{shown} Dateien")
        else:
            self.count_label.setText(f"{shown} von {total} Dateien")

        has_results = bool(entries)
        self.result_stack.setCurrentIndex(0 if has_results else 1)
        if not has_results and total:
            self.empty_title.setText("Keine passenden Medien")
            self.empty_hint.setText("Passe Suche oder Filter an.")
        else:
            self.empty_title.setText("Noch keine Medien gefunden")
            self.empty_hint.setText(
                "Downloads aus diesem Ordner erscheinen automatisch hier."
            )
        self._on_selection_changed()

    # -- Vorschaubilder -----------------------------------------------------

    def _placeholder_pixmap(self) -> QPixmap:
        """
        Leere Kachel fuer Zeilen, deren Bild noch fehlt oder nicht zu holen ist.

        Wird erst beim ersten Bedarf erzeugt: Ein QPixmap vor dem Start der
        Anwendung anzulegen - auch auf Modulebene - bringt Qt zum Absturz.
        """
        if self._placeholder is None:
            pixmap = QPixmap(THUMB_SIZE)
            pixmap.fill(QColor("#FBFBFA"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#EAEAEA"))
            painter.drawRect(0, 0, THUMB_SIZE.width() - 1, THUMB_SIZE.height() - 1)
            painter.end()
            self._placeholder = pixmap
        return self._placeholder

    def _on_thumb_ready(self, source: str, thumbnail: str) -> None:
        self._thumbs[source] = thumbnail
        item = self._rows.get(source)
        # Fehlt die Zeile, wurde inzwischen gefiltert oder neu eingelesen - das
        # Bild bleibt trotzdem gemerkt und erscheint beim naechsten Aufbau.
        if item is not None:
            item.setIcon(0, QIcon(thumbnail))

    def shutdown(self) -> None:
        """Haelt den Bilder-Thread an - beim Schliessen des Fensters aufzurufen."""
        self._thumb_worker.stop()
        self._thumb_worker.wait(3000)

    def selected_path(self) -> Optional[Path]:
        items = self.table.selectedItems()
        if not items:
            return None
        value = items[0].data(0, Qt.UserRole)
        return Path(value) if value else None

    def _on_selection_changed(self) -> None:
        selected = self.selected_path()
        enabled = selected is not None and selected.is_file()
        self.open_button.setEnabled(enabled)
        self.open_folder_button.setEnabled(enabled)
        self.import_button.setEnabled(enabled and self._import_file is not None)

    def _open_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            return
        try:
            os.startfile(str(path))
            self._set_status(f"Geoeffnet: {path.name}")
        except Exception as exc:
            self._set_status(f"Datei laesst sich nicht oeffnen: {exc}", error=True)

    def _show_selected_in_folder(self) -> None:
        path = self.selected_path()
        if path is None:
            return
        try:
            os.startfile(str(path.parent))
            self._set_status(str(path.parent))
        except Exception as exc:
            self._set_status(f"Ordner laesst sich nicht oeffnen: {exc}", error=True)

    def _import_selected(self) -> None:
        path = self.selected_path()
        if path is None or self._import_file is None:
            return
        self._import_file(path)
        self._set_status(f"An Media Pool uebergeben: {path.name}")

    def _set_status(self, message: str, error: bool = False) -> None:
        self.status_label.setText(message)
        self.status_label.setObjectName("error" if error else "muted")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
