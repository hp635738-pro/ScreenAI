"""Learn page: record demonstrations and manage saved workflows."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.models import LearnedStep, WorkflowSummary
from core.vision import MODE_DESKTOP, MODE_WINDOW
from ui.widgets import HintLabel


class LearnPage(QWidget):
    start_recording_requested = Signal()
    stop_recording_requested = Signal()
    save_workflow_requested = Signal(str, str)  # app_name, task_name
    play_workflow_requested = Signal(int)  # workflow id
    capture_mode_changed = Signal(str, int)  # mode, monitor index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._recording = False
        self._step_count = 0
        self._build_ui()
        self._wire()
        self._refresh_buttons()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(8)

        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        # ---- left column: form, transport buttons, recorded steps
        left = QVBoxLayout()
        left.setSpacing(10)

        title = QLabel("Learn")
        title.setObjectName("appTitle")
        subtitle = QLabel("Record a demonstration, then replay it any time")
        subtitle.setObjectName("appSubtitle")
        left.addWidget(title)
        left.addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(8)
        self._app_input = QLineEdit()
        self._app_input.setObjectName("learnField")
        self._app_input.setPlaceholderText("e.g. Firefox")
        self._task_input = QLineEdit()
        self._task_input.setObjectName("learnField")
        self._task_input.setPlaceholderText("e.g. Export report as PDF")
        form.addRow("App Name", self._app_input)
        form.addRow("Task Name", self._task_input)
        left.addLayout(form)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._record_button = QPushButton("Start Recording")
        self._record_button.setObjectName("runButton")
        self._stop_button = QPushButton("Stop")
        self._stop_button.setObjectName("stopButton")
        self._save_button = QPushButton("Save Workflow")
        self._save_button.setObjectName("saveButton")
        buttons.addWidget(self._record_button)
        buttons.addWidget(self._stop_button)
        buttons.addWidget(self._save_button)
        buttons.addStretch(1)
        left.addLayout(buttons)

        steps_label = QLabel("Recorded steps")
        steps_label.setObjectName("fieldLabel")
        left.addWidget(steps_label)
        self._steps_list = QListWidget()
        self._steps_list.setObjectName("stepsList")
        self._steps_list.setMinimumHeight(140)
        left.addWidget(self._steps_list, stretch=1)

        # ---- right column: preview + saved workflows
        right = QVBoxLayout()
        right.setSpacing(10)

        preview_header = QHBoxLayout()
        preview_label = QLabel("Preview")
        preview_label.setObjectName("fieldLabel")
        self._mode_combo = QComboBox()
        self._mode_combo.setObjectName("captureMode")
        preview_header.addWidget(preview_label)
        preview_header.addStretch(1)
        preview_header.addWidget(self._mode_combo)
        right.addLayout(preview_header)

        self._preview = QLabel()
        self._preview.setObjectName("previewLabel")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(150)
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._preview.setText("Preview will appear here")
        right.addWidget(self._preview, stretch=1)

        workflows_label = QLabel("Saved Workflows")
        workflows_label.setObjectName("fieldLabel")
        right.addWidget(workflows_label)
        self._workflows_list = QListWidget()
        self._workflows_list.setObjectName("stepsList")
        self._workflows_list.setMinimumHeight(120)
        right.addWidget(self._workflows_list)

        self._play_button = QPushButton("Play")
        self._play_button.setObjectName("restoreButton")
        right.addWidget(self._play_button)

        root.addLayout(left, stretch=1)
        root.addLayout(right, stretch=1)

        outer.addLayout(root)

        self._hint = HintLabel("Double-click a saved workflow to play it.")
        self._hint.setMinimumHeight(18)
        outer.addWidget(self._hint)

    def _wire(self) -> None:
        self._record_button.clicked.connect(self.start_recording_requested)
        self._stop_button.clicked.connect(self.stop_recording_requested)
        self._save_button.clicked.connect(self._emit_save)
        self._play_button.clicked.connect(self._emit_play)
        self._workflows_list.itemDoubleClicked.connect(lambda _item: self._emit_play())
        self._mode_combo.currentIndexChanged.connect(self._emit_mode)

    # ------------------------------------------------------------- signals

    @Slot()
    def _emit_save(self) -> None:
        app_name = self._app_input.text().strip()
        task_name = self._task_input.text().strip()
        if not app_name or not task_name:
            self.show_message("Enter both App Name and Task Name before saving.")
            return
        self.save_workflow_requested.emit(app_name, task_name)

    @Slot()
    def _emit_play(self) -> None:
        workflow_id = self.selected_workflow_id()
        if workflow_id is None:
            self.show_message("Select a saved workflow to play.")
            return
        self.play_workflow_requested.emit(workflow_id)

    @Slot()
    def _emit_mode(self) -> None:
        mode, monitor = self.current_capture_mode()
        self.capture_mode_changed.emit(mode, monitor)

    # ----------------------------------------------------------- interface

    def set_recording(self, active: bool) -> None:
        self._recording = active
        self._refresh_buttons()

    def set_steps(self, steps: list[LearnedStep]) -> None:
        self._step_count = len(steps)
        self._steps_list.clear()
        for step in steps:
            self._steps_list.addItem(QListWidgetItem(step.description))
        self._refresh_buttons()

    def set_workflows(self, workflows: list[WorkflowSummary]) -> None:
        self._workflows_list.clear()
        for workflow in workflows:
            item = QListWidgetItem(
                f"{workflow.label} — {workflow.step_count} steps"
            )
            item.setData(Qt.ItemDataRole.UserRole, workflow.id)
            self._workflows_list.addItem(item)

    def selected_workflow_id(self) -> int | None:
        item = self._workflows_list.currentItem()
        return int(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def set_preview(self, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image)
        target_width = max(160, self._preview.width())
        self._preview.setPixmap(
            pixmap.scaledToWidth(
                target_width, Qt.TransformationMode.SmoothTransformation
            )
        )

    def set_monitor_options(self, monitors: list[dict]) -> None:
        self._mode_combo.blockSignals(True)
        self._mode_combo.clear()
        self._mode_combo.addItem("All monitors", (MODE_DESKTOP, 0))
        self._mode_combo.addItem("Active window", (MODE_WINDOW, 0))
        for monitor in monitors:
            if monitor["index"] == 0:
                continue
            label = (
                f"Monitor {monitor['index']} "
                f"({monitor['width']}×{monitor['height']})"
            )
            self._mode_combo.addItem(label, (MODE_DESKTOP, monitor["index"]))
        self._mode_combo.blockSignals(False)

    def current_capture_mode(self) -> tuple[str, int]:
        data = self._mode_combo.currentData()
        return data if data else (MODE_DESKTOP, 0)

    def show_message(self, text: str) -> None:
        self._hint.show_temporary(text)

    def _refresh_buttons(self) -> None:
        self._record_button.setEnabled(not self._recording)
        self._stop_button.setEnabled(self._recording)
        self._save_button.setEnabled(not self._recording and self._step_count > 0)
