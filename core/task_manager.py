"""Task lifecycle management, fully decoupled from the UI."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.models import TaskState
from core.task_worker import TaskWorker


class TaskManager(QObject):
    started = Signal(str)
    progressed = Signal(str)
    finished = Signal(str)
    failed = Signal(str)
    state_changed = Signal(object)
    notice = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: TaskWorker | None = None
        self._state = TaskState.IDLE

    @property
    def state(self) -> TaskState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state is TaskState.WORKING

    def start(self, command: str) -> bool:
        if self.is_running:
            self.notice.emit("A task is already running.")
            return False

        self._discard_thread()

        thread = QThread()
        worker = TaskWorker(command)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progressed.connect(self.progressed)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._thread = thread
        self._worker = worker
        self._set_state(TaskState.WORKING)
        self.started.emit(command)
        thread.start()
        return True

    def pause(self) -> None:
        """Placeholder: real pause/resume arrives with the AI integrations."""
        self.notice.emit("Pause is a UI placeholder in this milestone.")

    def stop(self) -> None:
        """Emergency stop: cooperatively cancel the simulated task."""
        if self._worker is not None:
            self._worker.request_stop()
            self.notice.emit("Stopping the simulated task…")
        else:
            self.notice.emit("Nothing is running.")

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self._discard_thread()

    @Slot(str)
    def _on_completed(self, result: str) -> None:
        self._set_state(TaskState.DONE)
        self.finished.emit(result)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._set_state(TaskState.ERROR)
        self.failed.emit(message)

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

    def _set_state(self, state: TaskState) -> None:
        self._state = state
        self.state_changed.emit(state)
