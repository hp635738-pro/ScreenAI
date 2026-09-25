"""Pluggable speech-to-text architecture.

A :class:`VoiceProvider` turns recorded audio into text. ScreenAI never
depends on a concrete engine: providers register themselves and the
service degrades to a notice when none is available.
"""

from __future__ import annotations

from core.voice.base import AudioClip, VoiceError, VoiceProvider
from core.voice.null_provider import NullVoiceProvider
from core.voice.recorder import AudioRecorder, FakeAudioRecorder
from core.voice.service import VoiceInputService
from core.voice.whisper_provider import WhisperVoiceProvider


def available_providers() -> list[VoiceProvider]:
    """Fresh instances of every built-in provider (import-safe)."""
    return [NullVoiceProvider(), WhisperVoiceProvider()]


__all__ = [
    "AudioClip",
    "AudioRecorder",
    "FakeAudioRecorder",
    "NullVoiceProvider",
    "VoiceError",
    "VoiceInputService",
    "VoiceProvider",
    "WhisperVoiceProvider",
    "available_providers",
]
