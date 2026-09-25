"""OpenAI chat-completions backend over the standard REST API.

The API key is taken from settings/environment (never hardcoded) and is
never included in errors, logs or stored results. Responses stream token
deltas when a ``stream_cb`` is supplied.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from core.providers.base import (
    AIProvider,
    ProviderError,
    ProviderNotConfigured,
    ProviderResponse,
)
from core.providers.transport import HttpTransport, TransportError


class OpenAIProvider(AIProvider):
    name = "openai"
    is_cloud = True

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        transport: HttpTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport or HttpTransport()

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        return bool(self._api_key)

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
        if not self.is_available():
            raise ProviderNotConfigured(
                "OpenAI needs an API key (Settings → AI Engine, or OPENAI_API_KEY)."
            )
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in messages
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"
        started = time.monotonic()
        try:
            if stream_cb is not None:
                payload["stream"] = True
                text = self._stream(url, payload, headers, stream_cb)
            else:
                status, body = self._transport.request_json(
                    url, payload=payload, headers=headers, timeout=self._timeout
                )
                text = self._parse_completion(status, body)
        except TransportError as exc:
            raise ProviderError(f"OpenAI API unavailable: {exc}") from exc
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

    def _parse_completion(self, status: int, body) -> str:  # noqa: ANN001
        if status in (401, 403):
            raise ProviderNotConfigured(
                "OpenAI authentication failed — check the API key."
            )
        if status == 429:
            raise ProviderError("OpenAI rate limit reached — retry shortly.")
        if status >= 500:
            raise ProviderError(f"OpenAI service error (HTTP {status}).")
        if status != 200 or not isinstance(body, dict):
            raise ProviderError(f"OpenAI request failed (HTTP {status}).")
        try:
            return body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Unexpected OpenAI response format.") from exc

    def _stream(self, url, payload, headers, stream_cb) -> str:  # noqa: ANN001
        import json

        chunks: list[str] = []
        saw_payload = False
        for line in self._transport.stream_lines(
            url, payload=payload, headers=headers, timeout=self._timeout
        ):
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            saw_payload = True
            try:
                delta = event["choices"][0]["delta"].get("content") or ""
            except (KeyError, IndexError, TypeError):
                delta = ""
            if delta:
                chunks.append(delta)
                stream_cb(delta)
        if not chunks and not saw_payload:
            raise ProviderError("OpenAI stream ended without a response.")
        return "".join(chunks)
