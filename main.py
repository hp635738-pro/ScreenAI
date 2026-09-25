#!/usr/bin/env python3
"""ScreenAI — desktop entry point."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.config import Config
from core.controller import ApplicationController
from core.logging_setup import setup_logging
from core.version import APP_NAME
from ui.theme import load_stylesheet


def create_application() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(Config.ORG_NAME)
    app.setApplicationVersion(Config.VERSION)
    app.setDesktopFileName(APP_NAME.lower())
    # Fusion keeps widget styling consistent regardless of the desktop theme.
    app.setStyle("Fusion")
    app.setStyleSheet(load_stylesheet())
    app.setWindowIcon(QIcon(str(Config.asset_path("icons", "screenai.svg"))))
    return app


def main() -> int:
    log = setup_logging(Config.data_dir())
    app = create_application()
    sys.excepthook = lambda etype, value, tb: log.critical(
        "unhandled exception", exc_info=(etype, value, tb)
    )
    controller = ApplicationController()
    app.aboutToQuit.connect(controller.shutdown)
    controller.start()
    controller.maybe_first_run()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
