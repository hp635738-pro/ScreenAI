"""Plugin discovery and registration.

Scans a directory for ``*_plugin.py`` modules (or packages with a
``plugin()``/``Plugin`` entry). One broken plugin never breaks the app:
failures are captured as load errors and reported in diagnostics.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from core.plugins.base import Command, Plugin, PluginContext, SettingDef, UIPage
from core.tools import Tool, ToolRegistry

log = logging.getLogger("screenai.plugins")


class PluginRegistry:
    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self._tool_registry = tool_registry or ToolRegistry()
        self._plugins: dict[str, Plugin] = {}
        self._commands: dict[str, Command] = {}
        self._settings: dict[str, SettingDef] = {}
        self._pages: dict[str, UIPage] = {}
        self.tool_specs: list[Tool] = []
        self.load_errors: list[str] = []

    # ---------------------------------------------------------- queries

    @property
    def tools(self) -> ToolRegistry:
        return self._tool_registry

    def commands(self) -> tuple[Command, ...]:
        return tuple(self._commands.values())

    def settings(self) -> tuple[SettingDef, ...]:
        return tuple(self._settings.values())

    def pages(self) -> tuple[UIPage, ...]:
        return tuple(self._pages.values())

    def plugins(self) -> tuple[Plugin, ...]:
        return tuple(self._plugins.values())

    # ------------------------------------------------------- registration

    def register(self, plugin: Plugin) -> None:
        self._plugins[plugin.name] = plugin

    def activate_all(self) -> None:
        for plugin in list(self._plugins.values()):
            self._activate(plugin)

    def _activate(self, plugin: Plugin) -> None:
        context = PluginContext(
            register_tool=self._register_tool,
            register_command=self._register_command,
            register_setting=self._register_setting,
            register_page=self._register_page,
            plugin_name=plugin.name,
        )
        try:
            plugin.activate(context)
        except Exception as exc:  # noqa: BLE001 — isolate plugin faults
            self.load_errors.append(f"{plugin.name}: {exc}")
            log.warning("plugin %s failed to activate: %s", plugin.name, exc)

    def _register_tool(self, tool: Tool) -> None:
        self._tool_registry.register(tool)
        self.tool_specs.append(tool)

    def _register_command(self, command: Command) -> None:
        self._commands[command.name] = command

    def _register_setting(self, setting: SettingDef) -> None:
        self._settings[setting.key] = setting

    def _register_page(self, page: UIPage) -> None:
        self._pages[page.name] = page

    # ---------------------------------------------------------- discovery

    def load_directory(self, directory: Path) -> int:
        """Import every ``*_plugin`` module in *directory*. Returns count."""
        directory = Path(directory)
        if not directory.is_dir():
            return 0
        loaded = 0
        for path in sorted(directory.glob("*_plugin.py")):
            if self._load_path(path):
                loaded += 1
        for path in sorted(directory.glob("*_plugin/__init__.py")):
            if self._load_path(path.parent):
                loaded += 1
        return loaded

    def _load_path(self, path: Path) -> bool:
        module_name = path.stem if path.is_file() else path.name
        unique = f"screenai_plugin_{module_name}"
        try:
            spec = importlib.util.spec_from_file_location(
                unique, path if path.is_file() else path / "__init__.py"
            )
            if spec is None or spec.loader is None:
                self.load_errors.append(f"{path}: no import spec")
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[unique] = module
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001
            self.load_errors.append(f"{path.name}: {exc}")
            log.warning("plugin module %s failed to import: %s", path, exc)
            return False

        plugin_type = getattr(module, "Plugin", None)
        factory = getattr(module, "plugin", None)
        try:
            if callable(factory):
                instance = factory()
            elif isinstance(plugin_type, type):
                instance = plugin_type()
            else:
                instance = None
        except Exception as exc:  # noqa: BLE001
            self.load_errors.append(f"{path.name}: {exc}")
            return False
        if instance is None:
            self.load_errors.append(f"{path.name}: no Plugin class or plugin() factory")
            return False
        self.register(instance)
        self._activate(instance)
        return True
