"""Schriften.

Qt-Stylesheets kennen weder 'letter-spacing' noch 'text-transform', und eine
Schriftgroesse im Stylesheet hat Vorrang vor setFont(). Schriftgroessen stehen
deshalb ausschliesslich hier - das Stylesheet regelt nur Farbe, Rahmen, Abstand.

Die Vorlage "Sammelmappe" rechnet in Pixeln (14 px Bedienung, 28 px
Ueberschrift). Qt rechnet in Punkt: 1 px = 0,75 pt bei 96 dpi. Hoehere
Skalierungen (125 %, 150 %) uebernimmt Qt selbst.
"""

from __future__ import annotations

from PySide6.QtGui import QFont

SANS = "Segoe UI Variable"  # Windows 11; faellt sonst auf Segoe UI zurueck
MONO = "Consolas"           # Messwerte - gleiche Zeichenbreite, ruhige Zahlen


def _px(family: str, pixels: float, weight=None, spacing: float = 0.0) -> QFont:
    font = QFont(family)
    font.setPointSizeF(pixels * 0.75)
    if weight is not None:
        font.setWeight(weight)
    if spacing:
        font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    font.setStyleHint(QFont.Monospace if family == MONO else QFont.SansSerif)
    return font


def body(size: float = 14) -> QFont:
    """Grundschrift der Bedienung (App-weit ueber app.setFont)."""
    return _px(SANS, size)


def small(size: float = 12) -> QFont:
    return _px(SANS, size)


def tiny(size: float = 11) -> QFont:
    return _px(SANS, size)


def strong(size: float = 14) -> QFont:
    return _px(SANS, size, QFont.DemiBold)


def heading(size: float = 26) -> QFont:
    """Ueberschrift der Spalten ("Deine Quelle", "Sammelmappe")."""
    return _px(SANS, size, QFont.DemiBold, -0.3)


def hero(size: float = 30) -> QFont:
    """Grosse Ueberschrift des leeren Zustands."""
    return _px(SANS, size, QFont.DemiBold, -0.5)


def title(size: float = 14) -> QFont:
    return _px(SANS, size, QFont.DemiBold)


def mono(size: float = 12) -> QFont:
    """Zeitangaben, Pfade, Qualitaeten - die Anzeige springt beim Zaehlen nicht."""
    return _px(MONO, size)


def mono_strong(size: float = 12) -> QFont:
    return _px(MONO, size, QFont.Bold)


# Aeltere Namen, damit nichts bricht, was sie noch benutzt.
def eyebrow(size: float = 11) -> QFont:
    return _px(SANS, size, QFont.DemiBold, 0.6)


def tag(size: float = 10) -> QFont:
    return _px(SANS, size, QFont.Bold, 0.6)
