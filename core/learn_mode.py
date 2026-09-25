"""Learn Mode: record user demonstrations into workflow steps.

Records mouse clicks, keyboard shortcuts, typed text, the active window
title and timestamps while recording is on. Events arrive on pynput
listener threads and are forwarded as Qt signals — the GUI never blocks.

Listeners are injectable (``listeners_factory``) so the recorder works
headless in tests and degrades gracefully when pynput is unavailable.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from core.models import ActionType, LearnedStep

MODIFIER_KEYS = frozenset({"ctrl", "shift", "alt", "super"})
MODIFIER_MAP = {
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "cmd": "super",
    "cmd_l": "super",
    "cmd_r": "super",
}
# Modifier order used when recording/playing combos.
MODIFIER_ORDER = ("ctrl", "shift", "alt", "super")

TYPING_GAP_S = 2.0  # split typed runs after this idle gap
DOUBLE_CLICK_S = 0.35
DOUBLE_CLICK_PX = 6

_CLICK_ACTIONS = {
    "left": ActionType.LEFT_CLICK,
    "right": ActionType.RIGHT_CLICK,
}


def active_window_title() -> str:
    """Title of the active window via xdotool (X11); "" when unavailable."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=0.7,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _key_name(key) -> str | None:  # noqa: ANN001
    """Map a pynput key object to a canonical name ('ctrl', 'a', 'enter'…)."""
    char = getattr(key, "char", None)
    if char is not None:
        return char
    name = getattr(key, "name", None)
    if name:
        return MODIFIER_MAP.get(name, name)
    text = str(key)
    if text.startswith("Key."):
        name = text[4:]
        return MODIFIER_MAP.get(name, name)
    return None


def _default_listeners_factory(on_click, on_key_press, on_key_release):  # noqa: ANN001
    """Create pynput listeners. Import deferred so headless use is possible."""
    try:
        from pynput import keyboard, mouse
    except Exception as exc:  # noqa: BLE001 - missing deps or no display
        raise RuntimeError(f"pynput is not available: {exc}") from exc
    mouse_listener = mouse.Listener(on_click=on_click)
    keyboard_listener = keyboard.Listener(
        on_press=on_key_press, on_release=on_key_release
    )
    return mouse_listener, keyboard_listener


