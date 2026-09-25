"""Desktop input automation: pyautogui first, xdotool as fallback.

All operations are cooperative with the emergency stop: ``abort()`` is
checked before every operation and between chunks of typed text, so a
global Stop cancels long typing runs almost immediately.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from abc import ABC, abstractmethod


class AutomationError(RuntimeError):
    """Raised when an input operation fails."""


class AutomationUnavailable(AutomationError):
    """Raised when no automation backend can work in this session."""


class AutomationStopped(AutomationError):
    """Raised when the emergency stop aborted an operation."""


# Canonical key names mapped per backend.
_KEY_ALIASES = {
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
_XDOTOOL_KEYS = {
    "enter": "Return",
    "escape": "Escape",
    "tab": "Tab",
    "space": "space",
    "backspace": "BackSpace",
    "delete": "Delete",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}
_PYAUTOGUI_KEYS = {
    "escape": "esc",
    "super": "win",
}
_XDOTOOL_BUTTONS = {"left": "1", "middle": "2", "right": "3"}

_TYPE_CHUNK = 24  # characters per abort-checked typing chunk


def _xdotool_key(key: str) -> str:
    return _XDOTOOL_KEYS.get(key, key)


class InputBackend(ABC):
    name: str = "base"

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool: ...

    @abstractmethod
    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None: ...

    @abstractmethod
    def click(self, x: int | None, y: int | None, button: str) -> None: ...

    @abstractmethod
    def double_click(self, x: int | None, y: int | None) -> None: ...

    @abstractmethod
    def type_text(self, text: str, interval: float) -> None: ...

    @abstractmethod
    def hotkey(self, keys: tuple[str, ...]) -> None: ...

    def press(self, key: str) -> None:
        self.hotkey((key,))


class PyAutoGuiBackend(InputBackend):
    name = "pyautogui"

    @staticmethod
    def _module():
        try:
            import pyautogui
        except Exception:  # noqa: BLE001 - import may fail without a display
            return None
        return pyautogui

    @classmethod
    def is_available(cls) -> bool:
        module = cls._module()
        if module is None:
            return False
        try:
            module.size()  # fails without an X / XWayland display
            return True
        except Exception:  # noqa: BLE001
            return False

    def __init__(self) -> None:
        module = self._module()
        if module is None:
            raise AutomationUnavailable("pyautogui is not installed")
        try:
            module.size()
        except Exception as exc:  # noqa: BLE001
            raise AutomationUnavailable(
                f"pyautogui cannot reach a display: {exc}"
            ) from exc
        module.FAILSAFE = True  # abort by moving the mouse into a corner
        module.PAUSE = 0.02
        self._pg = module

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None:
        self._pg.moveTo(x, y, duration=duration)

    def click(self, x: int | None, y: int | None, button: str) -> None:
        self._pg.click(x=x, y=y, button=button)

    def double_click(self, x: int | None, y: int | None) -> None:
        self._pg.doubleClick(x=x, y=y)

    def type_text(self, text: str, interval: float) -> None:
        self._pg.write(text, interval=interval)

    def hotkey(self, keys: tuple[str, ...]) -> None:
        self._pg.hotkey(*[_PYAUTOGUI_KEYS.get(key, key) for key in keys])


class XdotoolBackend(InputBackend):
    name = "xdotool"
    _BINARY = "xdotool"

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which(cls._BINARY) is not None

    def _run(self, *args: str) -> None:
        result = subprocess.run(
            [self._BINARY, *args], capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            raise AutomationError(
                result.stderr.strip() or f"xdotool {' '.join(args)} failed"
            )

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None:
        self._run("mousemove", "--sync", str(x), str(y))

    def click(self, x: int | None, y: int | None, button: str) -> None:
        if x is not None and y is not None:
            self.move_mouse(x, y)
        self._run("click", _XDOTOOL_BUTTONS.get(button, "1"))

    def double_click(self, x: int | None, y: int | None) -> None:
        if x is not None and y is not None:
            self.move_mouse(x, y)
        self._run("click", "--repeat", "2", "1")

    def type_text(self, text: str, interval: float) -> None:
        delay_ms = max(1, int(interval * 1000))
        self._run("type", "--clearmodifiers", "--delay", str(delay_ms), "--", text)

    def hotkey(self, keys: tuple[str, ...]) -> None:
        combo = "+".join(_xdotool_key(key) for key in keys)
        self._run("key", "--clearmodifiers", combo)


class Automation:
    """High-level input control with cooperative emergency-stop checks."""

    def __init__(self, backend: InputBackend | None = None) -> None:
        self._backend = backend
        self._stop = threading.Event()
        self._typing_interval = 0.02
        self._action_delay = 0.0

    def configure(
        self, *, typing_speed_ms: int = 24, action_delay_ms: int = 0
    ) -> None:
        """User-tunable pacing (Settings → Automation)."""
        self._typing_interval = max(1, int(typing_speed_ms)) / 1000.0
        self._action_delay = max(0, int(action_delay_ms)) / 1000.0

    def _settle(self) -> None:
        """Abort-checked pause after an action (user-configured delay)."""
        if self._action_delay > 0 and self._stop.wait(self._action_delay):
            raise AutomationStopped("emergency stop during action delay")

    @property
    def backend_name(self) -> str:
        return self._resolve_backend().name

    def abort(self) -> None:
        """Signal an emergency stop; in-flight chunks finish, new ones raise."""
        self._stop.set()

    def reset(self) -> None:
        self._stop.clear()

    # ---------------------------------------------------------- operations

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None:
        self._check()
        self._resolve_backend().move_mouse(x, y, duration)

    def left_click(self, x: int | None = None, y: int | None = None) -> None:
        self.click(x, y, button="left")

    def right_click(self, x: int | None = None, y: int | None = None) -> None:
        self.click(x, y, button="right")

    def click(
        self, x: int | None = None, y: int | None = None, *, button: str = "left"
    ) -> None:
        self._check()
        self._resolve_backend().click(x, y, button)

    def double_click(self, x: int | None = None, y: int | None = None) -> None:
        self._check()
        self._resolve_backend().double_click(x, y)

    def type_text(self, text: str, interval: float | None = None) -> None:
        backend = self._resolve_backend()
        step = self._typing_interval if interval is None else interval
        for start in range(0, len(text), _TYPE_CHUNK):
            self._check()
            backend.type_text(text[start : start + _TYPE_CHUNK], step)

    def press(self, key: str) -> None:
        self._check()
        self._resolve_backend().press(self._canonical(key))
        self._settle()

    def hotkey(self, combo: str) -> None:
        keys = tuple(self._canonical(part) for part in combo.replace("+", " ").split())
        self._check()
        self._resolve_backend().hotkey(keys)
        self._settle()

    # ------------------------------------------------------------ internal

    @staticmethod
    def _canonical(key: str) -> str:
        key = key.strip().lower()
        return _KEY_ALIASES.get(key, key)

    def _check(self) -> None:
        if self._stop.is_set():
            raise AutomationStopped("Automation stopped.")

    def _resolve_backend(self) -> InputBackend:
        if self._backend is None:
            for backend_cls in (PyAutoGuiBackend, XdotoolBackend):
                if backend_cls.is_available():
                    self._backend = backend_cls()
                    break
            else:
                raise AutomationUnavailable(
                    "No automation backend available (need pyautogui or xdotool on X11)"
                )
        return self._backend
