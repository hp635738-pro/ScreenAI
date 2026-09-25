"""AI agent core — a bounded tool-using loop over a registered tool set.

USER REQUEST → LLM → TOOL CALL → TOOL EXECUTION → OBSERVATION → LLM → … → DONE

The LLM may only request registered tools; generated code is never
executed. Failures are returned as observations so the model can try a
safe alternative; same-tool failures are capped and the loop has a hard
step limit. CONFIRM-level actions pause for the user; declining a
confirmation ends the task (no sneaky retries around the gate).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.memory import MemoryStore
from core.providers.base import AIProvider, ProviderError, ProviderNotConfigured
from core.safety import ErrorCategory, SafetyLevel, SafetyManager, ToolError, redact
from core.tools import ToolRegistry, ToolSpec


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(slots=True)
class ToolCall:
    name: str
    arguments: dict
    confirm_reason: str | None = None


@dataclass(slots=True)
class AgentEvent:
    kind: str
    tool_name: str | None
    arguments: dict | None
    result: str | None
    success: bool | None
    error_category: str | None
    started_at: str
    ended_at: str


@dataclass(slots=True)
class AgentResult:
    success: bool
    summary: str
    cancelled: bool = False
    steps: int = 0
    provider: str | None = None
    error_category: str | None = None
    events: list[AgentEvent] = field(default_factory=list)


_STATUS_HINTS: dict[str, Callable[[dict], str]] = {
    "open_application": lambda a: f"Opening {a.get('name', 'app')}",
    "close_application": lambda a: f"Closing {a.get('name', 'app')}",
    "run_terminal_command": lambda a: f"Running “{str(a.get('command', ''))[:28]}”",
    "mouse_move": lambda a: f"Moving mouse to {a.get('x')} {a.get('y')}",
    "mouse_click": lambda a: f"Clicking at {a.get('x')} {a.get('y')}",
    "type_text": lambda a: f"Typing “{str(a.get('text', ''))[:24]}”",
    "press_key": lambda a: f"Pressing {a.get('key')}",
    "hotkey": lambda a: f"Pressing {a.get('keys')}",
    "screenshot": lambda a: "Inspecting screen",
    "inspect_screen": lambda a: "Inspecting screen",
    "find_text": lambda a: f"Finding {a.get('text')}",
    "run_workflow": lambda a: "Playing workflow",
    "start_learning": lambda a: "Recording…",
    "stop_learning": lambda a: "Finishing recording",
    "save_workflow": lambda a: "Saving workflow",
    "list_workflows": lambda a: "Listing workflows",
}


class Agent:
    def __init__(
        self,
        provider: AIProvider,
        registry: ToolRegistry,
        safety: SafetyManager,
        *,
        memory: MemoryStore | None = None,
        status_cb: Callable[[str], None] | None = None,
        live_cb: Callable[[str], None] | None = None,
        confirm_cb: Callable[[str], bool] | None = None,
        event_cb: Callable[[AgentEvent], None] | None = None,
        cancel_event: threading.Event | None = None,
        max_steps: int = 12,
        tool_fail_limit: int = 3,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._safety = safety
        self._memory = memory
        self._status_cb = status_cb or (lambda text: None)
        self._live_cb = live_cb or (lambda text: None)
        self._confirm_cb = confirm_cb
        self._event_cb = event_cb or (lambda event: None)
        self._cancel = cancel_event or threading.Event()
        self._max_steps = max_steps
        self._tool_fail_limit = tool_fail_limit
        self._failures: dict[str, int] = {}
        self._events: list[AgentEvent] = []
        self._last_display: str | None = None

    # ------------------------------------------------------------- loop

    def run(self, command: str) -> AgentResult:
        provider_name = getattr(self._provider, "last_used", None) or self._provider.name
        session_id = (
            self._memory.start_session(command, provider_name) if self._memory else None
        )
        self._status_cb("Understanding request…")
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": command},
        ]
        parse_errors = 0
        api_errors = 0
        steps = 0
        result: AgentResult | None = None
        try:
            while steps < self._max_steps:
                if self._cancel.is_set():
                    result = self._cancelled_result(steps, provider_name)
                    break
                try:
                    response = self._chat(messages)
                    provider_name = response.provider or provider_name
                except ProviderError as exc:
                    api_errors += 1
                    if api_errors >= 2:
                        result = AgentResult(
                            False,
                            f"AI provider error: {exc}",
                            steps=steps,
                            provider=provider_name,
                            error_category=self._provider_category(exc).value,
                        )
                        break
                    continue

                call, final, parse_error = self._parse_decision(response.text)
                if parse_error is not None:
                    parse_errors += 1
                    messages.append(
                        {"role": "assistant", "content": redact(response.text)[:1500]}
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "OBSERVATION: protocol error — respond with ONLY one "
                                "JSON object: {\"tool\": …, \"arguments\": …} or "
                                "{\"final\": …}."
                            ),
                        }
                    )
                    if parse_errors > 1:
                        result = AgentResult(
                            False,
                            "The AI model did not respond in the expected format.",
                            steps=steps,
                            provider=provider_name,
                            error_category=ErrorCategory.PROTOCOL_ERROR.value,
                        )
                        break
                    continue

                if final is not None:
                    result = AgentResult(
                        True,
                        final,
                        steps=steps,
                        provider=provider_name,
                    )
                    break

                assert call is not None
                steps += 1
                event = self._execute_call(command, call, session_id)
                self._events.append(event)
                self._event_cb(event)
                observation = event.result or ""
                messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {"tool": call.name, "arguments": call.arguments}
                        )[:1500],
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"OBSERVATION (step {steps}): {observation}",
                    }
                )
                if event.success:
                    self._failures.pop(call.name, None)
                else:
                    self._failures[call.name] = self._failures.get(call.name, 0) + 1
                    if (
                        event.error_category
                        == ErrorCategory.CONFIRMATION_DECLINED.value
                    ):
                        if self._cancel.is_set():
                            result = self._cancelled_result(steps, provider_name)
                        else:
                            result = AgentResult(
                                False,
                                f"Stopped — you declined: {observation}",
                                steps=steps,
                                provider=provider_name,
                                error_category=ErrorCategory.CONFIRMATION_DECLINED.value,
                            )
                        break
                    if self._failures[call.name] >= self._tool_fail_limit:
                        result = AgentResult(
                            False,
                            f"Giving up after {self._failures[call.name]} failed "
                            f"attempts of '{call.name}'.",
                            steps=steps,
                            provider=provider_name,
                            error_category=event.error_category,
                        )
                        break
            if result is None:
                result = AgentResult(
                    False,
                    f"Stopped after {self._max_steps} steps without finishing.",
                    steps=steps,
                    provider=provider_name,
                    error_category=ErrorCategory.TIMEOUT.value,
                )
        finally:
            result.events = list(self._events)
            if session_id and self._memory:
                status = (
                    "cancelled"
                    if result.cancelled
                    else ("completed" if result.success else "failed")
                )
                self._memory.finish_session(session_id, status)
        return result

    # ------------------------------------------------------- single call

    def _execute_call(
        self, task: str, call: ToolCall, session_id: str | None
    ) -> AgentEvent:
        started = _utc_now()
        status = self._status_for(call)
        self._status_cb(status)

        spec: ToolSpec | None = (
            self._registry.get(call.name).spec if self._registry.get(call.name) else None
        )
        arguments = dict(call.arguments)
        outcome_text: str
        success: bool | None = None
        category: str | None = None

        if spec is None:
            success, category = False, ErrorCategory.INVALID_ARGUMENTS.value
            outcome_text = f"ERROR [{category}]: tool '{call.name}' is not registered."
        else:
            decision = self._safety.evaluate_tool(
                call.name,
                arguments,
                declared=spec.safety,
                confirm_reason=call.confirm_reason,
                description=status,
            )
            if decision.level is SafetyLevel.BLOCKED:
                success, category = False, ErrorCategory.BLOCKED.value
                outcome_text = f"ERROR [{category}]: {decision.reason}"
            elif decision.needs_confirmation:
                prompt = f"{status} requires confirmation."
                if call.confirm_reason:
                    prompt += f" {call.confirm_reason}."
                self._status_cb("Waiting for confirmation")
                approved = bool(self._confirm_cb and self._confirm_cb(prompt))
                if not approved:
                    success = False
                    category = ErrorCategory.CONFIRMATION_DECLINED.value
                    outcome_text = (
                        f"ERROR [{category}]: the user declined — do not retry "
                        "this action another way."
                    )
                else:
                    arguments["_approved"] = True
                    success, category, outcome_text = self._run_tool(call, arguments)
                    if success:
                        self._status_cb(self._last_display or status)
            else:
                success, category, outcome_text = self._run_tool(call, arguments)
                if success:
                    self._status_cb(self._last_display or status)

        ended = _utc_now()
        event = AgentEvent(
            kind="tool_call",
            tool_name=call.name,
            arguments={k: v for k, v in call.arguments.items()},
            result=outcome_text[:2000],
            success=success,
            error_category=category,
            started_at=started,
            ended_at=ended,
        )
        if session_id and self._memory:
            self._memory.log_tool(
                session_id,
                task=task,
                provider=self._provider.name,
                tool_name=call.name,
                arguments=call.arguments,
                result=outcome_text,
                success=bool(success),
                error_category=category,
                started_at=started,
                ended_at=ended,
            )
        return event

    def _run_tool(self, call: ToolCall, arguments: dict) -> tuple[bool, str | None, str]:
        try:
            result = self._registry.execute(call.name, arguments)
        except ToolError as exc:
            self._last_display = None
            return False, exc.category.value, f"ERROR [{exc.category.value}]: {exc}"
        self._last_display = result.display
        if result.success:
            return True, None, result.output
        category = result.error_category or ErrorCategory.UNKNOWN.value
        return False, category, f"ERROR [{category}]: {result.output}"

    def _status_for(self, call: ToolCall) -> str:
        hint = _STATUS_HINTS.get(call.name)
        return hint(call.arguments) if hint else f"Running {call.name}"

    def _cancelled_result(self, steps: int, provider_name: str) -> AgentResult:
        self._status_cb("Cancelled")
        return AgentResult(
            False,
            "Cancelled by user.",
            cancelled=True,
            steps=steps,
            provider=provider_name,
            error_category=ErrorCategory.CANCELLED.value,
        )

    # ------------------------------------------------------------ LLM IO

    def _chat(self, messages: list[dict]) -> object:  # noqa: ANN202
        def live(text: str) -> None:
            self._live_cb(redact(text))

        try:
            return self._provider.chat(messages, stream_cb=live)
        except ProviderNotConfigured as exc:
            raise ProviderError(str(exc)) from exc

    @staticmethod
    def _provider_category(exc: ProviderError) -> ErrorCategory:
        if isinstance(exc, ProviderNotConfigured):
            return ErrorCategory.PROVIDER_UNAVAILABLE
        text = str(exc).lower()
        if "unavailable" in text or "not available" in text:
            return ErrorCategory.API_UNAVAILABLE
        return ErrorCategory.API_ERROR

    # ---------------------------------------------------------- protocol

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        start = text.find("{")
        while start != -1:
            depth = 0
            in_string = False
            escape = False
            for index in range(start, len(text)):
                char = text[index]
                if in_string:
                    if escape:
                        escape = False
                    elif char == "\\":
                        escape = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(text[start : index + 1])
                        except ValueError:
                            break
                        return parsed if isinstance(parsed, dict) else None
            start = text.find("{", start + 1)
        return None

    def _parse_decision(self, text: str) -> tuple[ToolCall | None, str | None, str | None]:
        obj = self._extract_json(text or "")
        if obj is None:
            return None, None, "no JSON object in the response"
        if "final" in obj or "answer" in obj:
            final = str(obj.get("final") or obj.get("answer") or "").strip()
            return None, final or "Done.", None
        name = obj.get("tool") or obj.get("tool_name") or obj.get("action")
        arguments = obj.get("arguments") or obj.get("args") or {}
        if not name or not isinstance(arguments, dict):
            return None, None, "JSON must contain 'tool' + 'arguments' or 'final'"
        reason = obj.get("confirm_reason") or obj.get("reason")
        return (
            ToolCall(str(name), arguments, str(reason) if reason else None),
            None,
            None,
        )

    def _system_prompt(self) -> str:
        return (
            "You are ScreenAI, a Linux desktop agent. You complete the user's "
            "request by calling ONE tool at a time and reasoning over the "
            "observation before the next step.\n"
            "Respond with ONLY one JSON object — no other text:\n"
            '{"thought": "<brief reasoning>", "tool": "<name>", "arguments": {...}}\n'
            "or, when the task is done or you must report to the user:\n"
            '{"thought": "...", "final": "<report>"}\n\n'
            "Rules:\n"
            "- Use only these registered tools (never invent tools, never emit code):\n"
            f"{self._registry.schemas_for_prompt()}\n"
            "- One tool call per response; wait for OBSERVATION before continuing.\n"
            "- Prefer vision (inspect_screen, find_text) over fixed coordinates.\n"
            "- Prefer run_workflow when a matching saved workflow exists; only use "
            "start_learning when the user explicitly asks to learn a task.\n"
            "- For purchases, orders, messages, form submissions or file deletions "
            'set "confirm_reason" — the user must confirm first.\n'
            "- Never ask for or reveal passwords, API keys or tokens.\n"
            "- On ERROR observations, try a safe alternative or finish with a "
            f"clear report; the same failing tool stops after "
            f"{self._tool_fail_limit} attempts.\n"
        )
