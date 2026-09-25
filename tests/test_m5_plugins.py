"""Milestone 5: plugin architecture (internal extension points only)."""

from __future__ import annotations

from pathlib import Path

from core.plugins import Command, Plugin, PluginContext, PluginRegistry, SettingDef, UIPage
from core.safety import SafetyLevel
from core.tools import Tool, ToolResult, ToolSpec


class EchoTool(Tool):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            "plugin_echo",
            "Echo plugin tool",
            {"type": "object", "properties": {}},
            SafetyLevel.SAFE,
        )

    def execute(self, arguments: dict) -> ToolResult:
        return ToolResult(True, "echo", display="echo")


class DemoPlugin(Plugin):
    name = "demo"
    description = "Demo"
    version = "1.0"

    def activate(self, context: PluginContext) -> None:
        context.register_tool(EchoTool())
        context.register_command(Command("demo_cmd", "A command", lambda: "ok"))
        context.register_setting(SettingDef("demo.key", "Demo", "1", "desc"))
        context.register_page(UIPage("demo", lambda: None))

    def deactivate(self) -> None:
        return None


def test_plugin_registers_tools_commands_settings_pages() -> None:
    registry = PluginRegistry()
    registry.register(DemoPlugin())
    registry.activate_all()

    assert "plugin_echo" in registry.tools.names()
    assert [c.name for c in registry.commands()] == ["demo_cmd"]
    assert [s.key for s in registry.settings()] == ["demo.key"]
    assert [p.name for p in registry.pages()] == ["demo"]
    assert [t.spec.name for t in registry.tool_specs] == ["plugin_echo"]


def test_broken_plugin_never_crashes_registry() -> None:
    class Broken(Plugin):
        name = "broken"
        description = "x"
        version = "0"

        def activate(self, context: PluginContext) -> None:
            raise RuntimeError("boom")

    registry = PluginRegistry()
    registry.register(Broken())
    registry.register(DemoPlugin())
    registry.activate_all()  # must not raise

    assert any("broken" in error for error in registry.load_errors)
    assert "plugin_echo" in registry.tools.names()  # healthy plugin unaffected


def test_load_directory_discovers_plugin_modules(tmp_path: Path) -> None:
    plugin_file = tmp_path / "sample_plugin.py"
    plugin_file.write_text(
        "from core.plugins import Command, Plugin, SettingDef\n"
        "class Sample(Plugin):\n"
        "    name = 'sample'\n"
        "    description = 'sample plugin'\n"
        "    version = '0.1'\n"
        "    def activate(self, context):\n"
        "        context.register_command(Command('sample_cmd', 'c', lambda: 1))\n"
        "def plugin():\n"
        "    return Sample()\n"
    )
    bad_file = tmp_path / "bad_plugin.py"
    bad_file.write_text("raise RuntimeError('bad module')\n")

    registry = PluginRegistry()
    loaded = registry.load_directory(tmp_path)
    registry.activate_all()

    assert loaded == 1
    assert [c.name for c in registry.commands()] == ["sample_cmd"]
    assert len(registry.load_errors) == 1


def test_load_missing_directory_is_noop(tmp_path: Path) -> None:
    registry = PluginRegistry()
    assert registry.load_directory(tmp_path / "nope") == 0
    assert registry.load_errors == []
