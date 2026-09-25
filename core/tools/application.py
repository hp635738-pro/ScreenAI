"""Application tools: open_application, close_application."""

from __future__ import annotations

import os
import signal
import time

from core.app_launcher import AppLauncher, AppNotFoundError, LauncherError
from core.safety import ErrorCategory, SafetyLevel, ToolError
from core.tools import Tool, ToolResult, ToolSpec, enforce_safety
from core.safety import SafetyManager


class ProcessTracker:
    """Remembers PIDs launched this session so they can be closed."""

    def __init__(self) -> None:
        self._pids: dict[str, list[int]] = {}

    def track(self, key: str, pid: int) -> None:
        self._pids.setdefault(key, []).append(pid)

    def pop(self, key: str) -> list[int]:
        return self._pids.pop(key, [])


class OpenApplicationTool(Tool):
    spec = ToolSpec(
        name="open_application",
        description="Launch a desktop application by name (firefox, konsole, vscode …).",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "args": {"type": "array"},
            },
            "required": ["name"],
        },
        safety=SafetyLevel.SAFE,
    )

    def __init__(
        self,
        launcher: AppLauncher,
        tracker: ProcessTracker,
        safety: SafetyManager,
    ) -> None:
        self._launcher = launcher
        self._tracker = tracker
        self._safety = safety

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(self._safety, self.spec, arguments)
        name = str(arguments["name"])
        extra = [str(a) for a in arguments.get("args") or []]
        try:
            result = self._launcher.launch(name, *extra)
        except AppNotFoundError as exc:
            raise ToolError(str(exc), ErrorCategory.APP_NOT_FOUND) from exc
        except LauncherError as exc:
            raise ToolError(str(exc), ErrorCategory.AUTOMATION_FAILURE) from exc
        key = self._launcher.normalize(name)
        self._tracker.track(key, result.pid)
        return ToolResult(
            True,
            f"Opened {result.display} (pid {result.pid})",
            data={"pid": result.pid, "executable": result.executable},
            display=f"Opening {result.display}",
        )


class CloseApplicationTool(Tool):
    spec = ToolSpec(
        name="close_application",
        description=(
            "Close an application that ScreenAI launched this session "
            "(sends SIGTERM, then SIGKILL)."
        ),
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        safety=SafetyLevel.CONFIRM,
    )

    def __init__(
        self, tracker: ProcessTracker, safety: SafetyManager, timeout: float = 2.0
    ) -> None:
        self._tracker = tracker
        self._safety = safety
        self._timeout = timeout

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(
            self._safety,
            self.spec,
            arguments,
            description=str(arguments.get("name", "")),
        )
        name = str(arguments["name"])
        key = AppLauncher.normalize(name)
        pids = self._tracker.pop(key)
        if not pids:
            raise ToolError(
                f"'{name}' was not launched this session; close_application only "
                "closes ScreenAI-launched apps.",
                ErrorCategory.APP_NOT_FOUND,
            )
        closed = 0
        for pid in pids:
            if self._terminate(pid):
                closed += 1
        return ToolResult(
            closed > 0,
            f"Closed {closed}/{len(pids)} window(s) of {name}",
            data={"pids": pids},
            display=f"Closing {name}",
            error_category=None if closed else ErrorCategory.AUTOMATION_FAILURE.value,
        )

    def _terminate(self, pid: int) -> bool:
        for sig, wait in ((signal.SIGTERM, self._timeout), (signal.SIGKILL, 0.2)):
            try:
                os.killpg(pid, sig)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    os.kill(pid, sig)
                except OSError:
                    return False
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except OSError:
                    return True
                time.sleep(0.05)
        return True
