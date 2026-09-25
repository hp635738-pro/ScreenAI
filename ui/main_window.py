"""Main application window: Home · AI/Chat · Learn · Workflows · History · Settings."""

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
from core.settings import SettingsStore
from core.version import APP_NAME, VERSION
from ui.chat_page import ChatPage
from ui.history_page import HistoryPage
from ui.learn_page import LearnPage
from ui.settings_panel import SettingsPanel
from ui.widgets import HintLabel, StatusIndicator
from ui.workflow_page import WorkflowPage


class MainWindow(QMainWindow):
    # Section indices (kept as constants — the controller navigates by them).
    PAGE_HOME = 0
    PAGE_CHAT = 1
    PAGE_LEARN = 2
    PAGE_WORKFLOWS = 3
    PAGE_HISTORY = 4
    PAGE_SETTINGS = 5

    run_requested = Signal(str)
    stop_requested = Signal()
    voice_requested = Signal()  # mic click (legacy)
    voice_ptt_started = Signal()  # mic pressed — push to talk
    voice_ptt_ended = Signal()  # mic released
    settings_requested = Signal()
    settings_saved = Signal()
    page_changed = Signal(int)
    hidden_to_tray = Signal()

    def __init__(self, settings: SettingsStore | None = None) -> None:
        super().__init__()
        self._positioned = False
        self._qsettings = QSettings()
        self._settings = settings
        self._close_to_tray = True

        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.setMinimumSize(Config.WINDOW_MIN_WIDTH, Config.WINDOW_MIN_HEIGHT)
        self.resize(760, 480)
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
        nav.setSpacing(6)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[int, QPushButton] = {}
        labels = {
            self.PAGE_HOME: "Home",
            self.PAGE_CHAT: "AI / Chat",
            self.PAGE_LEARN: "Learn",
            self.PAGE_WORKFLOWS: "Workflows",
            self.PAGE_HISTORY: "History",
            self.PAGE_SETTINGS: "Settings",
        }
        for index, label in labels.items():
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setChecked(index == self.PAGE_HOME)
            self._nav_group.addButton(button, index)
            self._nav_buttons[index] = button
            nav.addWidget(button)
        nav.addStretch(1)
        outer.addLayout(nav)

        self._stack = QStackedWidget()
        self._home_page = self._build_home_page()
        self._chat_page = ChatPage()
        self._learn_page = LearnPage()
        self._workflow_page = WorkflowPage()
        self._history_page = HistoryPage()
        self._settings_page = self._build_settings_page()
        for page in (
            self._home_page,
            self._chat_page,
            self._learn_page,
            self._workflow_page,
            self._history_page,
            self._settings_page,
        ):
            self._stack.addWidget(page)
        outer.addWidget(self._stack, stretch=1)
        return root

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        subtitle = QLabel(f"AI desktop agent · v{VERSION}")
        subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)

        self._provider_label = QLabel("")
        self._provider_label.setObjectName("keyStatus")
        header.addWidget(self._provider_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._status = StatusIndicator()
        header.addWidget(self._status, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        self._task_status = QLabel("Ready")
        self._task_status.setObjectName("keyStatus")
        layout.addWidget(self._task_status)

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
        self._voice_button.setToolTip("Hold to speak (push-to-talk); release to transcribe")

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

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        if self._settings is None:
            placeholder = QLabel("Settings are unavailable (no settings store).")
            layout.addWidget(placeholder)
            return page
        self._settings_panel = SettingsPanel(self._settings, parent=page)
        layout.addWidget(self._settings_panel, stretch=1)
        row = QHBoxLayout()
        self._settings_save = QPushButton("Save settings")
        self._settings_save.setObjectName("runButton")
        row.addStretch(1)
        row.addWidget(self._settings_save)
        layout.addLayout(row)
        self._settings_save.clicked.connect(self._on_settings_save)
        return page

    def _wire(self) -> None:
        self._run_button.clicked.connect(self._emit_run)
        self._stop_button.clicked.connect(self.stop_requested)
        self._voice_button.clicked.connect(self.voice_requested)
        self._voice_button.pressed.connect(self.voice_ptt_started)
        self._voice_button.released.connect(self.voice_ptt_ended)
        self._command_input.returnPressed.connect(self._emit_run)
        self._nav_group.idClicked.connect(self._on_nav_clicked)
        self._chat_page.run_requested.connect(self.run_requested)

    # ------------------------------------------------------------- signals

    @Slot()
    def _emit_run(self) -> None:
        self.run_requested.emit(self.command())

    @Slot(int)
    def _on_nav_clicked(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self.page_changed.emit(index)

    @Slot()
    def _on_settings_save(self) -> None:
        if self._settings is not None:
            self._settings_panel.apply()
            self.settings_saved.emit()
            self.show_notice("Settings saved.")

    # ----------------------------------------------------------- interface

    @property
    def learn_page(self) -> LearnPage:
        return self._learn_page

    @property
    def chat_page(self) -> ChatPage:
        return self._chat_page

    @property
    def workflow_page(self) -> WorkflowPage:
        return self._workflow_page

    @property
    def history_page(self) -> HistoryPage:
        return self._history_page

    @property
    def settings_panel(self) -> SettingsPanel | None:
        return getattr(self, "_settings_panel", None)

    def show_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._nav_buttons[index].setChecked(True)
        self.page_changed.emit(index)

    def show_settings_page(self) -> None:
        self.show_page(self.PAGE_SETTINGS)

    def show_learn_page(self) -> None:
        self.show_page(self.PAGE_LEARN)

    def command(self) -> str:
        return self._command_input.text()

    def set_command_text(self, text: str) -> None:
        """Voice transcripts land here for editing before execution."""
        self._command_input.setText(text)
        self._command_input.setFocus()

    def set_provider_status(self, text: str) -> None:
        self._provider_label.setText(text)
        self._chat_page.set_provider(text)

    def set_task_status(self, text: str) -> None:
        self._task_status.setText(text)

    def set_state(self, state: TaskState) -> None:
        self._status.set_state(state)
        busy = state is TaskState.WORKING
        self._run_button.setEnabled(not busy)
        self._stop_button.setEnabled(busy)

    def show_notice(self, text: str) -> None:
        self._hint.show_temporary(text)

    def set_close_to_tray(self, enabled: bool) -> None:
        self._close_to_tray = enabled

    def minimize(self) -> None:
        self.showMinimized()

    def restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def force_quit(self) -> None:
        QGuiApplication.instance().quit()

    def save_geometry(self) -> None:
        self._qsettings.setValue("main/geometry", self.saveGeometry())

    # ------------------------------------------------------------- window

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        if not self._positioned:
            self._positioned = True
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen is not None and not self._qsettings.contains("main/geometry"):
                frame = self.frameGeometry()
                frame.moveCenter(screen.availableGeometry().center())
                self.move(frame.topLeft())

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt naming)
        self.save_geometry()
        if self._close_to_tray:
            event.ignore()
            self.hide()
            self.hidden_to_tray.emit()
        else:
            self.force_quit()
            event.accept()

    def _restore_geometry(self) -> None:
        geometry = self._qsettings.value("main/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
