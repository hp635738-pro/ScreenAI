"""Desktop capability detection.

Used by the first-run wizard and the diagnostics report. Every probe is
defensive: a missing library, headless session or denied permission
yields a warning entry with an actionable hint — never an exception.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass


@dataclass(slots=True)
class Capability:
    name: str
    ok: bool
    detail: str
    hint: str = ""

    @property
    def status(self) -> str:
        return "OK" if self.ok else "Unavailable"


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


class CapabilityProbe:
    """Collects capabilities; environment lookups are injectable for tests."""

    def __init__(
        self,
        env: dict[str, str] | None = None,
        which=shutil.which,  # noqa: ANN001
        voice_providers=None,  # noqa: ANN001
    ) -> None:
        self._env = os.environ if env is None else env
        self._which = which
        self._voice_providers = voice_providers

    # ------------------------------------------------------------ probes

    def display_server(self) -> Capability:
        session = str(self._env.get("XDG_SESSION_TYPE", "")).lower()
        has_x = bool(self._env.get("DISPLAY"))
        has_wayland = bool(self._env.get("WAYLAND_DISPLAY"))
        if session == "x11" or (has_x and not has_wayland):
            detail = "X11 session — full automation support."
            return Capability("Display server", True, detail)
        if has_wayland and has_x:
            detail = "Wayland via XWayland — automation works, some apps are shielded."
            return Capability(
                "Display server",
                True,
                detail,
                "Prefer X11 sessions for reliable input injection.",
            )
        if has_wayland:
            return Capability(
                "Display server",
                False,
                "Pure Wayland session — input injection unavailable.",
                "Log into an X11/XWayland session or enable XWayland.",
            )
        return Capability(
            "Display server",
            False,
            "No display detected (headless).",
            "Run on a desktop session.",
        )

    def mouse_automation(self) -> Capability:
        return self._input_capability("Mouse automation")

    def keyboard_automation(self) -> Capability:
        return self._input_capability("Keyboard automation")

    def _input_capability(self, name: str) -> Capability:
        has_x = bool(self._env.get("DISPLAY"))
        if self._which("xdotool"):
            return Capability(name, True, "xdotool available.")
        if not _module_available("pyautogui"):
            return Capability(
                name, False, "pyautogui missing.", "Install python3-pyautogui or xdotool."
            )
        if not has_x:
            return Capability(
                name,
                False,
                "pyautogui present but no X display.",
                "Needs X11 or XWayland (DISPLAY must be set).",
            )
        return Capability(name, True, "pyautogui + X display.")

    def screenshot(self) -> Capability:
        if not _module_available("mss"):
            return Capability(
                "Screenshot capture", False, "mss missing.", "Install python3-mss."
            )
        try:
            import mss  # noqa: PLC0415

            with (getattr(mss, "MSS", mss.mss))() as sct:
                sct.grab(sct.monitors[0])
            return Capability("Screenshot capture", True, "mss capture works.")
        except Exception as exc:  # noqa: BLE001
            return Capability(
                "Screenshot capture",
                False,
                f"Capture failed: {exc}",
                "Check display permissions.",
            )

    def ocr(self) -> Capability:
        if _module_available("easyocr"):
            return Capability("OCR (EasyOCR)", True, "EasyOCR installed (offline).")
        return Capability(
            "OCR (EasyOCR)",
            False,
            "easyocr not installed.",
            "pip install easyocr — find_text falls back to colour matching meanwhile.",
        )

    def voice(self) -> Capability:
        providers = self._voice_providers or []
        usable = [p for p in providers if getattr(p, "is_available", lambda: False)()]
        if usable:
            names = ", ".join(getattr(p, "name", "?") for p in usable)
            return Capability("Voice input", True, f"Providers: {names}")
        return Capability(
            "Voice input",
            False,
            "No speech-to-text engine available.",
            "Install faster-whisper or another VoiceProvider — the rest of "
            "ScreenAI works without it.",
        )

    def tray(self) -> Capability:
        try:
            from PySide6.QtWidgets import QSystemTrayIcon  # noqa: PLC0415

            ok = (QSystemTrayIcon.isSystemTrayAvailable() if _qt_app_available() else False)
        except Exception:  # noqa: BLE001
            ok = False
        return Capability(
            "System tray",
            ok,
            "Tray icon available." if ok else "No system tray in this session.",
            "" if ok else "Close-to-tray is unavailable; closing quits the app.",
        )

    # ----------------------------------------------------------- report

    def detect(self) -> list[Capability]:
        checks = [
            self.display_server,
            self.mouse_automation,
            self.keyboard_automation,
            self.screenshot,
            self.ocr,
            self.voice,
            self.tray,
        ]
        results: list[Capability] = []
        for check in checks:
            try:
                results.append(check())
            except Exception as exc:  # noqa: BLE001
                name = check.__name__.replace("_", " ")
                results.append(Capability(name, False, f"Check failed: {exc}"))
        return results


def _qt_app_available() -> bool:
    """Qt GUI probes need a real QApplication on a real platform.

    Without a QApplication, or on the offscreen/dummy test platforms,
    QSystemTrayIcon/DBus calls can hard-crash — so probe only when safe.
    """
    try:
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415

        app = QGuiApplication.instance()
        if app is None:
            return False
        return app.platformName() not in ("offscreen", "dummy", "minimal", "vnc")
    except Exception:  # noqa: BLE001
        return False
