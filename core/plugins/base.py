"""Plugin interface: what a plugin is and what it may register."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Callable

from core.tools import Tool


@dataclass(slots=True)
class Command:
    name: str
    description: str
    handler: Callable[[], None]


@dataclass(slots=True)
class SettingDef:
    key: str
    label: str
    default: object
    description: str = ""


@dataclass(slots=True)
class UIPage:
    """Optional UI contribution: a factory building a QWidget lazily."""

    name: str
    factory: Callable[[], object]


class Plugin(ABC):
    """Base class every plugin subclasses.

    ``activate`` is the only entry point; use ``context.register_*`` to
    contribute. Keep activation fast and free of side effects outside
    registration — heavy work belongs in the registered callables.
    """

    name: str = "plugin"
    description: str = ""
    version: str = "0.0.0"

    def activate(self, context: "PluginContext") -> None:  # noqa: D102
        raise NotImplementedError

    def deactivate(self) -> None:
        """Optional cleanup."""


@dataclass
class PluginContext:
    """Registration surface handed to each plugin."""

    register_tool: Callable[[Tool], None]
    register_command: Callable[[Command], None]
    register_setting: Callable[[SettingDef], None]
    register_page: Callable[[UIPage], None]
    plugin_name: str = ""
    extras: dict = field(default_factory=dict)
