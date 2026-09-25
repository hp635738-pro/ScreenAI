"""Shared domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskState(Enum):
    IDLE = "idle"
    WORKING = "working"
    DONE = "done"
    ERROR = "error"

    @property
    def label(self) -> str:
        return _STATE_LABELS[self]


_STATE_LABELS: dict[TaskState, str] = {
    TaskState.IDLE: "Ready",
    TaskState.WORKING: "Working",
    TaskState.DONE: "Done",
    TaskState.ERROR: "Error",
}


@dataclass(slots=True)
class TaskRecord:
    id: int | None
    command: str
    status: str = TaskState.WORKING.value
    started_at: str | None = None
    finished_at: str | None = None
    result: str | None = None


# --------------------------------------------------------------------------
# Milestone 2: control-engine models (plans, actions, results)
# --------------------------------------------------------------------------


class ActionType(Enum):
    LAUNCH_APP = "launch_app"
    RUN_TERMINAL = "run_terminal"
    TYPE_TEXT = "type_text"
    MOVE_MOUSE = "move_mouse"
    LEFT_CLICK = "left_click"
    RIGHT_CLICK = "right_click"
    DOUBLE_CLICK = "double_click"
    HOTKEY = "hotkey"
    PRESS_KEY = "press_key"
    WAIT = "wait"
    SIMULATE = "simulate"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Action:
    """A single structured step produced by the intent parser."""

    type: ActionType
    params: dict[str, Any]
    description: str


@dataclass(slots=True)
class Plan:
    """An ordered list of actions parsed from one user command."""

    command: str
    actions: list[Action]

    @property
    def total_steps(self) -> int:
        return len(self.actions)


@dataclass(slots=True)
class ActionResult:
    action: Action
    success: bool
    duration: float
    message: str = ""


@dataclass(slots=True)
class PlanResult:
    command: str
    results: list[ActionResult] = field(default_factory=list)
    cancelled: bool = False
    duration: float = 0.0
    total: int = 0

    @property
    def success(self) -> bool:
        return bool(self.results) and not self.cancelled and all(
            r.success for r in self.results
        )

    @property
    def summary(self) -> str:
        done = sum(1 for r in self.results if r.success)
        total = self.total or len(self.results)
        if self.cancelled:
            return f"Stopped after {done}/{total} steps"
        return f"{done}/{total} steps succeeded"

    @property
    def first_error(self) -> str | None:
        for result in self.results:
            if not result.success:
                return result.message or result.action.description
        return None


@dataclass(slots=True)
class ActionRecord:
    """One row of the action history table."""

    id: int | None
    command: str
    action: str
    success: bool
    duration: float
    timestamp: str | None = None


# --------------------------------------------------------------------------
# Milestone 3: learn-mode models (recorded workflows)
# --------------------------------------------------------------------------

_KEY_DISPLAY = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "super": "Super",
    "enter": "Enter",
    "escape": "Esc",
    "tab": "Tab",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
}


def format_keys(keys: str) -> str:
    """Format a key combination for display: 'ctrl+s' -> 'Ctrl+S'."""
    parts = [part for part in keys.replace("+", " ").split() if part]
    return "+".join(
        _KEY_DISPLAY.get(part.lower(), part.upper() if len(part) == 1 else part.title())
        for part in parts
    )


@dataclass(slots=True)
class LearnedStep:
    """One recorded user action (a workflow step)."""

    action: ActionType
    target_text: str | None = None
    coordinates: tuple[int, int] | None = None
    delay: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def description(self) -> str:
        if self.action is ActionType.TYPE_TEXT:
            text = (self.target_text or "").replace("\n", " ")
            shown = text if len(text) <= 24 else text[:24] + "…"
            return f"Type “{shown}”"
        if self.action in (ActionType.HOTKEY, ActionType.PRESS_KEY):
            return f"Press {format_keys(self.target_text or '')}"
        verb = {
            ActionType.LEFT_CLICK: "Click",
            ActionType.RIGHT_CLICK: "Right-click",
            ActionType.DOUBLE_CLICK: "Double-click",
        }.get(self.action, "Click")
        if self.target_text:
            return f"{verb} {self.target_text}"
        if self.coordinates:
            return f"{verb} at ({self.coordinates[0]}, {self.coordinates[1]})"
        return verb

    @property
    def coordinates_text(self) -> str | None:
        if self.coordinates is None:
            return None
        return f"{self.coordinates[0]},{self.coordinates[1]}"


@dataclass(slots=True)
class WorkflowSummary:
    id: int
    app_name: str
    task_name: str
    created_at: str
    step_count: int = 0

    @property
    def label(self) -> str:
        return f"{self.app_name}: {self.task_name}"


@dataclass(slots=True)
class Workflow:
    """A saved demonstration: metadata plus ordered steps."""

    id: int | None
    app_name: str
    task_name: str
    created_at: str | None = None
    steps: list[LearnedStep] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.app_name}: {self.task_name}"
