"""Terminal engine: runs commands with streamed output and full capture.

``execute()`` is a blocking call meant for worker threads — it never runs on
the GUI thread. Output is streamed line-by-line through Qt signals while
stdout/stderr are captured in full and returned with the exit code.
"""

from __future__ import annotations

import os
import queue
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

_SHELL_METACHARACTERS = "|&;<>$`\n()"


@dataclass(slots=True)
class TerminalResult:
    command: str
    argv: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    duration: float
    cancelled: bool = False
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.cancelled and not self.timed_out

    @property
    def summary(self) -> str:
        if self.cancelled:
            return "Stopped"
        if self.timed_out:
            return "Timed out"
        if self.exit_code == 0:
            return "Exit code 0"
        tail = (self.stderr or self.stdout).strip().splitlines()
        detail = f" — {tail[-1]}" if tail else ""
        return f"Exit code {self.exit_code}{detail}"


class TerminalEngine(QObject):
    """Executes shell-less (or explicit-shell) commands off the GUI thread."""

    started = Signal(str)
    output = Signal(str, str)  # text line, stream name ("stdout"/"stderr")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._cancelled = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def execute(self, command: str, timeout: float | None = None) -> TerminalResult:
        """Run ``command``; stream output; return captured result + exit code."""
        argv = self.build_argv(command)
        started = time.monotonic()
        self._cancelled = False
        self.started.emit(command)

        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            return TerminalResult(
                command, argv, None, "", str(exc), time.monotonic() - started
            )

        with self._lock:
            self._process = process

        chunks: dict[str, list[str]] = {"stdout": [], "stderr": []}
        incoming: queue.Queue[tuple[str, str]] = queue.Queue()
        readers = [
            threading.Thread(target=self._pump, args=(name, pipe, incoming), daemon=True)
            for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr))
        ]
        for reader in readers:
            reader.start()

        timed_out = False
        while True:
            try:
                stream, text = incoming.get(timeout=0.05)
                chunks[stream].append(text)
                self.output.emit(text.rstrip("\n"), stream)
            except queue.Empty:
                pass
            if timeout is not None and time.monotonic() - started > timeout:
                timed_out = True
                timeout = None
                self._terminate()
            if process.poll() is not None and incoming.empty():
                if not any(reader.is_alive() for reader in readers):
                    break

        while not incoming.empty():
            try:
                stream, text = incoming.get_nowait()
            except queue.Empty:
                break
            chunks[stream].append(text)
            self.output.emit(text.rstrip("\n"), stream)

        for reader in readers:
            reader.join(timeout=0.5)
        process.wait()
        with self._lock:
            self._process = None

        return TerminalResult(
            command,
            argv,
            process.returncode,
            "".join(chunks["stdout"]),
            "".join(chunks["stderr"]),
            time.monotonic() - started,
            cancelled=self._cancelled,
            timed_out=timed_out,
        )

    def cancel(self) -> None:
        """Immediately terminate the running command (thread-safe).

        The whole process group is signalled (SIGTERM, then SIGKILL shortly
        after) so child processes of shell pipelines are stopped too.
        """
        self._cancelled = True
        self._terminate()

    # ------------------------------------------------------------ internal

    @staticmethod
    def build_argv(command: str) -> list[str]:
        """No shell hacks: argv directly, or an explicit ``sh -c`` for
        pipelines/redirections."""
        if any(char in command for char in _SHELL_METACHARACTERS):
            shell = os.environ.get("SHELL") or "/bin/sh"
            return [shell, "-c", command]
        try:
            return shlex.split(command)
        except ValueError:
            shell = os.environ.get("SHELL") or "/bin/sh"
            return [shell, "-c", command]

    @staticmethod
    def _pump(
        stream: str, pipe, incoming: queue.Queue[tuple[str, str]]
    ) -> None:  # noqa: ANN001
        try:
            for line in iter(pipe.readline, ""):
                incoming.put((stream, line))
        finally:
            pipe.close()

    def _terminate(self) -> None:
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        self._signal_group(process, signal.SIGTERM)
        threading.Timer(0.4, self._kill, args=(process,)).start()

    @staticmethod
    def _kill(process: subprocess.Popen) -> None:
        if process.poll() is None:
            TerminalEngine._signal_group(process, signal.SIGKILL)

    @staticmethod
    def _signal_group(process: subprocess.Popen, sig: int) -> None:
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.send_signal(sig)
            except OSError:
                pass
