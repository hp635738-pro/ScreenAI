"""AI / Chat page: the conversation with the agent."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.version import APP_NAME


class ChatPage(QWidget):
    run_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("AI conversation")
        title.setObjectName("sectionTitle")
        self._provider_label = QLabel("")
        self._provider_label.setObjectName("keyStatus")
        self._provider_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self._provider_label)
        layout.addLayout(header)

        self._transcript = QPlainTextEdit()
        self._transcript.setObjectName("chatTranscript")
        self._transcript.setReadOnly(True)
        self._transcript.setPlaceholderText(
            "Ask anything — the agent reports its steps here."
        )
        font = QFont("monospace")
        self._transcript.setFont(font)
        layout.addWidget(self._transcript, stretch=1)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setObjectName("commandInput")
        self._input.setPlaceholderText("Command…")
        self._input.setClearButtonEnabled(True)
        self._send = QPushButton("Run")
        self._send.setObjectName("runButton")
        self._send.setDefault(True)
        row.addWidget(self._input, stretch=1)
        row.addWidget(self._send)
        layout.addLayout(row)

        self._send.clicked.connect(self._emit_run)
        self._input.returnPressed.connect(self._emit_run)

    def _emit_run(self) -> None:
        text = self._input.text().strip()
        if text:
            self.run_requested.emit(text)

    # ----------------------------------------------------------- content

    def set_provider(self, label: str) -> None:
        self._provider_label.setText(label)

    def append_user(self, text: str) -> None:
        self._transcript.appendPlainText(f"{APP_NAME} › task: {text}")

    def append_status(self, text: str) -> None:
        self._transcript.appendPlainText(f"  · {text}")

    def append_tool(self, name: str, ok: bool) -> None:
        mark = "✓" if ok else "✗"
        self._transcript.appendPlainText(f"  {mark} {name}")

    def append_result(self, text: str) -> None:
        self._transcript.appendPlainText(f"  ⇒ {text}")

    def set_command(self, text: str) -> None:
        """Voice transcripts land here for editing before execution."""
        self._input.setText(text)
        self._input.setFocus()
