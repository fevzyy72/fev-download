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

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
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
        self._stack.setMinimumHeight(240)

        self._stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Die beiden Dehnungen links und rechts halten die Flaeche bei
        # Hochformat in der Mitte. Im Querformat muessen sie abgeschaltet
        # werden, sonst quetschen sie das Bild auf seine Mindestbreite.
        self._stage = QHBoxLayout()
        self._stage.setContentsMargins(0, 0, 0, 0)
        self._stage.setSpacing(0)
        self._stage.addStretch(0)
        self._stage.addWidget(self._stack, 1)
        self._stage.addStretch(0)

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
        layout.addLayout(self._stage, 1)
        layout.addLayout(controls)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)

        self._fallback_duration = 0.0

    # -- Bildformat ---------------------------------------------------------

    def set_aspect(self, aspect: float) -> None:
        """
        Legt das Seitenverhaeltnis der Quelle fest.

        Bei Hochformat wird die Flaeche in der Breite begrenzt, damit das Bild
        die volle Hoehe nutzt statt klein zwischen schwarzen Raendern zu sitzen.
        """
        self._aspect = aspect if aspect and aspect > 0 else 16 / 9
        self._apply_stage_width()

    def _apply_stage_width(self) -> None:
        height = self._stack.height()
        if height <= 0:
            height = self._stack.minimumHeight()

        if self._aspect < 0.95:  # Hochformat
            self._stack.setMaximumWidth(max(220, int(height * self._aspect)))
            # Aussen dehnen, damit die schmale Flaeche mittig sitzt.
            self._stage.setStretch(0, 1)
            self._stage.setStretch(1, 0)
            self._stage.setStretch(2, 1)
        else:
            self._stack.setMaximumWidth(16777215)  # keine Begrenzung
            # Innen dehnen, damit das Bild die volle Breite bekommt.
            self._stage.setStretch(0, 0)
            self._stage.setStretch(1, 1)
            self._stage.setStretch(2, 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_stage_width()

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
