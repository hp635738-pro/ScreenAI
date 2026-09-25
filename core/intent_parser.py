"""Lightweight local intent parser (no AI).

Converts natural commands into structured :class:`core.models.Plan` objects:

    "open firefox"                  -> LAUNCH_APP firefox
    "launch vscode"                 -> LAUNCH_APP vscode
    "open terminal"                 -> LAUNCH_APP terminal
    "type hello world"              -> TYPE_TEXT "hello world"
    "run ls -la"                    -> RUN_TERMINAL "ls -la"
    "press ctrl+c"                  -> HOTKEY ctrl+c
    "open firefox then type hi"     -> two steps (chained with "then")

Steps are separated with ``then``, ``and then`` or ``;`` (outside quotes).
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable

from core.models import Action, ActionType, Plan

# Matchers are tried in order; the first match wins.
_RE_TYPE = re.compile(r"^(?:type|write|say|enter text)\s+(.+)$", re.IGNORECASE)
_RE_KEY = re.compile(r"^(?:press|hotkey|key)\s+(.+)$", re.IGNORECASE)
_RE_CLICK = re.compile(
    r"^(?:(left|right|double)[\s-]*)?click"
    r"(?:\s+(?:at|on|to)\s*\(?\s*(\d+)\s*[,\s]\s*(\d+)\s*\)?)?$",
    re.IGNORECASE,
)
_RE_DOUBLE_CLICK = re.compile(
    r"^double[\s-]*click"
    r"(?:\s+(?:at|on|to)\s*\(?\s*(\d+)\s*[,\s]\s*(\d+)\s*\)?)?$",
    re.IGNORECASE,
)
_RE_MOVE = re.compile(
    r"^move\s+(?:the\s+)?(?:mouse|cursor|pointer)?\s*(?:to)?\s*"
    r"\(?\s*(\d+)\s*[,\s]\s*(\d+)\s*\)?$",
    re.IGNORECASE,
)
_RE_WAIT = re.compile(
    r"^(?:wait|sleep|pause)\s+(\d+(?:\.\d+)?)\s*(ms|msec|s|sec|secs|seconds?|m|min|minutes?)?$",
    re.IGNORECASE,
)
_RE_SIMULATE = re.compile(r"^(?:simulate|demo|pretend)\s+(.+)$", re.IGNORECASE)
_RE_TERMINAL = re.compile(
    r"^(?:run\s+)?(?:the\s+)?(?:command\s+)?(?:in\s+)?(?:the\s+)?"
    r"(?:terminal|console|shell)\s*(?::|,)?\s+(.+)$",
    re.IGNORECASE,
)
_RE_APP = re.compile(r"^(?:open|launch|start)\s+(.+)$", re.IGNORECASE)
_RE_RUN = re.compile(r"^run\s+(.+)$", re.IGNORECASE)
_RE_BARE = re.compile(r"^[A-Za-z0-9_.+/@-]+(?:\s.*)?$")

_STEP_SPLIT = re.compile(r"\s+then\s+|\s+and then\s+|;\s*", re.IGNORECASE)

_KEY_CANONICAL = {
    "control": "ctrl",
    "ctl": "ctrl",
    "cmd": "super",
    "command": "super",
    "win": "super",
    "windows": "super",
    "option": "alt",
    "esc": "escape",
    "return": "enter",
    "spacebar": "space",
}
_KEY_DISPLAY = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "super": "Super",
    "enter": "Enter",
    "escape": "Esc",
    "tab": "Tab",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
}


class IntentParser:
    def __init__(
        self,
        *,
        known_apps: Callable[[], frozenset[str]] | None = None,
        display_name: Callable[[str], str] | None = None,
        executable_checker: Callable[[str], str | None] | None = None,
    ) -> None:
        self._known_apps = known_apps or (lambda: frozenset())
        self._display_name = display_name or (lambda name: name.title())
        self._is_executable = executable_checker or shutil.which

    # ------------------------------------------------------------ parsing

    def parse(self, command: str) -> Plan:
        segments = self._split_segments(command)
        actions = [a for segment in segments if (a := self._parse_segment(segment))]
        return Plan(command=command.strip(), actions=actions)

    @staticmethod
    def _split_segments(command: str) -> list[str]:
        """Split on then/;/and-then, honouring quoted text."""
        segments: list[str] = []
        current: list[str] = []
        quote: str | None = None
        index = 0
        lowered = command.lower()
        while index < len(command):
            char = command[index]
            if quote:
                current.append(char)
                if char == quote:
                    quote = None
                index += 1
                continue
            if char in "\"'":
                quote = char
                current.append(char)
                index += 1
                continue
            for separator in (" and then ", " then ", ";"):
                if lowered.startswith(separator, index):
                    segments.append("".join(current))
                    current = []
                    index += len(separator)
                    break
            else:
                current.append(char)
                index += 1
        segments.append("".join(current))
        return [s.strip() for s in segments if s.strip()]

    def _parse_segment(self, segment: str) -> Action | None:
        segment = self._strip_politeness(segment)

        if match := _RE_TYPE.match(segment):
            text = self._unquote(match.group(1).strip())
            return Action(ActionType.TYPE_TEXT, {"text": text}, f"Typing “{text}”")

        if match := _RE_KEY.match(segment):
            combo = match.group(1).strip()
            keys = self._parse_keys(combo)
            display = "+".join(self._display_key(k) for k in keys)
            if len(keys) == 1:
                return Action(ActionType.PRESS_KEY, {"key": keys[0]}, f"Pressing {display}")
            return Action(ActionType.HOTKEY, {"keys": keys}, f"Pressing {display}")

        if match := _RE_DOUBLE_CLICK.match(segment):
            return self._click_action(
                ActionType.DOUBLE_CLICK, "Double-clicking", match, 1, 2
            )

        if match := _RE_CLICK.match(segment):
            button = (match.group(1) or "left").lower()
            kind, label = {
                "left": (ActionType.LEFT_CLICK, "Clicking"),
                "right": (ActionType.RIGHT_CLICK, "Right-clicking"),
                "double": (ActionType.DOUBLE_CLICK, "Double-clicking"),
            }[button]
            return self._click_action(kind, label, match, 2, 3)

        if match := _RE_MOVE.match(segment):
            x, y = int(match.group(1)), int(match.group(2))
            return Action(
                ActionType.MOVE_MOUSE, {"x": x, "y": y}, f"Moving mouse to ({x}, {y})"
            )

        if match := _RE_WAIT.match(segment):
            seconds = float(match.group(1))
            unit = (match.group(2) or "s").lower()
            if unit.startswith("ms") or unit.startswith("msec"):
                seconds /= 1000.0
            elif unit.startswith("m"):
                seconds *= 60.0
            return Action(ActionType.WAIT, {"seconds": seconds}, f"Waiting {seconds:g}s")

        if match := _RE_SIMULATE.match(segment):
            task = match.group(1).strip()
            return Action(ActionType.SIMULATE, {"task": task}, f"Simulating “{task}”")

        if match := _RE_TERMINAL.match(segment):
            return self._terminal_action(match.group(1).strip())

        if match := _RE_APP.match(segment):
            return self._launch_action(match.group(1).strip())

        if match := _RE_RUN.match(segment):
            rest = match.group(1).strip()
            if self._is_known_app(rest):
                return self._launch_action(rest)
            return self._terminal_action(rest)

        if _RE_BARE.match(segment):
            first_token = segment.split()[0]
            if self._is_executable(first_token):
                return self._terminal_action(segment)

        return Action(
            ActionType.UNKNOWN,
            {"input": segment},
            f"Don't understand “{segment}”",
        )

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _strip_politeness(segment: str) -> str:
        for prefix in ("please ", "pls "):
            if segment.lower().startswith(prefix):
                return segment[len(prefix):].strip()
        return segment.strip()

    @staticmethod
    def _unquote(text: str) -> str:
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
            return text[1:-1]
        return text

    def _launch_action(self, name: str) -> Action:
        name = self._unquote(name)
        display = self._display_name(name)
        return Action(ActionType.LAUNCH_APP, {"app": name}, f"Opening {display}")

    def _terminal_action(self, command: str) -> Action:
        return Action(
            ActionType.RUN_TERMINAL, {"command": command}, f"Running “{command}” in terminal"
        )

    @staticmethod
    def _click_action(
        kind: ActionType,
        label: str,
        match: re.Match,
        x_group: int,
        y_group: int,
    ) -> Action:
        params: dict[str, object] = {}
        if match.group(x_group) and match.group(y_group):
            params["x"] = int(match.group(x_group))
            params["y"] = int(match.group(y_group))
        where = f" at ({params['x']}, {params['y']})" if params else ""
        return Action(kind, params, f"{label}{where}")

    @staticmethod
    def _parse_keys(combo: str) -> list[str]:
        raw = re.split(r"[+,\s]+", combo.strip())
        keys = [token.lower() for token in raw if token]
        return [_KEY_CANONICAL.get(key, key) for key in keys]

    @staticmethod
    def _display_key(key: str) -> str:
        return _KEY_DISPLAY.get(key, key.upper() if len(key) == 1 else key.title())

    def _is_known_app(self, name: str) -> bool:
        normalized = " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())
        return name.strip().lower() in self._known_apps() or normalized in self._known_apps()
