"""Settings dialog wrapping the shared SettingsPanel (Milestone 4 API kept)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QVBoxLayout

from core.safety import SafetyManager
from core.settings import SettingsStore
from ui.settings_panel import SettingsPanel


class SettingsDialog(QDialog):
    saved = Signal()
    models_arrived = Signal(list, str)

    def __init__(
        self,
        settings: SettingsStore,
        safety: SafetyManager,
        parent=None,  # noqa: ANN001
        *,
        voice_providers: list[str] | None = None,
        on_clear_history: Callable[[], object] | None = None,
        on_export_diagnostics: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._safety = safety
        self._on_clear_history = on_clear_history
        self._on_export_diagnostics = on_export_diagnostics
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 480)
        self._build_ui(voice_providers)

    def _build_ui(self, voice_providers: list[str] | None) -> None:
        outer = QVBoxLayout(self)
        self._panel = SettingsPanel(self._settings, voice_providers, parent=self)
        outer.addWidget(self._panel, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.models_arrived.connect(self._apply_models)
        self._panel.models_arrived.connect(self.models_arrived)
        self._panel.clear_credentials_requested.connect(self._clear_credentials)
        self._panel.clear_history_requested.connect(self._confirm_clear_history)
        self._panel.export_diagnostics_requested.connect(self._export_diagnostics)

    # ------------------------------------------------- compat (M4 surface)

    def _load(self) -> None:
        self._panel._load()

    @staticmethod
    def _select(combo, value) -> None:  # noqa: ANN001
        SettingsPanel._select(combo, value)

    def _apply_models(self, names: list, text: str) -> None:
        self._panel._apply_models(names, text)

    def _clear_api_key(self) -> None:
        self._panel._clear_api_key()

    # ----------------------------------------------------------- behaviour

    def _save(self) -> None:
        self._panel.apply()
        self._safety.configure(confirm_policy=str(self._settings.get("confirm_policy")))
        self.saved.emit()
        self.accept()

    def _clear_credentials(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear stored credentials",
            "Remove the saved API key from this machine?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._settings.clear_api_key()
            self._panel._load()

    def _confirm_clear_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear agent history",
            "Delete all agent sessions and tool logs?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes and self._on_clear_history:
            self._on_clear_history()

    def _export_diagnostics(self) -> None:
        if self._on_export_diagnostics:
            self._on_export_diagnostics()
