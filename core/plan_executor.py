"""Plan execution engine: runs parsed plans off the GUI thread.

Each plan runs inside a ``QThread`` worker and reports progress through Qt
signals (``step_started``, ``step_finished``, ``output_line``,
``plan_completed``). ``emergency_stop()`` cancels running automation
immediately and safely from any thread.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.app_launcher import AppLauncher, LauncherError
from core.automation import Automation, AutomationError
from core.config import Config
from core.models import Action, ActionResult, ActionType, Plan, PlanResult, TaskState
from core.terminal import TerminalEngine


class PlanWorker(QObject):
    step_started = Signal(int, int, str)  # index (1-based), total, description
    step_finished = Signal(object)  # ActionResult
    output_line = Signal(str)  # streamed terminal output
    plan_completed = Signal(object)  # PlanResult

    def __init__(
        self,
        plan: Plan,
        *,
        launcher: AppLauncher,
        automation: Automation,
    ) -> None:
        super().__init__()
        self._plan = plan
        self._launcher = launcher
        self._automation = automation
        self._terminal = TerminalEngine()
        self._terminal.output.connect(self._forward_output)
        self._abort = threading.Event()

    def request_stop(self) -> None:
        """Emergency stop: cancel in-flight work and skip remaining steps."""
        self._abort.set()
        self._terminal.cancel()
        self._automation.abort()

    @Slot()
    def run(self) -> None:
        self._automation.reset()
        started = time.monotonic()
        results: list[ActionResult] = []
        cancelled = False
        total = self._plan.total_steps

        for index, action in enumerate(self._plan.actions, start=1):
            if self._abort.is_set():
                cancelled = True
                break
            self.step_started.emit(index, total, action.description)
            result = self._execute_action(action)
            results.append(result)
            self.step_finished.emit(result)
            if self._abort.is_set():
                cancelled = True
                break
            if not result.success:
                break  # dependent steps make no sense after a failure

        self.plan_completed.emit(
            PlanResult(
                command=self._plan.command,
                results=results,
                cancelled=cancelled,
                duration=time.monotonic() - started,
                total=total,
            )
        )

    # ---------------------------------------------------------- execution

    def _execute_action(self, action: Action) -> ActionResult:
        started = time.monotonic()
        try:
            success, message = self._dispatch(action)
        except (LauncherError, AutomationError) as exc:
            success, message = False, str(exc)
        except Exception as exc:  # noqa: BLE001 - report anything to the UI
            success, message = False, f"{type(exc).__name__}: {exc}"
        if self._abort.is_set():
            success, message = False, "Stopped"
        return ActionResult(action, success, time.monotonic() - started, message)

    def _dispatch(self, action: Action) -> tuple[bool, str]:
        kind = action.type
        params = action.params

        if kind is ActionType.LAUNCH_APP:
            launched = self._launcher.launch(params["app"])
            return True, f"Launched {launched.display} (pid {launched.pid})"

        if kind is ActionType.RUN_TERMINAL:
            result = self._terminal.execute(params["command"])
            return result.success, result.summary

        if kind is ActionType.TYPE_TEXT:
            self._automation.type_text(params["text"])
            return True, f"Typed {len(params['text'])} characters"

        if kind is ActionType.MOVE_MOUSE:
            self._automation.move_mouse(params["x"], params["y"])
            return True, f"Mouse at ({params['x']}, {params['y']})"

        if kind is ActionType.LEFT_CLICK:
            self._automation.left_click(params.get("x"), params.get("y"))
            return True, "Left click"

        if kind is ActionType.RIGHT_CLICK:
            self._automation.right_click(params.get("x"), params.get("y"))
            return True, "Right click"

        if kind is ActionType.DOUBLE_CLICK:
            self._automation.double_click(params.get("x"), params.get("y"))
            return True, "Double click"

        if kind is ActionType.HOTKEY:
            combo = "+".join(params["keys"])
            self._automation.hotkey(combo)
            return True, f"Pressed {combo}"

        if kind is ActionType.PRESS_KEY:
            self._automation.press(params["key"])
            return True, f"Pressed {params['key']}"

        if kind is ActionType.WAIT:
            self._interruptable_sleep(params["seconds"])
            return True, f"Waited {params['seconds']:g}s"

        if kind is ActionType.SIMULATE:
            self._interruptable_sleep(Config.TASK_SIM_DURATION)
            return True, f"Simulated “{params['task']}”"

        return False, action.description  # UNKNOWN

    def _interruptable_sleep(self, seconds: float) -> None:
        deadline = seconds
        while deadline > 0 and not self._abort.is_set():
            step = min(0.05, deadline)
            time.sleep(step)
            deadline -= step

    @Slot(str, str)
    def _forward_output(self, text: str, stream: str) -> None:
        self.output_line.emit(text if stream == "stdout" else f"[err] {text}")


class PlanExecutor(QObject):
    """Owns the worker thread for one plan at a time."""

    plan_started = Signal(str)
    plan_completed = Signal(object)  # PlanResult
    step_started = Signal(int, int, str)
    step_finished = Signal(object)  # ActionResult
    output_line = Signal(str)
    state_changed = Signal(object)
    notice = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        launcher: AppLauncher | None = None,
        automation: Automation | None = None,
    ) -> None:
        super().__init__(parent)
        self._launcher = launcher or AppLauncher()
        self._automation = automation or Automation()
        self._thread: QThread | None = None
        self._worker: PlanWorker | None = None
        self._busy = False

    @property
    def is_running(self) -> bool:
        return self._busy

    @property
    def automation_backend(self) -> str:
        try:
            return self._automation.backend_name
        except AutomationError:
            return "none"

    def execute(self, plan: Plan) -> bool:
        if self._busy:
            self.notice.emit("A plan is already running.")
            return False

        self._discard_thread()

        thread = QThread()
        worker = PlanWorker(plan, launcher=self._launcher, automation=self._automation)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.step_started.connect(self.step_started)
        worker.step_finished.connect(self.step_finished)
        worker.output_line.connect(self.output_line)
        worker.plan_completed.connect(self._on_plan_completed)
        worker.plan_completed.connect(thread.quit)
        worker.plan_completed.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._thread = thread
        self._worker = worker
        self._busy = True
        self.state_changed.emit(TaskState.WORKING)
        self.plan_started.emit(plan.command)
        thread.start()
        return True

    def emergency_stop(self) -> None:
        """Immediately cancel any running automation (safe from any thread)."""
        if self._worker is not None:
            self._worker.request_stop()
            self.notice.emit("Emergency stop — cancelling…")
        else:
            self.notice.emit("Nothing is running.")

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self._discard_thread()

    @Slot(object)
    def _on_plan_completed(self, result: PlanResult) -> None:
        self._busy = False
        self.state_changed.emit(TaskState.DONE if result.success else TaskState.ERROR)
        self.plan_completed.emit(result)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._discard_thread()

    def _discard_thread(self) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        if thread is not None:
            if thread.isRunning():
                thread.quit()
                thread.wait(500)
            thread.deleteLater()
