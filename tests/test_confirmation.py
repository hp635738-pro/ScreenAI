"""Confirmation flow: popup buttons + full ApplicationController round-trip."""

from __future__ import annotations

import time

from tests.fakes import ScriptedProvider


def _pump(app, predicate, timeout=8.0):  # noqa: ANN001, ANN202
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            app.processEvents()
            return True
        time.sleep(0.02)
    app.processEvents()
    return predicate()


def test_popup_agent_displays_and_confirmation_buttons(qapp):
    from ui.popup import ExecutionPopup

    popup = ExecutionPopup()
    popup.begin_agent("Order this product.")
    assert popup._task_label.text() == "ScreenAI"
    assert popup._progress_label.text() == "Understanding request…"

    popup.update_agent("Inspecting screen")
    assert popup._progress_label.text() == "Inspecting screen"

    popup.update_agent("Found Export")
    popup.show_confirmation("Order requires confirmation.")
    assert popup._progress_label.text() == "Waiting for confirmation"
    assert popup._confirm_button.isVisible() or not popup.isVisible()  # hidden parent
    assert not popup._confirm_button.isHidden()
    assert not popup._decline_button.isHidden()
    assert popup._confirm_label.text() == "Order requires confirmation."

    answers: list[bool] = []
    popup.confirmation_responded.connect(answers.append)
    popup._confirm_button.click()
    assert answers == [True]
    assert popup._confirm_button.isHidden()

    popup.show_confirmation("Send the message?")
    popup._decline_button.click()
    assert answers == [True, False]


def test_controller_confirm_flow_approve(qapp, monkeypatch):
    from core.controller import ApplicationController

    from tests.fakes import FakeBackend, FakeReader, FakeSct

    controller = ApplicationController()
    monkeypatch.setattr(
        controller._agent, "_provider_factory",
        lambda: ScriptedProvider([
            '{"tool": "type_text", "arguments": {"text": "buy now"},'
            ' "confirm_reason": "placing an order"}',
            '{"final": "Product ordered."}',
        ]),
    )
    controller._automation._backend = FakeBackend()
    controller._vision._sct_factory = FakeSct
    controller._vision._window_geometry_fn = lambda: (0, 0, 8, 6)
    controller._ocr._reader = FakeReader()
    controller.start()

    confirms: list[str] = []
    controller._agent.confirmation_required.connect(confirms.append)
    controller._window.run_requested.emit("Order this product.")

    assert _pump(qapp, lambda: confirms)
    assert controller._popup._progress_label.text() == "Waiting for confirmation"
    controller._popup._confirm_button.click()
    assert _pump(qapp, lambda: not controller._agent.is_running)
    qapp.processEvents()

    assert controller._popup._progress_label.text() == "Task completed"
    assert ("type", "buy now") in controller._automation._backend.calls
    rows = controller._action_repository.recent(20)
    assert any(r.action.startswith("agent ·") for r in rows)
    controller.shutdown()


def test_controller_confirm_flow_decline(qapp, monkeypatch):
    from core.controller import ApplicationController

    from tests.fakes import FakeBackend, FakeReader, FakeSct

    controller = ApplicationController()
    monkeypatch.setattr(
        controller._agent, "_provider_factory",
        lambda: ScriptedProvider([
            '{"tool": "mouse_click", "arguments": {"x": 9, "y": 9},'
            ' "confirm_reason": "submitting the checkout form"}',
            '{"tool": "mouse_click", "arguments": {"x": 9, "y": 9}}',
            '{"final": "retrying another way"}',
        ]),
    )
    backend = FakeBackend()
    controller._automation._backend = backend
    controller._vision._sct_factory = FakeSct
    controller._vision._window_geometry_fn = lambda: (0, 0, 8, 6)
    controller._ocr._reader = FakeReader()
    controller.start()

    controller._window.run_requested.emit("Order this product.")
    assert _pump(qapp, lambda: controller._popup._progress_label.text()
                 == "Waiting for confirmation")
    controller._popup._decline_button.click()
    assert _pump(qapp, lambda: not controller._agent.is_running)
    qapp.processEvents()

    assert controller._popup._progress_label.text() == "Failed"
    assert backend.calls == []  # declined AND no alternate attempt
    controller.shutdown()


def test_controller_stop_cancels_agent(qapp, monkeypatch):
    from core.controller import ApplicationController

    from tests.fakes import FakeBackend, FakeReader, FakeSct

    controller = ApplicationController()
    slow = ScriptedProvider([])
    slow.responses = []  # chat would block? use a confirm-hang instead
    monkeypatch.setattr(
        controller._agent, "_provider_factory",
        lambda: ScriptedProvider([
            '{"tool": "type_text", "arguments": {"text": "x"},'
            ' "confirm_reason": "external message"}',
            '{"final": "never"}',
        ]),
    )
    controller._automation._backend = FakeBackend()
    controller._vision._sct_factory = FakeSct
    controller._vision._window_geometry_fn = lambda: (0, 0, 8, 6)
    controller._ocr._reader = FakeReader()
    controller.start()

    controller._window.run_requested.emit("Send it")
    assert _pump(qapp, lambda: controller._popup._progress_label.text()
                 == "Waiting for confirmation")
    controller._window.stop_requested.emit()
    assert _pump(qapp, lambda: not controller._agent.is_running)
    qapp.processEvents()
    assert controller._popup._progress_label.text() == "Stopped"
    controller.shutdown()
