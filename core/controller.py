"""Application controller: wires UI, task execution and persistence.

This is the only place that knows about both sides; windows and services
stay independent and communicate through signals and slots.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Slot

from core.models import TaskState
from core.task_manager import TaskManager
from core.voice_service import VoiceService
from database.db_manager import DatabaseManager
from database.task_repository import TaskRepository
from ui.main_window import MainWindow
from ui.popup import ExecutionPopup


class ApplicationController(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._window = MainWindow()
        self._popup = ExecutionPopup()
        self._tasks = TaskManager(self)
        self._voice = VoiceService(self)
        self._db = DatabaseManager()
        self._repository = TaskRepository(self._db)
        self._current_run_id: int | None = None

        self._wire()

    # ------------------------------------------------------------- wiring

    def _wire(self) -> None:
        window = self._window
        window.run_requested.connect(self._on_run_requested)
        window.voice_requested.connect(self._voice.start_listening)
        self._voice.notice.connect(window.show_notice)

        popup = self._popup
        popup.pause_requested.connect(self._tasks.pause)
        popup.stop_requested.connect(self._tasks.stop)
        popup.restore_requested.connect(self._on_restore_requested)
        popup.dismiss_requested.connect(self._on_dismiss_requested)

        tasks = self._tasks
        tasks.progressed.connect(self._on_progress)
        tasks.finished.connect(self._on_task_finished)
        tasks.failed.connect(self._on_task_failed)
        tasks.notice.connect(self._on_task_notice)

    # ---------------------------------------------------------- lifecycle

    def start(self) -> None:
        self._window.set_state(TaskState.IDLE)
        self._window.show()

    def shutdown(self) -> None:
        self._window.save_geometry()
        self._tasks.shutdown()
        self._db.close()

    # -------------------------------------------------------------- slots

    @Slot(str)
    def _on_run_requested(self, command: str) -> None:
        command = command.strip()
        if not command:
            self._window.show_notice("Enter a command before running.")
            return
        if self._tasks.is_running:
            self._window.show_notice("A task is already running.")
            return

        self._current_run_id = self._repository.create_run(command)
        self._window.set_state(TaskState.WORKING)
        self._window.minimize()
        self._popup.begin_task(command)
        self._popup.show_popup()
        self._tasks.start(command)

    @Slot()
    def _on_restore_requested(self) -> None:
        self._window.restore()

    @Slot()
    def _on_dismiss_requested(self) -> None:
        self._popup.hide()

    @Slot(str)
    def _on_progress(self, text: str) -> None:
        self._popup.set_progress(text)

    @Slot(str)
    def _on_task_finished(self, result: str) -> None:
        self._finish_run(TaskState.DONE, result)
        self._window.set_state(TaskState.DONE)
        self._window.show_notice(result)
        self._popup.set_state(TaskState.DONE)
        self._popup.set_progress("Completed")

    @Slot(str)
    def _on_task_failed(self, message: str) -> None:
        self._finish_run(TaskState.ERROR, message)
        self._window.set_state(TaskState.ERROR)
        self._window.show_notice(f"Error: {message}")
        self._popup.set_state(TaskState.ERROR)
        self._popup.set_progress("Failed")

    @Slot(str)
    def _on_task_notice(self, text: str) -> None:
        self._popup.show_notice(text)
        self._window.show_notice(text)

    def _finish_run(self, state: TaskState, result: str) -> None:
        if self._current_run_id is not None:
            self._repository.finish_run(self._current_run_id, state, result)
            self._current_run_id = None
