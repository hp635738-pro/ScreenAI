"""Milestone 5: task history (aggregated, searchable, redacted)."""

from __future__ import annotations

from pathlib import Path

from core.history import HistoryService
from core.memory import MemoryStore
from core.safety import redact
from database.agent_repository import AgentRepository
from database.db_manager import DatabaseManager


def _service(tmp_path: Path) -> tuple[HistoryService, MemoryStore]:
    db = DatabaseManager(tmp_path / "history.sqlite3")
    memory = MemoryStore(AgentRepository(db))
    return HistoryService(db), memory


def test_entries_include_agent_sessions(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    run_id = memory.start_session("open firefox", "ollama")
    memory.finish_session(run_id, "completed")

    entries = service.entries()
    assert entries
    top = entries[0]
    assert top.task == "open firefox"
    assert top.provider == "ollama"
    assert top.success is True


def test_search_and_status_filters(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    ok_id = memory.start_session("open firefox", "ollama")
    memory.finish_session(ok_id, "completed")
    bad_id = memory.start_session("delete everything", "openai")
    memory.finish_session(bad_id, "failed")

    assert all("firefox" in e.task for e in service.entries(search="firefox"))
    failed = service.entries(status="failed")
    assert [e.task for e in failed] == ["delete everything"]
    assert len(service.entries(status="success")) == 1


def test_clear_removes_all(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    run_id = memory.start_session("t", "ollama")
    memory.finish_session(run_id, "completed")
    assert service.entries()
    service.clear()
    assert service.entries() == []


def test_no_sensitive_data_is_displayed(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    run_id = memory.start_session("send sk-secretvalue12345 to openai", "openai")
    memory.log_note(
        run_id,
        task="send key",
        provider="openai",
        note="used sk-secretvalue12345",
    )
    memory.finish_session(run_id, "completed")
    for entry in service.entries():
        blob = f"{entry.task} {entry.result}"
        assert "sk-secretvalue12345" not in blob
    assert "sk-secretvalue12345" not in redact("sk-secretvalue12345")


def test_recent_error_categories(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    run_id = memory.start_session("t", "ollama")
    memory.log_tool(
        run_id,
        task="t",
        provider="ollama",
        tool_name="run_terminal",
        arguments={"command": "foo"},
        result="missing",
        success=False,
        error_category="app_not_found",
    )
    memory.finish_session(run_id, "failed")
    assert any("app_not_found" in c for c in service.recent_error_categories())
