"""Formal tool registry for the ScreenAI agent.

Every tool declares name, description, JSON input schema and a safety
level. The agent discovers capabilities through this registry — tool
logic is never hardcoded into the LLM layer, and the LLM can only request
registered tools (generated code is never executed).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.safety import ErrorCategory, SafetyLevel, SafetyManager, ToolError


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    safety: SafetyLevel


@dataclass(slots=True)
class ToolResult:
    success: bool
    output: str
    data: dict = field(default_factory=dict)
    error_category: str | None = None
    display: str | None = None  # short popup phrase, e.g. "Found Export"


class Tool(ABC):
    """One registered agent capability."""

    spec: ToolSpec

    @abstractmethod
    def execute(self, arguments: dict) -> ToolResult:
        """Run the tool. Raise ``ToolError`` on failure."""


def enforce_safety(
    safety: SafetyManager,
    spec: ToolSpec,
    arguments: dict,
    *,
    confirm_reason: str | None = None,
    description: str = "",
) -> None:
    """Second gate inside the tool (the agent asks the user beforehand).

    ``arguments['_approved']`` marks a call the user already confirmed.
    """
    decision = safety.evaluate_tool(
        spec.name,
        arguments,
        declared=spec.safety,
        confirm_reason=confirm_reason,
        description=description,
    )
    if decision.level is SafetyLevel.BLOCKED:
        raise ToolError(decision.reason, ErrorCategory.BLOCKED)
    if decision.needs_confirmation and not arguments.get("_approved"):
        raise ToolError(
            f"Confirmation required: {decision.reason}",
            ErrorCategory.CONFIRMATION_DECLINED,
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def specs(self) -> list[ToolSpec]:
        return [self._tools[name].spec for name in self.names()]

    def schemas_for_prompt(self) -> str:
        lines = []
        for spec in self.specs():
            props = spec.input_schema.get("properties", {})
            args = ", ".join(
                f"{key}: {value.get('type', 'string')}"
                + ("" if key in spec.input_schema.get("required", []) else "?")
                for key, value in props.items()
            )
            lines.append(
                f"- {spec.name} [{spec.safety.value}] ({args}) — {spec.description}"
            )
        return "\n".join(lines)

    def execute(self, name: str, arguments: dict) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(
                f"Tool '{name}' is not registered.",
                ErrorCategory.INVALID_ARGUMENTS,
            )
        self._validate(tool.spec.input_schema, arguments or {})
        return tool.execute(arguments or {})

    @staticmethod
    def _validate(schema: dict, arguments: dict) -> None:
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in arguments:
                raise ToolError(
                    f"Missing required argument '{key}'.",
                    ErrorCategory.INVALID_ARGUMENTS,
                )
        for key, value in arguments.items():
            if key.startswith("_") or key not in properties:
                continue
            expected = properties[key].get("type")
            ok = {
                "string": lambda v: isinstance(v, str),
                "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                "number": lambda v: isinstance(v, (int, float))
                and not isinstance(v, bool),
                "boolean": lambda v: isinstance(v, bool),
                "array": lambda v: isinstance(v, list),
            }.get(expected)
            if ok is not None and not ok(value):
                raise ToolError(
                    f"Argument '{key}' must be {expected}.",
                    ErrorCategory.INVALID_ARGUMENTS,
                )
