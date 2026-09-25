"""Workflow player: replays saved workflows with OCR-first targeting.

Rules (per step):
- prefer finding the target with OCR text (``Found Export``);
- if text lookup fails, fall back to the saved coordinates;
- retry a failing step twice before failing the playback;
- emit progress signals for the popup throughout.

Playback runs in a QThread worker — the GUI never blocks.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.automation import Automation, AutomationError
from core.models import ActionType, LearnedStep, Workflow
from core.ocr import OcrEngine, OcrError
from core.vision import VisionEngine, VisionError

MAX_ATTEMPTS = 3  # 1 try + 2 retries
STEP_SETTLE_S = 0.15
RETRY_DELAY_S = 0.4
MAX_STEP_DELAY_S = 10.0

_CLICK_ACTIONS = (ActionType.LEFT_CLICK, ActionType.RIGHT_CLICK, ActionType.DOUBLE_CLICK)


@dataclass(slots=True)
class StepPlaybackResult:
    step: LearnedStep
    success: bool
    message: str = ""


@dataclass(slots=True)
class PlaybackResult:
    workflow: Workflow
    results: list[StepPlaybackResult] = field(default_factory=list)
    cancelled: bool = False
    duration: float = 0.0

    @property
    def success(self) -> bool:
        total = len(self.workflow.steps)
        return (
            not self.cancelled
            and total > 0
            and len(self.results) == total
            and all(r.success for r in self.results)
        )

    @property
    def summary(self) -> str:
        done = sum(1 for r in self.results if r.success)
        total = len(self.workflow.steps)
        if self.cancelled:
            return f"Stopped after {done}/{total} steps"
        return f"{done}/{total} steps played"

    @property
    def first_error(self) -> str | None:
        for result in self.results:
            if not result.success:
                return result.message or result.step.description
        return None


class PlaybackWorker(QObject):
    step_started = Signal(int, int, str)  # index (1-based), total, description
    progress = Signal(str)  # "Found Export", "Using saved position…", "Retry …"
    step_finished = Signal(object)  # StepPlaybackResult
    playback_completed = Signal(object)  # PlaybackResult

    def __init__(
        self,
        workflow: Workflow,
        *,
        vision: VisionEngine,
        ocr: OcrEngine,
        automation: Automation,
    ) -> None:
        super().__init__()
        self._workflow = workflow
        self._vision = vision
        self._ocr = ocr
        self._automation = automation
        self._abort = threading.Event()

    def request_stop(self) -> None:
        self._abort.set()
        self._automation.abort()

    @Slot()
    def run(self) -> None:
        self._automation.reset()
        started = time.monotonic()
        results: list[StepPlaybackResult] = []
        cancelled = False
        steps = self._workflow.steps
        total = len(steps)

        for index, step in enumerate(steps, start=1):
            if self._abort.is_set():
                cancelled = True
                break
            self.step_started.emit(index, total, step.description)
            if step.delay > 0 and self._sleep(min(step.delay, MAX_STEP_DELAY_S)):
                cancelled = True
                break
            success, message = self._execute_step(step)
            results.append(StepPlaybackResult(step, success, message))
            self.step_finished.emit(results[-1])
            if self._abort.is_set():
                cancelled = True
                break
            if not success:
                break
            self._sleep(STEP_SETTLE_S)

        self.playback_completed.emit(
            PlaybackResult(self._workflow, results, cancelled, time.monotonic() - started)
        )

    # ------------------------------------------------------- execution

    def _execute_step(self, step: LearnedStep) -> tuple[bool, str]:
        message = "Step failed"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self._abort.is_set():
                return False, "Stopped"
            try:
                success, message = self._attempt(step)
            except (AutomationError, OcrError, VisionError) as exc:
                success, message = False, str(exc)
            if success:
                return True, message
            if attempt < MAX_ATTEMPTS:
                self.progress.emit(f"Retry {attempt}/2 — {step.description}")
                if self._sleep(RETRY_DELAY_S):
                    return False, "Stopped"
        return False, message

    def _attempt(self, step: LearnedStep) -> tuple[bool, str]:
        action = step.action

        if action in _CLICK_ACTIONS:
            point = None
            if step.target_text:
                frame = self._vision.grab()
                detection = self._ocr.find_text(step.target_text, frame.pil_image)
                if detection is not None:
                    point = detection.center
                    self.progress.emit(f"Found {step.target_text}")
            if point is None:
                if step.coordinates is None:
                    target = step.target_text or "target"
                    return False, f"“{target}” not found and no saved coordinates"
                point = step.coordinates
                self.progress.emit(f"Using saved position for {step.description}")
            x, y = point
            if action is ActionType.DOUBLE_CLICK:
                self._automation.double_click(x, y)
            elif action is ActionType.RIGHT_CLICK:
                self._automation.right_click(x, y)
            else:
                self._automation.left_click(x, y)
            return True, f"Clicked at ({x}, {y})"

        if action is ActionType.TYPE_TEXT:
            self._automation.type_text(step.target_text or "")
            return True, "Typed text"

        if action is ActionType.HOTKEY:
            self._automation.hotkey(step.target_text or "")
            return True, f"Pressed {step.target_text}"

        if action is ActionType.PRESS_KEY:
            self._automation.press(step.target_text or "")
            return True, f"Pressed {step.target_text}"

        return False, f"Unsupported action {action.value}"

    def _sleep(self, seconds: float) -> bool:
        """Interruptible sleep; returns True when stopped."""
        deadline = seconds
        while deadline > 0:
            if self._abort.wait(min(0.05, deadline)):
                return True
            deadline -= 0.05
        return self._abort.is_set()


class WorkflowPlayer(QObject):
    """Owns the playback thread for one workflow at a time."""

    step_started = Signal(int, int, str)
    progress = Signal(str)
    step_finished = Signal(object)
    playback_completed = Signal(object)
    notice = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        vision: VisionEngine,
        ocr: OcrEngine,
        automation: Automation,
    ) -> None:
        super().__init__(parent)
        self._vision = vision
        self._ocr = ocr
        self._automation = automation
        self._thread: QThread | None = None
        self._worker: PlaybackWorker | None = None
        self._busy = False

    @property
    def is_running(self) -> bool:
        return self._busy

    def play(self, workflow: Workflow) -> bool:
        if self._busy:
            self.notice.emit("A workflow is already playing.")
            return False
        if not workflow.steps:
            self.notice.emit("Workflow has no steps.")
            return False

        self._discard_thread()

        thread = QThread()
        worker = PlaybackWorker(
            workflow, vision=self._vision, ocr=self._ocr, automation=self._automation
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.step_started.connect(self.step_started)
        worker.progress.connect(self.progress)
        worker.step_finished.connect(self.step_finished)
        worker.playback_completed.connect(self._on_playback_completed)
        worker.playback_completed.connect(thread.quit)
        worker.playback_completed.connect(worker.deleteLater)
        thread.finished.connect(lambda t=thread: self._on_thread_finished(t))

        self._thread = thread
        self._worker = worker
        self._busy = True
        thread.start()
        return True

    def stop(self) -> None:
        """Emergency stop for playback (safe from any thread)."""
        if self._worker is not None:
            self._worker.request_stop()
            self.notice.emit("Stopping playback…")
        else:
            self.notice.emit("Nothing is playing.")

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self._discard_thread()

    @Slot(object)
    def _on_playback_completed(self, result: PlaybackResult) -> None:
        self._busy = False
        self.playback_completed.emit(result)

    def _on_thread_finished(self, thread: QThread) -> None:
        """Only reap the generation that just finished (restart-safe)."""
        if thread is self._thread:
            self._discard_thread()
        else:
            thread.deleteLater()

    def _discard_thread(self) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        if thread is not None:
            if thread.isRunning():
                thread.quit()
                thread.wait(500)
            if not thread.isRunning():
                thread.deleteLater()
