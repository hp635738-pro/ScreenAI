"""Shared fakes for the ScreenAI test-suite (no network, no display)."""

from __future__ import annotations

import itertools

from core.providers.base import AIProvider, ProviderResponse
from core.automation import InputBackend
from core.terminal import TerminalResult


# --------------------------------------------------------------- providers


class ScriptedProvider(AIProvider):
    """LLM stand-in: returns queued responses and records conversations."""

    name = "fake"
    is_cloud = False

    def __init__(self, responses: list[str], *, cloud: bool = False) -> None:
        self.responses = list(responses)
        self.is_cloud = cloud
        self.calls: list[list[dict]] = []
        self.streamed: list[str] = []

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, *, context=None) -> ProviderResponse:  # noqa: ANN001
        messages = [{"role": "user", "content": c} for c in (context or [])]
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)

    def chat(self, messages, *, stream_cb=None) -> ProviderResponse:  # noqa: ANN001
        self.calls.append([dict(m) for m in messages])
        text = self.responses.pop(0) if self.responses else '{"final": "done"}'
        if stream_cb:
            self.streamed.append(text)
            stream_cb(text)
        return ProviderResponse(text=text, provider=self.name, model="scripted")


class FakeTransport:
    """HttpTransport stand-in: canned replies keyed by URL substring."""

    def __init__(self) -> None:
        self.json_replies: list[tuple[str, int, object]] = []
        self.stream_replies: list[tuple[str, list[str]]] = []
        self.requests: list[dict] = []

    def add_json(self, url_part: str, status: int, body: object) -> None:
        self.json_replies.append((url_part, status, body))

    def add_stream(self, url_part: str, lines: list[str]) -> None:
        self.stream_replies.append((url_part, lines))

    def request_json(self, url, *, method="POST", payload=None, headers=None,
                     timeout=60.0) -> tuple[int, object]:  # noqa: ANN001
        self.requests.append({"url": url, "method": method, "payload": payload,
                              "headers": dict(headers or {})})
        for part, status, body in self.json_replies:
            if part in url:
                return status, body
        raise AssertionError(f"no fake reply for {url}")

    def stream_lines(self, url, *, method="POST", payload=None, headers=None,
                     timeout=60.0):  # noqa: ANN001
        self.requests.append({"url": url, "method": method, "payload": payload,
                              "headers": dict(headers or {}), "stream": True})
        for part, lines in self.stream_replies:
            if part in url:
                yield from lines
                return
        raise AssertionError(f"no fake stream for {url}")


# ----------------------------------------------------------------- engines


class FakeBackend(InputBackend):
    name = "fake"

    def __init__(self) -> None:
        self.calls = []

    @classmethod
    def is_available(cls) -> bool:
        return True

    def move_mouse(self, x, y, duration=0.0) -> None:
        self.calls.append(("move", x, y))

    def click(self, x, y, button) -> None:  # noqa: ANN001
        self.calls.append(("click", x, y, button))

    def double_click(self, x, y) -> None:
        self.calls.append(("dbl", x, y))

    def type_text(self, text, interval) -> None:  # noqa: ANN001
        self.calls.append(("type", text))

    def hotkey(self, keys) -> None:  # noqa: ANN001
        self.calls.append(("key", tuple(keys)))

    def press(self, key) -> None:  # noqa: ANN001
        self.calls.append(("press", key))


class FakeLauncher:
    """AppLauncher stand-in with a tiny app catalogue."""

    def __init__(self) -> None:
        self.launched: list[str] = []
        self._pids = itertools.count(4242)
        self.fail: str | None = None

    @staticmethod
    def normalize(name: str) -> str:
        return name.strip().lower()

    @staticmethod
    def known_names() -> frozenset[str]:
        return frozenset({"firefox", "konsole", "vscode"})

    @staticmethod
    def display_name(name: str) -> str:
        return name.title()

    def resolve(self, name: str):  # noqa: ANN001, ANN202
        from core.app_launcher import ResolvedApp

        if self.normalize(name) in self.known_names():
            return ResolvedApp(self.normalize(name), name.title(), f"/usr/bin/{name}")
        return None

    def launch(self, name, *args):  # noqa: ANN001, ANN202
        from core.app_launcher import AppNotFoundError, LaunchResult

        if self.fail == name:
            raise OSError("boom")
        if self.resolve(name) is None:
            raise AppNotFoundError(name, (name,))
        self.launched.append(name)
        return LaunchResult(name.title(), f"/usr/bin/{name}", next(self._pids))


