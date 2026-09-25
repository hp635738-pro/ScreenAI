"""Shared test configuration: offscreen Qt, isolated data dir, crash-avoidance."""

from __future__ import annotations

# Pre-import C-extension GUI/shm libraries BEFORE any Qt object exists.
# Importing mss mid-suite can trigger a GC pass that hard-crashes inside
# shiboken/PySide6 wrappers — pull it in while the heap is still clean and
# freeze old objects so later GC passes never traverse them.
import gc

try:
    import mss  # noqa: F401
except Exception:  # noqa: BLE001
    mss = None

gc.freeze()
# Automatic cycle-collection traverses live PySide6 wrappers and hard-crashes
# inside shiboken in this headless/stubbed-GL environment (seen as
# "Garbage-collecting" segfaults). Tests are short-lived and the session exits
# via os._exit — run them with the GC disabled.
gc.disable()

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


_EXIT_STATUS = 0


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001
    global _EXIT_STATUS
    _EXIT_STATUS = exitstatus


def _patch_terminal_reporter() -> None:
    """Exit only AFTER the final "N passed / M failed" stats line prints.

    PySide6 teardown hard-crashes this interpreter at shutdown (stubbed GL
    in CI); os._exit once reporting is fully done avoids the crash window.
    """
    import os as _os
    import sys as _sys

    from _pytest.terminal import TerminalReporter

    original = TerminalReporter.summary_stats

    def summary_stats_then_exit(self, *args, **kwargs):  # noqa: ANN001, ANN202
        result = original(self, *args, **kwargs)
        _sys.stdout.flush()
        _sys.stderr.flush()
        _os._exit(_EXIT_STATUS)
        return result  # pragma: no cover

    TerminalReporter.summary_stats = summary_stats_then_exit


_patch_terminal_reporter()
