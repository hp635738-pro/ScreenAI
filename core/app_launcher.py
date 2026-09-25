"""Application launcher with natural aliases.

Launches installed applications via ``subprocess.Popen()`` (no shell).
Executables are resolved on ``PATH`` at runtime — nothing is hardcoded.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass


class LauncherError(RuntimeError):
    """Raised when an application cannot be launched."""


class AppNotFoundError(LauncherError):
    def __init__(self, name: str, tried: tuple[str, ...]) -> None:
        super().__init__(
            f"Application '{name}' not found (tried: {', '.join(tried)})"
        )
        self.name = name
        self.tried = tried


@dataclass(frozen=True, slots=True)
class AppAlias:
    key: str
    display: str
    candidates: tuple[str, ...]


@dataclass(slots=True)
class ResolvedApp:
    key: str
    display: str
    executable: str


@dataclass(slots=True)
class LaunchResult:
    display: str
    executable: str
    pid: int


class AppLauncher:
    """Resolves natural app names and launches them detached."""

    _ALIASES: tuple[AppAlias, ...] = (
        AppAlias("firefox", "Firefox", ("firefox", "firefox-esr", "org.mozilla.firefox")),
        AppAlias(
            "chrome",
            "Google Chrome",
            (
                "google-chrome",
                "google-chrome-stable",
                "google-chrome-beta",
                "chromium",
                "chromium-browser",
                "org.google.Chrome",
                "com.google.Chrome",
            ),
        ),
        AppAlias(
            "chromium",
            "Chromium",
            ("chromium", "chromium-browser", "org.chromium.Chromium"),
        ),
        AppAlias(
            "brave",
            "Brave Browser",
            ("brave-browser", "brave-browser-stable", "brave", "com.brave.Browser"),
        ),
        AppAlias(
            "vscode",
            "Visual Studio Code",
            ("code", "code-insiders", "codium", "com.visualstudio.code"),
        ),
        AppAlias("konsole", "Konsole", ("konsole", "org.kde.konsole")),
        AppAlias(
            "terminal",
            "Terminal",
            (
                "konsole",
                "x-terminal-emulator",
                "yakuake",
                "kitty",
                "alacritty",
                "gnome-terminal",
                "xterm",
            ),
        ),
        AppAlias("dolphin", "Dolphin", ("dolphin", "org.kde.dolphin")),
        AppAlias(
            "files",
            "File Manager",
            ("dolphin", "org.kde.dolphin", "nautilus", "nemo", "thunar"),
        ),
        AppAlias(
            "settings",
            "System Settings",
            (
                "systemsettings",
                "systemsettings5",
                "kcmshell6",
                "gnome-control-center",
                "io.elementary.settings",
            ),
        ),
        AppAlias("kate", "Kate", ("kate", "kwrite")),
    )

    _SYNONYMS: dict[str, str] = {
        "google chrome": "chrome",
        "google chrome stable": "chrome",
        "google chrome beta": "chrome",
        "chromium browser": "chromium",
        "brave browser": "brave",
        "visual studio code": "vscode",
        "vs code": "vscode",
        "vscodium": "vscode",
        "vs codium": "vscode",
        "system settings": "settings",
        "control center": "settings",
        "kde settings": "settings",
        "terminal emulator": "terminal",
        "file manager": "files",
        "file explorer": "files",
        "explorer": "files",
        "text editor": "kate",
    }

    def __init__(self, finder: Callable[[str], str | None] | None = None) -> None:
        self._finder = finder or shutil.which

    # ----------------------------------------------------------- registry

    @classmethod
    def known_names(cls) -> frozenset[str]:
        names = {alias.key for alias in cls._ALIASES}
        names.update(cls._SYNONYMS)
        return frozenset(names)

    @classmethod
    def normalize(cls, name: str) -> str:
        key = " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())
        return cls._SYNONYMS.get(key, key)

    @classmethod
    def display_name(cls, name: str) -> str:
        key = cls.normalize(name)
        for alias in cls._ALIASES:
            if alias.key == key:
                return alias.display
        return name.strip().title()

    # ----------------------------------------------------------- resolve

    def resolve(self, name: str) -> ResolvedApp | None:
        key = self.normalize(name)
        alias = next((a for a in self._ALIASES if a.key == key), None)
        if alias is not None:
            candidates = alias.candidates
        else:
            # Unknown name: allow launching any executable on PATH.
            candidates = (name.strip().lower(), key)
        for candidate in candidates:
            executable = self._finder(candidate)
            if executable:
                display = alias.display if alias else name.strip()
                return ResolvedApp(key, display, executable)
        return None

    def launch(self, name: str, *args: str) -> LaunchResult:
        resolved = self.resolve(name)
        if resolved is None:
            key = self.normalize(name)
            alias = next((a for a in self._ALIASES if a.key == key), None)
            tried = alias.candidates if alias else (name.strip().lower(), key)
            raise AppNotFoundError(name, tried)

        try:
            process = subprocess.Popen(
                [resolved.executable, *args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # detach: app lifetime is independent
            )
        except OSError as exc:
            raise LauncherError(
                f"Failed to launch {resolved.display} ({resolved.executable}): {exc}"
            ) from exc
        return LaunchResult(resolved.display, resolved.executable, process.pid)
