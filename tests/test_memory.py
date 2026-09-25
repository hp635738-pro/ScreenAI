"""Agent memory persistence, redaction and screenshot policy."""

from __future__ import annotations

from core.memory import MemoryStore
from core.settings import SettingsStore
from database.agent_repository import AgentRepository
from database.db_manager import DatabaseManager


def _memory(tmp_path, screenshots=False):  # noqa: ANN001, ANN202
    repo = AgentRepository(DatabaseManager(tmp_path / "mem.db"))
    return MemoryStore(
        repo,
        screenshot_history=screenshots,
        screenshots_dir=tmp_path / "shots",
    ), repo


def test_session_and_tool_events_persist(tmp_path):
    memory, repo = _memory(tmp_path)
    session = memory.start_session("open firefox", "ollama")
    memory.log_tool(
        session,
        task="open firefox",
        provider="ollama",
        tool_name="open_application",
        arguments={"name": "firefox"},
        result="Opened Firefox",
        success=True,
        error_category=None,
    )
    memory.log_tool(
        session,
        task="open firefox",
        provider="ollama",
        tool_name="find_text",
        arguments={"text": "Export"},
        result="ERROR [target_not_found]: not found",
        success=False,
        error_category="target_not_found",
    )
    memory.finish_session(session, "completed")

    rows = repo.events_for_session(session)
    assert len(rows) == 2
    assert rows[0]["tool_name"] == "open_application"
    assert rows[0]["success"] == 1
    assert rows[1]["error_category"] == "target_not_found"
    assert rows[0]["started_at"] and rows[0]["ended_at"]
    session_rows = repo.sessions()
    assert session_rows[0]["status"] == "completed"
    assert session_rows[0]["user_command"] == "open firefox"


def test_memory_redacts_secrets(tmp_path):
    memory, repo = _memory(tmp_path)
    session = memory.start_session("use key", "openai")
    memory.log_tool(
        session,
        task="use key password=hunter2",
        provider="openai",
        tool_name="run_terminal_command",
        arguments={"command": "export TOKEN=sk-ABCDEF1234567890"},
        result="done sk-ABCDEF1234567890",
        success=True,
    )
    rows = repo.events_for_session(session)
    for row in rows:
        blob = " ".join(str(row[key]) for key in ("task", "arguments", "result"))
        assert "hunter2" not in blob
        assert "sk-ABCDEF1234567890" not in blob


def test_screenshot_history_off_by_default(tmp_path):
    from PIL import Image

    memory, _ = _memory(tmp_path, screenshots=False)
    assert memory.save_screenshot(Image.new("RGB", (4, 4))) is None
    assert not (tmp_path / "shots").exists()

    memory_on, _ = _memory(tmp_path / "on", screenshots=True)
    path = memory_on.save_screenshot(Image.new("RGB", (4, 4)))
    assert path is not None and path.exists()


def test_settings_store_and_api_key_hygiene(tmp_path):
    store = SettingsStore(data_dir=tmp_path, env={})
    assert store.get("provider") == "auto"
    assert store.masked_api_key() is None

    store.set_api_key("sk-1234567890abcdefgh")
    store.set("model_openai", "gpt-4o")
    store.save()

    assert store.masked_api_key() == "sk-…efgh"
    assert "sk-1234567890" not in (store.masked_api_key() or "")

    mode = (tmp_path / "credentials.json").stat().st_mode & 0o777
    assert mode == 0o600

    reloaded = SettingsStore(data_dir=tmp_path, env={})
    assert reloaded.api_key() == "sk-1234567890abcdefgh"
    assert reloaded.get("model_openai") == "gpt-4o"

    env = {"OPENAI_API_KEY": "sk-env", "SCREENAI_AI_PROVIDER": "openai"}
    assert SettingsStore(data_dir=tmp_path, env=env).api_key() == "sk-env"
    assert SettingsStore(data_dir=tmp_path, env=env).get("provider") == "openai"

    reloaded.clear_api_key()
    assert reloaded.api_key() is None
