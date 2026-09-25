"""Diagnostic report export.

Collects environment facts, capability status and recent error
categories for support. The finished text is redacted and MUST NOT
contain API keys, passwords, tokens or other credentials.
"""

from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from core.safety import redact
from core.version import APP_NAME, VERSION


def collect_error_categories(recent: list[str]) -> str:
    return ", ".join(recent) if recent else "none recorded"


def build_report(
    *,
    provider: str,
    privacy: str,
    confirm_policy: str,
    api_key_configured: bool,
    capabilities,  # noqa: ANN001 - list[Capability]
    error_categories: list[str],
    plugin_errors: list[str] | None = None,
    ollama_host: str = "",
) -> str:
    try:
        from PySide6 import QT_VERSION_STR  # noqa: PLC0415

        qt_version = QT_VERSION_STR
    except Exception:  # noqa: BLE001
        qt_version = "unavailable"

    lines = [
        f"{APP_NAME} diagnostic report",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "== Versions ==",
        f"{APP_NAME}: {VERSION}",
        f"Python: {sys.version.split()[0]} ({platform.python_implementation()})",
        f"Qt: {qt_version}",
        f"OS: {platform.platform()}",
        f"Machine: {platform.machine()}",
        "",
        "== AI configuration (no secrets) ==",
        f"Provider: {provider}",
        f"Privacy: {privacy}",
        f"Confirmation policy: {confirm_policy}",
        f"Ollama host: {ollama_host or '—'}",
        f"API key: {'configured' if api_key_configured else 'not set'}",
        "",
        "== Capabilities ==",
    ]
    for cap in capabilities:
        line = f"[{cap.status}] {cap.name}: {cap.detail}"
        if not cap.ok and cap.hint:
            line += f" (hint: {cap.hint})"
        lines.append(line)

    lines += [
        "",
        "== Recent error categories ==",
        collect_error_categories(error_categories),
    ]
    if plugin_errors:
        lines += ["", "== Plugin load errors ==", *plugin_errors]
    lines += [
        "",
        "Note: this report is passed through secret redaction before export.",
        "It contains no API keys, passwords or tokens.",
    ]
    return redact("\n".join(lines))


def export_report(path: Path, report: str) -> Path:
    path = Path(path)
    path.write_text(report, encoding="utf-8")
    return path
