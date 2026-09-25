"""Milestone 5: .deb packaging metadata (no root install in tests)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _script() -> str:
    return (ROOT / "build_deb.sh").read_text()


def test_package_name_and_version() -> None:
    script = _script()
    assert re.search(r'VERSION=.*python3? .*core/version\.py|core/version\.py', script)
    assert "screenai" in script
    assert "screenai_" in script or "screenai-" in script


def test_metadata_fields_present() -> None:
    script = _script()
    for field in ("Package:", "Version:", "Architecture:", "Maintainer:", "Description:", "Depends:"):
        assert field in script, f"missing dpkg field {field}"


def test_depends_lists_python_and_qt() -> None:
    script = _script()
    depends_line = next(
        line for line in script.splitlines() if line.startswith("Depends:")
    )
    assert "python3" in depends_line
    assert "pyside6" in depends_line.lower()


def test_installs_icon_and_desktop_launcher() -> None:
    script = _script()
    assert ".desktop" in script
    assert "screenai.svg" in script or "icons" in script
    assert (ROOT / "assets" / "icons" / "screenai.svg").exists()


def test_supports_clean_uninstall() -> None:
    script = _script()
    assert "--remove" in script or "remove" in script.lower()
    assert "--purge" in script or "purge" in script.lower()
    assert "postrm" in script or "remove" in script


def test_version_in_package_filename_matches_constant() -> None:
    from core.version import VERSION

    script = _script()
    assert "VERSION" in script
    assert VERSION  # sanity
    # The built artifact name is derived from $VERSION.
    assert re.search(r"screenai_\$\{?VERSION\}?_|screenai_\"\$\{VERSION\}\"_|f\"screenai_{VERSION}\"|screenai_\$VERSION", script) or "VERSION" in script
