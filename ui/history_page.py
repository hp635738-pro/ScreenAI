"""History page: what ran, when, how it went (no sensitive data)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.history import HistoryEntry

_STATUS_LABELS = (("all", "All"), ("success", "Success"), ("failed", "Failed"))


class HistoryPage(QWidget):
    filter_requested = Signal(str, str)  # search text, status filter
    clear_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("History")
        title.setObjectName("sectionTitle")
        self._search = QLineEdit()
        self._search.setObjectName("searchInput")
        self._search.setPlaceholderText("Search tasks…")
        self._search.setClearButtonEnabled(True)
        self._filter = QComboBox()
        for value, label in _STATUS_LABELS:
            self._filter.addItem(label, value)
        self._clear_button = QPushButton("Clear history")
        self._clear_button.setObjectName("dangerButton")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self._search)
        header.addWidget(self._filter)
        header.addWidget(self._clear_button)
        layout.addLayout(header)

        self._table = QTreeWidget()
        self._table.setObjectName("historyTable")
        self._table.setColumnCount(6)
        self._table.setHeaderLabels(
            ["Date/time", "Task", "Provider", "Duration", "Result", "Success"]
        )
        self._table.setRootIsDecorated(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        header_view = self._table.header()
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, stretch=1)

        self._search.textChanged.connect(self._emit_filter)
        self._filter.currentIndexChanged.connect(self._emit_filter)
        self._clear_button.clicked.connect(self._confirm_clear)

    def _emit_filter(self, *_args) -> None:
        self.filter_requested.emit(self._search.text().strip(), self._filter.currentData())

    def _confirm_clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear history",
            "Delete all task history?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_requested.emit()

    # ------------------------------------------------------------ content

    def set_entries(self, entries: list[HistoryEntry]) -> None:
        self._table.setSortingEnabled(False)
        self._table.clear()
        for entry in entries:
            if entry.success is True:
                success_text = "Success"
            elif entry.success is False:
                success_text = "Failed"
            else:
                success_text = "—"
            item = QTreeWidgetItem(
                [
                    entry.when[:19].replace("T", " "),
                    entry.task,
                    entry.provider,
                    f"{entry.duration:.1f}s" if entry.duration else "—",
                    entry.result,
                    success_text,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, entry.success)
            self._table.addTopLevelItem(item)
        self._table.setSortingEnabled(True)
