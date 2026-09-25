"""Reusable settings panel: AI · Automation · Vision · Voice · Interface · Security.

Embedded both in the Settings dialog and in the main window's Settings
section. UI only — persistence stays in :class:`core.settings.SettingsStore`.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.providers import OllamaProvider
from core.settings import (
    AUTOMATION_BACKEND_OPTIONS,
    CONFIRM_OPTIONS,
    POPUP_OPTIONS,
    PRIVACY_OPTIONS,
    PROVIDER_OPTIONS,
    VOICE_PROVIDER_OPTIONS,
    SettingsStore,
)

PROVIDER_LABELS = {
    "openai": "OpenAI (cloud)",
    "ollama": "Local / Ollama",
    "auto": "Auto (local first)",
}
PRIVACY_LABELS = {
    "local_only": "Local only — never send data to the cloud",
    "allow_cloud": "Allow cloud AI",
    "ask_before_cloud": "Ask before cloud use",
}
CONFIRM_LABELS = {
    "always": "Always ask",
    "required_only": "Ask when required",
    "never": "Never ask (purchases/external actions still always ask)",
}
BACKEND_LABELS = {
    "auto": "Auto (pyautogui / xdotool)",
    "pyautogui": "pyautogui",
    "xdotool": "xdotool",
}
POPUP_LABELS = {
    "auto": "Show during tasks",
    "quiet": "Notices only",
    "off": "Never show",
}
VOICE_LABELS = {
    "none": "Disabled (typing only)",
    "whisper": "Whisper (experimental)",
}


class SettingsPanel(QWidget):
    saved = Signal()
    models_arrived = Signal(list, str)
    clear_credentials_requested = Signal()
    clear_history_requested = Signal()
    export_diagnostics_requested = Signal()

    def __init__(
        self,
        settings: SettingsStore,
        voice_providers: list[str] | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._build_ui(voice_providers or list(VOICE_PROVIDER_OPTIONS))
        self._load()
        self.models_arrived.connect(self._apply_models)

    # ------------------------------------------------------------------ UI

    def _build_ui(self, voice_providers: list[str]) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("settingsTabs")
        self._tabs.addTab(self._build_ai_tab(), "AI")
        self._tabs.addTab(self._build_automation_tab(), "Automation")
        self._tabs.addTab(self._build_vision_tab(), "Vision")
        self._tabs.addTab(self._build_voice_tab(voice_providers), "Voice")
        self._tabs.addTab(self._build_interface_tab(), "Interface")
        self._tabs.addTab(self._build_security_tab(), "Security")
        outer.addWidget(self._tabs)

    def _build_ai_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        engine = QGroupBox("AI Engine")
        engine.setObjectName("settingsGroup")
        form = QFormLayout(engine)

        self._provider = QComboBox()
        for value in PROVIDER_OPTIONS:
            self._provider.addItem(PROVIDER_LABELS[value], value)
        form.addRow("Provider", self._provider)

        self._model_openai = QLineEdit()
        self._model_openai.setPlaceholderText("e.g. gpt-4o-mini")
        form.addRow("Model (OpenAI)", self._model_openai)

        model_row = QHBoxLayout()
        self._model_ollama = QComboBox()
        self._model_ollama.setEditable(True)
        self._model_ollama.setPlaceholderText("e.g. llama3.2")
        self._refresh_models = QPushButton("Refresh")
        self._refresh_models.setToolTip("List models from the running Ollama instance")
        model_row.addWidget(self._model_ollama, stretch=1)
        model_row.addWidget(self._refresh_models)
        form.addRow("Model (Ollama)", model_row)

        self._ollama_host = QLineEdit()
        self._ollama_host.setPlaceholderText("http://localhost:11434")
        form.addRow("Ollama host", self._ollama_host)

        self._ollama_status = QLabel("")
        self._ollama_status.setObjectName("keyStatus")
        form.addRow("Ollama status", self._ollama_status)

        key_row = QHBoxLayout()
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("sk-… (stored in a 0600 file, never shown again)")
        self._clear_key = QPushButton("Remove saved key")
        key_row.addWidget(self._api_key, stretch=1)
        key_row.addWidget(self._clear_key)
        form.addRow("OpenAI API key", key_row)

        self._key_status = QLabel("")
        self._key_status.setObjectName("keyStatus")
        form.addRow("Saved key", self._key_status)

        privacy_box = QGroupBox("Privacy")
        privacy_box.setObjectName("settingsGroup")
        privacy_form = QFormLayout(privacy_box)
        self._privacy = QComboBox()
        for value in PRIVACY_OPTIONS:
            self._privacy.addItem(PRIVACY_LABELS[value], value)
        privacy_form.addRow("Cloud AI", self._privacy)

        outer.addWidget(engine)
        outer.addWidget(privacy_box)
        outer.addStretch(1)

        self._provider.currentIndexChanged.connect(self._on_provider_changed)
        self._refresh_models.clicked.connect(self._fetch_models)
        self._clear_key.clicked.connect(self._clear_api_key)
        return page

    def _build_automation_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        group = QGroupBox("Desktop automation")
        group.setObjectName("settingsGroup")
        form = QFormLayout(group)

        self._backend = QComboBox()
        for value in AUTOMATION_BACKEND_OPTIONS:
            self._backend.addItem(BACKEND_LABELS[value], value)
        form.addRow("Automation backend", self._backend)

        self._typing_speed = QSpinBox()
        self._typing_speed.setRange(1, 200)
        self._typing_speed.setSuffix(" ms")
        form.addRow("Typing speed (per key)", self._typing_speed)

        self._action_delay = QDoubleSpinBox()
        self._action_delay.setRange(0.0, 5.0)
        self._action_delay.setSingleStep(0.05)
        self._action_delay.setSuffix(" s")
        form.addRow("Action delay", self._action_delay)

        self._confirm_policy = QComboBox()
        for value in CONFIRM_OPTIONS:
            self._confirm_policy.addItem(CONFIRM_LABELS[value], value)
        form.addRow("Confirmation behavior", self._confirm_policy)

        outer.addWidget(group)
        outer.addStretch(1)
        return page

    def _build_vision_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        group = QGroupBox("Vision")
        group.setObjectName("settingsGroup")
        form = QFormLayout(group)

        self._ocr_enabled = QCheckBox("Enable OCR text finding (find_text)")
        form.addRow(self._ocr_enabled)

        self._screenshot_interval = QSpinBox()
        self._screenshot_interval.setRange(100, 10_000)
        self._screenshot_interval.setSuffix(" ms")
        form.addRow("Screenshot interval", self._screenshot_interval)

        self._active_window = QCheckBox("Active-window capture only")
        form.addRow(self._active_window)

        self._screenshots = QCheckBox(
            "Keep screenshot history (off = screenshots are never stored)"
        )
        form.addRow(self._screenshots)

        outer.addWidget(group)
        outer.addStretch(1)
        return page

    def _build_voice_tab(self, voice_providers: list[str]) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        group = QGroupBox("Voice input")
        group.setObjectName("settingsGroup")
        form = QFormLayout(group)

        self._voice_provider = QComboBox()
        for value in voice_providers:
            self._voice_provider.addItem(VOICE_LABELS.get(value, value), value)
        form.addRow("Voice provider", self._voice_provider)

        self._microphone = QComboBox()
        self._microphone.setEditable(True)
        self._microphone.setPlaceholderText("default")
        form.addRow("Microphone", self._microphone)

        self._ptt = QCheckBox("Push-to-talk (hold the mic button to speak)")
        form.addRow(self._ptt)

        hint = QLabel(
            "Voice is optional — if no engine is available everything else keeps working."
        )
        hint.setObjectName("keyStatus")
        hint.setWordWrap(True)
        form.addRow(hint)

        outer.addWidget(group)
        outer.addStretch(1)
        return page

    def _build_interface_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        group = QGroupBox("Interface")
        group.setObjectName("settingsGroup")
        form = QFormLayout(group)

        self._theme = QComboBox()
        self._theme.addItem("Dark (ScreenAI)", "dark")
        form.addRow("Theme", self._theme)

        self._close_to_tray = QCheckBox("Minimize to tray when closing the window")
        self._close_to_tray.setToolTip(
            "When off, closing the window quits ScreenAI."
        )
        form.addRow("Close to tray", self._close_to_tray)

        self._popup_behavior = QComboBox()
        for value in POPUP_OPTIONS:
            self._popup_behavior.addItem(POPUP_LABELS[value], value)
        form.addRow("Execution popup", self._popup_behavior)

        outer.addWidget(group)
        outer.addStretch(1)
        return page

    def _build_security_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        group = QGroupBox("Security")
        group.setObjectName("settingsGroup")
        form = QFormLayout(group)

        note = QLabel(
            "Confirmation policy lives in Automation → Confirmation behavior. "
            "Consequential external actions (purchases, messages, form submissions) "
            "always require confirmation. Dangerous system operations are blocked."
        )
        note.setObjectName("keyStatus")
        note.setWordWrap(True)
        form.addRow(note)

        self._clear_credentials = QPushButton("Clear stored credentials")
        self._clear_credentials.setObjectName("dangerButton")
        self._clear_credentials.setToolTip("Remove the saved API key from this machine")
        form.addRow(self._clear_credentials)

        self._clear_history = QPushButton("Clear agent history")
        self._clear_history.setObjectName("dangerButton")
        self._clear_history.setToolTip("Delete all agent sessions and tool logs")
        form.addRow(self._clear_history)

        self._export_diagnostics = QPushButton("Export diagnostic report…")
        self._export_diagnostics.setToolTip(
            "Write a support report (never contains keys or passwords)"
        )
        form.addRow(self._export_diagnostics)

        outer.addWidget(group)
        outer.addStretch(1)

        self._clear_credentials.clicked.connect(self.clear_credentials_requested)
        self._clear_history.clicked.connect(self.clear_history_requested)
        self._export_diagnostics.clicked.connect(self.export_diagnostics_requested)
        return page

    # ----------------------------------------------------------- behaviour

    def _load(self) -> None:
        values = self._settings.all()
        self._select(self._provider, str(values["provider"]))
        self._model_openai.setText(str(values["model_openai"]))
        self._model_ollama.setEditText(str(values["model_ollama"]))
        self._ollama_host.setText(str(values["ollama_host"]))
        self._select(self._privacy, str(values["privacy"]))
        self._select(self._confirm_policy, str(values["confirm_policy"]))
        self._select(self._backend, str(values["automation_backend"]))
        self._typing_speed.setValue(int(values["typing_speed_ms"]))
        self._action_delay.setValue(int(values["action_delay_ms"]) / 1000.0)
        self._ocr_enabled.setChecked(bool(values["ocr_enabled"]))
        self._screenshot_interval.setValue(int(values["screenshot_interval_ms"]))
        self._active_window.setChecked(bool(values["active_window_only"]))
        self._screenshots.setChecked(bool(values["screenshot_history"]))
        self._select(self._voice_provider, str(values["voice_provider"]))
        self._microphone.setEditText(str(values["voice_microphone"]))
        self._ptt.setChecked(bool(values["push_to_talk"]))
        self._select(self._theme, str(values["theme"]))
        self._close_to_tray.setChecked(bool(values["close_to_tray"]))
        self._select(self._popup_behavior, str(values["popup_behavior"]))
        masked = self._settings.masked_api_key()
        self._key_status.setText(f"Saved: {masked}" if masked else "No key saved")
        self._on_provider_changed()

    @staticmethod
    def _select(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _on_provider_changed(self) -> None:
        cloud = self._provider.currentData() in ("openai", "auto")
        self._model_openai.setEnabled(cloud)
        self._api_key.setEnabled(cloud)

    def collect(self) -> dict:
        return {
            "provider": self._provider.currentData(),
            "model_openai": self._model_openai.text().strip() or "gpt-4o-mini",
            "model_ollama": self._model_ollama.currentText().strip() or "llama3.2",
            "ollama_host": self._ollama_host.text().strip() or "http://localhost:11434",
            "privacy": self._privacy.currentData(),
            "confirm_policy": self._confirm_policy.currentData(),
            "automation_backend": self._backend.currentData(),
            "typing_speed_ms": self._typing_speed.value(),
            "action_delay_ms": int(self._action_delay.value() * 1000),
            "ocr_enabled": self._ocr_enabled.isChecked(),
            "screenshot_interval_ms": self._screenshot_interval.value(),
            "active_window_only": self._active_window.isChecked(),
            "screenshot_history": self._screenshots.isChecked(),
            "voice_provider": self._voice_provider.currentData(),
            "voice_microphone": self._microphone.currentText().strip() or "default",
            "push_to_talk": self._ptt.isChecked(),
            "theme": self._theme.currentData(),
            "close_to_tray": self._close_to_tray.isChecked(),
            "popup_behavior": self._popup_behavior.currentData(),
        }

    def apply(self) -> dict:
        values = self.collect()
        self._settings.update(values)
        self._settings.save()
        key = self._api_key.text().strip()
        if key:
            self._settings.set_api_key(key)
        self._api_key.clear()
        masked = self._settings.masked_api_key()
        self._key_status.setText(f"Saved: {masked}" if masked else "No key saved")
        self.saved.emit()
        return values

    def _fetch_models(self) -> None:
        self._ollama_status.setText("Contacting Ollama…")
        host = self._ollama_host.text().strip() or "http://localhost:11434"

        def work() -> None:
            try:
                names = OllamaProvider(base_url=host).models()
                text = (
                    "Available: " + ", ".join(names[:8]) if names else "No models found."
                )
            except Exception:  # noqa: BLE001
                names, text = [], "Ollama unreachable — is `ollama serve` running?"
            self.models_arrived.emit(names, text)

        threading.Thread(target=work, daemon=True).start()

    def _apply_models(self, names: list, text: str) -> None:
        self._ollama_status.setText(text)
        current = self._model_ollama.currentText()
        self._model_ollama.clear()
        self._model_ollama.addItems(names)
        self._model_ollama.setEditText(current or (names[0] if names else ""))

    def _clear_api_key(self) -> None:
        self._settings.clear_api_key()
        self._api_key.clear()
        self._key_status.setText("No key saved")
