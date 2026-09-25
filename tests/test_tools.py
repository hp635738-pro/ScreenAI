"""Tool registry + tool execution suites."""

from __future__ import annotations

import pytest

from core.safety import ErrorCategory, SafetyLevel, SafetyManager, ToolError
from core.tools import ToolRegistry, ToolResult, ToolSpec


EXPECTED_TOOLS = {
    "open_application", "close_application",
    "run_terminal_command",
    "mouse_move", "mouse_click", "type_text", "press_key", "hotkey",
    "screenshot", "find_text", "inspect_screen",
    "start_learning", "stop_learning", "save_workflow", "list_workflows",
    "run_workflow",
}


def test_registry_covers_all_required_tools(registry_ctx):
    registry, _ = registry_ctx
    assert set(registry.names()) == EXPECTED_TOOLS
    assert len(registry.names()) == 16


def test_tool_specs_and_prompt_listing(registry_ctx):
    registry, _ = registry_ctx
    listing = registry.schemas_for_prompt()
    for spec in registry.specs():
        assert spec.name and spec.description
        assert spec.input_schema.get("type") == "object"
        assert isinstance(spec.safety, SafetyLevel)
        assert spec.name in listing
    assert "[confirm]" in listing  # terminal/close tools declared CONFIRM


def test_registry_validation(registry_ctx):
    registry, _ = registry_ctx
    with pytest.raises(ToolError) as excinfo:
        registry.execute("no_such_tool", {})
    assert excinfo.value.category is ErrorCategory.INVALID_ARGUMENTS

    with pytest.raises(ToolError) as excinfo:
        registry.execute("open_application", {})
    assert "name" in str(excinfo.value)

    with pytest.raises(ToolError) as excinfo:
        registry.execute("mouse_click", {"x": "left", "y": 1})
    assert excinfo.value.category is ErrorCategory.INVALID_ARGUMENTS


def test_open_and_close_application(registry_ctx):
    registry, services = registry_ctx
    result = registry.execute("open_application", {"name": "firefox"})
    assert result.success and "Firefox" in result.output
    assert services["launcher"].launched == ["firefox"]
    assert result.display == "Opening Firefox"

    with pytest.raises(ToolError) as excinfo:
        registry.execute("open_application", {"name": "definitely-missing"})
    assert excinfo.value.category is ErrorCategory.APP_NOT_FOUND

    with pytest.raises(ToolError) as excinfo:
        registry.execute("close_application", {"name": "firefox"})
    assert excinfo.value.category is ErrorCategory.CONFIRMATION_DECLINED

    # pid 4242 does not exist -> automation failure result, but safety passed
    close = registry.execute("close_application", {"name": "firefox", "_approved": True})
    assert not close.success and close.error_category == "automation_failure"
    result = registry.execute("open_application", {"name": "konsole"})
    assert result.success


def test_terminal_safety_pipeline(registry_ctx):
    registry, services = registry_ctx
    terminal = services["terminal"]

    with pytest.raises(ToolError) as excinfo:
        registry.execute(
            "run_terminal_command", {"command": "sudo rm -rf /"}
        )
    assert excinfo.value.category is ErrorCategory.BLOCKED
    assert terminal.commands == []  # never reached the engine

    with pytest.raises(ToolError) as excinfo:
        registry.execute("run_terminal_command", {"command": "rm old.txt"})
    assert excinfo.value.category is ErrorCategory.CONFIRMATION_DECLINED
    assert terminal.commands == []

    result = registry.execute(
        "run_terminal_command", {"command": "rm old.txt", "_approved": True}
    )
    assert result.success and terminal.commands == ["rm old.txt"]


def test_terminal_output_redacts_secrets(registry_ctx):
    registry, services = registry_ctx
    services["terminal"].result.stdout = "token sk-SECRETSECRET1234 done"
    result = registry.execute("run_terminal_command", {"command": "ls", "_approved": True})
    assert "sk-SECRETSECRET1234" not in result.output
    assert "[REDACTED]" in result.output


def test_automation_tools(registry_ctx):
    registry, services = registry_ctx
    backend = services["automation"]._backend
    registry.execute("mouse_move", {"x": 5, "y": 6})
    registry.execute("mouse_click", {"x": 7, "y": 8, "button": "right"})
    registry.execute("mouse_click", {"x": 1, "y": 2, "double": True})
    registry.execute("type_text", {"text": "hello"})
    registry.execute("press_key", {"key": "enter"})
    registry.execute("hotkey", {"keys": "ctrl+s"})
    assert ("move", 5, 6) in backend.calls
    assert ("click", 7, 8, "right") in backend.calls
    assert ("dbl", 1, 2) in backend.calls
    assert ("type", "hello") in backend.calls
    assert ("press", "enter") in backend.calls
    assert ("key", ("ctrl", "s")) in backend.calls


def test_vision_tools(registry_ctx):
    registry, services = registry_ctx

    result = registry.execute("screenshot", {})
    assert result.success and "Export" in result.output
    assert result.display == "Captured screen"

    result = registry.execute("inspect_screen", {})
    assert result.success and result.data["count"] == 2
    assert result.display == "Inspecting screen"

    result = registry.execute("find_text", {"text": "Export"})
    assert result.success
    assert result.display == "Found Export"
    assert result.data["center"] == [30, 20]

    with pytest.raises(ToolError) as excinfo:
        registry.execute("find_text", {"text": "Nonexistent"})
    assert excinfo.value.category is ErrorCategory.TARGET_NOT_FOUND


def test_workflow_tools(registry_ctx):
    registry, services = registry_ctx
    workflows = services["workflows"]

    result = registry.execute("list_workflows", {})
    assert "XYZ App: Export PDF" in result.output

    result = registry.execute(
        "run_workflow", {"app_name": "XYZ App", "task_name": "Export PDF"}
    )
    assert result.success
    assert workflows.run_calls[-1]["app_name"] == "XYZ App"

    with pytest.raises(ToolError) as excinfo:
        registry.execute("run_workflow", {"app_name": "Nope"})
    assert excinfo.value.category is ErrorCategory.WORKFLOW_NOT_FOUND

    result = registry.execute("start_learning", {})
    assert workflows.recording and result.display == "Recording…"
    workflows.steps_pending = 4
    result = registry.execute("stop_learning", {})
    assert result.data["steps"] == 4
    result = registry.execute(
        "save_workflow", {"app_name": "XYZ App", "task_name": "Export PDF"}
    )
    assert result.success and workflows.saved == [("XYZ App", "Export PDF")]


def test_custom_registry_and_result_helpers():
    registry = ToolRegistry()

    class Echo:
        spec = ToolSpec("echo", "Echo.", {"type": "object", "properties": {},
                                          "required": []}, SafetyLevel.SAFE)

        def execute(self, arguments: dict) -> ToolResult:
            return ToolResult(True, "echo", display="Echo")

    registry.register(Echo())
    assert registry.names() == ("echo",)
    assert registry.execute("echo", {}).output == "echo"


def test_enforce_safety_blocks_without_approval():
    from core.tools import enforce_safety

    safety = SafetyManager()
    spec = ToolSpec("demo", "", {"type": "object", "properties": {}, "required": []},
                    SafetyLevel.CONFIRM)
    with pytest.raises(ToolError) as excinfo:
        enforce_safety(safety, spec, {})
    assert excinfo.value.category is ErrorCategory.CONFIRMATION_DECLINED
    enforce_safety(safety, spec, {"_approved": True})  # no raise
