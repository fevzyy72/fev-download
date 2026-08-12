"""Erzeugt das Programmsymbol assets/fevdl.ico.

Gezeichnet statt gemalt: ein Pfeil nach unten auf eine Grundlinie - das
allgemein verstaendliche Zeichen fuers Herunterladen. Bewusst schlicht, damit
es auch bei 16 Bildpunkten in der Taskleiste noch erkennbar bleibt.

Die .ico-Datei wird von Hand zusammengesetzt, weil sie mehrere Groessen
enthalten soll und Qt beim Speichern nur eine einzige ablegen wuerde.

Aufruf:  python tools/make_icon.py
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "fevdl.ico"

INK = QColor("#111111")
PAPER = QColor("#FFFFFF")


def draw_icon(size: int) -> QImage:
    """Zeichnet das Symbol in der gewuenschten Kantenlaenge."""
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)

    unit = size / 256.0

    # Grundflaeche
    background = QPainterPath()
    background.addRoundedRect(QRectF(0, 0, size, size), 56 * unit, 56 * unit)
    painter.fillPath(background, INK)

    painter.setPen(Qt.NoPen)
    painter.setBrush(PAPER)

    # Schaft des Pfeils
    stem = QPainterPath()
    stem.addRoundedRect(
        QRectF(115 * unit, 52 * unit, 26 * unit, 78 * unit),
        13 * unit,
        13 * unit,
    )
    painter.drawPath(stem)

    # Spitze
    head = QPainterPath()
    head.moveTo(78 * unit, 118 * unit)
    head.lineTo(178 * unit, 118 * unit)
    head.lineTo(128 * unit, 180 * unit)
    head.closeSubpath()
    painter.drawPath(head)

    # Grundlinie
    baseline = QPainterPath()
    baseline.addRoundedRect(
        QRectF(62 * unit, 196 * unit, 132 * unit, 22 * unit),
        11 * unit,
        11 * unit,
    )
    painter.drawPath(baseline)

    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    # Das QByteArray muss in einer eigenen Variablen liegen: Als Ausdruck
    # direkt im Aufruf wuerde Python es sofort wieder einsammeln, waehrend der
    # Puffer auf der C++-Seite noch darauf zeigt - das endet im Absturz.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def build_ico(images: list[QImage], destination: Path) -> None:
    """
    Setzt mehrere Bilder zu einer .ico-Datei zusammen.

    Aufbau: ein kurzer Kopf, danach je Bild ein Verzeichniseintrag mit Groesse
    und Fundstelle, zuletzt die Bilddaten selbst als PNG.
    """
    payloads = [png_bytes(image) for image in images]

    header = struct.pack("<HHH", 0, 1, len(payloads))  # reserviert, Typ 1 = Symbol
    offset = len(header) + 16 * len(payloads)

    entries = bytearray()
    for image, payload in zip(images, payloads):
        # 256 wird als 0 geschrieben - mehr passt nicht in ein Byte.
        side = 0 if image.width() >= 256 else image.width()
        entries += struct.pack(
            "<BBBBHHII",
            side, side,
            0,          # Farbanzahl (0 = keine Palette)
            0,          # reserviert
            1,          # Ebenen
            32,         # Bit je Bildpunkt
            len(payload),
            offset,
        )
        offset += len(payload)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "wb") as handle:
        handle.write(header)
        handle.write(entries)
        for payload in payloads:
            handle.write(payload)


def main() -> None:
    app = QApplication([])  # noqa: F841 - QPainter braucht eine Anwendung
    images = [draw_icon(size) for size in SIZES]
    build_ico(images, OUTPUT)
    print(f"Symbol geschrieben: {OUTPUT}")
    print(f"Groessen: {', '.join(str(s) for s in SIZES)}")
    print(f"Dateigroesse: {OUTPUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
