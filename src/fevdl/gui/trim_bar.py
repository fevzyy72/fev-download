"""Ausschnitt-Zeitleiste im Zettel: Uebersicht oben, Detail darunter.

Die Sammelmappe ist schmal (rund 350 px). Ein Balken ueber das ganze Video
waere dort zu grob, um genau zu schneiden. Darum zwei Ebenen:

    Uebersicht   das ganze Video in einer Zeile: gemerkte Ausschnitte (blau),
                 die aktuelle Auswahl (Rahmen), der gezeigte Bereich, Abspielmarke
    Detail       mindestens 140 px hohe Wellenform, standardmaessig auf die
                 Auswahl gezoomt (plus Rand) - Griffe als Klammern, Zeitskala

Beim Ziehen eines Griffs steht der Detailbereich still - sonst wuerde sich die
Skala unter der Maus verschieben und der Griff "springen". Erst nach dem
Loslassen gleitet die Ansicht (160 ms) auf die neue Auswahl. Zieht man ueber
den Rand hinaus, erweitert sich die Ansicht schrittweise in diese Richtung.

Beim Ziehen meldet die Leiste laufend 'scrubbed' (die Vorschau springt mit),
beim Loslassen einmal 'scrubFinished' mit der genauen Stelle.

Tastatur (wenn die Leiste den Fokus hat): Pfeil links/rechts verschiebt den
aktiven Griff um 1 s, mit Umschalt um 10 s, mit Alt um 0,1 s; die Leertaste
wechselt zwischen Anfang und Ende, wenn man die Leiste per Tab erreicht hat
(sonst spielt sie das Video ab, siehe Hauptfenster).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..core.models import format_timecode
from . import style, typography
from .widgets import PANEL_MS, ease_out, reduced_motion

SIDE = 8            # seitlicher Rand, damit Griffe am Rand greifbar bleiben
OVERVIEW_H = 14     # Uebersicht
GAP = 8
RULER_H = 20        # Zeitskala im Detail
DRAW_H = 146        # reine Zeichenflaeche der Wellenform (>= 140)
MARK_BAND = 7       # gemerkte Ausschnitte am unteren Rand des Details
GRAB = 11           # Pixel, innerhalb derer ein Griff angefasst wird
MIN_SPAN = 3.0      # kleinster gezeigter Zeitraum in Sekunden

_TICK_STEPS = (0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200)


def precise_timecode(seconds: float) -> str:
    """Wie format_timecode, aber mit Zehnteln, wenn es welche gibt."""
    seconds = max(0.0, float(seconds or 0.0))
    tenths = round(seconds * 10) / 10
    if abs(tenths - round(tenths)) < 0.05:
        return format_timecode(round(tenths))
    whole = int(tenths)
    frac = int(round((tenths - whole) * 10))
    return f"{format_timecode(whole)}.{frac}"


class TrimBar(QWidget):
    """Waehlt den Ausschnitt - Uebersicht plus gezoomtes Detail."""

    rangeChanged = Signal(float, float)   # start, end in Sekunden
    seeked = Signal(float)                # Klick in die Leiste
    scrubbed = Signal(float)              # Griff wird gezogen - Vorschau folgt
    scrubFinished = Signal(float)         # Griff losgelassen - endgueltige Stelle
    segmentPicked = Signal(int)           # Klick auf einen gemerkten Ausschnitt
    zoomChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._duration = 0.0
        self._start = 0.0
        self._end = 0.0
        self._playhead = 0.0
        self._dragging: str | None = None  # "start" | "end" | None
        self._hover: str | None = None
        self._active = "start"             # Griff fuer die Tastatur
        self._focus_visible = False
        self._waveform: list[float] = []
        self._segments: list[tuple[float, float]] = []
        self._hint = ""
        self._zoomed = True
        self._view_lo = 0.0
        self._view_hi = 0.0
        self._last_x = 0.0

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(PANEL_MS)
        self._anim.setEasingCurve(ease_out())
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_view_step)
        self._anim_from = (0.0, 0.0)
        self._anim_to = (0.0, 0.0)

        # Rand-Verschiebung beim Ziehen ueber die Kante hinaus
        self._edge_timer = QTimer(self)
        self._edge_timer.setInterval(16)
        self._edge_timer.timeout.connect(self._edge_pan)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(OVERVIEW_H + GAP + RULER_H + DRAW_H)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Ausschnitt-Zeitleiste")
        self.setToolTip(
            "Griffe ziehen oder: Pfeil links/rechts verschiebt den aktiven Griff\n"
            "(Umschalt 10 s, Alt 0,1 s)"
        )
        self.setEnabled(False)

    def sizeHint(self) -> QSize:
        return QSize(340, self.height())

    # -- Zustand ------------------------------------------------------------

    def set_duration(self, duration: float) -> None:
        self._duration = max(0.0, float(duration))
        self._start = 0.0
        self._end = self._duration
        self._playhead = 0.0
        self._waveform = []  # gehoert zum vorherigen Video
        self._anim.stop()
        self._view_lo, self._view_hi = 0.0, self._duration
        self.setEnabled(self._duration > 0)
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def set_waveform(self, peaks: list[float]) -> None:
        self._waveform = list(peaks or [])
        self.update()

    def has_waveform(self) -> bool:
        return bool(self._waveform)

    def set_hint(self, text: str) -> None:
        """Text in der leeren Detailflaeche (z. B. 'Tonspur wird geladen')."""
        self._hint = text
        self.update()

    def set_segments(self, segments: list[tuple[float, float]]) -> None:
        self._segments = [(float(a), float(b)) for a, b in segments]
        self.update()

    def set_zoomed(self, zoomed: bool) -> None:
        if zoomed == self._zoomed:
            return
        self._zoomed = zoomed
        self._retarget()
        self.zoomChanged.emit(zoomed)

    def is_zoomed(self) -> bool:
        return self._zoomed

    def view_range(self) -> tuple[float, float]:
        return self._view_lo, self._view_hi

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
        self._changed(notify)

    def set_end(self, value: float, notify: bool = True) -> None:
        value = self._clamp(value)
        self._end = max(value, min(self._duration, self._start + 1.0))
        self._changed(notify)

    def set_range(self, start: float, end: float, notify: bool = True) -> None:
        start = self._clamp(start)
        end = self._clamp(end)
        if end < start + 1.0:
            end = min(self._duration, start + 1.0)
        self._start = start
        self._end = end
        self._changed(notify)

    def _changed(self, notify: bool) -> None:
        if self._dragging is None:
            self._retarget()
        self._update_accessible()
        self.update()
        if notify:
            self.rangeChanged.emit(self._start, self._end)

    def set_playhead(self, value: float) -> None:
        self._playhead = self._clamp(value)
        self.update()

    def is_full_range(self) -> bool:
        if self._duration <= 0:
            return True
        return self._start <= 0.05 and self._end >= self._duration - 0.05

    def _clamp(self, value: float) -> float:
        return max(0.0, min(float(value), self._duration))

    def _update_accessible(self) -> None:
        self.setAccessibleDescription(
            f"Anfang {precise_timecode(self._start)}, Ende {precise_timecode(self._end)}, "
            f"aktiver Griff: {'Anfang' if self._active == 'start' else 'Ende'}"
        )

    # -- Ansicht (Zoom) -----------------------------------------------------

    def _target_view(self) -> tuple[float, float]:
        if not self._zoomed or self._duration <= 0:
            return 0.0, self._duration
        span = self._end - self._start
        pad = max(1.5, span * 0.15)
        lo = max(0.0, self._start - pad)
        hi = min(self._duration, self._end + pad)
        if hi - lo < MIN_SPAN:
            mid = (lo + hi) / 2
            lo = max(0.0, mid - MIN_SPAN / 2)
            hi = min(self._duration, lo + MIN_SPAN)
        return lo, hi

    def _retarget(self) -> None:
        target = self._target_view()
        current = (self._view_lo, self._view_hi)
        if abs(target[0] - current[0]) < 1e-3 and abs(target[1] - current[1]) < 1e-3:
            return
        if reduced_motion() or not self.isVisible() or current[1] <= current[0]:
            self._anim.stop()
            self._view_lo, self._view_hi = target
            self.update()
            return
        self._anim.stop()
        self._anim_from = current
        self._anim_to = target
        self._anim.start()

    def _on_view_step(self, value) -> None:
        t = float(value)
        (a0, b0), (a1, b1) = self._anim_from, self._anim_to
        self._view_lo = a0 + (a1 - a0) * t
        self._view_hi = b0 + (b1 - b0) * t
        self.update()

    # -- Geometrie ----------------------------------------------------------

    def _overview_rect(self) -> QRectF:
        return QRectF(SIDE, 2, max(1.0, self.width() - 2 * SIDE), OVERVIEW_H - 4)

    def _canvas_rect(self) -> QRectF:
        """Zeitskala plus Zeichenflaeche."""
        top = OVERVIEW_H + GAP
        return QRectF(0, top, self.width(), RULER_H + DRAW_H)

    def _track_rect(self) -> QRectF:
        """Die reine Zeichenflaeche der Wellenform."""
        top = OVERVIEW_H + GAP + RULER_H
        return QRectF(SIDE, top, max(1.0, self.width() - 2 * SIDE), DRAW_H)

    def _seconds_to_x(self, seconds: float) -> float:
        track = self._track_rect()
        span = self._view_hi - self._view_lo
        if span <= 0:
            return track.left()
        return track.left() + (seconds - self._view_lo) / span * track.width()

    def _x_to_seconds(self, x: float) -> float:
        track = self._track_rect()
        span = self._view_hi - self._view_lo
        if track.width() <= 0 or span <= 0:
            return 0.0
        return self._clamp(self._view_lo + (x - track.left()) / track.width() * span)

    def _overview_x(self, seconds: float) -> float:
        rect = self._overview_rect()
        if self._duration <= 0:
            return rect.left()
        return rect.left() + seconds / self._duration * rect.width()

    def _overview_seconds(self, x: float) -> float:
        rect = self._overview_rect()
        if rect.width() <= 0 or self._duration <= 0:
            return 0.0
        return self._clamp((x - rect.left()) / rect.width() * self._duration)

    # -- Zeichnen -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        enabled = self.isEnabled() and self._duration > 0

        self._paint_overview(painter, enabled)

        canvas = self._canvas_rect()
        painter.fillRect(canvas, QColor(style.WAVE_BG))
        if not enabled:
            painter.setFont(typography.small(12))
            painter.setPen(QColor(style.MUTED))
            painter.drawText(canvas, Qt.AlignCenter, "Erst einen Link analysieren")
            return

        track = self._track_rect()
        painter.save()
        painter.setClipRect(canvas)
        start_x = self._seconds_to_x(self._start)
        end_x = self._seconds_to_x(self._end)
        selection = QRectF(start_x, canvas.top() + RULER_H, end_x - start_x, DRAW_H)
        painter.fillRect(selection, QColor(style.TINT))
        self._paint_ruler(painter, canvas)
        self._paint_wave(painter, track, start_x, end_x)
        self._paint_marks(painter, track)
        self._paint_handles(painter, track, start_x, end_x)
        self._paint_playhead(painter, canvas)
        painter.restore()

        if self.hasFocus() and self._focus_visible:
            pen = QPen(QColor(style.ACCENT), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(canvas.adjusted(1, 1, -1, -1))

    def _paint_overview(self, painter: QPainter, enabled: bool) -> None:
        rect = self._overview_rect()
        painter.fillRect(rect, QColor(style.LINE_SOFT))
        if not enabled:
            return
        if self._waveform:
            count = len(self._waveform)
            width = int(rect.width())
            painter.setPen(QPen(QColor(style.WAVE), 1))
            mid = rect.center().y()
            for px in range(0, width, 2):
                value = self._waveform[min(count - 1, int(px / width * count))]
                h = max(0.5, value * (rect.height() / 2 - 0.5))
                x = rect.left() + px + 0.5
                painter.drawLine(QPointF(x, mid - h), QPointF(x, mid + h))
        # Gezeigter Bereich des Details
        lo, hi = self._view_lo, self._view_hi
        if hi - lo < self._duration - 0.01:
            window = QRectF(self._overview_x(lo), rect.top() - 2, self._overview_x(hi) - self._overview_x(lo), rect.height() + 4)
            painter.fillRect(window, QColor(42, 52, 75, 30))
        # Gemerkte Ausschnitte
        for a, b in self._segments:
            x1, x2 = self._overview_x(a), self._overview_x(b)
            painter.fillRect(QRectF(x1, rect.top(), max(2.0, x2 - x1), rect.height()), QColor(style.ACCENT))
        # Aktuelle Auswahl als Rahmen
        x1, x2 = self._overview_x(self._start), self._overview_x(self._end)
        pen = QPen(QColor(style.INK), 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(x1, rect.top() - 1, max(2.0, x2 - x1), rect.height() + 2))
        # Abspielmarke
        px = self._overview_x(self._playhead)
        painter.fillRect(QRectF(px - 1, rect.top() - 3, 2, rect.height() + 6), QColor(style.INK))

    def _tick_step(self, span: float, width: float) -> float:
        for step in _TICK_STEPS:
            if width / max(1e-6, span / step) >= 64:
                return step
        return _TICK_STEPS[-1]

    def _paint_ruler(self, painter: QPainter, canvas: QRectF) -> None:
        lo, hi = self._view_lo, self._view_hi
        span = hi - lo
        if span <= 0:
            return
        track = self._track_rect()
        step = self._tick_step(span, track.width())
        painter.setFont(typography.tiny(11))
        metrics = QFontMetricsF(painter.font())
        first = math.ceil(lo / step) * step
        t = first
        tick_pen = QPen(QColor(style.LINE_SOFT), 1)
        while t <= hi + 1e-6:
            x = self._seconds_to_x(t)
            painter.setPen(tick_pen)
            painter.drawLine(QPointF(x, canvas.top() + RULER_H - 4), QPointF(x, canvas.bottom()))
            label = precise_timecode(t) if step < 1 else format_timecode(t)
            w = metrics.horizontalAdvance(label)
            lx = min(max(x + 3, 2), canvas.width() - w - 2)
            painter.setPen(QColor(style.MUTED))
            painter.drawText(QRectF(lx, canvas.top() + 1, w + 2, RULER_H - 4), Qt.AlignLeft | Qt.AlignVCenter, label)
            t += step
        painter.setPen(QPen(QColor(style.LINE), 1))
        painter.drawLine(QPointF(0, canvas.top() + RULER_H - 0.5), QPointF(canvas.width(), canvas.top() + RULER_H - 0.5))

    def _paint_wave(self, painter: QPainter, track: QRectF, start_x: float, end_x: float) -> None:
        if not self._waveform:
            text = self._hint or "Tonspur ueber das Wellen-Symbol laden"
            painter.setFont(typography.small(12))
            painter.setPen(QColor(style.MUTED))
            painter.drawText(track.adjusted(12, 0, -12, -MARK_BAND), Qt.AlignCenter | Qt.TextWordWrap, text)
            # Mittellinie, damit die Flaeche als Spur lesbar bleibt
            painter.setPen(QPen(QColor(style.LINE_SOFT), 1))
            mid = track.top() + (track.height() - MARK_BAND) / 2
            painter.drawLine(QPointF(track.left(), mid + 18), QPointF(track.right(), mid + 18))
            return
        count = len(self._waveform)
        lo, hi = self._view_lo, self._view_hi
        span = hi - lo
        if span <= 0 or self._duration <= 0:
            return
        mid = track.top() + (track.height() - MARK_BAND) / 2
        half = (track.height() - MARK_BAND) / 2 - 4
        inside = QColor(style.WAVE)
        outside = QColor(style.WAVE)
        outside.setAlpha(120)
        step = 3
        x = track.left()
        while x < track.right():
            t0 = lo + (x - track.left()) / track.width() * span
            t1 = lo + (x + step - track.left()) / track.width() * span
            i0 = int(t0 / self._duration * count)
            i1 = max(i0 + 1, int(math.ceil(t1 / self._duration * count)))
            i0 = max(0, min(count - 1, i0))
            i1 = max(i0 + 1, min(count, i1))
            value = max(self._waveform[i0:i1])
            h = max(1.0, value * half)
            color = inside if start_x <= x + 1 <= end_x else outside
            painter.fillRect(QRectF(x, mid - h, 2, 2 * h), color)
            x += step

    def _paint_marks(self, painter: QPainter, track: QRectF) -> None:
        """Gemerkte Ausschnitte als Marken am unteren Rand des Details."""
        band = QRectF(track.left(), track.bottom() - MARK_BAND, track.width(), MARK_BAND)
        painter.setFont(typography.mono_strong(9))
        for index, (a, b) in enumerate(self._segments, start=1):
            x1, x2 = self._seconds_to_x(a), self._seconds_to_x(b)
            if x2 < track.left() or x1 > track.right():
                continue
            block = QRectF(x1, band.top(), max(3.0, x2 - x1), band.height())
            painter.fillRect(block, QColor(style.ACCENT))
            if block.width() >= 16:
                painter.setPen(QColor(style.ON_ACCENT))
                painter.drawText(block, Qt.AlignCenter, str(index))

    def _paint_handles(self, painter: QPainter, track: QRectF, start_x: float, end_x: float) -> None:
        top = track.top()
        bottom = track.bottom() - MARK_BAND - 1
        accent = QColor(style.ACCENT)
        for name, x, inward in (("start", start_x, 1), ("end", end_x, -1)):
            if x < -10 or x > self.width() + 10:
                continue
            active = self._dragging == name or self._hover == name
            if active:
                painter.fillRect(QRectF(x - 10, top, 20, bottom - top), QColor(style.HOVER))
            # Klammer: senkrechter Strich, kurze Fuesse nach innen
            painter.fillRect(QRectF(x - 1.5, top, 3, bottom - top), accent)
            painter.fillRect(QRectF(x - 1.5 if inward > 0 else x - 7.5, top, 9, 3), accent)
            painter.fillRect(QRectF(x - 1.5 if inward > 0 else x - 7.5, bottom - 3, 9, 3), accent)
            painter.setFont(typography.mono_strong(11))
            painter.setPen(accent)
            letter_x = x + 4 if inward > 0 else x - 14
            painter.drawText(QRectF(letter_x, bottom - 20, 10, 14), Qt.AlignCenter, "I" if name == "start" else "O")
            if self.hasFocus() and self._focus_visible and self._active == name:
                pen = QPen(QColor(style.INK), 1.5)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(QRectF(x - 6, top + 1, 12, bottom - top - 2))
            if self._dragging == name:
                self._paint_bubble(painter, x, self._start if name == "start" else self._end)

    def _paint_bubble(self, painter: QPainter, x: float, seconds: float) -> None:
        text = precise_timecode(seconds)
        painter.setFont(typography.mono(12))
        metrics = QFontMetricsF(painter.font())
        w = metrics.horizontalAdvance(text) + 12
        canvas = self._canvas_rect()
        left = min(max(2.0, x - w / 2), self.width() - w - 2)
        box = QRectF(left, canvas.top() + 1, w, RULER_H - 2)
        painter.fillRect(box, QColor(style.INK))
        painter.setPen(QColor(style.BG))
        painter.drawText(box, Qt.AlignCenter, text)

    def _paint_playhead(self, painter: QPainter, canvas: QRectF) -> None:
        x = self._seconds_to_x(self._playhead)
        track = self._track_rect()
        ink = QColor(style.INK)
        if x < track.left() - 1 or x > track.right() + 1:
            # Ausserhalb der Detailansicht: kleiner Pfeil am Rand
            left = x < track.left()
            ax = 3 if left else self.width() - 3
            y = canvas.top() + RULER_H + 10
            tri = QPolygonF([QPointF(ax, y), QPointF(ax + (7 if left else -7), y - 5), QPointF(ax + (7 if left else -7), y + 5)])
            painter.setPen(Qt.NoPen)
            painter.setBrush(ink)
            painter.drawPolygon(tri)
            return
        painter.setPen(QPen(ink, 1.4))
        painter.drawLine(QPointF(x, canvas.top() + RULER_H - 6), QPointF(x, track.bottom() - MARK_BAND))
        tri = QPolygonF([QPointF(x - 4, canvas.top() + RULER_H - 7), QPointF(x + 4, canvas.top() + RULER_H - 7), QPointF(x, canvas.top() + RULER_H - 2)])
        painter.setPen(Qt.NoPen)
        painter.setBrush(ink)
        painter.drawPolygon(tri)

    # -- Maus ---------------------------------------------------------------

    def _segment_at_overview(self, x: float) -> int:
        for index, (a, b) in enumerate(self._segments):
            if self._overview_x(a) - 3 <= x <= max(self._overview_x(a) + 2, self._overview_x(b)) + 3:
                return index
        return -1

    def _segment_at_marks(self, x: float, y: float) -> int:
        track = self._track_rect()
        if not (track.bottom() - MARK_BAND - 3 <= y <= track.bottom() + 2):
            return -1
        for index, (a, b) in enumerate(self._segments):
            x1, x2 = self._seconds_to_x(a), self._seconds_to_x(b)
            if x1 - 2 <= x <= max(x1 + 3, x2) + 2:
                return index
        return -1

    def _handle_at(self, x: float, y: float) -> str | None:
        if y < OVERVIEW_H + GAP:
            return None
        ds = abs(x - self._seconds_to_x(self._start))
        de = abs(x - self._seconds_to_x(self._end))
        if min(ds, de) > GRAB:
            return None
        if abs(ds - de) < 0.5:
            # Uebereinander: nach der Seite entscheiden, auf der man greift
            return "start" if x < self._seconds_to_x(self._start) else "end"
        return "start" if ds < de else "end"

    def mousePressEvent(self, event) -> None:
        if not self.isEnabled() or self._duration <= 0 or event.button() != Qt.LeftButton:
            return
        x, y = event.position().x(), event.position().y()
        if y < OVERVIEW_H + GAP / 2:
            picked = self._segment_at_overview(x)
            if picked >= 0:
                self.segmentPicked.emit(picked)
            else:
                self.seeked.emit(self._overview_seconds(x))
            return
        picked = self._segment_at_marks(x, y)
        if picked >= 0:
            self.segmentPicked.emit(picked)
            return
        handle = self._handle_at(x, y)
        if handle is not None:
            self._dragging = handle
            self._active = handle
            self._last_x = x
            self._anim.stop()
            # Schon beim Anfassen springt die Vorschau an die Schnittstelle.
            self.scrubbed.emit(self._start if handle == "start" else self._end)
            self.update()
        else:
            self.seeked.emit(self._x_to_seconds(x))

    def mouseMoveEvent(self, event) -> None:
        if not self.isEnabled():
            return
        x, y = event.position().x(), event.position().y()
        if self._dragging is None:
            handle = self._handle_at(x, y)
            if handle != self._hover:
                self._hover = handle
                self.update()
            if handle is not None:
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)
            return
        self._last_x = x
        self._drag_to(x)
        track = self._track_rect()
        if self._zoomed and (x < track.left() + 2 or x > track.right() - 2):
            if not self._edge_timer.isActive():
                self._edge_timer.start()
        else:
            self._edge_timer.stop()

    def _drag_to(self, x: float) -> None:
        seconds = round(self._x_to_seconds(x) * 10) / 10  # Zehntelsekunden
        if self._dragging == "start":
            self.set_start(seconds)
            self.scrubbed.emit(self._start)
        else:
            self.set_end(seconds)
            self.scrubbed.emit(self._end)

    def _edge_pan(self) -> None:
        """Ueber den Rand gezogen: Ansicht in diese Richtung erweitern."""
        if self._dragging is None:
            self._edge_timer.stop()
            return
        track = self._track_rect()
        span = self._view_hi - self._view_lo
        if self._last_x < track.left() + 2:
            over = track.left() + 2 - self._last_x
            self._view_lo = max(0.0, self._view_lo - span * (0.01 + over / 2000))
        elif self._last_x > track.right() - 2:
            over = self._last_x - track.right() + 2
            self._view_hi = min(self._duration, self._view_hi + span * (0.01 + over / 2000))
        else:
            self._edge_timer.stop()
            return
        self._drag_to(min(max(self._last_x, track.left()), track.right()))

    def mouseReleaseEvent(self, event) -> None:
        self._edge_timer.stop()
        if self._dragging is None:
            return
        # Waehrend des Ziehens wird gedrosselt - der letzte Wert muss aber
        # genau stimmen, sonst steht die Vorschau ein paar Bilder daneben.
        final = self._start if self._dragging == "start" else self._end
        self._dragging = None
        self._retarget()
        self.update()
        self.scrubFinished.emit(final)

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(event)

    # -- Tastatur -----------------------------------------------------------

    def focusInEvent(self, event) -> None:
        self._focus_visible = event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        self._focus_visible = False
        super().focusOutEvent(event)
        self.update()

    def event(self, event) -> bool:
        # Leertaste: Abspielen/Pause am Hauptfenster - ausser die Leiste wurde
        # per Tab erreicht, dann wechselt sie zwischen Anfang und Ende.
        if (
            event.type() == QEvent.ShortcutOverride
            and event.key() == Qt.Key_Space
            and self._focus_visible
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if not self.isEnabled() or self._duration <= 0:
            return super().keyPressEvent(event)
        key = event.key()
        if key == Qt.Key_Space:
            self._active = "end" if self._active == "start" else "start"
            self._focus_visible = True
            self._update_accessible()
            self.update()
            return
        if key in (Qt.Key_Left, Qt.Key_Right):
            step = 1.0
            if event.modifiers() & Qt.ShiftModifier:
                step = 10.0
            elif event.modifiers() & Qt.AltModifier:
                step = 0.1
            delta = step if key == Qt.Key_Right else -step
            self._focus_visible = True
            if self._active == "start":
                self.set_start(round((self._start + delta) * 10) / 10)
                value = self._start
            else:
                self.set_end(round((self._end + delta) * 10) / 10)
                value = self._end
            self.scrubFinished.emit(value)
            return
        super().keyPressEvent(event)