class WorkflowRecorder(QObject):
    """Records a demonstration as a list of :class:`LearnedStep`."""

    step_recorded = Signal(object)  # newest LearnedStep
    steps_changed = Signal()
    recording_started = Signal()
    recording_stopped = Signal(int)  # number of recorded steps
    notice = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        listeners_factory: Callable | None = None,
        window_title_fn: Callable[[], str] | None = None,
        target_resolver: Callable[[int, int], str | None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(parent)
        self._listeners_factory = listeners_factory or _default_listeners_factory
        self._window_title_fn = window_title_fn or active_window_title
        self._target_resolver = target_resolver
        self._clock = clock
        self._lock = threading.RLock()

        self._steps: list[LearnedStep] = []
        self._recording = False
        self._mouse_listener = None
        self._keyboard_listener = None

        self._modifiers: set[str] = set()
        self._typed: list[str] = []
        self._last_type_at = 0.0
        self._last_step_at: float | None = None
        self._last_click: tuple[float, int, int, str, LearnedStep] | None = None

    # --------------------------------------------------------- interface

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def steps(self) -> list[LearnedStep]:
        with self._lock:
            return list(self._steps)

    def start(self) -> bool:
        if self._recording:
            return False
        self.clear()
        try:
            self._mouse_listener, self._keyboard_listener = self._listeners_factory(
                self.on_click, self.on_key_press, self.on_key_release
            )
            self._mouse_listener.start()
            self._keyboard_listener.start()
        except Exception as exc:  # noqa: BLE001 - pynput/display problems
            self.notice.emit(f"Cannot start recording: {exc}")
            return False
        self._recording = True
        self.recording_started.emit()
        return True

    def stop(self) -> list[LearnedStep]:
        if not self._recording:
            return self.steps
        with self._lock:
            self._flush_typed()
            self._recording = False
        for listener in (self._mouse_listener, self._keyboard_listener):
            try:
                if listener is not None:
                    listener.stop()
            except Exception:  # noqa: BLE001 - listener teardown is best-effort
                pass
        self._mouse_listener = None
        self._keyboard_listener = None
        self.recording_stopped.emit(len(self._steps))
        return self.steps

    def clear(self) -> None:
        with self._lock:
            self._steps.clear()
            self._typed.clear()
            self._modifiers.clear()
            self._last_step_at = None
            self._last_type_at = 0.0
            self._last_click = None
        self.steps_changed.emit()

    # --------------------------------------------------- event sinks

    def on_click(self, x: int, y: int, button, pressed: bool) -> None:  # noqa: ANN001
        if not self._recording or not pressed:
            return
        name = getattr(button, "name", str(button).split(".")[-1])
        if name not in _CLICK_ACTIONS:
            name = "left"
        with self._lock:
            self._flush_typed()
            now = self._clock()
            step = self._record(
                _CLICK_ACTIONS[name],
                coordinates=(int(x), int(y)),
                metadata={"button": name},
            )
            if (
                self._last_click is not None
                and name == self._last_click[3]
                and now - self._last_click[0] <= DOUBLE_CLICK_S
                and abs(x - self._last_click[1]) <= DOUBLE_CLICK_PX
                and abs(y - self._last_click[2]) <= DOUBLE_CLICK_PX
            ):
                previous = self._last_click[4]
                merged = LearnedStep(
                    ActionType.DOUBLE_CLICK,
                    previous.target_text or step.target_text,
                    (int(x), int(y)),
                    previous.delay + step.delay,
                    {**previous.metadata, "button": name, "timestamp": now},
                )
                with self._lock:
                    if step in self._steps:
                        self._steps.remove(step)
                    if previous in self._steps:
                        self._steps[self._steps.index(previous)] = merged
                self._last_click = None
                self.step_recorded.emit(merged)
                self.steps_changed.emit()
                return
            self._last_click = (now, int(x), int(y), name, step)

    def on_key_press(self, key) -> None:  # noqa: ANN001
        if not self._recording:
            return
        name = _key_name(key)
        if name is None:
            return
        with self._lock:
            if name in MODIFIER_KEYS:
                self._modifiers.add(name)
                return
            if self._modifiers:
                self._flush_typed()
                combo = self._combo(name)
                self._record(
                    ActionType.HOTKEY,
                    target_text=combo,
                    metadata={"keys": combo.split("+")},
                )
                return
            if name == "backspace":
                if self._typed:
                    self._typed.pop()
                else:
                    self._flush_typed()
                    self._record(ActionType.PRESS_KEY, target_text="backspace")
                return
            if name == "space":
                name = " "
            if len(name) == 1 and name.isprintable():
                now = self._clock()
                if self._typed and now - self._last_type_at > TYPING_GAP_S:
                    self._flush_typed()
                self._typed.append(name)
                self._last_type_at = now
                return
            self._flush_typed()
            self._record(ActionType.PRESS_KEY, target_text=name)

    def on_key_release(self, key) -> None:  # noqa: ANN001
        name = _key_name(key)
        if name in MODIFIER_KEYS:
            with self._lock:
                self._modifiers.discard(name)

    # ------------------------------------------------------- internal

    def _combo(self, key: str) -> str:
        ordered = [m for m in MODIFIER_ORDER if m in self._modifiers]
        ordered.append(key)
        return "+".join(ordered)

    def _flush_typed(self) -> None:
        if self._typed:
            text = "".join(self._typed)
            self._typed.clear()
            self._record(ActionType.TYPE_TEXT, target_text=text)

    def _record(
        self,
        action: ActionType,
        *,
        target_text: str | None = None,
        coordinates: tuple[int, int] | None = None,
        metadata: dict | None = None,
    ) -> LearnedStep:
        if (
            target_text is None
            and coordinates is not None
            and self._target_resolver is not None
            and action
            in (ActionType.LEFT_CLICK, ActionType.RIGHT_CLICK, ActionType.DOUBLE_CLICK)
        ):
            try:
                target_text = self._target_resolver(*coordinates)
            except Exception:  # noqa: BLE001 - labeling is best-effort
                target_text = None
        now = self._clock()
        delay = 0.0 if self._last_step_at is None else max(0.0, now - self._last_step_at)
        meta = dict(metadata or {})
        meta.setdefault("timestamp", now)
        meta.setdefault("window_title", self._window_title_fn())
        step = LearnedStep(action, target_text, coordinates, round(delay, 3), meta)
        self._steps.append(step)
        self._last_step_at = now
        self.step_recorded.emit(step)
        self.steps_changed.emit()
        return step
