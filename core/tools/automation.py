"""Automation tools: mouse_move, mouse_click, type_text, press_key, hotkey."""

from __future__ import annotations

from core.automation import Automation, AutomationError
from core.safety import ErrorCategory, SafetyLevel, SafetyManager, ToolError
from core.tools import Tool, ToolResult, ToolSpec, enforce_safety


class _AutomationTool(Tool):
    def __init__(self, automation: Automation, safety: SafetyManager) -> None:
        self._automation = automation
        self._safety = safety

    def _run(self, arguments: dict, display: str, fn) -> ToolResult:  # noqa: ANN001, ANN202
        enforce_safety(
            self._safety,
            self.spec,
            arguments,
            confirm_reason=arguments.get("confirm_reason"),
            description=display,
        )
        try:
            fn()
        except AutomationError as exc:
            raise ToolError(
                str(exc), ErrorCategory.AUTOMATION_FAILURE
            ) from exc
        return ToolResult(True, f"{display} — done", display=display)


class MouseMoveTool(_AutomationTool):
    spec = ToolSpec(
        name="mouse_move",
        description="Move the mouse pointer to screen coordinates.",
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "duration": {"type": "number"},
            },
            "required": ["x", "y"],
        },
        safety=SafetyLevel.SAFE,
    )

    def execute(self, arguments: dict) -> ToolResult:
        x, y = int(arguments["x"]), int(arguments["y"])
        duration = float(arguments.get("duration") or 0.0)
        display = f"Moving mouse to {x} {y}"
        return self._run(
            arguments,
            display,
            lambda: self._automation.move_mouse(x, y, duration),
        )


class MouseClickTool(_AutomationTool):
    spec = ToolSpec(
        name="mouse_click",
        description=(
            "Click at screen coordinates (pass confirm_reason when the click "
            "submits or purchases something)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string"},
                "double": {"type": "boolean"},
                "confirm_reason": {"type": "string"},
            },
            "required": ["x", "y"],
        },
        safety=SafetyLevel.SAFE,
    )

    def execute(self, arguments: dict) -> ToolResult:
        x, y = int(arguments["x"]), int(arguments["y"])
        button = str(arguments.get("button") or "left")
        double = bool(arguments.get("double"))
        display = f"{'Double-clicking' if double else 'Clicking'} at {x} {y}"

        def click() -> None:
            if double:
                self._automation.double_click(x, y)
            else:
                self._automation.click(x, y, button=button)

        return self._run(arguments, display, click)


class TypeTextTool(_AutomationTool):
    spec = ToolSpec(
        name="type_text",
        description="Type text at the current cursor position.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "confirm_reason": {"type": "string"},
            },
            "required": ["text"],
        },
        safety=SafetyLevel.SAFE,
    )

    def execute(self, arguments: dict) -> ToolResult:
        text = str(arguments["text"])
        display = f"Typing “{text[:32]}”"
        return self._run(arguments, display, lambda: self._automation.type_text(text))


class PressKeyTool(_AutomationTool):
    spec = ToolSpec(
        name="press_key",
        description="Press a single key (enter, tab, escape, backspace …).",
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
        safety=SafetyLevel.SAFE,
    )

    def execute(self, arguments: dict) -> ToolResult:
        key = str(arguments["key"])
        display = f"Pressing {key}"
        return self._run(arguments, display, lambda: self._automation.press(key))


class HotkeyTool(_AutomationTool):
    spec = ToolSpec(
        name="hotkey",
        description="Press a key combination (e.g. ctrl+s).",
        input_schema={
            "type": "object",
            "properties": {"keys": {"type": "string"}},
            "required": ["keys"],
        },
        safety=SafetyLevel.SAFE,
    )

    def execute(self, arguments: dict) -> ToolResult:
        keys = str(arguments["keys"])
        display = f"Pressing {keys}"
        return self._run(arguments, display, lambda: self._automation.hotkey(keys))
