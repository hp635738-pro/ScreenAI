"""Milestone 5: provider-agnostic voice interface (everything mocked)."""

from __future__ import annotations

import pytest

from core.voice import (
    AudioClip,
    FakeAudioRecorder,
    NullVoiceProvider,
    VoiceError,
    VoiceInputService,
    VoiceProvider,
    available_providers,
)


def _clip() -> AudioClip:
    return AudioClip(pcm=b"\x00" * 3200, sample_rate=16000, sample_width=2, channels=1)


class ScriptVoiceProvider(VoiceProvider):
    name = "script"
    description = "Scripted voice provider"

    def is_available(self) -> bool:
        return True

    def availability_detail(self) -> str:
        return "ready"

    def transcribe(self, clip: AudioClip) -> str:
        assert clip.sample_rate > 0
        return "open firefox"


def test_voice_provider_interface() -> None:
    provider = ScriptVoiceProvider()
    assert provider.name == "script"
    assert provider.is_available() is True
    assert provider.push_to_talk_enabled() is True


def test_null_provider_reports_unavailable() -> None:
    provider = NullVoiceProvider()
    assert provider.is_available() is False
    assert provider.availability_detail()
    with pytest.raises(VoiceError):
        provider.transcribe(_clip())


def test_available_providers_includes_builtins() -> None:
    names = [p.name for p in available_providers()]
    assert "none" in names
    assert "whisper" in names


def test_service_push_to_talk_transcribes_into_signal() -> None:
    service = VoiceInputService(recorder_factory=lambda: FakeAudioRecorder(_clip()))
    service.register_provider(ScriptVoiceProvider())
    service.set_provider("script")

    results: list[str] = []
    service.transcription_ready.connect(results.append)

    service.begin_push_to_talk()
    service.end_push_to_talk()
    assert results == ["open firefox"]


def test_service_without_engine_reports_gracefully() -> None:
    service = VoiceInputService(recorder_factory=lambda: FakeAudioRecorder(_clip()))
    service.register_provider(NullVoiceProvider())
    service.set_provider("none")
    messages: list[str] = []
    service.error.connect(messages.append)
    service.notice.connect(messages.append)
    service.transcription_ready.connect(lambda t: messages.append(f"heard:{t}"))
    service.begin_push_to_talk()
    service.end_push_to_talk()
    assert messages, "expected a graceful notice/error/transcription, not a crash"


def test_recorder_failure_is_reported_not_raised() -> None:
    def broken_factory() -> FakeAudioRecorder:  # noqa: ANN202
        raise RuntimeError("no microphone")

    service = VoiceInputService(recorder_factory=broken_factory)
    service.register_provider(ScriptVoiceProvider())
    service.set_provider("script")
    errors: list[str] = []
    service.error.connect(errors.append)
    service.notice.connect(errors.append)

    service.begin_push_to_talk()
    service.end_push_to_talk()
    assert errors


def test_whisper_provider_import_is_optional() -> None:
    from core.voice import WhisperVoiceProvider

    provider = WhisperVoiceProvider()
    # faster-whisper may be absent — either way this must not raise.
    assert isinstance(provider.is_available(), bool)
