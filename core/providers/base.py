"""Abstract provider interface for AI backends.

``generate()`` is the original contract and stays abstract.
``chat()`` adds multi-turn messages and optional token streaming for the
agent loop; the default implementation flattens onto ``generate()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field


class ProviderError(RuntimeError):
    """Raised when a provider cannot fulfil a request."""


class ProviderNotConfigured(ProviderError):
    """Raised when a provider is missing credentials or an endpoint."""


@dataclass(slots=True)
class ProviderResponse:
    text: str
    provider: str
    model: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class AIProvider(ABC):
    """Contract every AI backend (OpenAI, Ollama, …) must implement."""

    name: str = "base"
    is_cloud: bool = False

    @abstractmethod
    def is_available(self) -> bool:
        """Whether the provider has everything it needs to run."""

    @abstractmethod
    def generate(
        self, prompt: str, *, context: Sequence[str] | None = None
    ) -> ProviderResponse:
        """Generate a response for ``prompt``.

        Blocking by design: call from a worker thread, never from the GUI
        thread.
        """

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        stream_cb: Callable[[str], None] | None = None,
    ) -> ProviderResponse:
        """Multi-turn completion with optional streamed deltas.

        ``messages`` uses ``{"role": "system"|"user"|"assistant", "content"}``.
        The default flattens the conversation onto ``generate()``;
        providers with native chat APIs override this.
        """
        if not messages:
            return self.generate("", context=None)
        *head, last = list(messages)
        prompt = last.get("content", "")
        context = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in head]
        response = self.generate(prompt, context=context or None)
        if stream_cb and response.text:
            stream_cb(response.text)
        return response
