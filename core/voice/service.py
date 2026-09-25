"""Push-to-talk voice input service (UI-agnostic).

Speak while the microphone button is held (push-to-talk); on release the
clip is transcribed and handed to the command box for editing before the
user executes it. Every failure path degrades to a notice — voice is
always optional.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.voice.base import AudioClip, VoiceError, VoiceProvider
from core.voice.null_provider import NullVoiceProvider
from core.voice.recorder import AudioRecorder


class VoiceInputService(QObject):
    transcription_ready = Signal(str)  # editable draft for the command box
    state_changed = Signal(str)  # idle | listening | transcribing
    notice = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        provider: VoiceProvider | None = None,
        recorder_factory=None,  # noqa: ANN001
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._providers: dict[str, VoiceProvider] = {}
        self._provider_name = "none"
        self._recorder_factory = recorder_factory
        self._recorder: AudioRecorder | None = None
        self._listening = False
        if provider is not None:
            self.register_provider(provider)
            self._provider_name = provider.name

    # ------------------------------------------------------- providers

    def register_provider(self, provider: VoiceProvider) -> None:
        """Plugins/engines register additional VoiceProviders here."""
        self._providers[provider.name] = provider

    def provider_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def set_provider(self, name: str) -> None:
        if name not in self._providers and name != "none":
            self.notice.emit(f"Voice provider “{name}” is not registered.")
            return
        self._provider_name = name

    @property
    def provider(self) -> VoiceProvider:
        return self._providers.get(self._provider_name) or NullVoiceProvider()

    # -------------------------------------------------------- push-to-talk

    @property
    def is_listening(self) -> bool:
        return self._listening

    def start_listening(self) -> None:
        """Fallback entry point (click without hold) — a single tap toggles."""
        if self._listening:
            self.end_push_to_talk()
        else:
            self.begin_push_to_talk()

    def begin_push_to_talk(self) -> None:
        if self._listening:
            return
        provider = self.provider
        if not provider.is_available():
            self.notice.emit(provider.availability_detail())
            return
        try:
            self._recorder = self._make_recorder()
            self._recorder.start()
        except VoiceError as exc:
            self.error.emit(str(exc))
            self.notice.emit(str(exc))
            self._recorder = None
            return
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Microphone unavailable: {exc}")
            self._recorder = None
            return
        self._listening = True
        self.state_changed.emit("listening")
        self.notice.emit("Listening… release to transcribe.")

    def end_push_to_talk(self) -> None:
        if not self._listening:
            return
        self._listening = False
        recorder, self._recorder = self._recorder, None
        self.state_changed.emit("transcribing")
        try:
            clip = recorder.stop() if recorder is not None else AudioClip()
            text = self.provider.transcribe(clip)
        except VoiceError as exc:
            self.state_changed.emit("idle")
            self.error.emit(str(exc))
            self.notice.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.state_changed.emit("idle")
            self.notice.emit(f"Transcription failed: {exc}")
            return
        self.state_changed.emit("idle")
        if text.strip():
            self.transcription_ready.emit(text.strip())
            self.notice.emit("Transcribed — edit the command and press Run.")
        else:
            self.notice.emit("No speech detected.")

    # ---------------------------------------------------------- internals

    def _make_recorder(self) -> AudioRecorder:
        if self._recorder_factory is not None:
            return self._recorder_factory()
        from core.voice.recorder import QtAudioRecorder  # noqa: PLC0415

        return QtAudioRecorder(parent=self)
