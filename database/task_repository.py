"""Persistence for task runs."""

from __future__ import annotations

from core.models import TaskRecord, TaskState
from database.db_manager import DatabaseManager


class TaskRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def create_run(self, command: str) -> int:
        connection = self._db.connect()
        cursor = connection.execute(
            "INSERT INTO task_runs (command, status) VALUES (?, ?)",
            (command, TaskState.WORKING.value),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: TaskState, result: str | None = None) -> None:
        connection = self._db.connect()
        connection.execute(
            "UPDATE task_runs SET status = ?, result = ?, finished_at = datetime('now') "
            "WHERE id = ?",
            (status.value, result, run_id),
        )
        connection.commit()

    def recent_runs(self, limit: int = 20) -> list[TaskRecord]:
        rows = self._db.connect().execute(
            "SELECT id, command, status, started_at, finished_at, result "
            "FROM task_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [TaskRecord(**dict(row)) for row in rows]
