"""OpenAI backend — stub prepared for a later milestone."""

from __future__ import annotations

from collections.abc import Sequence

from core.providers.base import AIProvider, ProviderNotConfigured, ProviderResponse


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini") -> None:
        self._api_key = api_key
        self._model = model

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(
        self, prompt: str, *, context: Sequence[str] | None = None
    ) -> ProviderResponse:
        if not self.is_available():
            raise ProviderNotConfigured(
                "OpenAI provider needs an API key (not configured yet)."
            )
        raise NotImplementedError("OpenAI integration arrives in a later milestone.")
