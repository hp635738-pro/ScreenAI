"""SQLite persistence for agent memory and structured agent logs."""

from __future__ import annotations

import uuid

from database.db_manager import DatabaseManager


class AgentRepository:
    """Session and event storage (single ``agent_events`` feed serves both
    agent memory and the structured agent log)."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def create_session(self, command: str, provider: str) -> str:
        session_id = uuid.uuid4().hex[:16]
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO agent_sessions (session_id, user_command, provider, status)"
                " VALUES (?, ?, ?, 'running')",
                (session_id, command, provider),
            )
            conn.commit()
        return session_id

    def finish_session(self, session_id: str, status: str) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE agent_sessions SET status = ?,"
                " finished_at = datetime('now') WHERE session_id = ?",
                (status, session_id),
            )
            conn.commit()

    def insert_event(
        self,
        *,
        session_id: str,
        task: str,
        provider: str,
        kind: str,
        tool_name: str | None = None,
        arguments: str | None = None,
        result: str | None = None,
        success: int | None = None,
        error_category: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> int:
        with self._db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO agent_events (session_id, task, provider, kind,"
                " tool_name, arguments, result, success, error_category,"
                " started_at, ended_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id, task, provider, kind, tool_name, arguments,
                    result, success, error_category, started_at, ended_at,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def events_for_session(self, session_id: str) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_events WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_events(self, limit: int = 50) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def sessions(self, limit: int = 20) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_sessions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def error_categories(self, limit: int = 20) -> list[str]:
        rows = self._db.connect().execute(
            "SELECT error_category, COUNT(*) AS n FROM agent_events "
            "WHERE error_category IS NOT NULL "
            "GROUP BY error_category ORDER BY n DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [f"{row['error_category']} x{row['n']}" for row in rows]

    def clear_all(self) -> int:
        connection = self._db.connect()
        total = connection.execute("DELETE FROM agent_events").rowcount
        total += connection.execute("DELETE FROM agent_sessions").rowcount
        connection.commit()
        return total
