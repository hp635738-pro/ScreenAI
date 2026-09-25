"""Background task execution.

Milestone 1 simulates work inside a QThread so the UI stays responsive.
A real AI provider will replace the body of ``run()`` later without
changing the signal contract consumed by :class:`core.task_manager.TaskManager`.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot

from core.config import Config


class TaskWorker(QObject):
    progressed = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    _PHASES = (
        "Parsing command…",
        "Planning steps…",
        "Working on the task…",
        "Checking results…",
        "Wrapping up…",
    )

    def __init__(self, command: str, duration: float | None = None) -> None:
        super().__init__()
        self._command = command
        self._duration = Config.TASK_SIM_DURATION if duration is None else duration
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        """Ask the worker to finish early (hook for real cancellation)."""
        self._stop_event.set()

    @Slot()
    def run(self) -> None:
        try:
            phase_time = self._duration / len(self._PHASES)
            for phase in self._PHASES:
                self.progressed.emit(phase)
                if self._interruptable_sleep(phase_time):
                    self.completed.emit("Execution was interrupted before finishing.")
                    return
            self.completed.emit(f'Simulated execution finished for: "{self._command}"')
        except Exception as exc:  # noqa: BLE001 - report any failure to the UI
            self.failed.emit(str(exc))

    def _interruptable_sleep(self, seconds: float) -> bool:
        """Sleep in short slices so stop requests stay responsive.

        Returns True when a stop was requested during the wait.
        """
        remaining = seconds
        while remaining > 0:
            if self._stop_event.wait(min(0.05, remaining)):
                return True
            remaining -= 0.05
        return False
