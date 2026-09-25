"""Provider registry — the single entry point for AI backends."""

from __future__ import annotations

from core.providers.auto_provider import AutoProvider
from core.providers.base import (
    AIProvider,
    ProviderError,
    ProviderNotConfigured,
    ProviderResponse,
)
from core.providers.ollama_provider import OllamaProvider
from core.providers.openai_provider import OpenAIProvider

_REGISTRY: dict[str, type[AIProvider]] = {
    OpenAIProvider.name: OpenAIProvider,
    OllamaProvider.name: OllamaProvider,
    AutoProvider.name: AutoProvider,
}

__all__ = [
    "AIProvider",
    "ProviderError",
    "ProviderNotConfigured",
    "ProviderResponse",
    "AutoProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "available_providers",
    "create_provider",
]


def available_providers() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def create_provider(name: str, **kwargs: object) -> AIProvider:
    try:
        provider_cls = _REGISTRY[name.lower()]
    except KeyError as exc:
        raise ProviderError(
            f"Unknown provider '{name}'. Known: {', '.join(available_providers())}"
        ) from exc
    return provider_cls(**kwargs)  # type: ignore[arg-type]
