"""Lightweight internal plugin architecture (not a marketplace).

A plugin is a Python module or package exposing a ``Plugin`` subclass of
:class:`core.plugins.base.Plugin` (or a ``plugin()`` factory). On
activation it may register tools, commands, settings and optional UI
pages — without modifying the agent loop or any core module.
"""

from __future__ import annotations

from core.plugins.base import Command, Plugin, PluginContext, SettingDef, UIPage
from core.plugins.registry import PluginRegistry

__all__ = [
    "Command",
    "Plugin",
    "PluginContext",
    "PluginRegistry",
    "SettingDef",
    "UIPage",
]
