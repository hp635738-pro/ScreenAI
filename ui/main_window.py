"""Main application window (Command and Learn pages)."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.models import TaskState
from ui.learn_page import LearnPage
from ui.widgets import HintLabel, StatusIndicator


class MainWindow(QMainWindow):
    run_requested = Signal(str)
    stop_requested = Signal()
    voice_requested = Signal()
    settings_requested = Signal()
    page_changed = Signal(int)  # 0 = Command, 1 = Learn

    def __init__(self) -> None:
        super().__init__()
        self._positioned = False
        self._settings = QSettings()

        self.setWindowTitle(Config.APP_NAME)
        self.setMinimumSize(Config.WINDOW_MIN_WIDTH, Config.WINDOW_MIN_HEIGHT)
        self.resize(720, 440)
        self._restore_geometry()

        self.setCentralWidget(self._build_ui())
        self._wire()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> QWidget:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 18, 28, 22)
        outer.setSpacing(10)

        nav = QHBoxLayout()
        nav.setSpacing(8)
        self._nav_command = QPushButton("Command")
        self._nav_command.setObjectName("navButton")
        self._nav_command.setCheckable(True)
        self._nav_command.setChecked(True)
        self._nav_learn = QPushButton("Learn")
        self._nav_learn.setObjectName("navButton")
        self._nav_learn.setCheckable(True)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_group.addButton(self._nav_command, 0)
        self._nav_group.addButton(self._nav_learn, 1)
        self._settings_button = QPushButton("Settings")
        self._settings_button.setObjectName("navButton")
        self._settings_button.setToolTip("AI engine, privacy and confirmations")
        nav.addWidget(self._nav_command)
        nav.addWidget(self._nav_learn)
        nav.addStretch(1)
        nav.addWidget(self._settings_button)
        outer.addLayout(nav)

        self._stack = QStackedWidget()
        self._command_page = self._build_command_page()
        self._learn_page = LearnPage()
        self._stack.addWidget(self._command_page)  # index 0
        self._stack.addWidget(self._learn_page)  # index 1
        outer.addWidget(self._stack, stretch=1)

        return root

    def _build_command_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title = QLabel(Config.APP_NAME)
        title.setObjectName("appTitle")
        subtitle = QLabel("AI desktop agent · Milestone 4")
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
            "Ask anything… e.g. “Open Firefox and click Export”"
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

        self._stop_button = QPushButton("Stop")
        self._stop_button.setObjectName("stopButton")
        self._stop_button.setToolTip(
            "Emergency stop — immediately cancel any running automation"
        )
        self._stop_button.setEnabled(False)

        self._run_button = QPushButton("Run")
        self._run_button.setObjectName("runButton")
        self._run_button.setIcon(QIcon(str(Config.asset_path("icons", "run.svg"))))
        self._run_button.setDefault(True)

        buttons.addWidget(self._voice_button)
        buttons.addWidget(self._stop_button)
        buttons.addWidget(self._run_button)
        layout.addLayout(buttons)

        layout.addStretch(1)

        self._hint = HintLabel(
            "Try: Open Firefox · Open Konsole and run pwd · Find the Export button · "
            "Take a screenshot and tell me what is visible"
        )
        self._hint.setMinimumHeight(18)
        layout.addWidget(self._hint)

        return page

    def _wire(self) -> None:
        self._run_button.clicked.connect(self._emit_run)
        self._stop_button.clicked.connect(self.stop_requested)
        self._voice_button.clicked.connect(self.voice_requested)
        self._command_input.returnPressed.connect(self._emit_run)
        self._nav_group.idClicked.connect(self._on_nav_clicked)
        self._settings_button.clicked.connect(self.settings_requested)

    # ------------------------------------------------------------- signals

    @Slot()
    def _emit_run(self) -> None:
        self.run_requested.emit(self.command())

    @Slot(int)
    def _on_nav_clicked(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self.page_changed.emit(index)

    # ----------------------------------------------------------- interface

    @property
    def learn_page(self) -> LearnPage:
        return self._learn_page

    def command(self) -> str:
        return self._command_input.text()

    def set_state(self, state: TaskState) -> None:
        self._status.set_state(state)
        busy = state is TaskState.WORKING
        self._run_button.setEnabled(not busy)
        self._stop_button.setEnabled(busy)

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
