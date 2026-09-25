"""Reusable custom widgets."""

from __future__ import annotations

from PySide6.QtCore import QVariantAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.models import TaskState
from ui.theme import Palette


def repolish(widget: QWidget) -> None:
    """Refresh a widget after dynamic QSS properties changed."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


class StatusDot(QWidget):
    """Coloured dot that pulses while a task is running."""

    def __init__(self, diameter: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color: QColor = Palette.for_state(TaskState.IDLE)
        self._opacity = 1.0
        self.setFixedSize(diameter, diameter)

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(1000)
        self._animation.setStartValue(1.0)
        self._animation.setKeyValueAt(0.5, 0.3)
        self._animation.setEndValue(1.0)
        self._animation.setLoopCount(-1)  # loop forever while working
        self._animation.valueChanged.connect(self._on_pulse)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def set_pulsing(self, active: bool) -> None:
        if active:
            self._animation.start()
        else:
            self._animation.stop()
            self._on_pulse(1.0)

    def _on_pulse(self, value: float | object) -> None:
        self._opacity = float(value)  # type: ignore[arg-type]
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))


class StatusIndicator(QWidget):
    """Dot + text status pill shared by the main window and the popup."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = TaskState.IDLE

        self._dot = StatusDot(parent=self)
        self._label = QLabel(TaskState.IDLE.label, self)
        self._label.setObjectName("statusLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._dot)
        layout.addWidget(self._label)

        self.set_state(TaskState.IDLE)

    @property
    def state(self) -> TaskState:
        return self._state

    def set_state(self, state: TaskState) -> None:
        self._state = state
        self._dot.set_color(Palette.for_state(state))
        self._dot.set_pulsing(state is TaskState.WORKING)
        self._label.setText(state.label)
        self._label.setProperty("state", state.value)
        repolish(self._label)


class HintLabel(QLabel):
    """Muted helper line that can flash a temporary message."""

    def __init__(self, default_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(default_text, parent)
        self.setObjectName("hintLabel")
        self._default_text = default_text
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._restore)

    def show_temporary(self, text: str, timeout_ms: int = 3500) -> None:
        self.setText(text)
        self._timer.start(timeout_ms)

    def show_live(self, text: str) -> None:
        """Show a live message without auto-clear (e.g. streamed output)."""
        self._timer.stop()
        self.setText(text)

    def clear(self) -> None:
        self._timer.stop()
        self.setText(self._default_text)

    def _restore(self) -> None:
        self.setText(self._default_text)
