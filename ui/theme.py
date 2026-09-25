"""Dark theme: palette constants and QSS loading.

The stylesheet itself lives in ``assets/qss/dark.qss`` so visual tweaks
do not require touching Python code.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from core.config import Config
from core.models import TaskState


class Palette:
    BACKGROUND = QColor("#14151F")
    SURFACE = QColor("#1B1C2B")
    TEXT = QColor("#E6E7F0")
    MUTED = QColor("#9AA0B4")
    ACCENT = QColor("#5B7CFA")

    STATUS: dict[TaskState, QColor] = {
        TaskState.IDLE: MUTED,
        TaskState.WORKING: QColor("#FBBF24"),
        TaskState.DONE: QColor("#4ADE80"),
        TaskState.ERROR: QColor("#F87171"),
    }

    @classmethod
    def for_state(cls, state: TaskState) -> QColor:
        return cls.STATUS[state]


def load_stylesheet() -> str:
    return Config.asset_path("qss", "dark.qss").read_text(encoding="utf-8")
