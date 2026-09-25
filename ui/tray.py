"""System tray integration: show, pause, stop, settings, quit.

Thin Qt wrapper — behaviour lives in the application controller, which
connects to the exposed QActions.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from core.config import Config
from core.version import APP_NAME, VERSION


class AppTray:
    """Owns the tray icon and its menu (no business logic)."""

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        self._icon = QSystemTrayIcon(
            QIcon(str(Config.asset_path("icons", "screenai.svg"))), parent
        )
        self._icon.setToolTip(f"{APP_NAME} {VERSION}")
        self._menu = QMenu(parent)

        self.action_show = QAction("Show ScreenAI", self._menu)
        self.action_pause = QAction("Pause Agent", self._menu)
        self.action_stop = QAction("Stop Current Task", self._menu)
        self.action_settings = QAction("Settings", self._menu)
        self.action_quit = QAction("Quit ScreenAI", self._menu)

        self._menu.addAction(self.action_show)
        self._menu.addSeparator()
        self._menu.addAction(self.action_pause)
        self._menu.addAction(self.action_stop)
        self._menu.addSeparator()
        self._menu.addAction(self.action_settings)
        self._menu.addSeparator()
        self._menu.addAction(self.action_quit)
        self._icon.setContextMenu(self._menu)

    # ---------------------------------------------------------- lifecycle

    @property
    def icon(self) -> QSystemTrayIcon:
        return self._icon

    @property
    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        if self.available:
            self._icon.show()

    def hide(self) -> None:
        self._icon.hide()

    def set_paused(self, paused: bool) -> None:
        self.action_pause.setText("Resume Agent" if paused else "Pause Agent")

    def notify(self, title: str, message: str) -> None:
        if self.available:
            self._icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
