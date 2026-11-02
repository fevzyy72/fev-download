"""Selbst gezeichnete Bedienelemente der Oberflaeche "Sammelmappe".

Alles hier ist mit QPainter gezeichnet und trotzdem ein echtes Bedienelement:
Tastatur (Tab, Leertaste, Pfeiltasten in Gruppen), sichtbarer Fokus nur bei
Tastaturbedienung, Tooltip und Name fuer Bildschirmleser. Die Knoepfe erben von
QAbstractButton - damit liefert Qt Rolle, Klick-Logik und Zugaenglichkeit mit.

Bewegung (Stil Emil Kowalski): Hover 120 ms, Druck 100 ms auf 0,97, Schalter
140 ms, alles Ease-out ohne Federn. Ist in Windows "Animationen anzeigen"
ausgeschaltet, gibt es keine Uebergaenge.

Fallen: Kein QPixmap/QImage auf Modulebene (Absturz vor QApplication).
Schriftgroessen nur ueber typography.py.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import style, typography
from .icons import draw_icon, draw_logo

# -- Bewegung ----------------------------------------------------------------

HOVER_MS = 120
PRESS_MS = 100
SWITCH_MS = 140
SLIDE_MS = 140
PANEL_MS = 160
PRESS_SCALE = 0.97

_reduced: Optional[bool] = None


def reduced_motion() -> bool:
    """True, wenn Windows keine Animationen zeigen soll."""
    global _reduced
    if _reduced is None:
        _reduced = False
        if sys.platform == "win32":
            try:
                import ctypes

                value = ctypes.c_bool(True)
                # SPI_GETCLIENTAREAANIMATION
                if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0):
                    _reduced = not value.value
            except Exception:
                _reduced = False
    return _reduced


def ease_out() -> QEasingCurve:
    """cubic-bezier(.16, 1, .3, 1) aus der Vorlage."""
    curve = QEasingCurve(QEasingCurve.BezierSpline)
    curve.addCubicBezierSegment(QPointF(0.16, 1.0), QPointF(0.3, 1.0), QPointF(1.0, 1.0))
    return curve


class Tween:
    """Ein animierter Zahlenwert, der sein Widget neu zeichnen laesst."""

    def __init__(self, widget: QWidget, value: float = 0.0, duration: int = HOVER_MS) -> None:
        self.value = value
        self._widget = widget
        self._anim = QVariantAnimation(widget)
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(ease_out())
        self._anim.valueChanged.connect(self._step)

    def _step(self, value) -> None:
        self.value = float(value)
        self._widget.update()

    def to(self, target: float, duration: Optional[int] = None) -> None:
        if abs(target - self.value) < 1e-4 and self._anim.state() != QVariantAnimation.Running:
            return
        self._anim.stop()
        if reduced_motion() or not self._widget.isVisible():
            self.value = target
            self._widget.update()
            return
        if duration is not None:
            self._anim.setDuration(duration)
        self._anim.setStartValue(float(self.value))
        self._anim.setEndValue(float(target))
        self._anim.start()

    def set(self, value: float) -> None:
        self._anim.stop()
        self.value = value
        self._widget.update()


def mix(a: str | QColor, b: str | QColor, t: float) -> QColor:
    """Farbe zwischen a und b (t = 0..1)."""
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
        round(ca.alpha() + (cb.alpha() - ca.alpha()) * t),
    )


def corner_path(rect: QRectF, radius: float) -> QPainterPath:
    """Rechteck mit der einen abgerundeten Ecke oben rechts - das Zettelmotiv."""
    path = QPainterPath()
    r = min(radius, rect.height() / 2, rect.width() / 2)
    path.moveTo(rect.left(), rect.top())
    path.lineTo(rect.right() - r, rect.top())
    if r > 0:
        path.arcTo(QRectF(rect.right() - 2 * r, rect.top(), 2 * r, 2 * r), 90, -90)
    path.lineTo(rect.right(), rect.bottom())
    path.lineTo(rect.left(), rect.bottom())
    path.closeSubpath()
    return path


def chip_path(rect: QRectF) -> QPainterPath:
    """Marke mit angesetzter Rundung rechts (Qualitaetswahl)."""
    path = QPainterPath()
    r = rect.height() / 2
    path.moveTo(rect.left() + 2, rect.top())
    path.lineTo(rect.right() - r, rect.top())
    path.arcTo(QRectF(rect.right() - 2 * r, rect.top(), 2 * r, 2 * r), 90, -180)
    path.lineTo(rect.left() + 2, rect.bottom())
    path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - 2)
    path.lineTo(rect.left(), rect.top() + 2)
    path.quadTo(rect.left(), rect.top(), rect.left() + 2, rect.top())
    path.closeSubpath()
    return path


# -- Grundlage aller Knoepfe -------------------------------------------------


class _Interactive(QAbstractButton):
    """Hover, Druck und Fokus fuer alle selbst gezeichneten Knoepfe."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hover = Tween(self, 0.0, HOVER_MS)
        self._press = Tween(self, 1.0, PRESS_MS)
        self._focus_visible = False
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFocusPolicy(Qt.StrongFocus)

    # Zustand -------------------------------------------------------------

    def enterEvent(self, event) -> None:
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._press.to(PRESS_SCALE)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press.to(1.0)
        super().mouseReleaseEvent(event)

    def focusInEvent(self, event) -> None:
        # Der Ring erscheint nur bei Tastaturbedienung, nicht nach jedem Klick.
        self._focus_visible = event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        self._focus_visible = False
        super().focusOutEvent(event)
        self.update()

    def event(self, event) -> bool:
        # Die Leertaste spielt das Video ab (Kuerzel am Hauptfenster). Nur wer
        # den Knopf per Tab erreicht hat, bedient ihn damit - nach einem Klick
        # soll sie weiter das Video steuern, nicht den zuletzt angeklickten Knopf.
        if (
            event.type() == QEvent.ShortcutOverride
            and event.key() == Qt.Key_Space
            and self._focus_visible
        ):
            event.accept()
            return True
        return super().event(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        self.update()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt-Name
        super().setText(text)
        if not self.accessibleName() or getattr(self, "_name_from_text", True):
            self.setAccessibleName(text.replace("&", ""))
        self.updateGeometry()
        self.update()

    # Zeichnen ------------------------------------------------------------

    def hovered(self) -> float:
        return self._hover.value if self.isEnabled() else 0.0

    def is_down(self) -> bool:
        return self.isDown() and self.isEnabled()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        rect = QRectF(self.rect())
        scale = self._press.value
        if scale < 0.9999:
            center = rect.center()
            painter.translate(center)
            painter.scale(scale, scale)
            painter.translate(-center)
        self.paint_content(painter, rect)
        if self.hasFocus() and self._focus_visible:
            self.paint_focus(painter, rect)

    def paint_focus(self, painter: QPainter, rect: QRectF) -> None:
        pen = QPen(QColor(style.ACCENT), 2)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect.adjusted(1, 1, -1, -1))

    def paint_content(self, painter: QPainter, rect: QRectF) -> None:  # pragma: no cover
        raise NotImplementedError


