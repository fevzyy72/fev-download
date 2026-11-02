"""Vorschau-Player.

Spielt nach Moeglichkeit direkt den Stream der Plattform - dann muss nichts
vorab geladen werden. Geht das nicht (manche Seiten geben ihre Adressen nur
mit besonderen Kopfdaten heraus), meldet der Player das und das Hauptfenster
holt stattdessen eine kleine Datei.

Die Bildflaeche richtet sich nach dem Format der Quelle: Ein Hochformat-Video
bekommt eine hohe, schmale Flaeche statt in einem breiten Kasten zwischen zwei
schwarzen Balken zu verschwinden.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.models import format_timecode
from . import typography

STAGE_COLOR = QColor("#141414")


class _AspectStage(QWidget):
    """Passt das ganze Bild in den verfuegbaren Platz, ohne schwarze Restflaeche.

    Die Geometrie wird ausdruecklich gesetzt: Ein Maximum mit seitlichen
    Dehnungen laesst Qt das Video auf seine kleinste Breite zusammenschieben.
    Ausserdem darf die Originalaufloesung nicht zur Mindestgroesse der GUI werden.
    """

    def __init__(self, stack: QStackedWidget, parent=None) -> None:
        super().__init__(parent)
        self._stack = stack
        self._stack.setParent(self)
        self._aspect = 16 / 9
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stack.currentChanged.connect(self._fit_video)

    def sizeHint(self) -> QSize:
        return QSize(480, 270)

    def set_aspect(self, aspect: float) -> None:
        self._aspect = aspect
        self._fit_video()

    def _fit_video(self, *_args) -> None:
        area = self.contentsRect()
        if area.isEmpty():
            return
        if self._stack.currentIndex() == 0:
            # Lade- und Fehlermeldungen brauchen Platz fuer lesbaren Text.
            self._stack.setGeometry(area)
            return

        width, height = area.width(), area.height()
        if width / height > self._aspect:
            width = max(1, round(height * self._aspect))
        else:
            height = max(1, round(width / self._aspect))
        self._stack.setGeometry(QRect(
            area.x() + (area.width() - width) // 2,
            area.y() + (area.height() - height) // 2,
            width, height,
        ))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_video()


class PreviewPlayer(QWidget):
    """Videofenster mit Abspieltasten und Positionsanzeige."""

    positionChanged = Signal(float)   # Sekunden
    durationResolved = Signal(float)  # Sekunden
    streamFailed = Signal()           # Stream nicht abspielbar

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._aspect = 16 / 9
        self._reported_failure = False

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.7)
        self._player.setAudioOutput(self._audio)

        self._video = QVideoWidget(self)
        self._video.setAspectRatioMode(Qt.KeepAspectRatio)
        # Die natuerliche Groesse (z. B. 1080x1920) ist kein GUI-Mindestmass.
        self._video.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        # Der Rand neben dem Bild soll dunkel bleiben, nicht in Systemgrau
        # aufblitzen. QVideoWidget folgt keinem Stylesheet, daher per Palette.
        palette = self._video.palette()
        palette.setColor(self._video.backgroundRole(), STAGE_COLOR)
        self._video.setPalette(palette)
        self._video.setAutoFillBackground(True)
        self._player.setVideoOutput(self._video)

        self._placeholder = QLabel("Noch kein Video geladen")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setObjectName("placeholder")

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._video)
        self._stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._stage = _AspectStage(self._stack, self)

        self._play_button = QPushButton("Abspielen")
        self._play_button.setObjectName("quiet")
        self._play_button.setFixedWidth(96)
        self._play_button.setEnabled(False)
        self._play_button.clicked.connect(self.toggle_play)

        self._position_slider = QSlider(Qt.Horizontal)
        self._position_slider.setRange(0, 0)
        self._position_slider.setEnabled(False)
        self._position_slider.sliderMoved.connect(self._on_slider_moved)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setObjectName("muted")
        self._time_label.setFont(typography.mono())
        self._time_label.setMinimumWidth(104)
        self._time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self._play_button)
        controls.addWidget(self._position_slider, 1)
        controls.addWidget(self._time_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._stage, 1)
        layout.addLayout(controls)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)
        # Metadaten sind nur eine Vorgabe. Die abgespielte Vorschau kann ein
        # anderes Format haben oder eine Drehung enthalten.
        self._video.videoSink().videoSizeChanged.connect(self._on_video_size_changed)

        self._fallback_duration = 0.0

    # -- Bildformat ---------------------------------------------------------

    def set_aspect(self, aspect: float) -> None:
        """
        Legt das Seitenverhaeltnis der Quelle fest.

        Die Bildflaeche nutzt den groesstmoeglichen passenden Ausschnitt der
        freien Flaeche. Das ganze Video bleibt sichtbar und unverzerrt.
        """
        self._aspect = aspect if aspect and math.isfinite(aspect) and aspect > 0 else 16 / 9
        self._stage.set_aspect(self._aspect)

    def _on_video_size_changed(self) -> None:
        size = self._video.videoSink().videoSize()
        if size.width() > 0 and size.height() > 0:
            self.set_aspect(size.width() / size.height())

    # -- Steuerung ----------------------------------------------------------

    def load(self, source: str | Path, fallback_duration: float = 0.0) -> None:
        """
        Laedt einen Stream oder eine oertliche Datei.

        Leere Angabe bedeutet: keine Vorschau moeglich.
        """
        self._fallback_duration = fallback_duration
        self._reported_failure = False
        self.stop()

        if not source:
            self._show_message(
                "Fuer dieses Video gibt es keine abspielbare Vorschau.\n"
                "Der Ausschnitt laesst sich trotzdem ueber die Zeitfelder waehlen."
            )
            return

        self._stack.setCurrentWidget(self._video)
        self._play_button.setEnabled(True)
        self._position_slider.setEnabled(True)

        if isinstance(source, Path):
            self._player.setSource(QUrl.fromLocalFile(str(source)))
        else:
            self._player.setSource(QUrl(source))

    def show_loading(self, message: str = "Vorschau wird geladen...") -> None:
        """Zeigt einen Hinweis, waehrend die Ausweichdatei geholt wird."""
        self._show_message(message)

    def _show_message(self, text: str) -> None:
        # clear() entfernt ein etwaiges Standbild. Ein QPixmap dafuer vorab
        # anzulegen ginge nicht: Vor dem Start der Anwendung erzeugt, bringt es
        # Qt beim Laden des Moduls zum Absturz.
        self._placeholder.clear()
        self._placeholder.setText(text)
        self._stack.setCurrentWidget(self._placeholder)
        self._play_button.setEnabled(False)
        self._position_slider.setEnabled(False)
        self._set_time_label(0.0, self._fallback_duration)

    def stop(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())

    def toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def seek(self, seconds: float) -> None:
        self._player.setPosition(int(seconds * 1000))

    def position(self) -> float:
        return self._player.position() / 1000.0

    # -- Rueckmeldungen des Players -----------------------------------------

    def _on_slider_moved(self, value: int) -> None:
        self._player.setPosition(value)

    def _on_position_changed(self, milliseconds: int) -> None:
        if not self._position_slider.isSliderDown():
            self._position_slider.setValue(milliseconds)
        seconds = milliseconds / 1000.0
        self._set_time_label(seconds, self._player.duration() / 1000.0)
        self.positionChanged.emit(seconds)

    def _on_duration_changed(self, milliseconds: int) -> None:
        self._position_slider.setRange(0, milliseconds)
        if milliseconds > 0:
            self.durationResolved.emit(milliseconds / 1000.0)

    def _on_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        self._play_button.setText("Pause" if playing else "Abspielen")

    def _on_error(self, error, error_string: str) -> None:
        if error == QMediaPlayer.NoError or self._reported_failure:
            return
        self._reported_failure = True
        # Das Hauptfenster entscheidet, ob es eine Datei nachladen laesst.
        self.streamFailed.emit()

    def _set_time_label(self, position: float, duration: float) -> None:
        if duration <= 0:
            duration = self._fallback_duration
        self._time_label.setText(
            f"{format_timecode(position)} / {format_timecode(duration)}"
        )
