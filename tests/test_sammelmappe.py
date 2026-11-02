"""Prueft die Oberflaeche "Sammelmappe": Bedienelemente, Zustaende, Geometrie.

    1. Geometrie bei 1000x960 und 860x620: Hauptknopf, Zettel, Vorschau erreichbar
    2. Tastatur: Medienkarten (Pfeile), Schalter (Leertaste), Zeitleiste (Pfeile)
    3. Zeitleiste: Zoom auf die Auswahl, beim Ziehen springt nichts
    4. "Nichts zeigt mehr, als stimmt": Hinweise am Zettel und ueber dem Knopf
    5. Laden: Lieferliste, hoechstens drei gleichzeitig, Fertig
"""

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from fevdl import paths
from fevdl.core.models import Mode, Quality, VideoInfo
from fevdl.gui import typography
from fevdl.gui.widgets import JobRow, MainAction

tmp = Path(tempfile.mkdtemp(prefix="fevmappe_"))
paths.RESULT_FILE = tmp / "result.json"

app = QApplication(sys.argv[:1])
app.setFont(typography.body())
QSettings("fezco", "Fev Download").clear()

from fevdl.gui.main_window import MainWindow  # noqa: E402

window = MainWindow(job=None)
window._start_preview_fallback = lambda: None
window.player.load = lambda *_a, **_k: None
window.output_edit.setText(str(tmp))
window.show()
QTest.qWaitForWindowExposed(window)

# Vor der Analyse: nur der Einstieg
assert window.download_stack.currentIndex() == 0, "Ohne Video gehoert der Einstieg nach vorn"
assert window.url_edit.isVisible()

info = VideoInfo(url="https://example.com/v", title="Testvideo", duration=600.0, audio_url="a",
                 qualities=[Quality(1080, 30), Quality(720, 30)], extractor="Youtube",
                 width=1920, height=1080)
window._on_probe_succeeded(info)
QTest.qWait(250)
assert window.download_stack.currentIndex() == 1
assert window.url_edit.isVisible(), "Der Link bleibt auch nach der Analyse erreichbar"

# -- 1. Geometrie ------------------------------------------------------------


def inside(widget) -> bool:
    top_left = widget.mapTo(window, QPoint(0, 0))
    return QRect(QPoint(0, 0), window.size()).contains(QRect(top_left, widget.size()))


for width, height in ((1000, 960), (860, 620)):
    window.resize(width, height)
    QTest.qWait(150)
    app.processEvents()
    assert window.width() == width and window.height() == height, "Mindestgroesse 860x620 muss gehen"
    assert window.download_button.isVisible() and inside(window.download_button), \
        f"Hauptknopf bei {width}x{height} nicht erreichbar"
    assert inside(window.status_label), "Statuszeile ausserhalb"
    assert window.trim_bar._track_rect().height() >= 140, "Wellenform braucht >= 140 px"
    stage = window.player._stage
    assert stage.width() > 200 and stage.height() >= 160, f"Vorschau zu klein: {stage.size()}"
    assert window.collection.geometry().right() < window.width()
    print(f"{width}x{height}: Knopf {window.download_button.geometry().getRect()}, Buehne {stage.width()}x{stage.height()}")

window.resize(1000, 960)
QTest.qWait(150)

# -- 2. Tastatur -------------------------------------------------------------

cards = window.mode_combo.buttons()
cards[0].setFocus(Qt.TabFocusReason)
QTest.keyClick(cards[0], Qt.Key_Right)
print("Pfeil rechts   :", window._current_mode())
assert window._current_mode() is Mode.AUDIO_ONLY, "Pfeiltaste muss die Medienkarte wechseln"
assert not window.quality_combo.isEnabled(), "Nur Ton: Qualitaet gesperrt"
QTest.keyClick(window.mode_combo.buttons()[1], Qt.Key_Left)
assert window._current_mode() is Mode.VIDEO_AUDIO
assert window.quality_combo.isEnabled()

before = window.h264_check.isChecked()
window.h264_check.setFocus(Qt.TabFocusReason)
QTest.keyClick(window.h264_check, Qt.Key_Space)
assert window.h264_check.isChecked() is not before, "Leertaste schaltet den Schalter"

window.quality_combo.buttons()[1].click()
assert window.quality_combo.currentData() == 720

bar = window.trim_bar
bar.set_range(100.0, 130.0)
bar.setFocus(Qt.TabFocusReason)
QTest.keyClick(bar, Qt.Key_Right)
assert abs(bar.start() - 101.0) < 0.01, "Pfeil verschiebt den Anfang"
QTest.keyClick(bar, Qt.Key_Space)
QTest.keyClick(bar, Qt.Key_Left, Qt.ShiftModifier)
assert abs(bar.end() - 120.0) < 0.01, "Umschalt+Pfeil verschiebt das Ende um 10 s"
QTest.keyClick(bar, Qt.Key_Right, Qt.AltModifier)
assert abs(bar.end() - 120.1) < 0.01, "Alt+Pfeil: Zehntelsekunde"
print("Zeitfelder     :", window.start_edit.text(), window.end_edit.text())
assert window.end_edit.text() == "2:00.1", "Zeitfeld muss Zehntel zeigen, statt zu runden"

window.start_edit.setText("1:36.4")
window._on_start_edited()
assert abs(bar.start() - 96.4) < 0.01

# Kuerzel haengen am Fenster (es gibt keine Menueleiste mehr)
keys = {action.shortcut().toString() for action in window.actions()}
assert {"I", "O", "M", "Ctrl+K"} <= keys, keys

