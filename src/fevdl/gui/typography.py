"""Schriften.

Qt-Stylesheets kennen weder 'letter-spacing' noch 'text-transform'. Die
Laufweite muss deshalb ueber QFont gesetzt werden, Grossschreibung direkt im
Text. Diese Helfer buendeln das an einer Stelle.
"""

from __future__ import annotations

from PySide6.QtGui import QFont

# Auf diesem System vorhanden und geprueft.
SERIF = "Constantia"        # editorial, fuer die Ueberschrift
SANS = "Segoe UI Variable"  # Oberflaeche
MONO = "Cascadia Mono"      # Zeitangaben - gleiche Zeichenbreite


def hero(size: int = 20) -> QFont:
    """Grosse Serifen-Ueberschrift mit enger Laufweite."""
    font = QFont(SERIF, size)
    font.setLetterSpacing(QFont.AbsoluteSpacing, -0.7)
    return font


def eyebrow(size: int = 7) -> QFont:
    """Kleine Bereichsbeschriftung: gesperrt, in Versalien gesetzt."""
    font = QFont(SANS, size)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
    font.setWeight(QFont.DemiBold)
    return font


def title(size: int = 12) -> QFont:
    font = QFont(SANS, size)
    font.setWeight(QFont.DemiBold)
    return font


def tag(size: int = 7) -> QFont:
    font = QFont(SANS, size)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    font.setWeight(QFont.Bold)
    return font


def body(size: int = 10) -> QFont:
    return QFont(SANS, size)


def mono(size: int = 10) -> QFont:
    """Fuer Zeitangaben - so springt die Anzeige beim Zaehlen nicht."""
    return QFont(MONO, size)
