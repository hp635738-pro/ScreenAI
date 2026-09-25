"""Audio capture for push-to-talk.

The recorder is a small interface so alternative input sources (ALSA
tools, a phone companion, tests) can substitute the QtMultimedia
implementation without touching the voice service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.voice.base import AudioClip, VoiceError


class AudioRecorder(ABC):
    @abstractmethod
    def start(self) -> None:
        """Begin capturing."""

    @abstractmethod
    def stop(self) -> AudioClip:
        """Stop capturing and return the recorded clip."""


class QtAudioRecorder(AudioRecorder):
    """Microphone capture via QtMultimedia (lazy import, fail-soft)."""

    def __init__(self, device_name: str = "default", parent=None) -> None:  # noqa: ANN001
        self._device_name = device_name
        self._parent = parent
        self._buffer = bytearray()
        self._input = None
        self._source = None
        self._format = None

    def start(self) -> None:
        try:
            from PySide6.QtMultimedia import (  # noqa: PLC0415
                QAudioDevice,
                QAudioFormat,
                QAudioSource,
                QMediaDevices,
            )
            from PySide6.QtCore import QByteArray, QBuffer, QIODevice  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            raise VoiceError(
                f"Audio capture unavailable: {exc}",
                category="microphone_unavailable",
            ) from exc

        devices = QMediaDevices.audioInputs()
        if not devices:
            raise VoiceError(
                "No microphone found. Connect a microphone and try again.",
                category="microphone_unavailable",
            )
        device: QAudioDevice = devices[0]
        for candidate in devices:
            if candidate.description() == self._device_name:
                device = candidate
                break

        fmt = QAudioFormat()
        fmt.setSampleRate(16_000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()

        self._buffer = bytearray()
        self._byte_array = QByteArray()
        self._qbuffer = QBuffer(self._byte_array)
        self._qbuffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self._source = QAudioSource(device, fmt, self._parent)
        self._input = self._source.start()
        if self._input is None:
            raise VoiceError(
                "Microphone permission denied or device busy.",
                category="microphone_unavailable",
            )
        self._format = fmt
        self._input.readyRead.connect(self._drain)

    def _drain(self) -> None:
        if self._input is not None:
            self._buffer.extend(bytes(self._input.readAll()))

    def stop(self) -> AudioClip:
        if self._source is not None:
            self._source.stop()
        rate, width, channels = 16_000, 2, 1
        if self._format is not None:
            rate = self._format.sampleRate() or rate
            channels = self._format.channelCount() or channels
            width = max(1, self._format.bytesPerSample() or width)
        clip = AudioClip(
            pcm=bytes(self._buffer),
            sample_rate=rate,
            sample_width=width,
            channels=channels,
        )
        self._source = None
        self._input = None
        return clip


class FakeAudioRecorder(AudioRecorder):
    """Deterministic recorder for tests and demos."""

    def __init__(self, clip: AudioClip | None = None) -> None:
        self._clip = clip or AudioClip(pcm=b"\x00\x00" * 800)
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> AudioClip:
        self.started = False
        return self._clip
