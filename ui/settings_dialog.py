"""AI Engine settings: provider, model, privacy, API key, confirmations."""

from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.providers import OllamaProvider
from core.safety import SafetyManager
from core.settings import (
    CONFIRM_OPTIONS,
    PRIVACY_OPTIONS,
    PROVIDER_OPTIONS,
    SettingsStore,
)

_PROVIDER_LABELS = {
    "openai": "OpenAI (cloud)",
    "ollama": "Local / Ollama",
    "auto": "Auto (local first)",
}
_PRIVACY_LABELS = {
    "local_only": "Local only — never send data to the cloud",
    "allow_cloud": "Allow cloud AI",
    "ask_before_cloud": "Ask before cloud use",
}
_CONFIRM_LABELS = {
    "always": "Always ask",
    "required_only": "Ask when required",
    "never": "Never ask (purchases/external actions still always ask)",
}


class SettingsDialog(QDialog):
    saved = Signal()
    models_arrived = Signal(list, str)

    def __init__(
        self,
        settings: SettingsStore,
        safety: SafetyManager,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._safety = safety
        self.setWindowTitle("Settings — AI Engine")
        self.setMinimumWidth(440)
        self._build_ui()
        self._load()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        engine = QGroupBox("AI Engine")
        engine.setObjectName("settingsGroup")
        form = QFormLayout(engine)

        self._provider = QComboBox()
        for value in PROVIDER_OPTIONS:
            self._provider.addItem(_PROVIDER_LABELS[value], value)
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

        outer.addWidget(engine)

        privacy = QGroupBox("Privacy")
        privacy.setObjectName("settingsGroup")
        privacy_form = QFormLayout(privacy)
        self._privacy = QComboBox()
        for value in PRIVACY_OPTIONS:
            self._privacy.addItem(_PRIVACY_LABELS[value], value)
        privacy_form.addRow("Cloud AI", self._privacy)
        outer.addWidget(privacy)

        safety = QGroupBox("Confirmations & history")
        safety.setObjectName("settingsGroup")
        safety_form = QFormLayout(safety)
        self._confirm_policy = QComboBox()
        for value in CONFIRM_OPTIONS:
            self._confirm_policy.addItem(_CONFIRM_LABELS[value], value)
        safety_form.addRow("Confirmations", self._confirm_policy)
        self._screenshots = QCheckBox(
            "Keep screenshot history (off = screenshots are never stored)"
        )
        safety_form.addRow(self._screenshots)
        outer.addWidget(safety)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.models_arrived.connect(self._apply_models)
        self._refresh_models.clicked.connect(self._fetch_models)
        self._clear_key.clicked.connect(self._clear_api_key)
        self._provider.currentIndexChanged.connect(self._on_provider_changed)

    # ----------------------------------------------------------- behaviour

    def _load(self) -> None:
        values = self._settings.all()
        self._select(self._provider, str(values["provider"]))
        self._model_openai.setText(str(values["model_openai"]))
        self._model_ollama.setEditText(str(values["model_ollama"]))
        self._ollama_host.setText(str(values["ollama_host"]))
        self._select(self._privacy, str(values["privacy"]))
        self._select(self._confirm_policy, str(values["confirm_policy"]))
        self._screenshots.setChecked(bool(values["screenshot_history"]))
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
                names, text = [], "Ollama unreachable."
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

    def _save(self) -> None:
        self._settings.update(
            {
                "provider": self._provider.currentData(),
                "model_openai": self._model_openai.text().strip() or "gpt-4o-mini",
                "model_ollama": self._model_ollama.currentText().strip() or "llama3.2",
                "ollama_host": self._ollama_host.text().strip()
                or "http://localhost:11434",
                "privacy": self._privacy.currentData(),
                "confirm_policy": self._confirm_policy.currentData(),
                "screenshot_history": self._screenshots.isChecked(),
            }
        )
        self._settings.save()
        key = self._api_key.text().strip()
        if key:
            self._settings.set_api_key(key)
        self._api_key.clear()
        masked = self._settings.masked_api_key()
        self._key_status.setText(f"Saved: {masked}" if masked else "No key saved")
        self._safety.configure(
            confirm_policy=str(self._settings.get("confirm_policy"))
        )
        self.saved.emit()
        self.accept()
