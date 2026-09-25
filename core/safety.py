"""Safety classification for agent actions.

Three levels govern every tool call and terminal command:

* ``SAFE``           — run without asking (screenshots, inspect, open app…)
* ``CONFIRM``        — pause and ask the user first (terminal commands,
                       deleting files, sending messages, purchases…)
* ``BLOCKED``        — refuse by default (disk destruction, credential
                       theft, disabling security, privilege escalation)

Consequential external actions (purchases, orders, messages, form
submissions) ALWAYS require confirmation, regardless of the configured
policy. Secrets are redacted before anything reaches logs or the LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class SafetyLevel(str, Enum):
    SAFE = "safe"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


class ErrorCategory(str, Enum):
    APP_NOT_FOUND = "app_not_found"
    WORKFLOW_NOT_FOUND = "workflow_not_found"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    API_UNAVAILABLE = "api_unavailable"
    API_ERROR = "api_error"
    OCR_FAILURE = "ocr_failure"
    TARGET_NOT_FOUND = "target_not_found"
    AUTOMATION_FAILURE = "automation_failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    CONFIRMATION_DECLINED = "confirmation_declined"
    INVALID_ARGUMENTS = "invalid_arguments"
    PROTOCOL_ERROR = "protocol_error"
    UNKNOWN = "unknown"


class ToolError(RuntimeError):
    """A tool failure with a machine-readable category."""

    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.UNKNOWN):
        super().__init__(message)
        self.category = category


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    level: SafetyLevel
    reason: str
    category: ErrorCategory | None = None

    @property
    def allowed(self) -> bool:
        return self.level is not SafetyLevel.BLOCKED

    @property
    def needs_confirmation(self) -> bool:
        return self.level is SafetyLevel.CONFIRM


# ---------------------------------------------------------------- patterns

# Actions with external consequences must always be confirmed.
CONSEQUENTIAL_PATTERN = re.compile(
    r"\b(order|purchase|buy|checkout|pay|payment|transfer|send|email|message|"
    r"submit|post|publish|upload|book|reserve|subscribe|donate)\b",
    re.IGNORECASE,
)

_BLOCKED_COMMANDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brm\s+(-[a-z]*\s+)*(-r|-f|-rf|-fr)\b[^|;&]*\s(/|~|\$HOME)(\s|$)"),
     "destructive delete of / or $HOME"),
    (re.compile(r"\bmkfs(\.[a-z0-9]+)?\b"), "formatting a filesystem"),
    (re.compile(r"\bdd\b[^|;&]*\bof=/dev/"), "raw device overwrite"),
    (re.compile(r":\s*\(\s*\)\s*\{"), "fork bomb"),
    (re.compile(r"\bshutdown\b|\breboot\b|\bpoweroff\b"), "system power operation"),
    (re.compile(r"\bsetenforce\s+0\b|\bufw\s+disable\b|\biptables\s+-F\b|"
                r"\bsystemctl\s+stop\s+(firewalld|nftables)\b"),
     "disabling security mechanisms"),
    (re.compile(r"\bpasswd\b|\bvisudo\b|\bchage\b"), "credential management"),
    (re.compile(r"\bsu\b\s*$|\bsudo\s+-s\b|\bsudo\s+su\b|\bpkexec\b|\bdoas\b"),
     "privilege escalation"),
    (re.compile(r"\bsudo\b"), "privilege escalation"),
    (re.compile(r"(cat|less|more|head|tail|grep|awk|sed)\s+[^|;&]*"
                r"(\.ssh/|id_rsa|id_ed25519|\.aws/credentials|\.netrc|\.gnupg/|"
                r"\.kube/config|/etc/shadow|/etc/passwd\b|credentials\.json|"
                r"\.env\b)"),
     "credential extraction"),
    (re.compile(r"\b(curl|wget)\b[^|;&|]*\|\s*(sh|bash|zsh)\b"),
     "piping remote content into a shell"),
    (re.compile(r"\bbase64\s+(-d|--decode)\b[^|;&]*\|\s*(sh|bash)\b"),
     "executing obfuscated payload"),
    (re.compile(r"\bchmod\s+([4-7][0-7]{2}|[+-][sS])\s+[^|;&]*(/usr|/bin|/sbin|/etc)"),
     "privilege-sensitive permission change"),
)

_CONFIRM_COMMANDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brm\b|\bshred\b|\btruncate\b"), "deleting files"),
    (re.compile(r"\bmv\b\s+[^|;&]*\s/etc/|\bcp\b\s+[^|;&]*\s/etc/|\btee\b\s+/etc/"),
     "writing to system paths"),
    (re.compile(r"(^|[^>])>\s*[^|;&\s]"), "overwriting a file"),
    (re.compile(r"\bkill\b|\bpkill\b|\bkillall\b"), "terminating processes"),
    (re.compile(r"\bapt(-get)?\b|\bdpkg\b|\bpip3?\s+install\b|\bsnap\s+install\b"),
     "installing software"),
    (re.compile(r"\bgit\s+push\b|\bgit\s+remote\b"), "publishing to a remote"),
    (re.compile(r"\bssh\b|\bscp\b|\brsync\b[^|;&]*\s\S+@"), "remote access"),
    (re.compile(r"\bcurl\b[^|;&]*\s-X\s+(POST|PUT|DELETE|PATCH)\b|\bnc\b|\bnetcat\b"),
     "network write operation"),
    (re.compile(r"\bsystemctl\s+(stop|restart|disable)\b"), "changing services"),
    (re.compile(r"\bmount\b|\bumount\b"), "changing mounts"),
    (re.compile(r"\bchmod\b|\bchown\b"), "changing permissions"),
    (re.compile(r"\bhistory\s+-c\b"), "clearing shell history"),
)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)\b(password|passwd|api[_-]?key|access[_-]?token|secret)"
               r"\s*[=:]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?"
               r"-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bauthorization:\s*\S+\s+\S+"),
)

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Blank out credentials, tokens and key assignments."""
    if not text:
        return text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: (m.group(1) or "") + REDACTED, text)
        else:
            text = pattern.sub(REDACTED, text)
    return text


