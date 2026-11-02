"""Strichsymbole und das Programmlogo, gezeichnet mit QPainter.

QtSvg ist im fertigen Programm bewusst nicht enthalten (siehe fevdl.spec), daher
werden die SVG-Pfade der Gestaltungsvorlage hier selbst gelesen. Unterstuetzt
werden genau die Befehle, die die Vorlage benutzt: M L H V C Q A Z, gross und
klein geschrieben.

Wichtig: Nichts hier erzeugt auf Modulebene ein Qt-Zeichenobjekt. Ein QPixmap
oder QImage vor dem Start der Anwendung bringt Qt zum Absturz.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

# Raster 24 x 24, Strichstaerke 1,65 - wie in der Vorlage (mockup.js).
ICON_PATHS = {
    "play": "M9 5l12 7-12 7z",
    "pause": "M8 5v14M16 5v14",
    "plus": "M12 4v16M4 12h16",
    "close": "M6 6l12 12M18 6L6 18",
    "arrow": "M4 12h15M13 5l7 7-7 7",
    "back": "M20 12H5M11 5l-7 7 7 7",
    "paste": "M8 5H5v16h14V5h-3M9 3h6v5H9z",
    "folder": "M3 7V5h7l2 3h9v12H3z",
    "bin": "M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 10v7M14 10v7",
    "menu": "M4 6h16M4 12h16M4 18h16",
    "library": "M4 4v16h4V4zM11 4v16M15 5l5 14",
    "wave": "M2 12h2l2-7 3 14 3-17 3 19 3-14 2 5h2",
    "in": "M15 4H6v16h9M9 12h12M17 8l4 4-4 4",
    "out": "M9 4h9v16H9M3 12h12M7 8l-4 4 4 4",
    "all": "M7 4H3v16h4M17 4h4v16h-4M7 12h10",
    "mark": "M6 3h12v18l-6-4-6 4z",
    "check": "M4 12l5 5L20 6",
    "download": "M12 3v12M7 10l5 5 5-5M4 17v4h16v-4",
    "search": "M10 3a7 7 0 1 0 0 14 7 7 0 1 0 0-14M15 15l6 6",
    "video": "M3 5h13v14H3zM16 9l5-3v12l-5-3",
    "audio": "M4 10v4h4l6 5V5l-6 5zM18 8q6 4 0 8",
    "refresh": "M20 8a9 9 0 1 0 0 9M20 3v6h-6",
    "stop": "M6 6h12v12H6z",
    "zoom_in": "M10 3a7 7 0 1 0 0 14 7 7 0 1 0 0-14M15 15l6 6M7 10h6M10 7v6",
    "zoom_out": "M10 3a7 7 0 1 0 0 14 7 7 0 1 0 0-14M15 15l6 6M7 10h6",
    "open": "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
}

# Logo "Sammelmappe": abgelegtes Blatt mit Falte und zwei Inhaltslinien (48 x 48).
LOGO_BLUE = "#344fad"
_LOGO_PAGE = "M8 7h21l11 11v23H8z"
_LOGO_LINES = "M29 7v11h11M15 26h18M15 33h11"

_TOKEN = re.compile(r"[MmLlHhVvCcQqAaZz]|-?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def _arc_to_beziers(path: QPainterPath, x1, y1, rx, ry, phi, large, sweep, x2, y2) -> None:
    """SVG-Bogen (Endpunkt-Form) als Bezier-Kurven anhaengen."""
    if rx == 0 or ry == 0:
        path.lineTo(x2, y2)
        return
    rx, ry = abs(rx), abs(ry)
    cos_p, sin_p = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    xp = cos_p * dx + sin_p * dy
    yp = -sin_p * dx + cos_p * dy
    lam = (xp * xp) / (rx * rx) + (yp * yp) / (ry * ry)
    if lam > 1:
        rx *= math.sqrt(lam)
        ry *= math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    den = rx * rx * yp * yp + ry * ry * xp * xp
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp = coef * rx * yp / ry
    cyp = -coef * ry * xp / rx
    cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2
    cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = angle(1, 0, (xp - cxp) / rx, (yp - cyp) / ry)
    dt = angle((xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi

    segments = max(1, int(math.ceil(abs(dt) / (math.pi / 2))))
    step = dt / segments
    k = 4 / 3 * math.tan(step / 4)
    for i in range(segments):
        a1 = t1 + i * step
        a2 = a1 + step
        c1x, c1y = math.cos(a1) - k * math.sin(a1), math.sin(a1) + k * math.cos(a1)
        c2x, c2y = math.cos(a2) + k * math.sin(a2), math.sin(a2) - k * math.cos(a2)
        ex, ey = math.cos(a2), math.sin(a2)

        def tr(px, py):
            px, py = px * rx, py * ry
            return QPointF(cos_p * px - sin_p * py + cx, sin_p * px + cos_p * py + cy)

        path.cubicTo(tr(c1x, c1y), tr(c2x, c2y), tr(ex, ey))


@lru_cache(maxsize=None)
def _parse(data: str) -> QPainterPath:
    """Liest einen SVG-Pfad in einen QPainterPath."""
    tokens = _TOKEN.findall(data)
    path = QPainterPath()
    x = y = 0.0
    start_x = start_y = 0.0
    command = ""
    i = 0

    def num():
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            command = token
            i += 1
            if command in "Zz":
                path.closeSubpath()
                x, y = start_x, start_y
                continue
        rel = command.islower()
        c = command.upper()
        if c == "M":
            nx, ny = num(), num()
            if rel:
                nx, ny = x + nx, y + ny
            path.moveTo(nx, ny)
            x, y = start_x, start_y = nx, ny
            # Weitere Zahlenpaare nach M sind Linien.
            command = "l" if rel else "L"
        elif c == "L":
            nx, ny = num(), num()
            if rel:
                nx, ny = x + nx, y + ny
            path.lineTo(nx, ny)
            x, y = nx, ny
        elif c == "H":
            nx = num()
            x = x + nx if rel else nx
            path.lineTo(x, y)
        elif c == "V":
            ny = num()
            y = y + ny if rel else ny
            path.lineTo(x, y)
        elif c == "C":
            pts = [num() for _ in range(6)]
            if rel:
                pts = [pts[k] + (x if k % 2 == 0 else y) for k in range(6)]
            path.cubicTo(*pts)
            x, y = pts[4], pts[5]
        elif c == "Q":
            pts = [num() for _ in range(4)]
            if rel:
                pts = [pts[k] + (x if k % 2 == 0 else y) for k in range(4)]
            path.quadTo(*pts)
            x, y = pts[2], pts[3]
        elif c == "A":
            rx, ry, phi, large, sweep, nx, ny = (num() for _ in range(7))
            if rel:
                nx, ny = x + nx, y + ny
            _arc_to_beziers(path, x, y, rx, ry, phi, bool(large), bool(sweep), nx, ny)
            x, y = nx, ny
        else:  # unbekannt - ueberspringen statt abstuerzen
            i += 1
    return path


def icon_path(name: str) -> QPainterPath:
    return _parse(ICON_PATHS.get(name, ICON_PATHS["plus"]))


def draw_icon(painter: QPainter, name: str, rect: QRectF, color: QColor, stroke: float = 1.65) -> None:
    """Zeichnet ein Strichsymbol (24er Raster) in das Rechteck."""
    side = min(rect.width(), rect.height())
    scale = side / 24.0
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(rect.center().x() - side / 2, rect.center().y() - side / 2)
    painter.scale(scale, scale)
    pen = QPen(color, stroke)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(icon_path(name))
    painter.restore()


def draw_logo(painter: QPainter, rect: QRectF) -> None:
    """Das Programmsymbol: blaues Quadrat, weisses Blatt mit Falte."""
    side = min(rect.width(), rect.height())
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(rect.center().x() - side / 2, rect.center().y() - side / 2)
    painter.scale(side / 48.0, side / 48.0)
    blue = QColor(LOGO_BLUE)
    painter.fillRect(QRectF(0, 0, 48, 48), blue)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#ffffff"))
    painter.drawPath(_parse(_LOGO_PAGE))
    pen = QPen(blue, 3)
    pen.setCapStyle(Qt.FlatCap)
    pen.setJoinStyle(Qt.MiterJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(_parse(_LOGO_LINES))
    painter.restore()


def draw_logo_small(painter: QPainter, size: int) -> None:
    """
    Pixelgenaue Fassung fuer 16 bis 24 Pixel.

    Herunterskaliert verschwimmen die 3er-Linien der Vorlage zu grauem Brei.
    Hier liegen Blatt, Falte und Zeilen auf ganzen Pixeln.
    """
    blue = QColor(LOGO_BLUE)
    white = QColor("#ffffff")
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.fillRect(0, 0, size, size, blue)
    u = size / 16.0
    left, top = round(3 * u), round(2 * u)
    right, bottom = round(13 * u), round(14 * u)
    fold = max(3, round(3.5 * u))
    page = QPainterPath()
    page.moveTo(left, top)
    page.lineTo(right - fold, top)
    page.lineTo(right, top + fold)
    page.lineTo(right, bottom)
    page.lineTo(left, bottom)
    page.closeSubpath()
    painter.setPen(Qt.NoPen)
    painter.setBrush(white)
    painter.drawPath(page)
    # Falte als ausgesparte Ecke
    painter.fillRect(right - fold, top, 1, fold, blue)
    painter.fillRect(right - fold, top + fold - 1, fold, 1, blue)
    line = max(1, round(u))
    y1 = round(8.5 * u)
    y2 = round(11 * u)
    x0 = round(5 * u)
    painter.fillRect(x0, y1, round(6 * u), line, blue)
    painter.fillRect(x0, y2, round(4 * u), line, blue)
    painter.restore()
