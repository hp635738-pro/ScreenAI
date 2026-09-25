"""Abstract provider interface for future AI backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
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
