"""Application configuration and runtime path resolution.

Nothing here assumes a fixed checkout or install location: paths are
derived from this file's position or from the user's data directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from core.version import APP_NAME, ORG_NAME, VERSION


class Config:
    APP_NAME = APP_NAME
    ORG_NAME = ORG_NAME
    VERSION = VERSION

    # Duration of the simulated execution used in Milestone 1 (no AI yet).
    TASK_SIM_DURATION = 5.0

    WINDOW_MIN_WIDTH = 560
    WINDOW_MIN_HEIGHT = 340
    POPUP_WIDTH = 400

    # Reserved for the upcoming AI integrations ("openai" / "ollama").
    AI_PROVIDER = "ollama"
    AI_PROVIDER_OPTIONS: dict[str, dict[str, str]] = {
        "openai": {"model": "gpt-4o-mini"},
        "ollama": {"model": "llama3.2", "base_url": "http://localhost:11434"},
    }

    @staticmethod
    def project_root() -> Path:
        return Path(__file__).resolve().parent.parent

    @classmethod
    def asset_path(cls, *parts: str) -> Path:
        return cls.project_root().joinpath("assets", *parts)

    @staticmethod
    def data_dir() -> Path:
        """Writable per-user data directory (override: SCREENAI_DATA_DIR)."""
        override = os.environ.get("SCREENAI_DATA_DIR")
        if override:
            base = Path(override).expanduser()
        else:
            location = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            )
            base = Path(location)
        base.mkdir(parents=True, exist_ok=True)
        return base

    @classmethod
    def database_path(cls) -> Path:
        return cls.data_dir() / "screenai.db"
