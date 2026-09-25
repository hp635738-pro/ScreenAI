"""Auto provider — prefers local AI, falls back to cloud only when allowed.

Privacy is explicit: the cloud (OpenAI) candidate is used only when the
caller passes ``cloud_allowed=True`` (set by the controller after applying
the user's privacy setting and, when required, asking first). Auto never
switches to a cloud provider silently.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from core.providers.base import (
    AIProvider,
    ProviderError,
    ProviderNotConfigured,
    ProviderResponse,
)


class AutoProvider(AIProvider):
    name = "auto"

    def __init__(
        self,
        providers: Sequence[AIProvider],
        *,
        cloud_allowed: bool = False,
    ) -> None:
        self._providers = list(providers)
        self._cloud_allowed = cloud_allowed
        self.last_used: str | None = None

    @property
    def cloud_allowed(self) -> bool:
        return self._cloud_allowed

    def allow_cloud(self, value: bool) -> None:
        self._cloud_allowed = value

    def candidates(self) -> list[AIProvider]:
        if self._cloud_allowed:
            return list(self._providers)
        return [p for p in self._providers if not p.is_cloud]

    def is_available(self) -> bool:
        return any(p.is_available() for p in self.candidates())

    def _select(self) -> AIProvider:
        for provider in self.candidates():
            if provider.is_available():
                return provider
        if self._cloud_allowed:
            raise ProviderError(
                "No AI provider available (Ollama unreachable and OpenAI not configured)."
            )
        raise ProviderNotConfigured(
            "Local AI (Ollama) is unavailable and cloud AI is disabled by your "
            "privacy settings."
        )

    def generate(
        self, prompt: str, *, context: Sequence[str] | None = None
    ) -> ProviderResponse:
        provider = self._select()
        response = provider.generate(prompt, context=context)
        self.last_used = provider.name
        return response

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        stream_cb: Callable[[str], None] | None = None,
    ) -> ProviderResponse:
        provider = self._select()
        response = provider.chat(messages, stream_cb=stream_cb)
        self.last_used = provider.name
        return response
