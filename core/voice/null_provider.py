"""Fallback provider used when no speech engine is installed."""

from __future__ import annotations

from core.voice.base import AudioClip, VoiceError, VoiceProvider


class NullVoiceProvider(VoiceProvider):
    """Always unavailable — keeps the provider list total and explicit."""

    name = "none"
    description = "Voice input disabled (text typing works as usual)."

    def is_available(self) -> bool:
        return False

    def availability_detail(self) -> str:
        return self.description

    def transcribe(self, clip: AudioClip) -> str:
        raise VoiceError(
            "Voice input is disabled. Choose a voice engine in Settings → Voice.",
        )

    def push_to_talk_enabled(self) -> bool:
        return False
