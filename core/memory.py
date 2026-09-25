"""Agent memory: sessions, tool calls and results (redacted, SQLite).

Doubles as the structured agent log: every entry records task, provider,
tool, start/end times, success and an error category. Secrets are redacted
before storage. Screenshots are never stored unless the user explicitly
enables screenshot history.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from core.safety import redact
from database.agent_repository import AgentRepository


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class MemoryStore:
    def __init__(
        self,
        repository: AgentRepository,
        *,
        screenshot_history: bool = False,
        screenshots_dir: Path | None = None,
        clock=time.time,  # noqa: ANN001
    ) -> None:
        self._repo = repository
        self._screenshots = screenshot_history
        self._shots_dir = screenshots_dir
        self._clock = clock

    # ------------------------------------------------------------ session

    def start_session(self, command: str, provider: str) -> str:
        return self._repo.create_session(redact(command), provider)

    def finish_session(self, session_id: str, status: str) -> None:
        self._repo.finish_session(session_id, status)

    # -------------------------------------------------------------- log

    def log_tool(
        self,
        session_id: str,
        *,
        task: str,
        provider: str,
        tool_name: str,
        arguments: dict | None,
        result: str | None,
        success: bool,
        error_category: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> int:
        return self._repo.insert_event(
            session_id=session_id,
            task=redact(task),
            provider=provider,
            kind="tool_call",
            tool_name=tool_name,
            arguments=redact(str(arguments))[:2000] if arguments else None,
            result=redact((result or "")[:2000]) or None,
            success=1 if success else 0,
            error_category=error_category,
            started_at=started_at or _utc_now(),
            ended_at=ended_at or _utc_now(),
        )

    def log_note(
        self, session_id: str, *, task: str, provider: str, note: str
    ) -> int:
        return self._repo.insert_event(
            session_id=session_id,
            task=redact(task),
            provider=provider,
            kind="note",
            result=redact(note)[:2000],
            started_at=_utc_now(),
            ended_at=_utc_now(),
        )

    def events(self, session_id: str) -> list[dict]:
        return self._repo.events_for_session(session_id)

    def recent(self, limit: int = 50) -> list[dict]:
        return self._repo.recent_events(limit)

    # ------------------------------------------------------- screenshots

    def save_screenshot(self, image) -> Path | None:  # noqa: ANN001
        """Persist a screenshot only when screenshot history is enabled."""
        if not self._screenshots or self._shots_dir is None:
            return None
        self._shots_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        path = self._shots_dir / f"screen-{stamp}.png"
        image.save(path)
        return path