# -- Symbol-Knopf ------------------------------------------------------------


class IconButton(_Interactive):
    """
    Quadratischer Knopf mit Strichsymbol.

    Der Text ist unsichtbar, dient aber als Tooltip und Name fuer
    Bildschirmleser - darum gibt text() weiterhin z. B. "Tonspur anzeigen".
    'key' blendet das Tastenkuerzel klein neben dem Symbol ein.
    """

    def __init__(
        self,
        icon: str,
        text: str = "",
        parent=None,
        key: str = "",
        variant: str = "ghost",   # ghost | outline | onDark
        size: int = 34,
        tooltip: str = "",
    ) -> None:
        super().__init__(parent)
        self._icon = icon
        self._key = key
        self._variant = variant
        self._size = size
        self._tooltip_extra = tooltip
        self.setFocusPolicy(Qt.TabFocus)
        self.setText(text)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        tip = text
        if self._key:
            tip = f"{text}  ·  Taste {self._key}"
        if getattr(self, "_tooltip_extra", ""):
            tip = f"{tip}\n{self._tooltip_extra}"
        self.setToolTip(tip)

    def set_icon(self, icon: str) -> None:
        self._icon = icon
        self.update()

    def sizeHint(self) -> QSize:
        width = self._size + (18 if self._key else 0)
        return QSize(width, self._size)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paint_content(self, painter: QPainter, rect: QRectF) -> None:
        enabled = self.isEnabled()
        checked = self.isCheckable() and self.isChecked()
        hover = self.hovered()
        box = rect.adjusted(0.5, 0.5, -0.5, -0.5)

        if self._variant == "outline":
            fill = QColor(style.SURFACE) if enabled else QColor(style.DISABLED)
            if enabled:
                fill = mix(fill, style.HOVER, hover)
                if self.is_down():
                    fill = QColor(style.PRESS)
            painter.setPen(QPen(QColor(style.LINE if enabled else style.DISABLED), 1))
            painter.setBrush(fill)
            painter.drawRect(box)
        else:
            base = QColor(style.TINT) if checked else QColor(0, 0, 0, 0)
            fill = mix(base, style.PRESS if checked else style.HOVER, hover * (0.6 if checked else 1))
            if self.is_down():
                fill = QColor(style.PRESS)
            if fill.alpha():
                painter.setPen(Qt.NoPen)
                painter.setBrush(fill)
                painter.drawRect(box)

        if not enabled:
            color = QColor(style.DIM)
        elif checked:
            color = QColor(style.ACCENT)
        else:
            color = QColor(style.INK)
        icon_side = 20 if self._size >= 30 else 16
        icon_left = (self._size - icon_side) / 2
        if self._key:
            icon_left = 9
        icon_rect = QRectF(icon_left, (rect.height() - icon_side) / 2, icon_side, icon_side)
        draw_icon(painter, self._icon, icon_rect, color)

        if self._key:
            painter.setFont(typography.mono_strong(11))
            painter.setPen(QColor(style.ACCENT if enabled else style.DIM))
            painter.drawText(
                QRectF(icon_rect.right() + 4, 0, rect.width() - icon_rect.right() - 6, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                self._key,
            )


# -- Knopf mit Text ----------------------------------------------------------


class TextButton(_Interactive):
    """Knopf mit Symbol und Text. Varianten: ghost, outline, accent."""

    def __init__(self, text: str, icon: str = "", parent=None, variant: str = "ghost",
                 icon_right: bool = False, height: int = 36, corner: int = 0) -> None:
        super().__init__(parent)
        self._icon = icon
        self._variant = variant
        self._icon_right = icon_right
        self._height = height
        self._corner = corner if corner else (12 if variant == "accent" else (8 if variant == "outline" else 0))
        self._font = typography.strong(14) if variant != "ghost" else typography.body(14)
        self.setFont(self._font)
        self.setText(text)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_icon(self, icon: str) -> None:
        self._icon = icon
        self.update()

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        self._corner = 12 if variant == "accent" else (8 if variant == "outline" else 0)
        self.update()

    def sizeHint(self) -> QSize:
        metrics = QFontMetricsF(self._font)
        width = metrics.horizontalAdvance(self.text()) + 28
        if self._icon:
            width += 28
        return QSize(int(width + 0.99), self._height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paint_content(self, painter: QPainter, rect: QRectF) -> None:
        enabled = self.isEnabled()
        hover = self.hovered()
        box = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        if self._variant == "accent":
            fill = QColor(style.ACCENT) if enabled else QColor(style.DISABLED)
            if enabled:
                fill = mix(fill, style.ACCENT_HOVER, hover)
                if self.is_down():
                    fill = QColor(style.ACCENT_PRESS)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawPath(corner_path(box, self._corner))
            color = QColor(style.ON_ACCENT if enabled else style.DIM)
        elif self._variant == "outline":
            fill = mix(style.SURFACE, style.TINT, hover) if enabled else QColor(style.DISABLED)
            if self.is_down():
                fill = QColor(style.PRESS)
            painter.setPen(QPen(QColor(style.ACCENT if enabled else style.LINE), 1))
            painter.setBrush(fill)
            painter.drawPath(corner_path(box, self._corner))
            color = QColor(style.ACCENT if enabled else style.DIM)
        else:
            fill = mix(QColor(0, 0, 0, 0), style.HOVER, hover)
            if self.is_down():
                fill = QColor(style.PRESS)
            if fill.alpha():
                painter.setPen(Qt.NoPen)
                painter.setBrush(fill)
                painter.drawRect(box)
            color = QColor(style.INK if enabled else style.DIM)

        painter.setFont(self._font)
        metrics = QFontMetricsF(self._font)
        text_width = metrics.horizontalAdvance(self.text())
        total = text_width + (28 if self._icon else 0)
        x = (rect.width() - total) / 2
        if self._icon and not self._icon_right:
            draw_icon(painter, self._icon, QRectF(x, (rect.height() - 20) / 2, 20, 20), color)
            x += 28
        painter.setPen(color)
        painter.drawText(QRectF(x, 0, text_width + 2, rect.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text())
        if self._icon and self._icon_right:
            draw_icon(painter, self._icon, QRectF(x + text_width + 8, (rect.height() - 20) / 2, 20, 20), color)


# -- Navigation --------------------------------------------------------------


class NavButton(_Interactive):
    """Reiter der schmalen Leiste links: Symbol ueber kleiner Beschriftung."""

    def __init__(self, icon: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self._icon = icon
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFocusPolicy(Qt.TabFocus)
        self.setText(text)
        self.setFixedSize(53, 58)

    def paint_content(self, painter: QPainter, rect: QRectF) -> None:
        checked = self.isChecked()
        hover = self.hovered()
        fill = QColor(style.TINT) if checked else mix(QColor(0, 0, 0, 0), style.HOVER, hover)
        if self.is_down():
            fill = QColor(style.PRESS)
        if fill.alpha():
            painter.fillRect(rect, fill)
        if checked:
            painter.fillRect(QRectF(0, rect.height() - 2, rect.width(), 2), QColor(style.ACCENT))
        color = QColor(style.ACCENT if checked else style.INK)
        draw_icon(painter, self._icon, QRectF((rect.width() - 20) / 2, 9, 20, 20), color)
        painter.setFont(typography.tiny(11))
        painter.setPen(color)
        painter.drawText(QRectF(0, 33, rect.width(), 18), Qt.AlignHCenter | Qt.AlignVCenter, self.text())


# -- Auswahlgruppen (ersetzen die Auswahlfelder) ------------------------------


class ChoiceButton(_Interactive):
    """Ein Feld einer Auswahlgruppe: Medienkarte, Qualitaetsmarke oder Reiter."""

    def __init__(self, text: str, data: Any, variant: str, icon: str = "", tooltip: str = "", parent=None) -> None:
        super().__init__(parent)
        self.data = data
        self._icon = icon
        self._variant = variant  # card | chip | tab
        self._compact = False
        self._selected = Tween(self, 0.0, HOVER_MS)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        if variant == "chip":
            self._font = typography.mono(12)
        elif variant == "tab":
            self._font = typography.body(14)
        else:
            self._font = typography.small(12)
        self.setText(text)
        if tooltip:
            self.setToolTip(tooltip)
        self.toggled.connect(lambda on: self._selected.to(1.0 if on else 0.0))
        if variant == "card":
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_compact(self, compact: bool) -> None:
        if compact != self._compact:
            self._compact = compact
            self.updateGeometry()
            self.update()

    def sizeHint(self) -> QSize:
        metrics = QFontMetricsF(self._font)
        text = metrics.horizontalAdvance(self.text())
        if self._variant == "chip":
            return QSize(max(70, int(text + 30)), 30)
        if self._variant == "tab":
            return QSize(int(text + 22), 34)
        if self._compact:
            return QSize(int(text + 52), 38)
        return QSize(int(max(text + 20, 80)), 64)

    def minimumSizeHint(self) -> QSize:
        hint = self.sizeHint()
        if self._variant == "card":
            return QSize(min(hint.width(), 90), hint.height())
        return hint

    def paint_focus(self, painter: QPainter, rect: QRectF) -> None:
        # Der Ring folgt der Form: Marke rund, Karte mit Zettelecke.
        pen = QPen(QColor(style.INK if self.isChecked() and self._variant == "chip" else style.ACCENT), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        inner = rect.adjusted(1, 1, -1, -1)
        if self._variant == "chip":
            painter.drawPath(chip_path(inner))
        elif self._variant == "card":
            painter.drawPath(corner_path(inner, 8))
        else:
            painter.drawRect(inner)

    def paint_content(self, painter: QPainter, rect: QRectF) -> None:
        enabled = self.isEnabled()
        sel = self._selected.value
        hover = self.hovered()
        box = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setFont(self._font)

        if self._variant == "chip":
            if not enabled:
                fill, border, ink = QColor(style.DISABLED), QColor(style.DISABLED), QColor(style.DIM)
            else:
                idle = mix(style.SURFACE, style.HOVER, hover)
                active = mix(style.ACCENT, style.ACCENT_HOVER, hover)
                fill = mix(idle, active, sel)
                border = mix(style.LINE, style.ACCENT, max(sel, hover * 0.6))
                ink = mix(style.INK, style.ON_ACCENT, sel)
                if self.is_down():
                    fill = QColor(style.ACCENT_PRESS if self.isChecked() else style.PRESS)
            painter.setPen(QPen(border, 1))
            painter.setBrush(fill)
            painter.drawPath(chip_path(box))
            painter.setPen(ink)
            painter.drawText(rect.adjusted(0, 0, -4, 0), Qt.AlignCenter, self.text())
            return

        if self._variant == "tab":
            fill = mix(mix(QColor(0, 0, 0, 0), style.HOVER, hover), style.TINT, sel)
            if self.is_down():
                fill = QColor(style.PRESS)
            if fill.alpha():
                painter.fillRect(box, fill)
            ink = mix(style.INK, style.ACCENT, sel) if enabled else QColor(style.DIM)
            painter.setPen(ink)
            painter.drawText(rect, Qt.AlignCenter, self.text())
            return

        # Medienkarte
        if not enabled:
            fill, border, ink = QColor(style.DISABLED), QColor(style.DISABLED), QColor(style.DIM)
        else:
            fill = mix(mix(style.SURFACE, style.HOVER, hover), style.TINT, sel)
            border = mix(style.LINE, style.ACCENT, sel)
            ink = mix(style.INK, style.ACCENT, sel)
            if self.is_down():
                fill = QColor(style.PRESS)
        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawPath(corner_path(box, 8))
        if self._compact:
            metrics = QFontMetricsF(self._font)
            width = 20 + 8 + metrics.horizontalAdvance(self.text())
            x = (rect.width() - width) / 2
            draw_icon(painter, self._icon, QRectF(x, (rect.height() - 20) / 2, 20, 20), ink)
            painter.setPen(ink)
            painter.drawText(QRectF(x + 28, 0, rect.width() - x - 28, rect.height()),
                             Qt.AlignLeft | Qt.AlignVCenter, self.text())
        else:
            draw_icon(painter, self._icon, QRectF((rect.width() - 20) / 2, 12, 20, 20), ink)
            painter.setPen(ink)
            painter.drawText(QRectF(4, 36, rect.width() - 8, 20), Qt.AlignCenter, self.text())


class FlowLayout(QLayout):
    """Reiht Elemente nebeneinander und bricht um, wenn der Platz endet."""

    def __init__(self, parent=None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect: QRect, apply: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for item in self._items:
            if item.widget() is not None and not item.widget().isVisibleTo(item.widget().parentWidget()):
                continue
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x = rect.x()
                y += line + self._spacing
                line = 0
            if apply:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x += hint.width() + self._spacing
            line = max(line, hint.height())
        return y + line - rect.y()


class ChoiceGroup(QWidget):
    """
    Eine Gruppe ausschliesslicher Felder mit der Schnittstelle eines QComboBox.

    So bleibt die Logik im Hauptfenster (findData, currentData, Mode.value ...)
    unveraendert, nur das Aussehen ist neu. Pfeiltasten wechseln die Auswahl
    wie bei Optionsfeldern.
    """

    currentIndexChanged = Signal(int)

    def __init__(self, variant: str = "chip", parent=None, accessible_name: str = "") -> None:
        super().__init__(parent)
        self._variant = variant
        self._buttons: list[ChoiceButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idToggled.connect(self._on_toggled)
        if variant == "chip":
            self._layout = FlowLayout(self, spacing=8)
        else:
            self._layout = QHBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(8 if variant == "card" else 2)
        if accessible_name:
            self.setAccessibleName(accessible_name)
        self.setSizePolicy(QSizePolicy.Expanding if variant != "tab" else QSizePolicy.Fixed,
                           QSizePolicy.Preferred if variant == "chip" else QSizePolicy.Fixed)

    # -- Combo-Schnittstelle -------------------------------------------------

    def addItem(self, text: str, data: Any = None, icon: str = "", tooltip: str = "") -> None:  # noqa: N802
        button = ChoiceButton(text, data, self._variant, icon=icon, tooltip=tooltip, parent=self)
        index = len(self._buttons)
        self._buttons.append(button)
        self._group.addButton(button, index)
        self._layout.addWidget(button)
        if index == 0:
            button.setChecked(True)
        self.updateGeometry()

    def clear(self) -> None:
        previous = self.currentIndex()
        for button in self._buttons:
            self._group.removeButton(button)
            self._layout.removeWidget(button)
            button.deleteLater()
        self._buttons = []
        if previous != -1:
            self.currentIndexChanged.emit(-1)
        self.updateGeometry()

    def count(self) -> int:
        return len(self._buttons)

    def itemText(self, index: int) -> str:  # noqa: N802
        return self._buttons[index].text() if 0 <= index < len(self._buttons) else ""

    def itemData(self, index: int):  # noqa: N802
        return self._buttons[index].data if 0 <= index < len(self._buttons) else None

    def findData(self, data: Any) -> int:  # noqa: N802
        for index, button in enumerate(self._buttons):
            if button.data == data:
                return index
        return -1

    def currentIndex(self) -> int:  # noqa: N802
        return self._group.checkedId()

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)

    def currentData(self):  # noqa: N802
        return self.itemData(self.currentIndex())

    def currentText(self) -> str:  # noqa: N802
        return self.itemText(self.currentIndex())

    def buttons(self) -> list[ChoiceButton]:
        return list(self._buttons)

    def set_compact(self, compact: bool) -> None:
        for button in self._buttons:
            button.set_compact(compact)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        for button in self._buttons:
            button.update()

    def _on_toggled(self, index: int, checked: bool) -> None:
        if checked:
            self.currentIndexChanged.emit(index)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return self._variant == "chip"

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        if self._variant == "chip":
            return self._layout.heightForWidth(width)
        return super().heightForWidth(width)


# -- Schiebeschalter ---------------------------------------------------------


class ToggleSwitch(_Interactive):
    """Rechteckiger Schiebeschalter mit Beschriftung (ersetzt den Haken)."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self._knob = Tween(self, 0.0, SWITCH_MS)
        self._font = typography.small(13)
        self.toggled.connect(lambda on: self._knob.to(1.0 if on else 0.0))
        self.setText(text)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        if not self.isVisible():
            self._knob.set(1.0 if checked else 0.0)

    def sizeHint(self) -> QSize:
        metrics = QFontMetricsF(self._font)
        return QSize(int(35 + 10 + metrics.horizontalAdvance(self.text()) + 10), 30)

    def paint_content(self, painter: QPainter, rect: QRectF) -> None:
        enabled = self.isEnabled()
        hover = self.hovered()
        on = self._knob.value
        track = QRectF(1, (rect.height() - 18) / 2, 35, 18)
        if enabled:
            fill = mix(style.LINE, style.ACCENT, on)
            if hover:
                fill = mix(fill, style.ACCENT_HOVER if on > 0.5 else style.DIM, hover * 0.5)
        else:
            fill = QColor(style.DISABLED if on < 0.5 else style.LINE)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawPath(corner_path(track, 5))
        knob_x = track.left() + 3 + on * 15
        painter.setBrush(QColor(style.ON_ACCENT if enabled else style.SURFACE))
        painter.drawRect(QRectF(knob_x, track.top() + 3, 14, 12))
        painter.setFont(self._font)
        painter.setPen(QColor(style.INK if enabled else style.DIM))
        painter.drawText(QRectF(track.right() + 10, 0, rect.width(), rect.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, self.text())

    def paint_focus(self, painter: QPainter, rect: QRectF) -> None:
        pen = QPen(QColor(style.ACCENT), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect.adjusted(-0, 1, -1, -1))


# -- Hauptaktion -------------------------------------------------------------


class MainAction(_Interactive):
    """
    Der grosse Knopf unten rechts: laden, Fortschritt, fertig.

    Im Laufzustand zeigt er nur, was wirklich bekannt ist: einen Prozentwert,
    wenn yt-dlp einen meldet, sonst einen wandernden Abschnitt ("laeuft,
    Dauer unbekannt"). Der Fortschritt zieht als Linie am unteren Rand ein.
    Abbrechen ist ein eigener Knopf rechts im Balken - ein versehentlicher
    Klick auf die grosse Flaeche bricht nichts ab.
    """

    IDLE, RUNNING, DONE = "idle", "running", "done"

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._state = self.IDLE
        self._progress = Tween(self, 0.0, 180)
        self._known = False
        self._detail = ""
        self._phase = 0.0
        self._loop = QVariantAnimation(self)
        self._loop.setStartValue(0.0)
        self._loop.setEndValue(1.0)
        self._loop.setDuration(1400)
        self._loop.setLoopCount(-1)
        self._loop.valueChanged.connect(self._on_phase)
        self._font = typography.strong(15)
        self.setText(text)
        self.setMinimumHeight(54)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.cancel_button = IconButton("stop", "Abbrechen", self, variant="ghost")
        self.cancel_button.setVisible(False)

    def _on_phase(self, value) -> None:
        self._phase = float(value)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(260, 54)

    def state(self) -> str:
        return self._state

    def set_idle(self, text: str) -> None:
        self._state = self.IDLE
        self._loop.stop()
        self._progress.set(0.0)
        self._detail = ""
        self.cancel_button.setVisible(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(text)

    def set_running(self, text: str = "Wird geladen") -> None:
        self._state = self.RUNNING
        self._known = False
        self._detail = ""
        self._progress.set(0.0)
        if not reduced_motion():
            self._loop.start()
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.setCursor(Qt.ArrowCursor)
        self.setText(text)

    def set_progress(self, percent: Optional[float], detail: str = "") -> None:
        """percent=None bedeutet: laeuft, aber ohne bekannten Wert."""
        self._detail = detail
        if percent is None:
            if not self._known and not self._loop.state() == QVariantAnimation.Running and not reduced_motion():
                self._loop.start()
            self.update()
            return
        self._known = True
        self._loop.stop()
        self._progress.to(max(0.0, min(1.0, percent / 100.0)))

    def set_done(self, text: str = "Fertig") -> None:
        self._state = self.DONE
        self._loop.stop()
        self._known = True
        self._progress.set(1.0)
        self._detail = ""
        self.cancel_button.setVisible(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        size = 34
        self.cancel_button.setGeometry(self.width() - size - 12, (self.height() - size) // 2, size, size)

    def mousePressEvent(self, event) -> None:
        if self._state == self.RUNNING:
            return  # die Flaeche zeigt nur den Fortschritt
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if self._state == self.RUNNING:
            return
        super().keyPressEvent(event)

    def paint_content(self, painter: QPainter, rect: QRectF) -> None:
        enabled = self.isEnabled()
        hover = self.hovered()
        shape = corner_path(rect, style.RADIUS_ACTION)
        running = self._state == self.RUNNING
        if running:
            fill, ink = QColor(style.TINT), QColor(style.ACCENT)
        elif not enabled:
            fill, ink = QColor(style.DISABLED), QColor(style.DIM)
        else:
            fill = mix(style.ACCENT, style.ACCENT_HOVER, hover)
            if self.is_down():
                fill = QColor(style.ACCENT_PRESS)
            ink = QColor(style.ON_ACCENT)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawPath(shape)

        if running:
            line = QRectF(20, rect.height() - 6, rect.width() - 40, 3)
            painter.fillRect(line, mix(style.TINT, style.ACCENT, 0.18))
            if self._known:
                painter.fillRect(QRectF(line.left(), line.top(), line.width() * self._progress.value, 3),
                                 QColor(style.ACCENT))
            else:
                seg = line.width() * 0.3
                x = line.left() + (line.width() + seg) * self._phase - seg
                left = max(line.left(), x)
                right = min(line.right(), x + seg)
                if reduced_motion():
                    left, right = line.left(), line.left() + seg
                if right > left:
                    painter.fillRect(QRectF(left, line.top(), right - left, 3), QColor(style.ACCENT))

        painter.setFont(self._font)
        painter.setPen(ink)
        text_rect = QRectF(20, 0, rect.width() - 80, rect.height())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())
        if running and self._detail:
            painter.setFont(typography.mono(12))
            painter.drawText(QRectF(20, 0, rect.width() - 76, rect.height()),
                             Qt.AlignRight | Qt.AlignVCenter, self._detail)
        if not running:
            icon = "check" if self._state == self.DONE else "download"
            draw_icon(painter, icon, QRectF(rect.width() - 42, (rect.height() - 22) / 2, 22, 22), ink)

    def paint_focus(self, painter: QPainter, rect: QRectF) -> None:
        pen = QPen(QColor(style.INK), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(corner_path(rect.adjusted(3, 3, -3, -3), style.RADIUS_ACTION - 3))


# -- Kleinteile --------------------------------------------------------------


class LogoMark(QWidget):
    """Das Programmsymbol als Bild in der Oberflaeche."""

    def __init__(self, size: int = 32, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAccessibleName("Fev Download")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        draw_logo(painter, QRectF(self.rect()))


class Rule(QFrame):
    """Eine 1-px-Linie."""

    def __init__(self, name: str = "rule", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(1)


class NumberBox(QWidget):
    """Nummer eines Ausschnitts - kleines umrandetes Feld."""

    def __init__(self, number: int, parent=None) -> None:
        super().__init__(parent)
        self.number = number
        self.setFixedSize(28, 28)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(style.LINE), 1))
        painter.setBrush(QColor(style.SURFACE))
        painter.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        painter.setFont(typography.mono(13))
        painter.setPen(QColor(style.INK))
        painter.drawText(self.rect(), Qt.AlignCenter, str(self.number))


# -- Gemerkte Ausschnitte ----------------------------------------------------


class SavedTicket(_Interactive):
    """Ein abgelegter Zettel: Nummer, Titel, Zeitraum. Klick holt ihn zurueck."""

    removeRequested = Signal()

    def __init__(self, number: int, title: str, detail: str, parent=None) -> None:
        super().__init__(parent)
        self.number = number
        self._title = title
        self._detail = detail
        self._current = False
        self._enter = Tween(self, 1.0, SLIDE_MS)
        self.setText(f"Ausschnitt {number}: {detail}")
        self.setToolTip("Zurueck in den Zettel holen  ·  Entf entfernt ihn")
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.remove_button = IconButton("close", f"Ausschnitt {number} entfernen", self, size=30)
        self.remove_button.clicked.connect(self.removeRequested.emit)

    def animate_in(self) -> None:
        self._enter.set(0.0)
        self._enter.to(1.0)

    def set_current(self, current: bool) -> None:
        self._current = current
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.remove_button.move(self.width() - 38, (self.height() - 30) // 2)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.removeRequested.emit()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.click()
            return
        super().keyPressEvent(event)

    def paint_content(self, painter: QPainter, rect: QRectF) -> None:
        t = self._enter.value
        painter.setOpacity(0.2 + 0.8 * t)
        painter.translate((1.0 - t) * 6, 0)
        hover = self.hovered()
        box = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        fill = QColor(style.TINT) if self._current else mix(style.SURFACE, style.HOVER, hover * 0.7)
        if self.is_down():
            fill = QColor(style.PRESS)
        painter.setPen(QPen(QColor(style.ACCENT if self._current else style.LINE), 1))
        painter.setBrush(fill)
        painter.drawPath(corner_path(box, style.RADIUS_CORNER))
        if self._current:
            painter.fillRect(QRectF(0, 0, 3, rect.height()), QColor(style.ACCENT))
        painter.setFont(typography.mono(15))
        painter.setPen(QColor(style.ACCENT if self._current else style.INK))
        painter.drawText(QRectF(0, 0, 36, rect.height()), Qt.AlignCenter, str(self.number))
        pen = QPen(QColor(style.LINE), 1, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(36.5, 10), QPointF(36.5, rect.height() - 10))
        text_width = rect.width() - 50 - 44
        painter.setFont(typography.strong(13))
        painter.setPen(QColor(style.INK))
        metrics = QFontMetricsF(painter.font())
        painter.drawText(QRectF(48, 8, text_width, 20), Qt.AlignLeft | Qt.AlignVCenter,
                         metrics.elidedText(self._title, Qt.ElideRight, text_width))
        painter.setFont(typography.mono(12))
        painter.setPen(QColor(style.MUTED))
        painter.drawText(QRectF(48, 28, text_width, 20), Qt.AlignLeft | Qt.AlignVCenter, self._detail)


class SegmentList(QWidget):
    """
    Die abgelegten Zettel untereinander.

    Bietet die Teile der QListWidget-Schnittstelle, die das Hauptfenster
    benutzt (count, currentRow, setCurrentRow), damit dessen Logik bleibt.
    """

    activated = Signal(int)
    removeRequested = Signal(int)
    currentRowChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tickets: list[SavedTicket] = []
        self._current = -1
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self.setAccessibleName("Gemerkte Ausschnitte")

    def set_items(self, items: list[tuple[str, str]], animate_index: int = -1) -> None:
        """items: (Titel, Zeitraum) je Ausschnitt."""
        for ticket in self._tickets:
            self._layout.removeWidget(ticket)
            ticket.deleteLater()
        self._tickets = []
        for index, (title, detail) in enumerate(items):
            ticket = SavedTicket(index + 1, title, detail, self)
            ticket.clicked.connect(lambda _=False, i=index: self.activated.emit(i))
            ticket.removeRequested.connect(lambda i=index: self.removeRequested.emit(i))
            self._tickets.append(ticket)
            self._layout.addWidget(ticket)
            if index == animate_index:
                ticket.animate_in()
        if self._current >= len(self._tickets):
            self._current = -1
        self._apply_current()

    def ticket(self, index: int) -> Optional[SavedTicket]:
        return self._tickets[index] if 0 <= index < len(self._tickets) else None

    def count(self) -> int:
        return len(self._tickets)

    def currentRow(self) -> int:  # noqa: N802
        return self._current

    def setCurrentRow(self, row: int) -> None:  # noqa: N802
        row = row if 0 <= row < len(self._tickets) else -1
        if row != self._current:
            self._current = row
            self._apply_current()
            self.currentRowChanged.emit(row)

    def _apply_current(self) -> None:
        for index, ticket in enumerate(self._tickets):
            ticket.set_current(index == self._current)


# -- Lieferliste waehrend des Ladens -----------------------------------------


class JobRow(QWidget):
    """Ein Auftrag in der Lieferliste: Nummer, Titel, Stand, Fortschrittslinie."""

    WAITING, RUNNING, DONE, FAILED = "waiting", "running", "done", "failed"

    def __init__(self, number: int, title: str, span: str, parent=None) -> None:
        super().__init__(parent)
        self.number = number
        self._title = title
        self._span = span
        self._state = self.WAITING
        self._phase = 0.0
        self._loop = QVariantAnimation(self)
        self._loop.setStartValue(0.0)
        self._loop.setEndValue(1.0)
        self._loop.setDuration(1400)
        self._loop.setLoopCount(-1)
        self._loop.valueChanged.connect(self._tick)
        self._fill = Tween(self, 0.0, 220)
        self.setFixedHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.folder_button = IconButton("folder", "Im Ordner zeigen", self, size=30)
        self.folder_button.setVisible(False)
        self._update_accessible()

    def _tick(self, value) -> None:
        self._phase = float(value)
        self.update()

    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        if state == self.RUNNING and not reduced_motion():
            self._loop.start()
        else:
            self._loop.stop()
        if state == self.DONE:
            self._fill.to(1.0)
        self.folder_button.setVisible(state == self.DONE)
        self._update_accessible()
        self.update()

    def _status_text(self) -> str:
        return {
            self.WAITING: "Wartet",
            self.RUNNING: "Wird geladen ...",
            self.DONE: "Gespeichert",
            self.FAILED: "Nicht geladen",
        }[self._state]

    def _update_accessible(self) -> None:
        self.setAccessibleName(f"{self._title}, {self._span}, {self._status_text()}")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.folder_button.move(self.width() - 34, 8)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        box = QRectF(0.5, 10.5, 27, 27)
        painter.setPen(QPen(QColor(style.LINE), 1))
        painter.setBrush(QColor(style.SURFACE))
        painter.drawRect(box)
        painter.setFont(typography.mono(13))
        painter.setPen(QColor(style.INK))
        painter.drawText(box, Qt.AlignCenter, str(self.number))

        left = 40
        right_space = 44
        width = rect.width() - left - right_space
        painter.setFont(typography.strong(13))
        metrics = QFontMetricsF(painter.font())
        painter.drawText(QRectF(left, 2, width, 20), Qt.AlignLeft | Qt.AlignVCenter,
                         metrics.elidedText(self._title, Qt.ElideRight, width))
        painter.setFont(typography.small(12))
        failed = self._state == self.FAILED
        painter.setPen(QColor(style.ERROR if failed else style.MUTED))
        painter.drawText(QRectF(left, 22, width, 20), Qt.AlignLeft | Qt.AlignVCenter,
                         f"{self._span}  ·  {self._status_text()}")

        line = QRectF(left, 46, width, 3)
        painter.fillRect(line, QColor(style.LINE))
        accent = QColor(style.ACCENT)
        if self._state == self.RUNNING:
            seg = line.width() * 0.28
            x = line.left() + (line.width() + seg) * self._phase - seg
            if reduced_motion():
                x = line.left()
            a, b = max(line.left(), x), min(line.right(), x + seg)
            if b > a:
                painter.fillRect(QRectF(a, line.top(), b - a, 3), accent)
        elif self._fill.value > 0:
            painter.fillRect(QRectF(line.left(), line.top(), line.width() * self._fill.value, 3), accent)

        if self._state in (self.WAITING, self.RUNNING):
            draw_icon(painter, "download", QRectF(rect.width() - 30, 12, 20, 20),
                      QColor(style.ACCENT if self._state == self.RUNNING else style.DIM))
        elif failed:
            draw_icon(painter, "close", QRectF(rect.width() - 30, 12, 20, 20), QColor(style.ERROR))


class DeliveryList(QWidget):
    """Die Auftraege eines Downloads untereinander."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[JobRow] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(18)
        self.setAccessibleName("Laufende Auftraege")

    def set_jobs(self, jobs: list[tuple[str, str]]) -> list[JobRow]:
        for row in self._rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._rows = []
        for index, (title, span) in enumerate(jobs, start=1):
            row = JobRow(index, title, span, self)
            self._rows.append(row)
            self._layout.addWidget(row)
        return list(self._rows)

    def rows(self) -> list[JobRow]:
        return list(self._rows)


def fade_in(widget: QWidget, duration: int = PANEL_MS) -> None:
    """Blendet einen Bereich weich ein (nicht fuer das Videobild verwenden)."""
    if reduced_motion():
        return
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QVariantAnimation(widget)
    anim.setDuration(duration)
    anim.setEasingCurve(ease_out())
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.valueChanged.connect(lambda v: effect.setOpacity(float(v)))

    def done() -> None:
        # Effekt wieder entfernen: Er zwingt sonst jedes Neuzeichnen durch
        # einen Zwischenpuffer.
        widget.setGraphicsEffect(None)

    anim.finished.connect(done)
    anim.start(QVariantAnimation.DeleteWhenStopped)


def single_shot(msec: int, func) -> None:
    QTimer.singleShot(msec, func)


class BusyLine(QWidget):
    """Duenne Linie mit wanderndem Abschnitt: laeuft, Dauer unbekannt."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self._loop = QVariantAnimation(self)
        self._loop.setStartValue(0.0)
        self._loop.setEndValue(1.0)
        self._loop.setDuration(1300)
        self._loop.setLoopCount(-1)
        self._loop.valueChanged.connect(self._tick)
        self.setFixedHeight(2)
        self._running = False

    def _tick(self, value) -> None:
        self._phase = float(value)
        self.update()

    def set_running(self, running: bool) -> None:
        self._running = running
        if running and not reduced_motion():
            self._loop.start()
        else:
            self._loop.stop()
        self.update()

    def paintEvent(self, event) -> None:
        if not self._running:
            return
        painter = QPainter(self)
        width = self.width()
        seg = width * 0.25
        x = (width + seg) * self._phase - seg
        if reduced_motion():
            x = 0
        painter.fillRect(QRectF(max(0.0, x), 0, min(width, x + seg) - max(0.0, x), 2), QColor(style.ACCENT))


class IconMark(QWidget):
    """Ein Strichsymbol als reines Bild (ohne Bedienung)."""

    def __init__(self, icon: str, size: int = 28, color: str = style.ACCENT, parent=None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._color = color
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        draw_icon(painter, self._icon, QRectF(self.rect()), QColor(self._color), 1.8)
