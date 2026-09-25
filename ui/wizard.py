"""First-run setup wizard (5 steps).

Welcome → AI mode → provider configuration (with Ollama connection
test) → desktop automation capability check → privacy (defaults to the
safer option). Writes nothing until Finish.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.providers import OllamaProvider
from core.safety import SafetyManager
from core.settings import (
    PRIVACY_ALLOW_CLOUD,
    PRIVACY_ASK_BEFORE_CLOUD,
    PRIVACY_LOCAL_ONLY,
    PROVIDER_AUTO,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    SettingsStore,
)
from core.version import APP_NAME, VERSION

PROVIDER_IDS = {0: PROVIDER_OLLAMA, 1: PROVIDER_OPENAI, 2: PROVIDER_AUTO}
PRIVACY_IDS = {
    0: PRIVACY_LOCAL_ONLY,
    1: PRIVACY_ALLOW_CLOUD,
    2: PRIVACY_ASK_BEFORE_CLOUD,
}


class FirstRunWizard(QDialog):
    """Five-step setup shown on first launch (written to settings on Finish)."""

    models_arrived = Signal(list, str)

    def __init__(
        self,
        settings: SettingsStore,
        safety: SafetyManager | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._safety = safety
        self._probe = None  # lazy CapabilityProbe
        self.setWindowTitle(f"{APP_NAME} {VERSION} — First-run setup")
        self.setMinimumSize(520, 440)
        self._build_ui()
        self.models_arrived.connect(self._apply_test_result)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._page_welcome())  # 0
        self._stack.addWidget(self._page_mode())  # 1
        self._stack.addWidget(self._page_provider())  # 2
        self._stack.addWidget(self._page_capabilities())  # 3
        self._stack.addWidget(self._page_privacy())  # 4
        outer.addWidget(self._stack, stretch=1)

        nav = QHBoxLayout()
        self._back = QPushButton("Back")
        self._next = QPushButton("Next")
        self._finish = QPushButton("Finish")
        self._finish.hide()
        nav.addWidget(self._back)
        nav.addStretch(1)
        nav.addWidget(self._next)
        nav.addWidget(self._finish)
        outer.addLayout(nav)

        self._back.clicked.connect(self._go_back)
        self._next.clicked.connect(self._go_next)
        self._finish.clicked.connect(self._finish_wizard)
        self._show_page(0)

    def _page_welcome(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel(f"Welcome to {APP_NAME}")
        title.setObjectName("appTitle")
        body = QLabel(
            f"{APP_NAME} {VERSION} is a personal desktop assistant: it can launch "
            "apps, run terminal commands, drive mouse/keyboard automation, read "
            "the screen and replay learned workflows — all under a strict safety "
            "system.\n\nThis short setup configures the AI backend and privacy."
        )
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(body)
        layout.addStretch(1)
        return page

    def _page_mode(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Choose AI mode")
        title.setObjectName("appTitle")
        layout.addWidget(title)
        self._mode_group = QButtonGroup(self)
        labels = (
            "Local / Ollama — runs on this machine, nothing leaves it",
            "OpenAI — cloud model (needs an API key)",
            "Auto — prefer local, use cloud when allowed",
        )
        for index, label in enumerate(labels):
            button = QRadioButton(label)
            self._mode_group.addButton(button, index)
            layout.addWidget(button)
            if index == 2:
                button.setChecked(True)
        layout.addStretch(1)
        return page

    def _page_provider(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Configure provider")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        openai_label = QLabel("OpenAI")
        openai_label.setObjectName("fieldLabel")
        layout.addWidget(openai_label)
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("API key (sk-…)")
        self._model_openai = QLineEdit("gpt-4o-mini")
        layout.addWidget(self._api_key)
        layout.addWidget(self._model_openai)

        ollama_label = QLabel("Ollama")
        ollama_label.setObjectName("fieldLabel")
        layout.addWidget(ollama_label)
        self._ollama_host = QLineEdit("http://localhost:11434")
        self._model_ollama = QLineEdit("llama3.2")
        layout.addWidget(self._ollama_host)
        layout.addWidget(self._model_ollama)

        test_row = QHBoxLayout()
        self._test_button = QPushButton("Test connection")
        self._test_status = QLabel("")
        self._test_status.setObjectName("keyStatus")
        test_row.addWidget(self._test_button)
        test_row.addWidget(self._test_status, stretch=1)
        layout.addLayout(test_row)
        layout.addStretch(1)
        self._test_button.clicked.connect(self._test_ollama)
        return page

    def _page_capabilities(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Desktop automation check")
        title.setObjectName("appTitle")
        layout.addWidget(title)
        self._cap_table = QTreeWidget()
        self._cap_table.setColumnCount(3)
        self._cap_table.setHeaderLabels(["Capability", "Status", "Detail"])
        self._cap_table.setRootIsDecorated(False)
        self._cap_table.header().setStretchLastSection(True)
        layout.addWidget(self._cap_table, stretch=1)
        note = QLabel("Unavailable capabilities are listed with setup hints.")
        note.setObjectName("keyStatus")
        layout.addWidget(note)
        return page

    def _page_privacy(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Privacy")
        title.setObjectName("appTitle")
        layout.addWidget(title)
        self._privacy_group = QButtonGroup(self)
        labels = (
            "Local only — never send data to the cloud (safest)",
            "Allow cloud AI",
            "Ask before cloud use",
        )
        for index, label in enumerate(labels):
            button = QRadioButton(label)
            self._privacy_group.addButton(button, index)
            layout.addWidget(button)
            if index == 0:
                button.setChecked(True)  # safer default
        layout.addStretch(1)
        return page

    # ----------------------------------------------------------- behaviour

    def _show_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._back.setEnabled(index > 0)
        self._next.setVisible(index < 4)
        self._finish.setVisible(index == 4)
        if index == 3:
            self._populate_capabilities()

    def _go_back(self) -> None:
        self._show_page(max(0, self._stack.currentIndex() - 1))

    def _go_next(self) -> None:
        self._show_page(min(4, self._stack.currentIndex() + 1))

    def _test_ollama(self) -> None:
        self._test_status.setText("Contacting Ollama…")
        host = self._ollama_host.text().strip() or "http://localhost:11434"

        def work() -> None:
            try:
                names = OllamaProvider(base_url=host).models()
                text = (
                    "Connection OK — models: " + ", ".join(names[:6])
                    if names
                    else "Connected, but no models found."
                )
            except Exception:  # noqa: BLE001
                names, text = [], f"Cannot reach {host} — start Ollama (ollama serve)."
            self.models_arrived.emit(names, text)

        threading.Thread(target=work, daemon=True).start()

    def _apply_test_result(self, names: list, text: str) -> None:
        self._test_status.setText(text)

    def _populate_capabilities(self) -> None:
        if self._probe is None:
            from core.capabilities import CapabilityProbe  # noqa: PLC0415

            self._probe = CapabilityProbe()
        self._cap_table.clear()
        for cap in self._probe.detect():
            detail = cap.detail + (f" — {cap.hint}" if cap.hint else "")
            item = QTreeWidgetItem([cap.name, cap.status, detail])
            self._cap_table.addTopLevelItem(item)

    def apply_settings(self) -> dict[str, object]:
        values = {
            "provider": PROVIDER_IDS.get(self._mode_group.checkedId(), PROVIDER_AUTO),
            "privacy": PRIVACY_IDS.get(
                self._privacy_group.checkedId(), PRIVACY_LOCAL_ONLY
            ),
            "model_openai": self._model_openai.text().strip() or "gpt-4o-mini",
            "model_ollama": self._model_ollama.text().strip() or "llama3.2",
            "ollama_host": self._ollama_host.text().strip()
            or "http://localhost:11434",
            "first_run_done": True,
        }
        self._settings.update(values)
        key = self._api_key.text().strip()
        if key:
            self._settings.set_api_key(key)
        self._settings.save()
        return values

    def _finish_wizard(self) -> None:
        self.apply_settings()
        if self._safety is not None:
            self._safety.configure(
                confirm_policy=str(self._settings.get("confirm_policy"))
            )
        self.accept()
