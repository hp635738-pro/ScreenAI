"""Application controller: wires UI, engines and persistence.

This is the only place that knows about both sides; windows and services
stay independent and communicate through signals and slots.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Slot

from core.agent_controller import AgentController
from core.app_launcher import AppLauncher
from core.automation import Automation
from core.intent_parser import IntentParser
from core.learn_mode import WorkflowRecorder
from core.models import ActionResult, ActionType, PlanResult, TaskState
from core.ocr import OcrEngine
from core.plan_executor import PlanExecutor
from core.safety import SafetyManager
from core.settings import SettingsStore
from core.task_manager import TaskManager
from core.terminal import TerminalEngine
from core.vision import VisionEngine, VisionError
from core.voice_service import VoiceService
from core.workflow_player import StepPlaybackResult, WorkflowPlayer
from database.action_repository import ActionRepository
from database.db_manager import DatabaseManager
from database.task_repository import TaskRepository
from database.workflow_repository import WorkflowRepository
from ui.main_window import MainWindow
from ui.popup import ExecutionPopup


class ApplicationController(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._window = MainWindow()
        self._popup = ExecutionPopup()
        self._launcher = AppLauncher()
        self._parser = IntentParser(
            known_apps=AppLauncher.known_names,
            display_name=AppLauncher.display_name,
        )
        self._automation = Automation()
        self._executor = PlanExecutor(
            self, launcher=self._launcher, automation=self._automation
        )
        self._tasks = TaskManager(self)  # Milestone 1 simulation engine
        self._voice = VoiceService(self)
        self._vision = VisionEngine(self)
        self._ocr = OcrEngine(vision=self._vision)
        self._recorder = WorkflowRecorder(self, target_resolver=self._click_target)
        self._player = WorkflowPlayer(
            self, vision=self._vision, ocr=self._ocr, automation=self._automation
        )
        self._db = DatabaseManager()
        self._repository = TaskRepository(self._db)
        self._action_repository = ActionRepository(self._db)
        self._workflow_repository = WorkflowRepository(self._db)
        self._settings = SettingsStore()
        self._safety = SafetyManager(
            confirm_policy=str(self._settings.get("confirm_policy"))
        )
        self._terminal = TerminalEngine(self)
        self._agent = AgentController(
            self._settings,
            self._safety,
            self._launcher,
            self._automation,
            self._terminal,
            self._vision,
            self._ocr,
            self._recorder,
            self._player,
            self._workflow_repository,
            self,
        )
        self._agent_step_count = 0
        self._current_run_id: int | None = None
        self._active_command = ""
        self._run_started = 0.0
        self._simulate_run = False

        self._wire()
        self._reload_workflows()

    # ------------------------------------------------------------- wiring

    def _wire(self) -> None:
        window = self._window
        window.run_requested.connect(self._on_run_requested)
        window.stop_requested.connect(self._on_stop_requested)
        window.voice_requested.connect(self._voice.start_listening)
        window.page_changed.connect(self._on_page_changed)
        self._voice.notice.connect(window.show_notice)

        popup = self._popup
        popup.pause_requested.connect(self._on_pause_requested)
        popup.stop_requested.connect(self._on_stop_requested)
        popup.restore_requested.connect(self._on_restore_requested)
        popup.dismiss_requested.connect(self._on_dismiss_requested)

        tasks = self._tasks
        tasks.progressed.connect(self._on_progress)
        tasks.finished.connect(self._on_task_finished)
        tasks.failed.connect(self._on_task_failed)
        tasks.notice.connect(self._on_task_notice)

        executor = self._executor
        executor.step_started.connect(self._on_step_started)
        executor.step_finished.connect(self._on_step_finished)
        executor.output_line.connect(self._on_output_line)
        executor.plan_completed.connect(self._on_plan_completed)
        executor.notice.connect(self._on_task_notice)

        learn = window.learn_page
        learn.start_recording_requested.connect(self._on_start_recording)
        learn.stop_recording_requested.connect(self._on_stop_recording)
        learn.save_workflow_requested.connect(self._on_save_workflow)
        learn.play_workflow_requested.connect(self._on_play_workflow)
        learn.capture_mode_changed.connect(self._on_capture_mode_changed)

        recorder = self._recorder
        recorder.step_recorded.connect(self._on_step_recorded)
        recorder.recording_stopped.connect(self._on_recording_stopped)
        recorder.notice.connect(self._on_task_notice)

        player = self._player
        player.step_started.connect(self._on_playback_step)
        player.progress.connect(self._on_playback_progress)
        player.step_finished.connect(self._on_playback_step_finished)
        player.playback_completed.connect(self._on_playback_completed)
        player.notice.connect(self._on_task_notice)

        self._vision.frame_ready.connect(self._on_frame)
        self._vision.error.connect(self._on_vision_error)

        popup.confirmation_responded.connect(self._agent.respond_to_confirmation)
        window.settings_requested.connect(self._on_settings_requested)

        agent = self._agent
        agent.started.connect(self._on_agent_started)
        agent.status.connect(self._on_agent_status)
        agent.live.connect(self._popup.show_live)
        agent.confirmation_required.connect(self._on_agent_confirmation)
        agent.learning_started.connect(self._on_agent_learning_started)
        agent.tool_finished.connect(self._on_agent_tool_finished)
        agent.finished.connect(self._on_agent_finished)
        agent.notice.connect(self._on_task_notice)

    # ---------------------------------------------------------- lifecycle

    def start(self) -> None:
        self._window.set_state(TaskState.IDLE)
        self._window.show()

    def shutdown(self) -> None:
        self._window.save_geometry()
        self._agent.cancel()
        self._recorder.stop()
        self._player.shutdown()
        self._vision.shutdown()
        self._executor.shutdown()
        self._tasks.shutdown()
        self._db.close()

    def _is_busy(self) -> bool:
        return (
            self._tasks.is_running
            or self._executor.is_running
            or self._player.is_running
            or self._recorder.is_recording
            or self._agent.is_running
        )

    # ------------------------------------------------- command execution

    @Slot(str)
    def _on_run_requested(self, command: str) -> None:
        command = command.strip()
        if not command:
            self._window.show_notice("Enter a command before running.")
            return
        if self._is_busy():
            self._window.show_notice("A task is already running — press Stop to cancel.")
            return

        if not command.lower().startswith("simulate") and self._try_agent(command):
            return
        self._run_legacy(command)

    def _try_agent(self, command: str) -> bool:
        """Route through the AI agent when a provider is configured."""
        if not self._agent.can_run()[0]:
            return False
        if not self._agent.run(command):
            return False
        self._active_command = command
        self._run_started = time.monotonic()
        self._current_run_id = self._repository.create_run(command)
        self._window.set_state(TaskState.WORKING)
        self._window.minimize()
        self._popup.begin_agent(command)
        self._popup.show_popup()
        return True

    def _run_legacy(self, command: str) -> None:
        """Milestone 2 local parser path (kept when no AI runs)."""
        plan = self._parser.parse(command)
        if not any(action.type is not ActionType.UNKNOWN for action in plan.actions):
            detail = plan.actions[0].description if plan.actions else "Empty command"
            self._window.show_notice(
                f"{detail}. Try: open firefox · run ls -la · type hi · press ctrl+c"
            )
            self._action_repository.record(command, "Unrecognized command", False, 0.0)
            return

        self._active_command = command
        self._run_started = time.monotonic()
        self._current_run_id = self._repository.create_run(command)
        self._window.set_state(TaskState.WORKING)
        self._window.minimize()

        # A single simulated step keeps using the Milestone 1 TaskManager path.
        if len(plan.actions) == 1 and plan.actions[0].type is ActionType.SIMULATE:
            self._simulate_run = True
            self._popup.begin_task(command)
            self._popup.show_popup()
            self._tasks.start(plan.actions[0].params["task"])
            return

        self._simulate_run = False
        self._popup.begin_plan(command, plan.total_steps)
        self._popup.show_popup()
        self._executor.execute(plan)

    @Slot()
    def _on_stop_requested(self) -> None:
        """Global emergency stop: cancels whatever is executing."""
        stopped = False
        if self._executor.is_running:
            self._executor.emergency_stop()
            stopped = True
        if self._player.is_running:
            self._player.stop()
            stopped = True
        if self._tasks.is_running:
            self._tasks.stop()
            stopped = True
        if self._recorder.is_recording:
            self._on_stop_recording()
            stopped = True
        if self._agent.is_running:
            self._agent.cancel()
            stopped = True
        if not stopped:
            self._window.show_notice("Nothing is running.")

    @Slot()
    def _on_pause_requested(self) -> None:
        message = "Pause is a UI placeholder in this milestone."
        self._popup.show_notice(message)
        self._window.show_notice(message)

    @Slot()
    def _on_restore_requested(self) -> None:
        self._window.restore()

    @Slot()
    def _on_dismiss_requested(self) -> None:
        self._popup.hide()

    @Slot(str)
    def _on_progress(self, text: str) -> None:
        self._popup.set_progress(text)

    @Slot(int, int, str)
    def _on_step_started(self, index: int, total: int, description: str) -> None:
        self._popup.set_step(index, total)
        self._popup.set_progress(description)

    @Slot(object)
    def _on_step_finished(self, result: ActionResult) -> None:
        self._action_repository.record(
            self._active_command,
            result.action.description,
            result.success,
            result.duration,
        )

    @Slot(str)
    def _on_output_line(self, text: str) -> None:
        if text.strip():
            self._popup.show_live(text.strip()[:120])

    @Slot(object)
    def _on_plan_completed(self, result: PlanResult) -> None:
        if result.cancelled:
            state = TaskState.ERROR
            summary = f"Emergency stop — {result.summary.lower()}"
            popup_progress = "Stopped"
        elif result.success:
            state = TaskState.DONE
            summary = result.summary
            popup_progress = "Completed"
        else:
            state = TaskState.ERROR
            summary = result.first_error or "Execution failed"
            popup_progress = "Failed"

        self._finish_run(state, summary)
        self._window.set_state(state)
        self._window.show_notice(summary)
        self._popup.set_state(state)
        self._popup.set_progress(popup_progress)

    @Slot(str)
    def _on_task_finished(self, result: str) -> None:
        self._record_simulate_action(True)
        self._finish_run(TaskState.DONE, result)
        self._window.set_state(TaskState.DONE)
        self._window.show_notice(result)
        self._popup.set_state(TaskState.DONE)
        self._popup.set_progress("Completed")

    @Slot(str)
    def _on_task_failed(self, message: str) -> None:
        self._record_simulate_action(False)
        self._finish_run(TaskState.ERROR, message)
        self._window.set_state(TaskState.ERROR)
        self._window.show_notice(f"Error: {message}")
        self._popup.set_state(TaskState.ERROR)
        self._popup.set_progress("Failed")

    @Slot(str)
    def _on_task_notice(self, text: str) -> None:
        self._popup.show_notice(text)
        self._window.show_notice(text)

    # ------------------------------------------------------- learn mode

    @Slot()
    def _on_start_recording(self) -> None:
        if self._is_busy():
            self._window.show_notice("A task is already running — press Stop to cancel.")
            return
        if not self._recorder.start():
            return  # recorder emitted a notice
        self._window.learn_page.set_recording(True)
        self._window.set_state(TaskState.WORKING)
        self._window.minimize()
        self._popup.begin_recording()
        self._popup.show_popup()

    @Slot()
    def _on_stop_recording(self) -> None:
        if not self._recorder.is_recording:
            self._window.show_notice("Not recording.")
            return
        self._recorder.stop()  # recording_stopped slot does the UI updates

    @Slot(int)
    def _on_recording_stopped(self, count: int) -> None:
        self._window.learn_page.set_steps(self._recorder.steps)
        self._window.learn_page.set_recording(False)
        self._window.set_state(TaskState.DONE)
        self._popup.set_state(TaskState.DONE)
        self._popup.set_progress("Recorded")
        message = (
            f"Recorded {count} steps — set App/Task name and press Save Workflow"
        )
        self._popup.show_notice(message)
        self._window.show_notice(message)
        self._window.restore()

    @Slot(object)
    def _on_step_recorded(self, step) -> None:  # noqa: ANN001
        count = len(self._recorder.steps)
        self._popup.update_recording(count, step.description)
        self._window.learn_page.set_steps(self._recorder.steps)

    @Slot(str, str)
    def _on_save_workflow(self, app_name: str, task_name: str) -> None:
        if self._recorder.is_recording:
            self._window.show_notice("Stop recording before saving.")
            return
        steps = self._recorder.steps
        if not steps:
            self._window.show_notice("Record some steps first.")
            return
        workflow = self._workflow_repository.save_workflow(app_name, task_name, steps)
        self._recorder.clear()
        self._window.learn_page.set_steps([])
        self._reload_workflows()
        message = f"Saved workflow “{workflow.label}” ({len(steps)} steps)"
        self._window.show_notice(message)

    @Slot(int)
    def _on_play_workflow(self, workflow_id: int) -> None:
        if self._is_busy():
            self._window.show_notice("A task is already running — press Stop to cancel.")
            return
        workflow = self._workflow_repository.load_workflow(workflow_id)
        if workflow is None or not workflow.steps:
            self._window.show_notice("Workflow not found or empty.")
            return
        self._active_workflow_label = workflow.label
        self._window.set_state(TaskState.WORKING)
        self._window.minimize()
        self._popup.begin_playback(workflow.label, len(workflow.steps))
        self._popup.show_popup()
        self._player.play(workflow)

    @Slot(int, int, str)
    def _on_playback_step(self, index: int, total: int, description: str) -> None:
        self._popup.update_playback(index, total, description)

    @Slot(str)
    def _on_playback_progress(self, message: str) -> None:
        self._popup.set_progress(message)

    @Slot(object)
    def _on_playback_step_finished(self, result: StepPlaybackResult) -> None:
        label = getattr(self, "_active_workflow_label", "") or "workflow"
        self._action_repository.record(
            f"workflow: {label}",
            result.step.description,
            result.success,
            0.0,
        )

    @Slot(object)
    def _on_playback_completed(self, result) -> None:  # noqa: ANN001
        if result.cancelled:
            state = TaskState.ERROR
            summary = f"Playback stopped — {result.summary.lower()}"
            popup_progress = "Stopped"
        elif result.success:
            state = TaskState.DONE
            summary = result.summary
            popup_progress = "Completed"
        else:
            state = TaskState.ERROR
            summary = result.first_error or "Playback failed"
            popup_progress = "Failed"
        self._window.set_state(state)
        self._window.show_notice(summary)
        self._popup.set_state(state)
        self._popup.set_progress(popup_progress)

    # ---------------------------------------------------------- AI agent

    @Slot(str, str)
    def _on_agent_started(self, command: str, label: str) -> None:
        self._agent_step_count = 0
        self._window.show_notice(f"AI task via {label}")

    @Slot(str)
    def _on_agent_status(self, text: str) -> None:
        self._popup.update_agent(text)

    @Slot(str)
    def _on_agent_confirmation(self, prompt: str) -> None:
        self._popup.show_confirmation(prompt)
        self._popup.show_popup()

    @Slot()
    def _on_agent_learning_started(self) -> None:
        self._window.learn_page.set_recording(True)
        self._window.set_state(TaskState.WORKING)
        self._window.minimize()
        self._popup.begin_recording()
        self._popup.show_popup()

    @Slot(object)
    def _on_agent_tool_finished(self, event) -> None:  # noqa: ANN001
        self._agent_step_count += 1
        self._popup.set_step_text(f"Step {self._agent_step_count}")
        duration = 0.0
        self._action_repository.record(
            self._active_command or "agent",
            f"agent · {event.tool_name or 'note'}",
            bool(event.success),
            duration,
        )

    @Slot(object)
    def _on_agent_finished(self, result) -> None:  # noqa: ANN001
        self._popup.hide_confirmation()
        fallback = (
            not result.success
            and result.steps == 0
            and result.error_category
            in ("provider_unavailable", "api_unavailable")
        )
        if result.cancelled:
            state = TaskState.ERROR
            summary = "Stopped."
            popup_progress = "Stopped"
        elif result.success:
            state = TaskState.DONE
            summary = result.summary
            popup_progress = "Task completed"
        else:
            state = TaskState.ERROR
            summary = result.summary or "Agent failed."
            popup_progress = "Failed"
        self._finish_run(state, summary)
        self._window.set_state(state)
        self._window.show_notice(summary[:140])
        self._popup.set_state(state)
        self._popup.set_progress(popup_progress)
        if fallback:
            self._window.show_notice("AI unavailable — using local command parser.")
            self._run_legacy(self._active_command)

    @Slot()
    def _on_settings_requested(self) -> None:
        from ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            self._settings, self._safety, parent=self._window
        )
        dialog.exec()

    # -------------------------------------------------------- vision/preview

    @Slot(int)
    def _on_page_changed(self, index: int) -> None:
        if index == 1:  # Learn page
            try:
                self._window.learn_page.set_monitor_options(self._vision.list_monitors())
            except VisionError as exc:
                self._window.learn_page.show_message(f"Capture unavailable: {exc}")
            mode, monitor = self._window.learn_page.current_capture_mode()
            self._vision.start_stream(mode=mode, monitor=monitor)
        else:
            self._vision.stop_stream()

    @Slot(str, int)
    def _on_capture_mode_changed(self, mode: str, monitor: int) -> None:
        if self._vision.is_streaming:
            self._vision.start_stream(mode=mode, monitor=monitor)

    @Slot(object)
    def _on_frame(self, frame) -> None:  # noqa: ANN001
        self._window.learn_page.set_preview(frame.qimage)

    @Slot(str)
    def _on_vision_error(self, message: str) -> None:
        self._window.learn_page.show_message(message)

    # ------------------------------------------------------------ helpers

    def _click_target(self, x: int, y: int) -> str | None:
        """OCR label for a recorded click (runs on the listener thread)."""
        try:
            frame = self._vision.grab()
            detections = self._ocr.detect_text(frame.pil_image)
        except Exception:  # noqa: BLE001 - labeling is best-effort
            return None
        origin_x, origin_y = frame.geometry[0], frame.geometry[1]
        best, best_area = None, None
        for detection in detections:
            bx, by, bw, bh = detection.bbox
            left, top = origin_x + bx, origin_y + by
            if left - 8 <= x <= left + bw + 8 and top - 8 <= y <= top + bh + 8:
                area = bw * bh
                if best_area is None or area < best_area:
                    best, best_area = detection.text, area
        return best

    def _reload_workflows(self) -> None:
        self._window.learn_page.set_workflows(self._workflow_repository.list_workflows())

    def _record_simulate_action(self, success: bool) -> None:
        if self._simulate_run:
            self._action_repository.record(
                self._active_command,
                "Simulated run",
                success,
                time.monotonic() - self._run_started,
            )
            self._simulate_run = False

    def _finish_run(self, state: TaskState, result: str) -> None:
        if self._current_run_id is not None:
            self._repository.finish_run(self._current_run_id, state, result)
            self._current_run_id = None
