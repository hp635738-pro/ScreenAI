"""Injectable JSON/HTTP transport used by the AI providers.

The default implementation uses stdlib ``urllib`` (no extra dependency).
Tests inject fakes, so provider suites never require network access.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any


class TransportError(RuntimeError):
    """Network-level failure (DNS, refused, timeout …)."""


class HttpTransport:
    """Small HTTP client: JSON requests plus line-oriented streaming."""

    def request_json(
        self,
        url: str,
        *,
        method: str = "POST",
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> tuple[int, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            url, data=data, method=method, headers=dict(headers or {})
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            status = exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(str(exc)) from exc
        try:
            return status, json.loads(body) if body else None
        except ValueError:
            return status, body

    def stream_lines(
        self,
        url: str,
        *,
        method: str = "POST",
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> Iterator[str]:
        """Yield response lines as they arrive (SSE or NDJSON)."""
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            url, data=data, method=method, headers=dict(headers or {})
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                for raw in response:  # line-buffered iteration
                    line = raw.decode("utf-8", "replace").strip()
                    if line:
                        yield line
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise TransportError(f"HTTP {exc.code}: {body[:200]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(str(exc)) from exc
