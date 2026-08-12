"""Balken zum Waehlen des Ausschnitts.

Enthaelt drei Dinge uebereinander:

    Zeitangaben   was Anfang und Ende gerade bedeuten, direkt ueber den Griffen
    Balken        das ganze Video, mit Wellenform, Griffen und Abspielmarke
    Streifen      die gemerkten Ausschnitte - nur sichtbar, wenn es welche gibt

Beim Ziehen eines Griffs meldet der Balken laufend 'scrubbed'. Das Hauptfenster
spult die Vorschau daraufhin an diese Stelle, damit man das Bild sieht, an dem
geschnitten wird - und nicht nur eine Zahl.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..core.models import format_timecode
from . import typography

HANDLE_WIDTH = 9
TRACK_HEIGHT = 44  # hoch genug, dass die Wellenform etwas aussagt
GRAB_TOLERANCE = 14  # Pixel, innerhalb derer ein Griff angefasst wird
LABEL_BAND = 16  # Platz ueber dem Balken fuer die Zeitangaben
SEGMENT_BAND = 12  # Streifen unter dem Balken fuer gemerkte Ausschnitte
GAP = 4

COLOR_TRACK = QColor("#FFFFFF")
COLOR_TRACK_BORDER = QColor("#EAEAEA")
COLOR_EXCLUDED = QColor(17, 17, 17, 28)  # was wegfaellt, wird abgedunkelt
COLOR_HANDLE = QColor("#111111")
COLOR_PLAYHEAD = QColor("#9F2F2D")
COLOR_WAVE = QColor("#B9B7B1")
COLOR_LABEL = QColor("#787774")
COLOR_LABEL_ACTIVE = QColor("#111111")
COLOR_SEGMENT = QColor("#1F6C9F")
COLOR_SEGMENT_FILL = QColor(31, 108, 159, 46)  # Vorschau im Balken selbst
COLOR_SEGMENT_RAIL = QColor("#F1F0EE")


class TrimBar(QWidget):
    """
    Zeigt die gesamte Videolaenge als Balken.

    Der markierte Bereich ist das, was spaeter geladen wird. Die rote Linie ist
    die aktuelle Stelle in der Vorschau.
    """

    rangeChanged = Signal(float, float)   # start, end in Sekunden
    seeked = Signal(float)                # Nutzer klickt auf den Balken
    scrubbed = Signal(float)              # Griff wird gezogen - Vorschau folgt
    scrubFinished = Signal(float)         # Griff losgelassen - endgueltige Stelle
    segmentPicked = Signal(int)           # Klick auf einen gemerkten Ausschnitt

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._duration = 0.0
        self._start = 0.0
        self._end = 0.0
        self._playhead = 0.0
        self._dragging: str | None = None  # "start" | "end" | None
        self._waveform: list[float] = []
        self._segments: list[tuple[float, float]] = []

        # Schriften erst hier anlegen: vor dem Start der Anwendung erzeugt,
        # brechen Qt-Zeichenobjekte den Import ab.
        self._label_font = typography.mono(8)
        self._segment_font = typography.mono(7)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setEnabled(False)
        self._apply_height()

    # -- Zustand ------------------------------------------------------------

    def set_duration(self, duration: float) -> None:
        self._duration = max(0.0, float(duration))
        self._start = 0.0
        self._end = self._duration
        self._playhead = 0.0
        self._waveform = []  # gehoert zum vorherigen Video
        self.setEnabled(self._duration > 0)
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def set_waveform(self, peaks: list[float]) -> None:
        """Hinterlegt die Tonspur als Verlaufsbild im Balken."""
        self._waveform = list(peaks or [])
        self.update()

    def has_waveform(self) -> bool:
        return bool(self._waveform)

    def set_segments(self, segments: list[tuple[float, float]]) -> None:
        """Uebernimmt die gemerkten Ausschnitte zum Anzeigen."""
        self._segments = [(float(a), float(b)) for a, b in segments]
        self._apply_height()
        self.update()

    def duration(self) -> float:
        return self._duration

    def start(self) -> float:
        return self._start

    def end(self) -> float:
        return self._end

    def set_start(self, value: float, notify: bool = True) -> None:
        value = self._clamp(value)
        # Mindestens eine Sekunde Abstand, sonst waere der Ausschnitt leer.
        self._start = min(value, max(0.0, self._end - 1.0))
        self.update()
        if notify:
            self.rangeChanged.emit(self._start, self._end)

    def set_end(self, value: float, notify: bool = True) -> None:
        value = self._clamp(value)
        self._end = max(value, min(self._duration, self._start + 1.0))
        self.update()
        if notify:
            self.rangeChanged.emit(self._start, self._end)

    def set_range(self, start: float, end: float, notify: bool = True) -> None:
        """Setzt beide Griffe auf einmal - fuer das Zurueckholen aus der Liste."""
        start = self._clamp(start)
        end = self._clamp(end)
        if end < start + 1.0:
            end = min(self._duration, start + 1.0)
        self._start = start
        self._end = end
        self.update()
        if notify:
            self.rangeChanged.emit(self._start, self._end)

    def set_playhead(self, value: float) -> None:
        self._playhead = self._clamp(value)
        self.update()

    def is_full_range(self) -> bool:
        """True, wenn das ganze Video gemeint ist (dann kein Schnitt noetig)."""
        if self._duration <= 0:
            return True
        return self._start <= 0.05 and self._end >= self._duration - 0.05

    def _clamp(self, value: float) -> float:
        return max(0.0, min(float(value), self._duration))

    def _apply_height(self) -> None:
        """Der Streifen kostet nur Hoehe, wenn wirklich Ausschnitte gemerkt sind."""
        height = LABEL_BAND + GAP + TRACK_HEIGHT + 4
        if self._segments:
            height += GAP + SEGMENT_BAND
        self.setFixedHeight(height)

    # -- Umrechnung Pixel <-> Sekunden --------------------------------------

    def _track_rect(self) -> QRectF:
        margin = HANDLE_WIDTH / 2
        return QRectF(
            margin,
            LABEL_BAND + GAP,
            max(1.0, self.width() - 2 * margin),
            TRACK_HEIGHT,
        )

    def _segment_rect(self) -> QRectF:
        track = self._track_rect()
        return QRectF(track.left(), track.bottom() + GAP + 2, track.width(), SEGMENT_BAND)

    def _seconds_to_x(self, seconds: float) -> float:
        track = self._track_rect()
        if self._duration <= 0:
            return track.left()
        return track.left() + (seconds / self._duration) * track.width()

    def _x_to_seconds(self, x: float) -> float:
        track = self._track_rect()
        if track.width() <= 0:
            return 0.0
        ratio = (x - track.left()) / track.width()
        return self._clamp(ratio * self._duration)

    # -- Zeichnen -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = self._track_rect()

        background = QPainterPath()
        background.addRoundedRect(track, 4, 4)
        painter.fillPath(background, QBrush(COLOR_TRACK))
        painter.setPen(QPen(COLOR_TRACK_BORDER, 1))
        painter.drawPath(background)

        if not self.isEnabled() or self._duration <= 0:
            return

        start_x = self._seconds_to_x(self._start)
        end_x = self._seconds_to_x(self._end)

        painter.setClipPath(background)
        self._draw_waveform(painter, track)
        self._draw_segment_shading(painter, track)

        # Nicht die Auswahl einfaerben, sondern alles ausserhalb abdunkeln -
        # so ist auf einen Blick klar, was wegfaellt.
        if start_x > track.left():
            painter.fillRect(
                QRectF(track.left(), track.top(), start_x - track.left(), track.height()),
                QBrush(COLOR_EXCLUDED),
            )
        if end_x < track.right():
            painter.fillRect(
                QRectF(end_x, track.top(), track.right() - end_x, track.height()),
                QBrush(COLOR_EXCLUDED),
            )
        painter.setClipping(False)

        # Abspielmarke - der einzige Farbtupfer im Balken.
        playhead_x = self._seconds_to_x(self._playhead)
        painter.setPen(QPen(COLOR_PLAYHEAD, 1.5))
        painter.drawLine(
            QPointF(playhead_x, track.top() - 3),
            QPointF(playhead_x, track.bottom() + 3),
        )

        # Griffe: schmale, ruhige Balken statt dicker Knoepfe.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(COLOR_HANDLE))
        for x in (start_x, end_x):
            handle = QRectF(
                x - HANDLE_WIDTH / 2,
                track.top() - 2,
                HANDLE_WIDTH,
                track.height() + 4,
            )
            path = QPainterPath()
            path.addRoundedRect(handle, 2, 2)
            painter.drawPath(path)

        self._draw_handle_labels(painter, start_x, end_x)
        self._draw_segments(painter)

    def _draw_waveform(self, painter: QPainter, track: QRectF) -> None:
        """Zeichnet je Bildspalte einen Strich, der vom Mittelpunkt ausschlaegt."""
        if not self._waveform:
            return

        count = len(self._waveform)
        width = int(track.width())
        if width <= 0:
            return

        center_y = track.center().y()
        half_height = (track.height() - 7) / 2

        painter.setPen(QPen(COLOR_WAVE, 1))
        for pixel in range(width):
            index = min(count - 1, int(pixel / width * count))
            amplitude = max(0.4, self._waveform[index] * half_height)
            x = track.left() + pixel + 0.5
            painter.drawLine(
                QPointF(x, center_y - amplitude),
                QPointF(x, center_y + amplitude),
            )

    def _draw_segment_shading(self, painter: QPainter, track: QRectF) -> None:
        """Faerbt die gemerkten Ausschnitte schon im Balken selbst ein."""
        for start, end in self._segments:
            left = self._seconds_to_x(start)
            right = self._seconds_to_x(end)
            if right - left < 1.0:
                right = left + 1.0
            painter.fillRect(
                QRectF(left, track.top(), right - left, track.height()),
                QBrush(COLOR_SEGMENT_FILL),
            )

    def _draw_handle_labels(self, painter: QPainter, start_x: float, end_x: float) -> None:
        """
        Schreibt die Zeiten direkt ueber die Griffe.

        Damit sieht man beim Ziehen sofort, an welcher Minute geschnitten wird,
        statt die Zahl im Eingabefeld daneben suchen zu muessen.
        """
        painter.setFont(self._label_font)
        metrics = QFontMetricsF(self._label_font)

        start_text = format_timecode(self._start)
        end_text = format_timecode(self._end)
        start_width = metrics.horizontalAdvance(start_text) + 2
        end_width = metrics.horizontalAdvance(end_text) + 2

        # Mittig ueber dem Griff, aber nie ueber den Rand hinaus.
        start_left = max(0.0, min(start_x - start_width / 2, self.width() - start_width))
        end_left = max(0.0, min(end_x - end_width / 2, self.width() - end_width))

        # Ruecken die Angaben zusammen, weicht das Ende nach rechts aus.
        overlap = (start_left + start_width + 6) - end_left
        if overlap > 0:
            end_left = min(self.width() - end_width, end_left + overlap)
            start_left = max(0.0, min(start_left, end_left - start_width - 6))

        painter.setPen(QPen(COLOR_LABEL_ACTIVE if self._dragging == "start" else COLOR_LABEL))
        painter.drawText(
            QRectF(start_left, 0, start_width, LABEL_BAND),
            Qt.AlignLeft | Qt.AlignVCenter,
            start_text,
        )
        painter.setPen(QPen(COLOR_LABEL_ACTIVE if self._dragging == "end" else COLOR_LABEL))
        painter.drawText(
            QRectF(end_left, 0, end_width, LABEL_BAND),
            Qt.AlignLeft | Qt.AlignVCenter,
            end_text,
        )

    def _draw_segments(self, painter: QPainter) -> None:
        """Zeichnet die gemerkten Ausschnitte als nummerierte Bloecke."""
        if not self._segments:
            return

        band = self._segment_rect()
        rail = QPainterPath()
        rail.addRoundedRect(band, 3, 3)
        painter.fillPath(rail, QBrush(COLOR_SEGMENT_RAIL))

        painter.setFont(self._segment_font)
        for index, (start, end) in enumerate(self._segments, start=1):
            left = self._seconds_to_x(start)
            right = self._seconds_to_x(end)
            width = max(3.0, right - left)
            block = QRectF(left, band.top(), width, band.height())

            path = QPainterPath()
            path.addRoundedRect(block, 3, 3)
            painter.fillPath(path, QBrush(COLOR_SEGMENT))

            # Die Nummer nur setzen, wenn sie auch lesbar hineinpasst.
            if width >= 14:
                painter.setPen(QPen(QColor("#FFFFFF")))
                painter.drawText(block, Qt.AlignCenter, str(index))

    # -- Maus ---------------------------------------------------------------

    def _segment_at(self, x: float, y: float) -> int:
        """Index des Ausschnitts unter dem Zeiger, sonst -1."""
        if not self._segments:
            return -1
        band = self._segment_rect()
        if not (band.top() - 2 <= y <= band.bottom() + 2):
            return -1
        for index, (start, end) in enumerate(self._segments):
            left = self._seconds_to_x(start)
            right = max(left + 3.0, self._seconds_to_x(end))
            if left - 2 <= x <= right + 2:
                return index
        return -1

    def mousePressEvent(self, event) -> None:
        if not self.isEnabled() or self._duration <= 0:
            return

        x = event.position().x()
        y = event.position().y()

        picked = self._segment_at(x, y)
        if picked >= 0:
            self.segmentPicked.emit(picked)
            return

        start_x = self._seconds_to_x(self._start)
        end_x = self._seconds_to_x(self._end)

        distance_to_start = abs(x - start_x)
        distance_to_end = abs(x - end_x)

        if min(distance_to_start, distance_to_end) <= GRAB_TOLERANCE:
            self._dragging = "start" if distance_to_start <= distance_to_end else "end"
            # Schon beim Anfassen springt die Vorschau an die Schnittstelle.
            self.scrubbed.emit(self._start if self._dragging == "start" else self._end)
            self.update()
        else:
            # Klick daneben bedeutet: dorthin springen.
            self.seeked.emit(self._x_to_seconds(x))

    def mouseMoveEvent(self, event) -> None:
        if not self.isEnabled():
            return

        x = event.position().x()
        y = event.position().y()

        if self._dragging is None:
            if self._segment_at(x, y) >= 0:
                self.setCursor(Qt.PointingHandCursor)
                return
            near_handle = min(
                abs(x - self._seconds_to_x(self._start)),
                abs(x - self._seconds_to_x(self._end)),
            ) <= GRAB_TOLERANCE
            self.setCursor(Qt.SizeHorCursor if near_handle else Qt.PointingHandCursor)
            return

        seconds = self._x_to_seconds(x)
        if self._dragging == "start":
            self.set_start(seconds)
            self.scrubbed.emit(self._start)
        else:
            self.set_end(seconds)
            self.scrubbed.emit(self._end)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging is None:
            return
        # Waehrend des Ziehens wird gedrosselt - der letzte Wert muss aber
        # genau stimmen, sonst steht die Vorschau ein paar Bilder daneben.
        final = self._start if self._dragging == "start" else self._end
        self._dragging = None
        self.update()
        self.scrubFinished.emit(final)
