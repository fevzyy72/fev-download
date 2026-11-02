"""Erzeugt das Programmsymbol assets/fevdl.ico.

Download-F: blaues Quadrat, darauf ein weisses F, dessen Stamm als Pfeil
ueber einer Ablage endet. Gezeichnet wird
mit derselben Funktion wie in der Oberflaeche (src/fevdl/gui/icons.py), damit
Taskleiste, Fensterkopf und Dialoge dasselbe Zeichen zeigen. Bis 32 Pixel gibt
es eine pixelgenaue Fassung fuer scharfe Balken und eine saubere Ablage.

Die .ico-Datei wird von Hand zusammengesetzt, weil sie mehrere Groessen
enthalten soll und Qt beim Speichern nur eine einzige ablegen wuerde.

Aufruf:  python tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fevdl.gui.icons import draw_logo, draw_logo_small  # noqa: E402

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "fevdl.ico"


def draw_icon(size: int) -> QImage:
    """Zeichnet das Symbol in der gewuenschten Kantenlaenge."""
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    if size <= 32:
        draw_logo_small(painter, size)
    else:
        draw_logo(painter, QRectF(0, 0, size, size))
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
    if "--vorschau" in sys.argv:
        for image in images:
            image.save(str(OUTPUT.with_name(f"_logo_{image.width()}.png")))
    print(f"Symbol geschrieben: {OUTPUT}")
    print(f"Groessen: {', '.join(str(s) for s in SIZES)}")
    print(f"Dateigroesse: {OUTPUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
