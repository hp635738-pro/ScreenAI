"""Pytest bootstrap: headless Qt, temp data dir, repo root on sys.path."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="screenai-tests-"))
os.environ["SCREENAI_DATA_DIR"] = str(_TMP)
for var in ("OPENAI_API_KEY", "OPENAI_MODEL", "SCREENAI_AI_PROVIDER", "SCREENAI_AI_PRIVACY"):
    os.environ.pop(var, None)

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def data_dir():
    return _TMP


@pytest.fixture()
def safety():
    from core.safety import SafetyManager

    return SafetyManager()


@pytest.fixture()
def registry_ctx():
    from core.safety import SafetyManager
    from core.tools.standard import build_standard_registry
    from tests.fakes import (
        FakeLauncher,
        FakeTerminal,
        FakeWorkflowService,
    )

    from core.automation import Automation
    from core.ocr import OcrEngine
    from core.vision import VisionEngine
    from tests.fakes import FakeBackend, FakeReader, FakeSct

    ctx_services = {
        "launcher": FakeLauncher(),
        "automation": Automation(backend=FakeBackend()),
        "terminal": FakeTerminal(),
        "vision": VisionEngine(sct_factory=FakeSct, window_geometry_fn=lambda: (0, 0, 8, 6)),
        "ocr": OcrEngine(reader=FakeReader()),
        "safety": SafetyManager(),
        "workflows": FakeWorkflowService(),
    }
    registry = build_standard_registry(_ctx(ctx_services))
    return registry, ctx_services


def _ctx(services: dict):  # noqa: ANN202
    from core.tools.standard import ToolContext

    return ToolContext(**services)