def is_consequential(text: str) -> bool:
    """Whether an action description names an external consequence."""
    return bool(CONSEQUENTIAL_PATTERN.search(text or ""))


class SafetyManager:
    """Classifies tool calls and terminal commands; owns the ask policy."""

    def __init__(
        self,
        confirm_policy: str = "required_only",
        overrides: dict[str, str] | None = None,
    ) -> None:
        self._policy = confirm_policy if confirm_policy in (
            "always", "required_only", "never"
        ) else "required_only"
        # Optional per-tool overrides ("safe" / "confirm" / "blocked").
        self._overrides = dict(overrides or {})

    @property
    def confirm_policy(self) -> str:
        return self._policy

    def configure(self, confirm_policy: str | None = None, **tool_levels: str) -> None:
        if confirm_policy in ("always", "required_only", "never"):
            self._policy = confirm_policy
        self._overrides.update(tool_levels)

    # ------------------------------------------------------------- tools

    def evaluate_tool(
        self,
        tool_name: str,
        arguments: dict,
        *,
        declared: SafetyLevel,
        confirm_reason: str | None = None,
        description: str = "",
    ) -> SafetyDecision:
        override = self._overrides.get(tool_name)
        level = SafetyLevel(override) if override else declared
        reason = f"tool '{tool_name}' is {level.value} by default"

        if "command" in arguments:
            command_decision = self.evaluate_command(str(arguments["command"]))
            if command_decision.level is SafetyLevel.BLOCKED:
                return command_decision

        blob = " ".join(
            str(v) for v in (
                confirm_reason or "",
                description or "",
                arguments.get("command", ""),
                arguments.get("text", ""),
                arguments.get("name", ""),
            )
            if v
        )
        if level is not SafetyLevel.BLOCKED and is_consequential(blob):
            return SafetyDecision(
                SafetyLevel.CONFIRM,
                "action has external consequences (always confirmed)",
            )
        if confirm_reason:
            return SafetyDecision(
                SafetyLevel.CONFIRM, f"declared for confirmation: {confirm_reason}"
            )
        if level is SafetyLevel.BLOCKED:
            return SafetyDecision(
                SafetyLevel.BLOCKED,
                f"tool '{tool_name}' is blocked by policy",
                ErrorCategory.BLOCKED,
            )
        if level is SafetyLevel.CONFIRM:
            if self._policy == "never":
                return SafetyDecision(
                    SafetyLevel.SAFE, "confirmation policy: never (auto-approved)"
                )
            return SafetyDecision(SafetyLevel.CONFIRM, reason)
        if self._policy == "always":
            return SafetyDecision(SafetyLevel.CONFIRM, "confirmation policy: always")
        return SafetyDecision(SafetyLevel.SAFE, reason)

    # --------------------------------------------------------- commands

    def evaluate_command(self, command: str) -> SafetyDecision:
        text = (command or "").strip()
        if not text:
            return SafetyDecision(
                SafetyLevel.BLOCKED, "empty command", ErrorCategory.INVALID_ARGUMENTS
            )
        for pattern, why in _BLOCKED_COMMANDS:
            if pattern.search(text):
                return SafetyDecision(
                    SafetyLevel.BLOCKED,
                    f"blocked: {why}",
                    ErrorCategory.BLOCKED,
                )
        if is_consequential(text):
            return SafetyDecision(
                SafetyLevel.CONFIRM,
                "action has external consequences (always confirmed)",
            )
        for pattern, why in _CONFIRM_COMMANDS:
            if pattern.search(text):
                if self._policy == "never":
                    return SafetyDecision(
                        SafetyLevel.SAFE,
                        "confirmation policy: never (auto-approved)",
                    )
                return SafetyDecision(SafetyLevel.CONFIRM, f"needs confirmation: {why}")
        if self._policy == "always":
            return SafetyDecision(SafetyLevel.CONFIRM, "confirmation policy: always")
        return SafetyDecision(SafetyLevel.SAFE, "routine read-only style command")
