"""Playback bar: QMediaPlayer transport at the bottom of the window."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from keydup.domain import Track
from keydup.notation import get_formatter, saved_notation
from keydup.ui.key_timeline import KeyTimeline
from keydup.ui.waveform_widget import WaveformWidget


def _fmt_ms(ms: int) -> str:
    s = max(0, ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


class PlayerBar(QWidget):
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.9)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.track: Track | None = None
        self.key_formatter = get_formatter(saved_notation())

        style = self.style()
        self.play_button = QPushButton(self)
        self.play_button.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
        self.play_button.setFixedWidth(36)
        self.stop_button = QPushButton(self)
        self.stop_button.setIcon(style.standardIcon(QStyle.SP_MediaStop))
        self.stop_button.setFixedWidth(36)

        self.waveform = WaveformWidget(self)
        self.key_timeline = KeyTimeline(self)
        self.key_timeline.hide()  # only shown for modulating tracks
        self.time_label = QLabel("0:00 / 0:00", self)
        self.now_playing = QLabel("", self)
        self.now_playing.setMinimumWidth(220)

        self.volume = QSlider(Qt.Horizontal, self)
        self.volume.setRange(0, 100)
        self.volume.setValue(90)
        self.volume.setFixedWidth(90)

        transport = QHBoxLayout()
        transport.addWidget(self.play_button)
        transport.addWidget(self.stop_button)
        transport.addWidget(self.now_playing)
        transport.addStretch(1)
        transport.addWidget(self.time_label)
        transport.addWidget(QLabel("Vol", self))
        transport.addWidget(self.volume)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        layout.addWidget(self.waveform)
        layout.addWidget(self.key_timeline)
        layout.addLayout(transport)

        def seek_to(fraction: float) -> None:
            self.player.setPosition(int(fraction * self.player.duration()))

        self.play_button.clicked.connect(self.toggle)
        self.stop_button.clicked.connect(self.player.stop)
        self.waveform.seek_fraction.connect(seek_to)
        self.key_timeline.seek_fraction.connect(seek_to)
        self.volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(
            lambda _err, msg: self.error.emit(msg or "playback error")
        )

    # -- API -------------------------------------------------------------

    def play_track(self, track: Track) -> None:
        self.track = track
        self.player.setSource(QUrl.fromLocalFile(track.path))
        self.player.play()
        bits = [track.artist or "", track.title or track.filename]
        label = " - ".join(b for b in bits if b)
        key = self.key_formatter(track.key_camelot) if track.key_camelot else None
        extras = " · ".join(
            x for x in (key, f"{track.bpm}" if track.bpm else None) if x
        )
        self.now_playing.setText(f"{label}   {extras}" if extras else label)

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.player.source().isValid():
            self.player.play()

    # -- slots -------------------------------------------------------------

    def _on_position(self, pos: int) -> None:
        duration = self.player.duration()
        if duration > 0:
            self.waveform.set_progress(pos / duration)
        self.time_label.setText(f"{_fmt_ms(pos)} / {_fmt_ms(duration)}")

    def _on_duration(self, duration: int) -> None:
        pass  # waveform progress is fractional; nothing to resize

    def _on_state(self, state) -> None:
        icon = (
            QStyle.SP_MediaPause
            if state == QMediaPlayer.PlayingState
            else QStyle.SP_MediaPlay
        )
        self.play_button.setIcon(self.style().standardIcon(icon))
