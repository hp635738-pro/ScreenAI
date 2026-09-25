"""Ollama backend — talks to a locally running Ollama instance.

Host and model are configurable; availability is probed over HTTP. When
Ollama is unreachable the provider raises a clear ``ProviderError`` so the
caller can decide (fall back, ask the user, or stop).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence

from core.providers.base import AIProvider, ProviderError, ProviderResponse
from core.providers.transport import HttpTransport, TransportError


class OllamaProvider(AIProvider):
    name = "ollama"
    is_cloud = False

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: float = 120.0,
        probe_timeout: float = 2.0,
        transport: HttpTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._probe_timeout = probe_timeout
        self._transport = transport or HttpTransport()

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def is_available(self) -> bool:
        try:
            status, _ = self._transport.request_json(
                f"{self._base_url}/api/tags",
                method="GET",
                timeout=self._probe_timeout,
            )
            return status == 200
        except TransportError:
            return False

    def models(self) -> list[str]:
        """Model names served by the instance (for the settings UI)."""
        try:
            status, body = self._transport.request_json(
                f"{self._base_url}/api/tags",
                method="GET",
                timeout=self._probe_timeout,
            )
        except TransportError as exc:
            raise ProviderError(self._unavailable_message(exc)) from exc
        if status != 200 or not isinstance(body, dict):
            raise ProviderError(self._unavailable_message(f"HTTP {status}"))
        names = [m.get("name") for m in body.get("models", []) if m.get("name")]
        return sorted(names)

    def generate(
        self, prompt: str, *, context: Sequence[str] | None = None
    ) -> ProviderResponse:
        messages = [{"role": "user", "content": line} for line in (context or [])]
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        stream_cb: Callable[[str], None] | None = None,
    ) -> ProviderResponse:
        payload = {
            "model": self._model,
            "messages": [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in messages
            ],
            "stream": stream_cb is not None,
        }
        url = f"{self._base_url}/api/chat"
        started = time.monotonic()
        try:
            if stream_cb is not None:
                text = self._stream(url, payload, stream_cb)
            else:
                status, body = self._transport.request_json(
                    url, payload=payload, timeout=self._timeout
                )
                text = self._parse_completion(status, body)
        except TransportError as exc:
            raise ProviderError(self._unavailable_message(exc)) from exc
        return ProviderResponse(
            text=text,
            provider=self.name,
            model=self._model,
            metadata={
                "duration": round(time.monotonic() - started, 3),
                "streamed": stream_cb is not None,
            },
        )

    # ------------------------------------------------------------ internal

    def _unavailable_message(self, detail: object = "") -> str:
        base = f"Ollama is not available at {self._base_url} (start it with `ollama serve`)"
        return f"{base}: {detail}" if detail else base

    def _parse_completion(self, status: int, body) -> str:  # noqa: ANN001
        if status != 200 or not isinstance(body, dict):
            raise ProviderError(self._unavailable_message(f"HTTP {status}"))
        message = body.get("message") or {}
        return message.get("content") or ""

    def _stream(self, url, payload, stream_cb) -> str:  # noqa: ANN001
        chunks: list[str] = []
        saw_payload = False
        for line in self._transport.stream_lines(
            url, payload=payload, timeout=self._timeout
        ):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            saw_payload = True
            delta = (event.get("message") or {}).get("content") or ""
            if delta:
                chunks.append(delta)
                stream_cb(delta)
            if event.get("done"):
                break
        if not chunks and not saw_payload:
            raise ProviderError(self._unavailable_message("empty stream"))
        return "".join(chunks)
