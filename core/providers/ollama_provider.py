"""Ollama backend — stub prepared for a later milestone."""

from __future__ import annotations

from collections.abc import Sequence

from core.providers.base import AIProvider, ProviderNotConfigured, ProviderResponse


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(
        self, base_url: str = "http://localhost:11434", model: str = "llama3.2"
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def is_available(self) -> bool:
        # No connectivity probe until the AI milestone lands.
        return False

    def generate(
        self, prompt: str, *, context: Sequence[str] | None = None
    ) -> ProviderResponse:
        raise ProviderNotConfigured(
            "Ollama provider is not connected yet (integration arrives later)."
        )
