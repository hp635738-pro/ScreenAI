"""Unified task history for the History page.

Merges agent sessions (Milestone 4+) and legacy task runs (Milestones 1–3)
into one queryable feed. Task text is redacted on the way out — the
History page must never display sensitive data.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.safety import redact
from database.db_manager import DatabaseManager

_SUCCESS_STATES = {"done", "completed", "success"}
_FAILURE_STATES = {"failed", "error", "cancelled"}


@dataclass(slots=True)
class HistoryEntry:
    when: str
    task: str
    provider: str
    duration: float
    result: str
    success: bool | None  # None = unknown outcome
    source: str  # agent | legacy


class HistoryService:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # ------------------------------------------------------------- query

    def entries(
        self,
        search: str = "",
        status: str = "all",
        limit: int = 200,
    ) -> list[HistoryEntry]:
        rows: list[HistoryEntry] = []
        rows.extend(self._agent_entries(search, limit))
        rows.extend(self._legacy_entries(search, limit))
        rows.sort(key=lambda entry: entry.when, reverse=True)
        if status == "success":
            rows = [r for r in rows if r.success is True]
        elif status == "failed":
            rows = [r for r in rows if r.success is not True]
        return rows[:limit]

    def _agent_entries(self, search: str, limit: int) -> list[HistoryEntry]:
        pattern = f"%{search.lower()}%"
        sql = (
            "SELECT created_at, user_command, provider, status, finished_at, "
            "CAST ((julianday(COALESCE(finished_at, created_at)) - "
            "julianday(created_at)) * 86400.0 AS REAL) AS duration "
            "FROM agent_sessions "
            "WHERE LOWER(user_command) LIKE ? "
            "ORDER BY created_at DESC LIMIT ?"
        )
        out: list[HistoryEntry] = []
        for row in self._db.connect().execute(sql, (pattern, limit)).fetchall():
            status = str(row["status"])
            out.append(
                HistoryEntry(
                    when=row["created_at"],
                    task=redact(row["user_command"]),
                    provider=row["provider"] or "—",
                    duration=float(row["duration"] or 0.0),
                    result=status,
                    success=True if status == "completed" else (
                        None if status == "running" else False
                    ),
                    source="agent",
                )
            )
        return out

    def _legacy_entries(self, search: str, limit: int) -> list[HistoryEntry]:
        pattern = f"%{search.lower()}%"
        sql = (
            "SELECT started_at, command, status, result, "
            "CAST ((julianday(COALESCE(finished_at, started_at)) - "
            "julianday(started_at)) * 86400.0 AS REAL) AS duration "
            "FROM task_runs "
            "WHERE LOWER(command) LIKE ? "
            "ORDER BY started_at DESC LIMIT ?"
        )
        out: list[HistoryEntry] = []
        for row in self._db.connect().execute(sql, (pattern, limit)).fetchall():
            status = str(row["status"]).lower()
            if status in _SUCCESS_STATES:
                success: bool | None = True
            elif status in _FAILURE_STATES or status == "working":
                success = False if status != "working" else None
            else:
                success = None
            out.append(
                HistoryEntry(
                    when=row["started_at"],
                    task=redact(row["command"]),
                    provider="local parser",
                    duration=float(row["duration"] or 0.0),
                    result=redact(row["result"] or status),
                    success=success,
                    source="legacy",
                )
            )
        return out

    # ------------------------------------------------------------- clear

    def clear(self) -> int:
        connection = self._db.connect()
        total = 0
        for table in ("agent_events", "agent_sessions", "action_history", "task_runs"):
            total += connection.execute(f"DELETE FROM {table}").rowcount
        connection.commit()
        return total

    def recent_error_categories(self, limit: int = 20) -> list[str]:
        rows = self._db.connect().execute(
            "SELECT error_category, COUNT(*) AS n FROM agent_events "
            "WHERE error_category IS NOT NULL "
            "GROUP BY error_category ORDER BY n DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [f"{row['error_category']} ×{row['n']}" for row in rows]
