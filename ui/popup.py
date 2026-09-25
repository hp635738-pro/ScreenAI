"""Frameless always-on-top execution popup."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.models import TaskState
from ui.widgets import HintLabel, StatusIndicator


class ExecutionPopup(QWidget):
    pause_requested = Signal()
    stop_requested = Signal()
    restore_requested = Signal()
    dismiss_requested = Signal()
    confirmation_responded = Signal(bool)

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self._drag_offset: QPoint | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(Config.POPUP_WIDTH)

        self._build_ui()
        self._wire()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 18)

        self._card = QFrame()
        self._card.setObjectName("popupCard")

        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 150))
        self._card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("EXECUTION")
        title.setObjectName("popupTitle")
        self._pass_through(title)

        self._dismiss_button = QPushButton("×")
        self._dismiss_button.setObjectName("dismissButton")
        self._dismiss_button.setToolTip("Dismiss popup")
        self._dismiss_button.setFixedSize(28, 28)

        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self._dismiss_button)
        layout.addLayout(header)

        self._task_label = QLabel()
        self._task_label.setObjectName("popupTask")
        self._task_label.setWordWrap(True)
        self._pass_through(self._task_label)
        layout.addWidget(self._task_label)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self._status = StatusIndicator()
        self._pass_through(self._status)

        self._step_label = QLabel()
        self._step_label.setObjectName("stepLabel")
        self._step_label.hide()
        self._pass_through(self._step_label)

        status_row.addWidget(self._status)
        status_row.addStretch(1)
        status_row.addWidget(self._step_label)
        layout.addLayout(status_row)

        self._progress_label = QLabel()
        self._progress_label.setObjectName("progressLabel")
        self._pass_through(self._progress_label)
        layout.addWidget(self._progress_label)

        confirm_row = QHBoxLayout()
        confirm_row.setSpacing(8)
        self._confirm_button = QPushButton("Confirm")
        self._confirm_button.setObjectName("confirmButton")
        self._confirm_button.setToolTip("Approve the pending action")
        self._confirm_button.hide()
        self._decline_button = QPushButton("Cancel")
        self._decline_button.setObjectName("declineButton")
        self._decline_button.setToolTip("Decline the pending action")
        self._decline_button.hide()
        confirm_row.addWidget(self._confirm_button)
        confirm_row.addWidget(self._decline_button)
        confirm_row.addStretch(1)
        layout.addLayout(confirm_row)

        self._confirm_label = QLabel()
        self._confirm_label.setObjectName("confirmLabel")
        self._confirm_label.setWordWrap(True)
        self._confirm_label.hide()
        self._pass_through(self._confirm_label)
        layout.addWidget(self._confirm_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._pause_button = QPushButton("Pause")
        self._pause_button.setObjectName("pauseButton")
        self._pause_button.setToolTip(
            "UI placeholder — real pause arrives with AI integration"
        )
        self._stop_button = QPushButton("Stop")
        self._stop_button.setObjectName("stopButton")
        self._stop_button.setToolTip("Emergency stop — immediately cancels running automation")
        self._restore_button = QPushButton("Restore")
        self._restore_button.setObjectName("restoreButton")
        self._restore_button.setToolTip("Reopen the main window")

        buttons.addWidget(self._pause_button)
        buttons.addWidget(self._stop_button)
        buttons.addStretch(1)
        buttons.addWidget(self._restore_button)
        layout.addLayout(buttons)

        self._notice = HintLabel()
        self._notice.setFixedHeight(18)
        self._pass_through(self._notice)
        layout.addWidget(self._notice)

        outer.addWidget(self._card)

    def _wire(self) -> None:
        self._pause_button.clicked.connect(self.pause_requested)
        self._stop_button.clicked.connect(self.stop_requested)
        self._restore_button.clicked.connect(self.restore_requested)
        self._dismiss_button.clicked.connect(self.dismiss_requested)
        self._confirm_button.clicked.connect(lambda: self._respond_confirmation(True))
        self._decline_button.clicked.connect(lambda: self._respond_confirmation(False))
        QShortcut("Esc", self, activated=self.dismiss_requested)

    @staticmethod
    def _pass_through(widget: QWidget) -> None:
        """Let mouse events fall through so the card can be dragged."""
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    # ----------------------------------------------------------- interface

    def begin_task(self, command: str) -> None:
        """Milestone 1 style single task display (simulation path)."""
        self._task_label.setText(command)
        self._task_label.setToolTip(command)
        self._progress_label.setText("Starting…")
        self._step_label.hide()
        self._notice.clear()
        self.set_state(TaskState.WORKING)

    def begin_plan(self, command: str, total_steps: int) -> None:
        """Multi-step plan display: shows 'Step x/N' during execution."""
        self.begin_task(command)
        self.set_step(1, total_steps)

    def set_step(self, index: int, total: int) -> None:
        self._step_label.setText(f"Step {index}/{total}")
        self._step_label.show()

    def set_step_text(self, text: str) -> None:
        self._step_label.setText(text)
        self._step_label.show()

    def begin_recording(self) -> None:
        """Learn Mode: 'Recording… / Click File / Step 4' display."""
        self._task_label.setText("Recording…")
        self._task_label.setToolTip("")
        self._progress_label.setText("Recording…")
        self.set_step_text("Step 0")
        self._notice.clear()
        self.set_state(TaskState.WORKING)

    def update_recording(self, count: int, description: str) -> None:
        self.set_step_text(f"Step {count}")
        self._progress_label.setText(description)

    def begin_playback(self, label: str, total: int) -> None:
        """Workflow playback: 'Playing… / Found Export / Step 6/9' display."""
        self._task_label.setText("Playing…")
        self._task_label.setToolTip(label)
        self._progress_label.setText("Playing…")
        if total > 0:
            self.set_step(1, total)
        else:
            self.set_step_text("Step 0")
        self._notice.clear()
        self.set_state(TaskState.WORKING)

    def update_playback(self, index: int, total: int, message: str) -> None:
        self.set_step(index, total)
        self._progress_label.setText(message)

    def begin_agent(self, command: str) -> None:
        """Agent run: 'ScreenAI' + 'Understanding request…'."""
        self._task_label.setText("ScreenAI")
        self._task_label.setToolTip(command)
        self._progress_label.setText("Understanding request…")
        self.set_step_text("Step 0")
        self._notice.clear()
        self.hide_confirmation()
        self.set_state(TaskState.WORKING)

    def update_agent(self, status: str) -> None:
        self._progress_label.setText(status)

    def show_confirmation(self, prompt: str) -> None:
        """Pause display: 'Waiting for confirmation' + [Confirm] [Cancel]."""
        self._confirm_label.setText(prompt)
        self._confirm_label.show()
        self._confirm_button.show()
        self._decline_button.show()
        self._progress_label.setText("Waiting for confirmation")

    def hide_confirmation(self) -> None:
        self._confirm_label.hide()
        self._confirm_button.hide()
        self._decline_button.hide()

    def _respond_confirmation(self, approved: bool) -> None:
        self.hide_confirmation()
        self._progress_label.setText("Continuing…" if approved else "Stopping…")
        self.confirmation_responded.emit(approved)

    def set_state(self, state: TaskState) -> None:
        self._status.set_state(state)
        active = state is TaskState.WORKING
        self._pause_button.setEnabled(active)
        self._stop_button.setEnabled(active)

    def set_progress(self, text: str) -> None:
        self._progress_label.setText(text)

    def show_notice(self, text: str) -> None:
        self._notice.show_temporary(text)

    def show_live(self, text: str) -> None:
        """Show live streamed output without auto-clear."""
        self._notice.show_live(text)

    def show_popup(self) -> None:
        self._reposition()
        self.show()
        self.raise_()
        self.activateWindow()

    def _reposition(self) -> None:
        self.adjustSize()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.x() + (area.width() - self.width()) // 2
        y = area.y() + 28
        self.move(x, y)

    # -------------------------------------------------------------- drag

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)
