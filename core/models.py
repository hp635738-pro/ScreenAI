"""Shared domain models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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
