"""Persistence for per-action execution history (Milestone 2)."""

from __future__ import annotations

from core.models import ActionRecord
from database.db_manager import DatabaseManager


class ActionRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def record(self, command: str, action: str, success: bool, duration: float) -> int:
        connection = self._db.connect()
        cursor = connection.execute(
            "INSERT INTO action_history (command, action, success, duration) "
            "VALUES (?, ?, ?, ?)",
            (command, action, 1 if success else 0, round(duration, 4)),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def recent(self, limit: int = 50) -> list[ActionRecord]:
        rows = self._db.connect().execute(
            "SELECT id, command, action, success, duration, timestamp "
            "FROM action_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            ActionRecord(
                id=row["id"],
                command=row["command"],
                action=row["action"],
                success=bool(row["success"]),
                duration=row["duration"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]
