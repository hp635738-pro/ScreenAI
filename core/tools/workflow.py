"""Workflow tools — bridge the Milestone 3 Learn Mode to the agent.

Learning stays an explicit, user-controlled mode: tools only record when
the agent is asked to, and never create workflows from normal
interactions.
"""

from __future__ import annotations

from typing import Protocol

from core.safety import ErrorCategory, SafetyLevel, SafetyManager, ToolError
from core.tools import Tool, ToolResult, ToolSpec, enforce_safety


class WorkflowService(Protocol):
    """Thread-safe facade over recorder + player + workflow storage."""

    def is_recording(self) -> bool: ...
    def start_learning(self) -> bool: ...
    def stop_learning(self) -> int: ...
    def save_workflow(self, app_name: str, task_name: str) -> dict | None: ...
    def list_workflows(self) -> list[dict]: ...
    def run_workflow(
        self, *, app_name: str | None = None, task_name: str | None = None,
        workflow_id: int | None = None,
    ) -> dict: ...


class StartLearningTool(Tool):
    spec = ToolSpec(
        name="start_learning",
        description=(
            "Start recording a workflow from the user's demonstration. Only "
            "use when the user explicitly asks to learn/record a task."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        safety=SafetyLevel.SAFE,
    )

    def __init__(self, workflows: WorkflowService, safety: SafetyManager) -> None:
        self._workflows = workflows
        self._safety = safety

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(self._safety, self.spec, arguments)
        if self._workflows.is_recording():
            return ToolResult(True, "Already recording.", display="Recording…")
        if not self._workflows.start_learning():
            raise ToolError(
                "Could not start recording.",
                ErrorCategory.AUTOMATION_FAILURE,
            )
        return ToolResult(
            True,
            "Recording started — ask the user to perform the task.",
            display="Recording…",
        )


class StopLearningTool(Tool):
    spec = ToolSpec(
        name="stop_learning",
        description="Stop recording the current workflow demonstration.",
        input_schema={"type": "object", "properties": {}, "required": []},
        safety=SafetyLevel.SAFE,
    )

    def __init__(self, workflows: WorkflowService, safety: SafetyManager) -> None:
        self._workflows = workflows
        self._safety = safety

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(self._safety, self.spec, arguments)
        count = self._workflows.stop_learning()
        return ToolResult(
            count > 0,
            f"Recording stopped — {count} steps captured.",
            data={"steps": count},
            display="Finished recording",
            error_category=None if count else ErrorCategory.INVALID_ARGUMENTS.value,
        )


class SaveWorkflowTool(Tool):
    spec = ToolSpec(
        name="save_workflow",
        description="Save the recorded steps as a named workflow.",
        input_schema={
            "type": "object",
            "properties": {
                "app_name": {"type": "string"},
                "task_name": {"type": "string"},
            },
            "required": ["app_name", "task_name"],
        },
        safety=SafetyLevel.SAFE,
    )

    def __init__(self, workflows: WorkflowService, safety: SafetyManager) -> None:
        self._workflows = workflows
        self._safety = safety

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(self._safety, self.spec, arguments)
        app_name = str(arguments["app_name"])
        task_name = str(arguments["task_name"])
        saved = self._workflows.save_workflow(app_name, task_name)
        if not saved:
            raise ToolError(
                "Nothing recorded to save (or still recording).",
                ErrorCategory.INVALID_ARGUMENTS,
            )
        return ToolResult(
            True,
            f"Saved workflow {saved.get('label')} ({saved.get('steps')} steps).",
            data=saved,
            display=f"Saved {saved.get('label')}",
        )


class ListWorkflowsTool(Tool):
    spec = ToolSpec(
        name="list_workflows",
        description="List saved workflows (app name, task name, step count).",
        input_schema={"type": "object", "properties": {}, "required": []},
        safety=SafetyLevel.SAFE,
    )

    def __init__(self, workflows: WorkflowService, safety: SafetyManager) -> None:
        self._workflows = workflows
        self._safety = safety

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(self._safety, self.spec, arguments)
        items = self._workflows.list_workflows()
        if not items:
            return ToolResult(True, "No saved workflows yet.", display="No workflows")
        listing = "; ".join(
            f"[{w['id']}] {w['label']} ({w.get('step_count', '?')} steps)" for w in items
        )
        return ToolResult(
            True, f"Saved workflows: {listing}", data={"workflows": items},
            display="Listed workflows",
        )


class RunWorkflowTool(Tool):
    spec = ToolSpec(
        name="run_workflow",
        description=(
            "Replay a saved workflow (e.g. run_workflow('XYZ App', 'Export PDF')). "
            "Preferred over re-learning: uses OCR-first playback with retries."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "app_name": {"type": "string"},
                "task_name": {"type": "string"},
                "workflow_id": {"type": "integer"},
                "confirm_reason": {"type": "string"},
            },
            "required": [],
        },
        safety=SafetyLevel.SAFE,
    )

    def __init__(self, workflows: WorkflowService, safety: SafetyManager) -> None:
        self._workflows = workflows
        self._safety = safety

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(
            self._safety,
            self.spec,
            arguments,
            confirm_reason=arguments.get("confirm_reason"),
            description=str(arguments.get("task_name") or arguments.get("app_name") or ""),
        )
        outcome = self._workflows.run_workflow(
            app_name=arguments.get("app_name"),
            task_name=arguments.get("task_name"),
            workflow_id=arguments.get("workflow_id"),
        )
        if outcome.get("missing"):
            raise ToolError(outcome["summary"], ErrorCategory.WORKFLOW_NOT_FOUND)
        return ToolResult(
            bool(outcome.get("success")),
            str(outcome.get("summary")),
            data=outcome,
            display=outcome.get("display") or "Playing workflow",
            error_category=None
            if outcome.get("success")
            else (outcome.get("error_category") or ErrorCategory.UNKNOWN.value),
        )
