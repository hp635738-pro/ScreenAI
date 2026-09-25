"""Agent loop: protocol, recovery limits, cancellation, memory hooks."""

from __future__ import annotations

import threading

from core.agent import Agent, AgentResult
from core.providers.base import ProviderError
from core.safety import SafetyManager
from tests.fakes import ScriptedProvider


def _agent(responses, registry, **kwargs):  # noqa: ANN001, ANN202
    provider = ScriptedProvider(responses)
    return Agent(provider, registry, SafetyManager(), **kwargs), provider


def test_agent_runs_tool_loop_to_completion(registry_ctx):
    registry, services = registry_ctx
    statuses: list[str] = []
    agent, provider = _agent(
        [
            '{"thought": "look", "tool": "find_text", "arguments": {"text": "Export"}}',
            '{"thought": "click", "tool": "mouse_click", "arguments": {"x": 30, "y": 20}}',
            '{"thought": "done", "final": "Clicked Export."}',
        ],
        registry,
        status_cb=statuses.append,
    )
    result = agent.run("Open the app and click Export.")
    assert result.success and result.steps == 2
    assert result.summary == "Clicked Export."
    assert [e.tool_name for e in result.events] == ["find_text", "mouse_click"]
    assert ("click", 30, 20, "left") in services["automation"]._backend.calls
    assert statuses[0] == "Understanding request…"
    assert "Finding Export" in statuses
    # observations flow back to the model
    observation_turn = provider.calls[1]
    assert any("OBSERVATION" in m["content"] for m in observation_turn)


def test_agent_parse_error_retries_then_fails(registry_ctx):
    registry, _ = registry_ctx
    agent, _ = _agent(
        ["not json at all", "still not json", '{"final": "never reached"}'],
        registry,
    )
    result = agent.run("x")
    assert not result.success
    assert result.error_category == "protocol_error"

    agent, _ = _agent(["not json", '{"final": "recovered"}'], registry)
    result = agent.run("x")
    assert result.success and result.summary == "recovered"


def test_agent_unknown_tool_becomes_observation(registry_ctx):
    registry, _ = registry_ctx
    agent, _ = _agent(
        [
            '{"tool": "hack_the_gibson", "arguments": {}}',
            '{"final": "fell back"}',
        ],
        registry,
    )
    result = agent.run("x")
    assert result.success
    assert result.events[0].error_category == "invalid_arguments"


def test_agent_tool_failure_limit(registry_ctx):
    registry, _ = registry_ctx
    fail = '{"tool": "find_text", "arguments": {"text": "Missing"}}'
    agent, _ = _agent([fail, fail, fail], registry, tool_fail_limit=3)
    result = agent.run("x")
    assert not result.success
    assert result.steps == 3
    assert result.error_category == "target_not_found"
    assert "Giving up" in result.summary


def test_agent_step_limit_prevents_infinite_loops(registry_ctx):
    registry, _ = registry_ctx
    endless = '{"tool": "mouse_move", "arguments": {"x": 1, "y": 1}}'
    agent, _ = _agent([endless] * 10, registry, max_steps=4)
    result = agent.run("x")
    assert not result.success
    assert result.steps == 4
    assert result.error_category == "timeout"


def test_agent_cancellation(registry_ctx):
    registry, _ = registry_ctx
    cancel = threading.Event()
    cancel.set()
    agent, _ = _agent(['{"final": "never"}'], registry, cancel_event=cancel)
    result = agent.run("x")
    assert result.cancelled and result.error_category == "cancelled"


def test_agent_provider_errors_are_bounded(registry_ctx):
    registry, _ = registry_ctx

    class Down(ScriptedProvider):
        def chat(self, messages, *, stream_cb=None):  # noqa: ANN001
            raise ProviderError("API unavailable")

    agent = Agent(Down([]), registry, SafetyManager())
    result = agent.run("x")
    assert not result.success
    assert result.error_category == "api_unavailable"


def test_agent_confirmation_declined_ends_task(registry_ctx):
    registry, services = registry_ctx
    prompts: list[str] = []
    agent, provider = _agent(
        [
            '{"tool": "type_text", "arguments": {"text": "buy it"},'
            ' "confirm_reason": "placing an order"}',
            '{"tool": "mouse_click", "arguments": {"x": 1, "y": 1}}',
            '{"final": "never reached"}',
        ],
        registry,
        confirm_cb=lambda prompt: prompts.append(prompt) or False,
    )
    result = agent.run("Order this product.")
    assert not result.success
    assert result.error_category == "confirmation_declined"
    assert result.steps == 1  # no sneaky alternative after a decline
    assert prompts and "requires confirmation" in prompts[0]
    assert services["automation"]._backend.calls == []


def test_agent_confirmation_approved_executes(registry_ctx):
    registry, services = registry_ctx
    agent, _ = _agent(
        [
            '{"tool": "type_text", "arguments": {"text": "buy it"},'
            ' "confirm_reason": "placing an order"}',
            '{"final": "Order placed."}',
        ],
        registry,
        confirm_cb=lambda prompt: True,
    )
    result = agent.run("Order this product.")
    assert result.success
    assert ("type", "buy it") in services["automation"]._backend.calls


def test_agent_blocked_action_is_refused(registry_ctx):
    registry, _ = registry_ctx
    agent, _ = _agent(
        [
            '{"tool": "run_terminal_command", "arguments": {"command": "sudo su"}}',
            '{"final": "could not escalate"}',
        ],
        registry,
    )
    result = agent.run("x")
    assert result.success  # model recovered with a report
    assert result.events[0].error_category == "blocked"


def test_agent_memory_records_events(registry_ctx, tmp_path):
    from core.memory import MemoryStore
    from database.agent_repository import AgentRepository
    from database.db_manager import DatabaseManager

    registry, _ = registry_ctx
    memory = MemoryStore(AgentRepository(DatabaseManager(tmp_path / "m.db")))
    agent, _ = _agent(
        [
            '{"tool": "screenshot", "arguments": {}}',
            '{"final": "done"}',
        ],
        registry,
        memory=memory,
    )
    result = agent.run("Take a screenshot.")
    assert result.success
    events = memory.recent(20)
    kinds = [e["kind"] for e in events]
    assert "tool_call" in kinds
    tool_rows = [e for e in events if e["kind"] == "tool_call"]
    assert tool_rows[0]["tool_name"] == "screenshot"
    assert tool_rows[0]["success"] == 1
    sessions = AgentRepository(DatabaseManager(tmp_path / "m.db")).sessions()
    assert sessions and sessions[0]["status"] == "completed"


def test_agent_result_shape():
    result = AgentResult(True, "ok", steps=1, provider="fake")
    assert result.success and result.events == []