class FakeTerminal:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.result = TerminalResult(
            command="ok", argv=["echo", "ok"], exit_code=0,
            stdout="ok\n", stderr="", duration=0.01,
        )
        self.cancelled = False

    def execute(self, command, timeout=None) -> TerminalResult:  # noqa: ANN001
        self.commands.append(command)
        return TerminalResult(
            command=command,
            argv=[command],
            exit_code=self.result.exit_code,
            stdout=self.result.stdout,
            stderr=self.result.stderr,
            duration=0.01,
            cancelled=self.cancelled,
        )

    def cancel(self) -> None:
        self.cancelled = True

    @property
    def is_running(self) -> bool:
        return False


class FakeShot:
    def __init__(self, w=8, h=6, left=0, top=0, rgb=None):
        self.width, self.height, self.left, self.top = w, h, left, top
        self.rgb = rgb or bytes([10, 20, 30] * (w * h))

    def __bytes__(self) -> bytes:
        return self.rgb


class FakeSct:
    monitors = [{"left": 0, "top": 0, "width": 8, "height": 6}]

    def __init__(self) -> None:
        self.grabs = []

    def grab(self, target):  # noqa: ANN001
        self.grabs.append(target)
        return FakeShot(target["width"], target["height"], target["left"], target["top"])

    def close(self) -> None:
        pass


class FakeReader:
    """EasyOCR stand-in: canned (bbox, text, confidence) rows."""

    def __init__(self, rows=None) -> None:
        self.rows = rows or [
            ([[10, 10], [50, 10], [50, 30], [10, 30]], "Export", 0.97),
            ([[0, 80], [30, 80], [30, 95], [0, 95]], "File", 0.88),
        ]
        self.calls = 0

    def readtext(self, image) -> list:  # noqa: ANN001
        self.calls += 1
        return self.rows


class FakeWorkflowService:
    def __init__(self) -> None:
        self.recording = False
        self.saved: list[tuple[str, str]] = []
        self.steps_pending = 0
        self.workflows = [
            {
                "id": 1,
                "app_name": "XYZ App",
                "task_name": "Export PDF",
                "label": "XYZ App: Export PDF",
                "step_count": 3,
            }
        ]
        self.run_calls: list[dict] = []
        self.run_result = {
            "success": True,
            "summary": "3/3 steps played",
            "display": "Played XYZ App: Export PDF",
        }

    def is_recording(self) -> bool:
        return self.recording

    def start_learning(self) -> bool:
        self.recording = True
        return True

    def stop_learning(self) -> int:
        self.recording = False
        return self.steps_pending

    def save_workflow(self, app_name: str, task_name: str):  # noqa: ANN001
        if self.recording or not self.steps_pending:
            return None
        label = f"{app_name}: {task_name}"
        self.saved.append((app_name, task_name))
        return {"id": 2, "label": label, "steps": self.steps_pending}

    def list_workflows(self) -> list[dict]:
        return list(self.workflows)

    def run_workflow(self, *, app_name=None, task_name=None, workflow_id=None):  # noqa: ANN001
        self.run_calls.append(
            {"app_name": app_name, "task_name": task_name, "workflow_id": workflow_id}
        )
        for wf in self.workflows:
            if workflow_id == wf["id"] or (
                (app_name is None or wf["app_name"].lower() == app_name.lower())
                and (task_name is None or wf["task_name"].lower() == task_name.lower())
            ):
                return dict(self.run_result)
        return {"missing": True, "success": False, "summary": "No matching saved workflow"}
