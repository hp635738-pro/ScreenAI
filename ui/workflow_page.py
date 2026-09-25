"""Workflow manager: view, search, rename, delete, run, learn."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import WorkflowSummary


class WorkflowPage(QWidget):
    run_requested = Signal(int)  # workflow id
    rename_requested = Signal(int, str, str)  # id, app name, task name
    delete_requested = Signal(int)
    learn_requested = Signal()
    search_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Workflows")
        title.setObjectName("sectionTitle")
        self._search = QLineEdit()
        self._search.setObjectName("searchInput")
        self._search.setPlaceholderText("Search workflows…")
        self._search.setClearButtonEnabled(True)
        self._learn_button = QPushButton("Enter Learn Mode")
        self._learn_button.setToolTip("Record a new workflow from your actions")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self._search)
        header.addWidget(self._learn_button)
        layout.addLayout(header)

        self._table = QTreeWidget()
        self._table.setObjectName("workflowTable")
        self._table.setColumnCount(4)
        self._table.setHeaderLabels(["Application", "Workflow", "Steps", "Created"])
        self._table.setRootIsDecorated(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        header_view = self._table.header()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, stretch=1)

        buttons = QHBoxLayout()
        self._run_button = QPushButton("Run")
        self._run_button.setObjectName("runButton")
        self._rename_button = QPushButton("Rename")
        self._delete_button = QPushButton("Delete")
        self._delete_button.setObjectName("dangerButton")
        buttons.addWidget(self._run_button)
        buttons.addWidget(self._rename_button)
        buttons.addWidget(self._delete_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._search.textChanged.connect(self.search_changed)
        self._learn_button.clicked.connect(self.learn_requested)
        self._run_button.clicked.connect(self._emit_run)
        self._rename_button.clicked.connect(self._emit_rename)
        self._delete_button.clicked.connect(self._emit_delete)
        self._table.itemDoubleClicked.connect(lambda *_: self._emit_run())

    # ------------------------------------------------------------- actions

    def selected_id(self) -> int | None:
        item = self._table.currentItem()
        return int(item.data(0, Qt.ItemDataRole.UserRole)) if item else None

    def _emit_run(self) -> None:
        workflow_id = self.selected_id()
        if workflow_id is not None:
            self.run_requested.emit(workflow_id)

    def _emit_rename(self) -> None:
        workflow_id = self.selected_id()
        if workflow_id is None:
            return
        item = self._table.currentItem()
        current_app = item.text(0)
        current_task = item.text(1)
        app_name, ok = QInputDialog.getText(
            self, "Rename workflow", "Application:", text=current_app
        )
        if not ok:
            return
        task_name, ok = QInputDialog.getText(
            self, "Rename workflow", "Workflow name:", text=current_task
        )
        if ok:
            self.rename_requested.emit(workflow_id, app_name.strip(), task_name.strip())

    def _emit_delete(self) -> None:
        workflow_id = self.selected_id()
        if workflow_id is None:
            return
        item = self._table.currentItem()
        answer = QMessageBox.question(
            self,
            "Delete workflow",
            f"Delete “{item.text(0)}: {item.text(1)}”?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(workflow_id)

    # ------------------------------------------------------------ content

    def set_workflows(self, items: list[WorkflowSummary]) -> None:
        selected = self.selected_id()
        self._table.clear()
        restore = None
        for summary in items:
            row = QTreeWidgetItem(
                [
                    summary.app_name,
                    summary.task_name,
                    str(summary.step_count),
                    str(summary.created_at or "")[:19].replace("T", " "),
                ]
            )
            row.setData(0, Qt.ItemDataRole.UserRole, summary.id)
            self._table.addTopLevelItem(row)
            if summary.id == selected:
                restore = row
        if restore is not None:
            self._table.setCurrentItem(restore)
