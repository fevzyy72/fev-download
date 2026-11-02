"""Bildschirmfotos der echten Qt-Oberflaeche in allen Hauptzustaenden.

Aufruf (aus dem Projektordner):
    $env:PYTHONPATH = "src"
    .venv\\Scripts\\python.exe tools\\umsetzung_fotos.py

Ohne Netz: Die Analyse wird vorgetaeuscht, das Videobild ist ein Standbild aus
Big Buck Bunny (design/looks2/assets, CC BY 3.0). QVideoWidget erscheint bei
grab() als weisse Flaeche - das Standbild wird deshalb nachtraeglich genau in
die Bildflaeche gemalt. Ergebnis: design/umsetzung/*.png
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QPoint, QRect, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fevdl import paths  # noqa: E402
from fevdl.core import thumbs  # noqa: E402
from fevdl.core.models import Quality, VideoInfo  # noqa: E402
from fevdl.gui import typography  # noqa: E402
from fevdl.gui.main_window import MainWindow  # noqa: E402

OUT = ROOT / "design" / "umsetzung"
ASSETS = ROOT / "design" / "looks2" / "assets"
TMP = Path(tempfile.mkdtemp(prefix="fevfotos_"))
paths.RESULT_FILE = TMP / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())
QSettings("fezco", "Fev Download").clear()
QApplication.clipboard().clear()

PEAKS = json.loads((ASSETS / "waveform.json").read_text(encoding="utf-8"))
STILLS = {name: QImage(str(ASSETS / f"bbb-{name}.jpg")) for name in ("landscape", "portrait", "square")}


def info_for(width: int, height: int) -> VideoInfo:
    return VideoInfo(
        url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
        title="Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film",
        duration=635.0,
        uploader="Blender",
        audio_url="https://example.com/a.m4a",
        qualities=[Quality(2160, 60), Quality(1440, 60), Quality(1080, 60), Quality(720, 60)],
        extractor="Youtube",
        width=width,
        height=height,
    )


def new_window(w: int, h: int) -> MainWindow:
    window = MainWindow(job=None)
    window._start_preview_fallback = lambda: None
    window.player.load = lambda *_a, **_k: None
    window.output_edit.setText(r"C:\Users\fevzy\Videos\FevDownloader")
    window.resize(w, h)
    window.show()
    QTest.qWaitForWindowExposed(window)
    return window


def analysed(window: MainWindow, still: str = "landscape", segments=True) -> None:
    size = {"landscape": (1920, 1080), "portrait": (1080, 1920), "square": (1080, 1080)}[still]
    window._on_probe_succeeded(info_for(*size))
    window.player._stack.setCurrentWidget(window.player._video)
    window.player._play_button.setEnabled(True)
    window.player._position_slider.setEnabled(True)
    window.player._position_slider.setRange(0, 635000)
    window.player._position_slider.setValue(181000)
    window.player._set_time_label(181, 635)
    window._on_waveform_ready(PEAKS)
    if segments:
        for a, b in ((60, 64), (180, 184)):
            window.trim_bar.set_range(a, b)
            window._add_segment()
    window.trim_bar.set_range(96, 268)
    window.trim_bar.set_playhead(181)
    window._set_status("")
    settle()


def settle(ms: int = 400) -> None:
    QTest.qWait(ms)
    app.processEvents()


def shoot(window: MainWindow, name: str, still: str | None = "landscape") -> None:
    settle()
    pixmap = window.grab()
    stack = window.player._stack
    if still and stack.currentWidget() is window.player._video and stack.isVisible():
        top_left = stack.mapTo(window, QPoint(0, 0))
        rect = QRect(top_left, stack.size())
        painter = QPainter(pixmap)
        painter.fillRect(rect, Qt.black)
        image = STILLS[still].scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawImage(rect.x() + (rect.width() - image.width()) // 2,
                          rect.y() + (rect.height() - image.height()) // 2, image)
        painter.end()
    OUT.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(OUT / f"{name}.jpg"), "JPG", 88)
    print("gespeichert:", name, pixmap.width(), "x", pixmap.height())


def make_media() -> Path:
    folder = TMP / "Videos"
    folder.mkdir()
    ffmpeg = paths.FFMPEG_EXE
    for number, still in ((1, "landscape"), (2, "square")):
        target = folder / f"Big Buck Bunny - Official Blender Foundation Short Film_{number}.mp4"
        subprocess.run([str(ffmpeg), "-v", "error", "-loop", "1", "-i", str(ASSETS / f"bbb-{still}.jpg"),
                        "-t", "1", "-vf", "scale=640:-2", "-pix_fmt", "yuv420p", str(target)],
                       check=False, creationflags=0x08000000)
        # Vorab in den Zwischenspeicher, damit das Foto nicht auf ffmpeg wartet.
        thumbs.ensure_thumbnail(target, "video")
    return folder


# 1. Leer
w = new_window(1000, 960)
shoot(w, "01-leer", None)
w.close()

# 2. Analysiert
w = new_window(1000, 960)
analysed(w)
shoot(w, "02-analysiert")

# 3. Laeuft (zwei Ausschnitte gleichzeitig, Fortschritt unbekannt)
requests = w._build_requests()
w._open_delivery(requests)
w._set_state_busy()
w._set_status("Lade 2 Ausschnitte gleichzeitig...")
settle(700)
shoot(w, "03-laeuft")

# 4. Fertig
fake = TMP / "clip.mp4"
fake.write_bytes(b"x")
w._on_part_ready(0, fake)
w._on_part_ready(1, fake)
w._on_file_ready(fake)
w._on_download_succeeded(fake)
w._running = False
settle(500)
shoot(w, "04-fertig")
w._download_worker = None
w.close()

# 5. Bibliothek
w = new_window(1000, 960)
w.output_edit.setText(str(make_media()))
w._show_library()
for _ in range(60):
    settle(250)
    if len(w.library_page._thumbs) >= 2:
        break
w.library_page.table.setCurrentItem(w.library_page.table.topLevelItem(0))
shoot(w, "05-bibliothek", None)
w.close()

# 6./7. Hoch- und Quadratformat
for still, name in (("portrait", "06-hochformat"), ("square", "07-quadrat")):
    w = new_window(1000, 960)
    analysed(w, still)
    shoot(w, name, still)
    w.close()

# 8. Kleinstes Fenster
w = new_window(860, 620)
analysed(w)
shoot(w, "08-klein-860x620")
w.editor_scroll.verticalScrollBar().setValue(w.editor_scroll.verticalScrollBar().maximum())
shoot(w, "09-klein-gescrollt")
w.close()

# 10. Leere Mappe, Tastaturfokus auf der Qualitaet
w = new_window(1000, 960)
analysed(w, segments=False)
w.trim_bar.set_range(96, 268)
w.quality_combo.buttons()[1].setFocus(Qt.TabFocusReason)
shoot(w, "10-mappe-leer-fokus")
w.close()

app.processEvents()
QSettings("fezco", "Fev Download").clear()
print("fertig:", OUT)
