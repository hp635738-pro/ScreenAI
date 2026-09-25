"""Example ScreenAI plugin: a Photoshop bridge.

This file is documentation-grade: it is NOT loaded automatically. Plugins are
loaded from ``<user-data>/ScreenAI/plugins/`` — copy this file there (and fill
in a real Photoshop bridge) to activate it. The point of this example is to
show that a Photoshop integration can register its own tools, commands,
settings, and UI page WITHOUT modifying ScreenAI's core agent loop.

A real implementation would talk to Photoshop through its scripting DOM
(ExtendScript / UXP), a socket, or a helper like `photoshop-python-api`.
The stubs below show exactly where that glue would go.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.plugins import Command, Plugin, PluginContext, SettingDef, UIPage
from core.tools import Tool, ToolRegistry, ToolResult, ToolSpec
from core.tools.safety import SafetyLevel

if TYPE_CHECKING:  # pragma: no cover - type hints only
    pass


class PhotoshopBridge:
    """Placeholder for the Photoshop connection (socket / COM / UXP)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 49321) -> None:
        self.host = host
        self.port = port

    def connected(self) -> bool:
        """Return whether Photoshop is reachable. Always False in the stub."""
        return False


# --- tools -----------------------------------------------------------------

class OpenDocumentTool(Tool):
    """Open an image file as a Photoshop document (confirmation required)."""

    def __init__(self) -> None:
        super().__init__()
        self.spec = ToolSpec(
            name="photoshop_open_document",
            description="Open an image file as a new Photoshop document.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Image file path."},
                },
                "required": ["path"],
            },
            safety=SafetyLevel.CONFIRM,  # touches external application state
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:  # noqa: ARG002
        return ToolResult(
            success=False,
            output="Photoshop bridge is not configured in this example plugin.",
            error_category="plugin_not_configured",
        )


class ExportPngTool(Tool):
    """Export the active document as PNG (confirmation required)."""

    def __init__(self) -> None:
        super().__init__()
        self.spec = ToolSpec(
            name="photoshop_export_png",
            description="Export the active Photoshop document as a PNG file.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Destination PNG path."},
                },
                "required": ["path"],
            },
            safety=SafetyLevel.CONFIRM,
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:  # noqa: ARG002
        return ToolResult(
            success=False,
            output="Photoshop bridge is not configured in this example plugin.",
            error_category="plugin_not_configured",
        )


class ApplyFilterTool(Tool):
    """Apply a named filter to the active layer (confirmation required)."""

    def __init__(self) -> None:
        super().__init__()
        self.spec = ToolSpec(
            name="photoshop_apply_filter",
            description="Apply a named Photoshop filter to the active layer.",
            input_schema={
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "Filter name."},
                },
                "required": ["filter"],
            },
            safety=SafetyLevel.CONFIRM,
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:  # noqa: ARG002
        return ToolResult(
            success=False,
            output="Photoshop bridge is not configured in this example plugin.",
            error_category="plugin_not_configured",
        )


# --- the plugin ------------------------------------------------------------

class PhotoshopPlugin(Plugin):
    """Registers Photoshop tools, a command, a setting, and an optional page.

    The core agent discovers these through :class:`PluginContext` — the
    agent loop itself is never modified.
    """

    def __init__(self) -> None:
        super().__init__(
            name="photoshop",
            version="0.1.0",
            description="Bridge tools for Adobe Photoshop (example plugin).",
        )

    def on_load(self, context: PluginContext) -> None:
        self._bridge = PhotoshopBridge()
        # The bridge host/port would come from the plugin setting below.
        context.register_tool(OpenDocumentTool())
        context.register_tool(ExportPngTool())
        context.register_tool(ApplyFilterTool())

        def _status() -> str:
            connected = self._bridge.connected()
            return "Photoshop bridge connected." if connected else "Photoshop not reachable."

        context.register_command(Command(name="photoshop_status", description=_status))
        context.register_setting(
            SettingDef(
                key="photoshop.bridge_port",
                label="Photoshop bridge port",
                value=str(self._bridge.port),
            )
        )
        try:  # optional UI page — QtWidgets may be absent in headless tests
            from PySide6.QtWidgets import QLabel

            context.register_page(
                UIPage(
                    name="Photoshop",
                    widget_factory=lambda: QLabel(
                        "Connect Photoshop's scripting bridge to enable these tools."
                    ),
                )
            )
        except Exception:  # noqa: BLE001
            pass


PLUGIN_CLASS = PhotoshopPlugin


def register(registry: ToolRegistry) -> None:
    """Optional alternate entry point some hosts use: register tools directly."""
    registry.register(OpenDocumentTool())
    registry.register(ExportPngTool())
    registry.register(ApplyFilterTool())
