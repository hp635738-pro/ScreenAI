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
