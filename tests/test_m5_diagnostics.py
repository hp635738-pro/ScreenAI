"""Milestone 5: diagnostics export + capability probe (fail-soft, no secrets)."""

from __future__ import annotations

from pathlib import Path

from core.capabilities import Capability, CapabilityProbe
from core.diagnostics import build_report, export_report
from core.version import VERSION


def _caps() -> list[Capability]:
    return [
        Capability("screenshot", True, "mss", ""),
        Capability("ocr", False, "easyocr missing", "pip install easyocr"),
    ]


def test_report_contains_essentials() -> None:
    text = build_report(
        provider="auto",
        privacy="local_only",
        confirm_policy="required_only",
        api_key_configured=True,
        capabilities=_caps(),
        error_categories=["network"],
        plugin_errors=["broken: boom"],
        ollama_host="http://localhost:11434",
    )
    assert VERSION in text
    assert "auto" in text
    assert "local_only" in text
    assert "screenshot" in text
    assert "network" in text
    assert "broken: boom" in text
    assert "configured" in text  # key state only — never the key itself


def test_report_never_contains_secrets() -> None:
    text = build_report(
        provider="openai",
        privacy="allow_cloud",
        confirm_policy="never",
        api_key_configured=True,
        capabilities=_caps(),
        error_categories=[],
        plugin_errors=[],
        ollama_host="http://localhost:11434",
    )
    lowered = text.lower()
    assert "sk-" not in text  # no key material, ever
    assert "authorization:" not in lowered
    assert "bearer " not in lowered


def test_export_report_writes_file(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    export_report(target, "hello")
    assert target.read_text() == "hello"


def test_capability_probe_is_fail_soft() -> None:
    probe = CapabilityProbe()
    caps = probe.detect()
    names = [c.name.lower() for c in caps]
    for expected in ("display", "mouse", "keyboard", "screen", "ocr", "voice", "tray"):
        assert any(expected in name for name in names), expected
    for cap in caps:
        assert isinstance(cap.ok, bool)
        assert cap.name
        if not cap.ok:
            assert cap.hint or cap.detail  # actionable


def test_probe_accepts_injected_environment() -> None:
    probe = CapabilityProbe(env={"XDG_SESSION_TYPE": "x11"}, which=lambda _: "/usr/bin/true")
    caps = list(probe.detect())
    display = next(c for c in caps if "display" in c.name.lower())
    mouse = next(c for c in caps if "mouse" in c.name.lower())
    assert display.ok is True
    assert mouse.ok is True
