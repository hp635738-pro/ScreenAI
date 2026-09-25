"""VoiceProvider interface — the contract every speech engine implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class AudioClip:
    """Raw PCM audio captured by a recorder."""

    pcm: bytes = b""
    sample_rate: int = 16_000
    sample_width: int = 2  # bytes per sample
    channels: int = 1
    metadata: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        width = max(1, self.sample_width * self.channels)
        return len(self.pcm) / (self.sample_rate * width)


class VoiceError(Exception):
    """Raised when recording or transcription cannot proceed."""

    def __init__(self, message: str, *, category: str = "voice_unavailable") -> None:
        super().__init__(message)
        self.category = category


class VoiceProvider(ABC):
    """Speech-to-text engine contract.

    Implementations must be cheap to construct and must never raise
    from :meth:`is_available`; transcription problems raise
    :class:`VoiceError` with an actionable message.
    """

    name: str = "voice"
    description: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this engine can transcribe right now."""

    def availability_detail(self) -> str:
        return "Available." if self.is_available() else "Not available."

    @abstractmethod
    def transcribe(self, clip: AudioClip) -> str:
        """Return the transcript text for an audio clip."""

    def push_to_talk_enabled(self) -> bool:
        return True
