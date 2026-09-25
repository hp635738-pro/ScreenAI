"""Terminal tool — TerminalTool → SafetyManager → TerminalEngine.

The LLM cannot bypass the safety layer with shell syntax: every command is
classified first (blocked commands are refused, risky commands need user
confirmation) and secrets are redacted from the observation.
"""

from __future__ import annotations

from core.safety import ErrorCategory, SafetyLevel, SafetyManager, ToolError, redact
from core.terminal import TerminalEngine
from core.tools import Tool, ToolResult, ToolSpec, enforce_safety


class RunTerminalCommandTool(Tool):
    spec = ToolSpec(
        name="run_terminal_command",
        description=(
            "Run a terminal command and return its output. Destructive or "
            "privilege-escalating commands are refused; risky ones ask the user."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["command"],
        },
        safety=SafetyLevel.CONFIRM,
    )

    def __init__(
        self, terminal: TerminalEngine, safety: SafetyManager, timeout: float = 30.0
    ) -> None:
        self._terminal = terminal
        self._safety = safety
        self._timeout = timeout

    def execute(self, arguments: dict) -> ToolResult:
        command = str(arguments["command"]).strip()
        decision = self._safety.evaluate_command(command)
        if decision.level is SafetyLevel.BLOCKED:
            raise ToolError(decision.reason, ErrorCategory.BLOCKED)
        enforce_safety(
            self._safety,
            self.spec,
            arguments,
            description=command,
        )

        timeout = arguments.get("timeout") or self._timeout
        result = self._terminal.execute(command, timeout=float(timeout))

        output = redact((result.stdout or "") + ("\n" + result.stderr if result.stderr else ""))
        output = output.strip()[:2000]
        if result.cancelled:
            return ToolResult(
                False,
                "Command cancelled.",
                error_category=ErrorCategory.CANCELLED.value,
                display="Command cancelled",
            )
        if result.timed_out:
            return ToolResult(
                False,
                f"Command timed out after {timeout}s.",
                error_category=ErrorCategory.TIMEOUT.value,
                display="Command timed out",
            )
        summary = result.summary
        return ToolResult(
            result.success,
            output or summary,
            data={"exit_code": result.exit_code, "summary": summary},
            error_category=None if result.success else ErrorCategory.UNKNOWN.value,
            display="Running command" if result.success else summary,
        )
