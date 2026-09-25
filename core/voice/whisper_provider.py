"""Whisper-based speech-to-text (experimental).

Loads ``faster-whisper`` lazily; when the dependency (or its runtime)
is missing the provider reports unavailable with an actionable hint and
the rest of ScreenAI keeps working.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from core.voice.base import AudioClip, VoiceError, VoiceProvider


class WhisperVoiceProvider(VoiceProvider):
    name = "whisper"
    description = "Local Whisper transcription (experimental — needs faster-whisper)."

    def __init__(self, model_name: str = "base") -> None:
        self._model_name = model_name
        self._model = None

    def is_available(self) -> bool:
        try:
            import importlib.util  # noqa: PLC0415

            return importlib.util.find_spec("faster_whisper") is not None
        except Exception:  # noqa: BLE001
            return False

    def availability_detail(self) -> str:
        if self.is_available():
            return f"Whisper model “{self._model_name}” ready."
        return "faster-whisper is not installed (pip install faster-whisper)."

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # noqa: PLC0415

                self._model = WhisperModel(self._model_name, device="cpu")
            except Exception as exc:  # noqa: BLE001
                raise VoiceError(
                    f"Could not load Whisper model “{self._model_name}”: {exc}. "
                    "Install faster-whisper or pick another engine in Settings.",
                ) from exc
        return self._model

    def transcribe(self, clip: AudioClip) -> str:
        if not clip.pcm:
            raise VoiceError("No audio captured.", category="voice_empty")
        model = self._load()
        try:
            import wave  # noqa: PLC0415

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
                path = Path(fh.name)
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(clip.channels)
                wav.setsampwidth(clip.sample_width)
                wav.setframerate(clip.sample_rate)
                wav.writeframes(clip.pcm)
            segments, _info = model.transcribe(str(path))
            text = " ".join(segment.text.strip() for segment in segments).strip()
            path.unlink(missing_ok=True)
            return text
        except VoiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VoiceError(f"Transcription failed: {exc}") from exc
