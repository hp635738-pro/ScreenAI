"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.models import TaskState
from ui.widgets import HintLabel, StatusIndicator


class MainWindow(QMainWindow):
    run_requested = Signal(str)
    voice_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._positioned = False
        self._settings = QSettings()

        self.setWindowTitle(Config.APP_NAME)
        self.setMinimumSize(Config.WINDOW_MIN_WIDTH, Config.WINDOW_MIN_HEIGHT)
        self.resize(620, 380)
        self._restore_geometry()

        self.setCentralWidget(self._build_ui())
        self._wire()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title = QLabel(Config.APP_NAME)
        title.setObjectName("appTitle")
        subtitle = QLabel("Command launcher · Milestone 1")
        subtitle.setObjectName("appSubtitle")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)

        self._status = StatusIndicator()
        header.addWidget(self._status, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        field_label = QLabel("Command")
        field_label.setObjectName("fieldLabel")
        layout.addWidget(field_label)

        self._command_input = QLineEdit()
        self._command_input.setObjectName("commandInput")
        self._command_input.setPlaceholderText(
            "Enter a command… e.g. “Summarize the text on screen”"
        )
        self._command_input.setClearButtonEnabled(True)
        layout.addWidget(self._command_input)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)

        self._voice_button = QPushButton("Voice")
        self._voice_button.setObjectName("voiceButton")
        self._voice_button.setIcon(QIcon(str(Config.asset_path("icons", "mic.svg"))))
        self._voice_button.setToolTip("Voice input — placeholder in this milestone")

        self._run_button = QPushButton("Run")
        self._run_button.setObjectName("runButton")
        self._run_button.setIcon(QIcon(str(Config.asset_path("icons", "run.svg"))))
        self._run_button.setDefault(True)

        buttons.addWidget(self._voice_button)
        buttons.addWidget(self._run_button)
        layout.addLayout(buttons)

        layout.addStretch(1)

        self._hint = HintLabel(
            "AI providers are not connected yet — executions are simulated."
        )
        self._hint.setMinimumHeight(18)
        layout.addWidget(self._hint)

        return root

    def _wire(self) -> None:
        self._run_button.clicked.connect(self._emit_run)
        self._voice_button.clicked.connect(self.voice_requested)
        self._command_input.returnPressed.connect(self._emit_run)

    # ------------------------------------------------------------- signals

    @Slot()
    def _emit_run(self) -> None:
        self.run_requested.emit(self.command())

    # ----------------------------------------------------------- interface

    def command(self) -> str:
        return self._command_input.text()

    def set_state(self, state: TaskState) -> None:
        self._status.set_state(state)
        self._run_button.setEnabled(state is not TaskState.WORKING)

    def show_notice(self, text: str) -> None:
        self._hint.show_temporary(text)

    def minimize(self) -> None:
        self.showMinimized()

    def restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def save_geometry(self) -> None:
        self._settings.setValue("main/geometry", self.saveGeometry())

    # ------------------------------------------------------------- window

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        if not self._positioned:
            self._positioned = True
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen is not None and not self._settings.contains("main/geometry"):
                frame = self.frameGeometry()
                frame.moveCenter(screen.availableGeometry().center())
                self.move(frame.topLeft())

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt naming)
        self.save_geometry()
        # Closing the main window ends the session even if the popup is open.
        QGuiApplication.instance().quit()
        event.accept()

    def _restore_geometry(self) -> None:
        geometry = self._settings.value("main/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
