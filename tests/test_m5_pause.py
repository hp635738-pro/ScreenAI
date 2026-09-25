"""Milestone 5: real pause/resume + stop coverage (fully mocked)."""

from __future__ import annotations

import json
import threading
import time

from core.controller import ApplicationController
from core.safety import SafetyLevel
from core.tools import Tool, ToolResult, ToolSpec
from tests.fakes import FakeBackend, FakeReader, FakeSct, ScriptedProvider


class SlowMoveTool(Tool):
    def __init__(self, gate) -> None:  # noqa: ANN001
        self.spec = ToolSpec(
            "slow_move",
            "Move with a gate",
            {"type": "object", "properties": {}},
            SafetyLevel.SAFE,
        )
        self.gate = gate
        self.runs = 0

    def execute(self, arguments: dict) -> ToolResult:
        self.runs += 1
        self.gate.wait(2.0)
        return ToolResult(True, "moved", display="moved")


def _controller(qapp):  # noqa: ANN001, ANN202
    controller = ApplicationController()
    controller._automation._backend = FakeBackend()
    controller._vision._sct_factory = lambda: FakeSct()
    controller._vision._window_geometry_fn = lambda *_: (0, 0, 640, 480)
    controller._ocr._reader = FakeReader()
    return controller


def test_pause_idle_notice_and_toggle(qapp) -> None:  # noqa: ANN001, ANN202
    controller = _controller(qapp)
    try:
        notices: list[str] = []
        controller._window.show_notice = notices.append
        controller._on_pause_requested()
        assert any("No running task to pause" in n for n in notices)
        assert controller._agent.is_paused is False
    finally:
        controller.shutdown()


def test_pause_and_resume_api_and_signal(qapp) -> None:  # noqa: ANN001, ANN202
    controller = _controller(qapp)
    try:
        flags: list[bool] = []
        controller._agent.paused.connect(flags.append)
        controller._agent._running = True  # seam: pretend a run is active
        controller._agent.pause()
        assert controller._agent.is_paused is True
        controller._agent.pause()  # idempotent
        controller._agent.resume()
        assert controller._agent.is_paused is False
        controller._agent.resume()  # idempotent
        assert flags == [True, False]
    finally:
        controller.shutdown()


def test_cancel_clears_pause(qapp) -> None:  # noqa: ANN001, ANN202
    controller = _controller(qapp)
    try:
        controller._agent._running = True
        controller._agent.pause()
        assert controller._agent.is_paused is True
        controller._agent.cancel()
        assert controller._agent.is_paused is False
    finally:
        controller.shutdown()


def test_pause_blocks_new_steps_until_resume(qapp) -> None:  # noqa: ANN001, ANN202
    controller = _controller(qapp)
    gate = threading.Event()
    tool = SlowMoveTool(gate)
    plan_step = json.dumps({"thought": "go", "tool": "slow_move", "arguments": {}})
    plan_done = json.dumps({"thought": "done", "final": "done"})
    try:
        controller._agent._provider_factory = lambda: ScriptedProvider(
            [plan_step, plan_step, plan_done]
        )
        controller._agent._tool_hook = lambda registry: registry.register(tool)

        controller._window.run_requested.emit("move twice")
        time.sleep(0.15)  # first tool starts and blocks on the gate
        controller._on_pause_requested()  # pause while the first step runs
        assert controller._agent.is_paused is True
        gate.set()  # first step may finish; no new step may start while paused
        time.sleep(0.3)
        assert tool.runs == 1, f"paused agent started a new action ({tool.runs})"

        controller._agent.resume()
        deadline = time.monotonic() + 5.0
        while controller._agent.is_running and time.monotonic() < deadline:
            time.sleep(0.02)
        assert tool.runs == 2
    finally:
        gate.set()
        controller._agent.cancel()
        controller.shutdown()
