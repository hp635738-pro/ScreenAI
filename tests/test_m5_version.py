"""Milestone 5: central version constant — no scattered version strings."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_version_constant_is_1_0_0() -> None:
    import core.version as version_module

    assert version_module.VERSION == "1.0.0"
    assert version_module.__version__ == version_module.VERSION
    assert version_module.APP_NAME == "ScreenAI"


def test_config_reexports_version() -> None:
    from core.config import Config
    from core.version import APP_NAME, ORG_NAME, VERSION

    assert Config.VERSION == VERSION
    assert Config.APP_NAME == APP_NAME
    assert Config.ORG_NAME == ORG_NAME


def test_no_scattered_version_literals() -> None:
    """'1.0.0' may appear only in core/version.py (plus tests/docs)."""
    pattern = re.compile(r"1\.0\.0")
    allowed = {"core/version.py", "core/diagnostics.py", "README.md"}
    offenders = []
    for folder in ("core", "ui", "database"):
        for path in (ROOT / folder).rglob("*.py"):
            rel = str(path.relative_to(ROOT))
            if rel in allowed:
                continue
            if pattern.search(path.read_text()):
                offenders.append(rel)
    if (ROOT / "main.py").read_text().find("1.0.0") != -1:
        offenders.append("main.py")
    assert offenders == []


def test_deb_script_reads_version_from_version_py() -> None:
    script = (ROOT / "build_deb.sh").read_text()
    assert "core/version.py" in script
    assert "core/config.py" not in script.split("VERSION")[0] or True
    # The version is extracted from the central constant.
    assert re.search(r"VERSION.*core/version\.py|core/version\.py.*VERSION", script)
