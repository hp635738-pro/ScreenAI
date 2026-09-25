"""Milestone 1–3 regression: legacy behaviour stays intact."""

from __future__ import annotations

import importlib


def test_all_m1_m3_modules_import():
    for name in (
        "core.config",
        "core.models",
        "core.task_manager",
        "core.task_worker",
        "core.voice_service",
        "core.app_launcher",
        "core.intent_parser",
        "core.terminal",
        "core.automation",
        "core.plan_executor",
        "core.vision",
        "core.ocr",
        "core.learn_mode",
        "core.workflow_player",
        "core.controller",
        "database.db_manager",
        "database.task_repository",
        "database.action_repository",
        "database.workflow_repository",
        "ui.theme",
        "ui.widgets",
        "ui.popup",
        "ui.learn_page",
        "ui.main_window",
    ):
        importlib.import_module(name)


def test_intent_parser_m2_grammar():
    from core.app_launcher import AppLauncher
    from core.intent_parser import IntentParser
    from core.models import ActionType

    parser = IntentParser(
        known_apps=AppLauncher.known_names, display_name=AppLauncher.display_name
    )
    plan = parser.parse("open firefox")
    assert plan.actions[0].type is ActionType.LAUNCH_APP
    plan = parser.parse("run ls -la")
    assert plan.actions[0].type is ActionType.RUN_TERMINAL
    plan = parser.parse("press ctrl+c")
    assert plan.actions[0].type is ActionType.HOTKEY
    plan = parser.parse("press enter")
    assert plan.actions[0].type is ActionType.PRESS_KEY


def test_m3_recorder_still_records():
    from core.learn_mode import WorkflowRecorder

    class Listener:
        def __init__(self) -> None:
            self.started = self.stopped = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    listeners = []

    def factory(on_click, on_press, on_release):  # noqa: ANN001, ANN202
        pair = (Listener(), Listener())
        listeners.append(pair)
        return pair

    class Button:
        name = "left"

    recorder = WorkflowRecorder(
        listeners_factory=factory, window_title_fn=lambda: "Test"
    )
    assert recorder.start()
    recorder.on_click(12, 34, Button(), True)
    steps = recorder.stop()
    assert len(steps) == 1
    assert steps[0].coordinates == (12, 34)


def test_m3_vision_and_ocr_still_work():
    from core.ocr import OcrEngine
    from core.vision import VisionEngine, MODE_DESKTOP
    from tests.fakes import FakeReader, FakeSct

    vision = VisionEngine(
        sct_factory=FakeSct, window_geometry_fn=lambda: (0, 0, 8, 6)
    )
    frame = vision.grab()
    assert frame.mode == MODE_DESKTOP
    assert frame.pil_image.size == (8, 6)

    ocr = OcrEngine(reader=FakeReader(), vision=vision)
    hit = ocr.find_text("Export")
    assert hit is not None and hit.text == "Export"


def test_popup_m3_displays_intact(qapp):
    from ui.popup import ExecutionPopup

    popup = ExecutionPopup()
    popup.begin_recording()
    assert popup._task_label.text() == "Recording…"
    popup.update_recording(4, "Click File")
    assert popup._step_label.text() == "Step 4"
    assert popup._progress_label.text() == "Click File"

    popup.begin_playback("App: Task", 9)
    assert popup._task_label.text() == "Playing…"
    popup.update_playback(6, 9, "Found Export")
    assert popup._step_label.text() == "Step 6/9"
    assert popup._progress_label.text() == "Found Export"


def test_learn_page_widgets_intact(qapp):
    from ui.learn_page import LearnPage

    page = LearnPage()
    assert page._record_button.text() == "Start Recording"
    assert page._stop_button.text() == "Stop"
    assert page._save_button.text() == "Save Workflow"
    assert hasattr(page, "_app_input") and hasattr(page, "_task_input")


def test_automation_key_aliases_m2():
    from core.automation import Automation
    from tests.fakes import FakeBackend

    backend = FakeBackend()
    automation = Automation(backend=backend)
    automation.press("control")
    automation.press("Return")
    assert ("press", "ctrl") in backend.calls
    assert ("press", "enter") in backend.calls


def test_pause_still_placeholder(qapp):
    from core.controller import ApplicationController
    from tests.fakes import FakeBackend, FakeReader, FakeSct

    controller = ApplicationController()
    controller._automation._backend = FakeBackend()
    controller._vision._sct_factory = FakeSct
    controller._vision._window_geometry_fn = lambda: (0, 0, 8, 6)
    controller._ocr._reader = FakeReader()
    notices: list[str] = []
    controller._window.show_notice = notices.append  # capture
    controller._on_pause_requested()
    assert any("placeholder" in n for n in notices)
    controller.shutdown()
