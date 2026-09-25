"""Persistent AI settings and credential storage.

Plain settings live in ``settings.json`` inside the user data directory.
The API key is kept in a separate ``credentials.json`` with 0600
permissions and never written to SQLite or logs. Environment variables
override file values.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path

from core.config import Config

# Provider ids (match core.providers registry names).
PROVIDER_OPENAI = "openai"
PROVIDER_OLLAMA = "ollama"
PROVIDER_AUTO = "auto"
PROVIDER_OPTIONS = (PROVIDER_OPENAI, PROVIDER_OLLAMA, PROVIDER_AUTO)

# Privacy policy: whether cloud AI (OpenAI) may ever see user data.
PRIVACY_LOCAL_ONLY = "local_only"
PRIVACY_ALLOW_CLOUD = "allow_cloud"
PRIVACY_ASK_BEFORE_CLOUD = "ask_before_cloud"
PRIVACY_OPTIONS = (
    PRIVACY_LOCAL_ONLY,
    PRIVACY_ALLOW_CLOUD,
    PRIVACY_ASK_BEFORE_CLOUD,
)

# Confirmation policy for CONFIRM-level actions (BLOCKED always refuses).
CONFIRM_ALWAYS = "always"
CONFIRM_REQUIRED = "required_only"
CONFIRM_NEVER = "never"
CONFIRM_OPTIONS = (CONFIRM_ALWAYS, CONFIRM_REQUIRED, CONFIRM_NEVER)

DEFAULTS: dict[str, object] = {
    # AI
    "provider": PROVIDER_AUTO,
    "model_openai": "gpt-4o-mini",
    "model_ollama": "llama3.2",
    "ollama_host": "http://localhost:11434",
    "privacy": PRIVACY_ASK_BEFORE_CLOUD,
    # Automation
    "automation_backend": "auto",  # auto | pyautogui | xdotool
    "typing_speed_ms": 24,
    "action_delay_ms": 80,
    # Vision
    "ocr_enabled": True,
    "screenshot_interval_ms": 1000,
    "active_window_only": False,
    "screenshot_history": False,
    # Voice
    "voice_provider": "none",  # none | whisper (extensible)
    "voice_microphone": "default",
    "push_to_talk": True,
    # Interface
    "theme": "dark",
    "close_to_tray": True,
    "popup_behavior": "auto",  # auto | quiet | off
    # Security
    "confirm_policy": CONFIRM_REQUIRED,
    # Setup
    "first_run_done": False,
}

# Interface / automation option ids (labels live in the UI layer).
POPUP_OPTIONS = ("auto", "quiet", "off")
VOICE_PROVIDER_OPTIONS = ("none", "whisper")
AUTOMATION_BACKEND_OPTIONS = ("auto", "pyautogui", "xdotool")

ENV_PROVIDER = "SCREENAI_AI_PROVIDER"
ENV_PRIVACY = "SCREENAI_AI_PRIVACY"
ENV_OPENAI_KEY = "OPENAI_API_KEY"
ENV_OPENAI_MODEL = "OPENAI_MODEL"
ENV_OLLAMA_HOST = "OLLAMA_HOST"
ENV_OLLAMA_MODEL = "OLLAMA_MODEL"


class SettingsStore:
    """Loads and saves AI settings; resolves the API key securely."""

    def __init__(
        self,
        data_dir: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._dir = data_dir or Config.data_dir()
        self._env = os.environ if env is None else env
        self._settings_path = self._dir / "settings.json"
        self._credentials_path = self._dir / "credentials.json"
        self._values: dict[str, object] = dict(DEFAULTS)
        self._load()

    # ------------------------------------------------------------ settings

    def get(self, key: str) -> object:
        env_key = {
            "provider": ENV_PROVIDER,
            "privacy": ENV_PRIVACY,
            "model_openai": ENV_OPENAI_MODEL,
            "model_ollama": ENV_OLLAMA_MODEL,
            "ollama_host": ENV_OLLAMA_HOST,
        }.get(key)
        if env_key and env_key in self._env:
            return self._env[env_key]
        return self._values.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: object) -> None:
        self._values[key] = value

    def update(self, values: Mapping[str, object]) -> None:
        for key, value in values.items():
            if key in DEFAULTS:
                self._values[key] = value

    def save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps(self._values, indent=2), encoding="utf-8"
        )

    def all(self) -> dict[str, object]:
        return {key: self.get(key) for key in DEFAULTS}

    # ---------------------------------------------------------- credential

    def api_key(self) -> str | None:
        env_key = self._env.get(ENV_OPENAI_KEY)
        if env_key:
            return env_key.strip()
        stored = self._read_credentials().get("openai_api_key")
        return stored.strip() if stored else None

    def set_api_key(self, value: str) -> None:
        data = self._read_credentials()
        data["openai_api_key"] = value.strip()
        self._write_credentials(data)

    def clear_api_key(self) -> None:
        data = self._read_credentials()
        data.pop("openai_api_key", None)
        self._write_credentials(data)

    def masked_api_key(self) -> str | None:
        """A display-safe form of the saved key (never the full value)."""
        key = self.api_key()
        if not key:
            return None
        tail = key[-4:] if len(key) >= 8 else ""
        return f"sk-…{tail}" if tail else "••••"

    # ------------------------------------------------------------ internal

    def _load(self) -> None:
        try:
            raw = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            for key in DEFAULTS:
                if key in raw:
                    self._values[key] = raw[key]

    def _read_credentials(self) -> dict[str, str]:
        try:
            raw = json.loads(self._credentials_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write_credentials(self, data: dict[str, str]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._credentials_path.write_text(json.dumps(data), encoding="utf-8")
        self._credentials_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
