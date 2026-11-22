"""Reproductor de vista previa integrado (QtMultimedia) para un stream directo."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from firedownload.core.utils import format_duration


class PreviewDialog(QDialog):
    """Reproduce una URL de vídeo con controles básicos."""

    def __init__(self, stream_url: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or "Vista previa")
        self.resize(820, 520)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.7)
        self._player.setAudioOutput(self._audio)
        self._video = QVideoWidget()
        self._player.setVideoOutput(self._video)

        self._play = QPushButton("Pausar")
        self._position = QSlider(Qt.Orientation.Horizontal)
        self._time = QLabel("0:00")
        self._time.setObjectName("muted")
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(90)
        self._error = QLabel()
        self._error.setObjectName("warning")
        self._error.setWordWrap(True)

        controls = QHBoxLayout()
        controls.addWidget(self._play)
        controls.addWidget(self._position, 1)
        controls.addWidget(self._time)
        controls.addWidget(QLabel("Vol."))
        controls.addWidget(self._volume)
        layout = QVBoxLayout(self)
        layout.addWidget(self._video, 1)
        layout.addWidget(self._error)
        layout.addLayout(controls)

        self._play.clicked.connect(self._toggle)
        self._position.sliderMoved.connect(self._player.setPosition)
        self._volume.valueChanged.connect(lambda v: self._audio.setVolume(v / 100))
        self._player.durationChanged.connect(lambda ms: self._position.setRange(0, ms))
        self._player.positionChanged.connect(self._on_position)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.errorOccurred.connect(lambda _err, message: self._error.setText(f"Error de reproducción: {message}"))

        self._player.setSource(QUrl(stream_url))
        self._player.play()

    def _toggle(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_state(self, state: QMediaPlayer.PlaybackState) -> None:
        self._play.setText("Pausar" if state == QMediaPlayer.PlaybackState.PlayingState else "Reproducir")

    def _on_position(self, ms: int) -> None:
        if not self._position.isSliderDown():
            self._position.setValue(ms)
        self._time.setText(f"{format_duration(ms / 1000) or '0:00'} / {format_duration(self._player.duration() / 1000) or '0:00'}")

    def done(self, result: int) -> None:
        self._player.stop()
        super().done(result)