# Jeder Symbolknopf hat einen Namen fuer Bildschirmleser
for button in (window.paste_button, window.clear_link_button, window.zoom_button,
               window.waveform_button, window.set_start_button, window.set_end_button,
               window.reset_trim_button, window.clear_segments_button, window.menu_button):
    assert button.accessibleName(), f"Knopf ohne Namen: {button}"
    assert button.toolTip(), f"Knopf ohne Tooltip: {button.accessibleName()}"

# -- 3. Zoom und Ziehen ------------------------------------------------------

bar.set_range(300.0, 330.0)
QTest.qWait(400)
lo, hi = bar.view_range()
print("Ansicht        :", round(lo, 1), round(hi, 1))
assert lo <= 300.0 and hi >= 330.0 and hi - lo < 60, "Detail muss auf die Auswahl zoomen"

y = int(bar._track_rect().center().y())
x = int(bar._seconds_to_x(bar.start()))
view_before = bar.view_range()
QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, QPoint(x, y))
QTest.mouseMove(bar, QPoint(x + 40, y))
QTest.qWait(50)
assert bar.view_range() == view_before, "Waehrend des Ziehens darf die Skala nicht springen"
assert bar.start() > 300.0
QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, QPoint(x + 40, y))
QTest.qWait(400)
assert bar.view_range() != view_before, "Nach dem Loslassen folgt die Ansicht der Auswahl"
assert abs(bar.start() * 10 - round(bar.start() * 10)) < 1e-6, "Ziehen rastet auf Zehntel ein"

window._toggle_zoom()
QTest.qWait(400)
assert bar.view_range() == (0.0, 600.0), "Ohne Zoom zeigt das Detail das ganze Video"
window._toggle_zoom()

# -- 4. Wahrheit am Zettel ---------------------------------------------------

bar.set_range(10.0, 20.0)
window._add_segment()
bar.set_range(40.0, 50.0)
assert window.slip_note.isVisible(), "Nicht abgelegte Auswahl muss als solche erkennbar sein"
assert "1 abgelegter" in window.plan_label.text(), window.plan_label.text()
window._load_segment(0)
assert not window.add_segment_button.isEnabled(), "Schon abgelegt - kein zweites Ablegen"
assert not window.slip_note.isVisible()

# Klick auf einen gemerkten Ausschnitt spielt genau diesen Teil in Schleife
played = []
window.player.loop_range = lambda a, b: played.append((a, b))
window.segment_list.ticket(0).click()
assert played == [(10.0, 20.0)], played

# Leertaste: Abspielen/Pause - aber der per Tab erreichte Schalter behaelt sie
toggled = []
window.player.can_play = lambda: True
window.player.toggle_play = lambda: toggled.append(1)
window.add_segment_button.setFocus(Qt.MouseFocusReason)
QTest.keyClick(window.add_segment_button, Qt.Key_Space)
assert toggled == [1], "Leertaste nach einem Klick spielt das Video ab"
before = window.h264_check.isChecked()
window.h264_check.setFocus(Qt.TabFocusReason)
QTest.keyClick(window.h264_check, Qt.Key_Space)
assert toggled == [1] and window.h264_check.isChecked() is not before, \
    "Per Tab erreichter Schalter bekommt die Leertaste"
window.h264_check.setChecked(before)
window.url_edit.setFocus(Qt.MouseFocusReason)
QTest.keyClick(window.url_edit, Qt.Key_Space)
assert toggled == [1], "Im Eingabefeld ist die Leertaste ein Leerzeichen"
window.url_edit.clear()

# Die Schleife bleibt am Ende des Ausschnitts bestehen und endet beim Springen
window.player._loop_range = (2000, 5000)
window.player._on_position_changed(5100)
assert window.player.is_looping(), "Am Ausschnittsende laeuft die Schleife weiter"
window.player.seek(1.0)
assert not window.player.is_looping(), "Wer selbst springt, verlaesst die Schleife"

for a, b in ((100, 110), (200, 210), (300, 310)):
    bar.set_range(a, b)
    window._add_segment()
assert window.download_button.text() == "4 Ausschnitte laden"
assert "4 abgelegte" in window.plan_label.text()

# Entfernen ueber das X am Zettel
window.segment_list.ticket(3).remove_button.click()
assert len(window._segments) == 3
bar.set_range(300, 310)
window._add_segment()

# -- 5. Laden ----------------------------------------------------------------

requests = window._build_requests()
assert len(requests) == 4
window._open_delivery(requests)
window._set_state_busy()
rows = window.delivery_list.rows()
states = [row.state() for row in rows]
print("Start          :", states)
assert states == [JobRow.RUNNING] * 3 + [JobRow.WAITING], "Hoechstens drei laufen gleichzeitig"
assert window.download_button.state() == MainAction.RUNNING
assert window.cancel_button.isVisible()
assert window.collection_stack.currentIndex() == 1

clip = tmp / "c.mp4"
clip.write_bytes(b"x")
window._on_part_ready(1, clip)
states = [row.state() for row in rows]
print("Nach Teil 2    :", states)
assert states[1] == JobRow.DONE and states[3] == JobRow.RUNNING, "Der naechste rueckt nach"

for index in (0, 2, 3):
    window._on_part_ready(index, clip)
window._on_file_ready(clip)
window._on_download_succeeded(clip)
assert window.download_button.state() == MainAction.DONE
assert window.download_button.text() == "Fertig"
assert window.delivery_heading.text() == "Abgelegt."
assert window.back_button.isVisible()

window._back_to_collection()
assert window.collection_stack.currentIndex() == 0
assert window.download_button.text() == "4 Ausschnitte laden"

window.close()
app.processEvents()
QSettings("fezco", "Fev Download").clear()
print("\nSAMMELMAPPE-TEST OK")
