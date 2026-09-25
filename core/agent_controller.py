"""Agent controller — the layer between the UI and the agent.

Owns provider selection with explicit privacy rules (Auto prefers local
Ollama and only touches OpenAI after the privacy gate), the agent worker
thread, the confirmation handshake, and a thread-safe bridge onto
GUI-owned engines (workflow player/recorder stay on the GUI thread).
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.agent import Agent, AgentResult
from core.app_launcher import AppLauncher
from core.automation import Automation
from core.config import Config
from core.learn_mode import WorkflowRecorder
from core.memory import MemoryStore
from core.ocr import OcrEngine
from core.providers import OllamaProvider, OpenAIProvider
from core.providers.base import AIProvider, ProviderError, ProviderNotConfigured
from core.safety import SafetyManager
from core.settings import (
    PRIVACY_ALLOW_CLOUD,
    PRIVACY_ASK_BEFORE_CLOUD,
    PRIVACY_LOCAL_ONLY,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    SettingsStore,
)
from core.terminal import TerminalEngine
from core.tools.standard import ToolContext, build_standard_registry
from core.vision import VisionEngine
from core.workflow_player import WorkflowPlayer
from database.agent_repository import AgentRepository
from database.db_manager import DatabaseManager
from database.workflow_repository import WorkflowRepository


class ConfirmationTicket:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.approved = False


class GuiBridge(QObject):
    """Executes small callables on the GUI thread for agent-side callers."""

    _invoke = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._invoke.connect(self._on_invoke)

    def call(self, fn, *args, timeout: float = 15.0):  # noqa: ANN001, ANN202
        if QThread.currentThread() is self.thread():
            return fn(*args)
        holder: dict = {}
        done = threading.Event()

        def job() -> None:
            try:
                holder["value"] = fn(*args)
            except Exception as exc:  # noqa: BLE001 - re-raised on caller thread
                holder["error"] = exc
            done.set()

        self._invoke.emit(job)
        if not done.wait(timeout):
            raise TimeoutError("Timed out waiting for the UI thread.")
        if "error" in holder:
            raise holder["error"]
        return holder.get("value")

    @Slot(object)
    def _on_invoke(self, job) -> None:  # noqa: ANN001
        job()


class DesktopWorkflowService:
    """Thread-safe WorkflowService over recorder, player and storage."""

    def __init__(
        self,
        gui: GuiBridge,
        recorder: WorkflowRecorder,
        player: WorkflowPlayer,
        repository: WorkflowRepository,
        cancel_event: threading.Event,
        on_learning_started=None,  # noqa: ANN001
    ) -> None:
        self._gui = gui
        self._recorder = recorder
        self._player = player
        self._repo = repository
        self._cancel = cancel_event
        self._on_learning_started = on_learning_started

    def is_recording(self) -> bool:
        return bool(self._gui.call(lambda: self._recorder.is_recording))

    def start_learning(self) -> bool:
        def op() -> bool:
            if self._recorder.is_recording:
                return True
            started = self._recorder.start()
            if started and self._on_learning_started:
                self._on_learning_started()
            return bool(started)
        return bool(self._gui.call(op))

    def stop_learning(self) -> int:
        def op() -> int:
            steps = self._recorder.stop()
            return len(steps or self._recorder.steps)
        return int(self._gui.call(op))

    def save_workflow(self, app_name: str, task_name: str) -> dict | None:
        def op() -> dict | None:
            if self._recorder.is_recording or not self._recorder.steps:
                return None
            steps = list(self._recorder.steps)
            workflow = self._repo.save_workflow(app_name, task_name, steps)
            self._recorder.clear()
            return {
                "id": workflow.id,
                "label": workflow.label,
                "steps": len(steps),
            }
        return self._gui.call(op)

    def _safe_disconnect(self, callback) -> None:  # noqa: ANN001
        try:
            self._player.playback_completed.disconnect(callback)
        except (RuntimeError, TypeError):
            pass

    def list_workflows(self) -> list[dict]:
        def op() -> list[dict]:
            return [
                {
                    "id": w.id,
                    "app_name": w.app_name,
                    "task_name": w.task_name,
                    "label": w.label,
                    "step_count": w.step_count,
                }
                for w in self._repo.list_workflows()
            ]
        return list(self._gui.call(op))

    def run_workflow(
        self,
        *,
        app_name: str | None = None,
        task_name: str | None = None,
        workflow_id: int | None = None,
    ) -> dict:
        def resolve():  # noqa: ANN202
            if workflow_id is not None:
                return self._repo.load_workflow(int(workflow_id))
            matches = [
                w
                for w in self._repo.list_workflows()
                if (app_name is None or w.app_name.lower() == str(app_name).lower())
                and (task_name is None or w.task_name.lower() == str(task_name).lower())
            ]
            if not matches:
                return None
            return self._repo.load_workflow(matches[0].id)

        workflow = self._gui.call(resolve)
        if workflow is None or not workflow.steps:
            return {
                "missing": True,
                "success": False,
                "summary": "No matching saved workflow — use list_workflows to see options.",
            }

        outcome: dict = {}
        done = threading.Event()

        def on_completed(result) -> None:  # noqa: ANN001
            outcome["cancelled"] = result.cancelled
            outcome["success"] = result.success
            outcome["summary"] = result.summary
            done.set()

        def start() -> bool:
            self._player.playback_completed.connect(on_completed)
            return bool(self._player.play(workflow))

        started = self._gui.call(start)
        try:
            if not started:
                return {
                    "success": False,
                    "summary": "Workflow player is busy.",
                    "error_category": "automation_failure",
                }
            while not done.wait(0.1):
                if self._cancel.is_set() and self._player.is_running:
                    self._player.stop()
        finally:
            self._gui.call(lambda: self._safe_disconnect(on_completed))
        success = bool(outcome.get("success"))
        return {
            "success": success,
            "cancelled": bool(outcome.get("cancelled")),
            "summary": str(outcome.get("summary") or ""),
            "display": f"Played {workflow.label}",
            "error_category": None if success else "automation_failure",
        }


class AgentController(QObject):
    started = Signal(str, str)  # command, provider label
    status = Signal(str)
    live = Signal(str)
    confirmation_required = Signal(str)
    learning_started = Signal()
    tool_finished = Signal(object)  # AgentEvent
    finished = Signal(object)  # AgentResult
    notice = Signal(str)

    def __init__(
        self,
        settings: SettingsStore,
        safety: SafetyManager,
        launcher: AppLauncher,
        automation: Automation,
        terminal: TerminalEngine,
        vision: VisionEngine,
        ocr: OcrEngine,
        recorder: WorkflowRecorder,
        player: WorkflowPlayer,
        workflows: WorkflowRepository,
        provider_factory=None,  # noqa: ANN001 - tests inject a scripted provider
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._safety = safety
        self._launcher = launcher
        self._automation = automation
        self._terminal = terminal
        self._vision = vision
        self._ocr = ocr
        self._recorder = recorder
        self._player = player
        self._workflow_repo = workflows
        self._gui = GuiBridge(self)
        self._cancel_event = threading.Event()
        self._ticket: ConfirmationTicket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._provider_factory = provider_factory

    # ----------------------------------------------------------- control

    @property
    def is_running(self) -> bool:
        return self._running

    def can_run(self) -> tuple[bool, str]:
        kind = str(self._settings.get("provider"))
        privacy = str(self._settings.get("privacy"))
        if kind == PROVIDER_OPENAI and privacy == PRIVACY_LOCAL_ONLY:
            return False, "Privacy is “Local only” — enable cloud AI to use OpenAI."
        return True, ""

    def run(self, command: str) -> bool:
        if self._running:
            self.notice.emit("An AI task is already running.")
            return False
        ok, reason = self.can_run()
        if not ok:
            self.notice.emit(reason)
            return False
        self._cancel_event = threading.Event()
        self._running = True
        self._thread = threading.Thread(
            target=self._run, args=(command,), daemon=True
        )
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._cancel_event.set()
        ticket = self._ticket
        if ticket is not None:
            ticket.approved = False
            ticket.event.set()
        if self._player.is_running:
            self._player.stop()
        self._terminal.cancel()
        self._automation.abort()

    @Slot(bool)
    def respond_to_confirmation(self, approved: bool) -> None:
        ticket = self._ticket
        if ticket is not None:
            ticket.approved = approved
            ticket.event.set()

    # ------------------------------------------------------------ thread

    def _run(self, command: str) -> None:
        result: AgentResult
        try:
            provider = (
                self._provider_factory()
                if self._provider_factory is not None
                else self._resolve_provider()
            )
            label = provider.name
            self.started.emit(command, label)
            memory = MemoryStore(
                AgentRepository(DatabaseManager()),
                screenshot_history=bool(self._settings.get("screenshot_history")),
                screenshots_dir=Config.data_dir() / "screenshots",
            )
            service = DesktopWorkflowService(
                self._gui,
                self._recorder,
                self._player,
                self._workflow_repo,
                self._cancel_event,
                on_learning_started=self.learning_started.emit,
            )
            registry = build_standard_registry(
                ToolContext(
                    launcher=self._launcher,
                    automation=self._automation,
                    terminal=self._terminal,
                    vision=self._vision,
                    ocr=self._ocr,
                    safety=self._safety,
                    workflows=service,
                    memory=memory,
                )
            )
            agent = Agent(
                provider,
                registry,
                self._safety,
                memory=memory,
                status_cb=self.status.emit,
                live_cb=self.live.emit,
                confirm_cb=self._confirm,
                event_cb=self.tool_finished.emit,
                cancel_event=self._cancel_event,
            )
            self._automation.reset()
            result = agent.run(command)
        except ProviderError as exc:
            result = AgentResult(
                False,
                str(exc),
                error_category="provider_unavailable"
                if isinstance(exc, ProviderNotConfigured)
                else "api_unavailable",
            )
        except Exception as exc:  # noqa: BLE001 - keep the worker alive
            result = AgentResult(False, f"Agent error: {exc}", error_category="unknown")
        self._running = False
        self.finished.emit(result)

    def _resolve_provider(self) -> AIProvider:
        """Pick a provider explicitly — Auto prefers local, cloud only with consent."""
        privacy = str(self._settings.get("privacy"))
        kind = str(self._settings.get("provider"))
        ollama = OllamaProvider(
            base_url=str(self._settings.get("ollama_host")),
            model=str(self._settings.get("model_ollama")),
        )
        openai = OpenAIProvider(
            api_key=self._settings.api_key(),
            model=str(self._settings.get("model_openai")),
        )

        def cloud_gate() -> bool:
            if privacy == PRIVACY_ALLOW_CLOUD:
                return True
            if privacy == PRIVACY_ASK_BEFORE_CLOUD:
                return self._confirm(
                    "Allow cloud AI (OpenAI) for this task? The request would be "
                    "sent to an external API."
                )
            return False

        if kind == PROVIDER_OPENAI:
            if privacy == PRIVACY_LOCAL_ONLY:
                raise ProviderError(
                    "Privacy is “Local only” — cloud AI is disabled in Settings."
                )
            if not openai.is_available():
                raise ProviderNotConfigured(
                    "OpenAI needs an API key (Settings → AI Engine)."
                )
            if not cloud_gate():
                raise ProviderError("Cloud AI was not approved for this task.")
            return openai
        if kind == PROVIDER_OLLAMA:
            return ollama
        # Auto: prefer local Ollama, fall back to OpenAI only when allowed.
        if ollama.is_available():
            return ollama
        if openai.is_available() and cloud_gate():
            return openai
        raise ProviderNotConfigured(
            "Local AI (Ollama) is unavailable and cloud AI is disabled or not "
            "approved."
        )

    def _confirm(self, prompt: str) -> bool:
        if self._cancel_event.is_set():
            return False
        ticket = ConfirmationTicket()
        self._ticket = ticket
        self.confirmation_required.emit(prompt)
        while not ticket.event.wait(0.1):
            if self._cancel_event.is_set():
                break
        self._ticket = None
        return bool(ticket.approved) and not self._cancel_event.is_set()
