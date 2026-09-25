"""SQLite connection management."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from core.config import Config


class DatabaseManager:
    """Owns the SQLite connection. Intended for use from the GUI thread."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Config.database_path()
        self._lock = threading.Lock()
        self._connection: sqlite3.Connection | None = None

    @property
    def path(self) -> Path:
        return self._path

    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is None:
                self._connection = sqlite3.connect(self._path)
                self._connection.row_factory = sqlite3.Row
                self._connection.executescript(self._schema_sql())
                self._connection.commit()
            return self._connection

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    @staticmethod
    def _schema_sql() -> str:
        return Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
