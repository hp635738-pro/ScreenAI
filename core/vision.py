"""Screen capture engine (mss + Pillow).

Captures the desktop continuously on a worker thread — or on demand —
with 300–500 ms refresh intervals. Frames are exposed as both ``QImage``
and PIL ``Image``. Multiple monitors are supported (index 0 = the whole
virtual desktop, 1..N = individual monitors), plus an optional
active-window-only capture mode. Never blocks the GUI thread.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import mss
from PIL import Image
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage

MIN_INTERVAL_MS = 300
MAX_INTERVAL_MS = 500
DEFAULT_INTERVAL_MS = 400

MODE_DESKTOP = "desktop"
MODE_WINDOW = "window"


class VisionError(RuntimeError):
    """Raised when the screen cannot be captured."""


@dataclass(slots=True)
class CaptureFrame:
    qimage: QImage
    pil_image: Image.Image
    monitor: int  # 0 = all monitors (virtual desktop), 1..N = one monitor
    geometry: tuple[int, int, int, int]  # left, top, width, height
    timestamp: float
    mode: str  # "desktop" | "window"


def active_window_geometry() -> tuple[int, int, int, int] | None:
    """Rect of the active window via xdotool (X11); None when unavailable."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowgeometry"],
            capture_output=True,
            text=True,
            timeout=0.7,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    left = top = width = height = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Position:"):
            try:
                x_str, y_str = line.split(":", 1)[1].strip().split()[0].split(",")
                left, top = int(x_str), int(y_str)
            except (ValueError, IndexError):
                return None
        elif line.startswith("Geometry:"):
            try:
                w_str, h_str = line.split(":", 1)[1].strip().split("x")
                width, height = int(w_str), int(h_str)
            except (ValueError, IndexError):
                return None
    if None in (left, top, width, height):
        return None
    return (left, top, width, height)


def clamp_interval(interval_ms: int) -> int:
    """Keep refresh intervals inside the supported 300–500 ms band."""
    return max(MIN_INTERVAL_MS, min(MAX_INTERVAL_MS, interval_ms))


class CaptureWorker(QObject):
    """Grabs frames on a loop inside a QThread."""

    frame_ready = Signal(object)  # CaptureFrame
    failed = Signal(str)

    def __init__(
        self,
        engine: VisionEngine,
        mode: str,
        monitor: int,
        interval_ms: int,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._mode = mode
        self._monitor = monitor
        self._interval = clamp_interval(interval_ms) / 1000.0
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    @Slot()
    def run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                frame = self._engine.grab(
                    self._monitor, window_only=self._mode == MODE_WINDOW
                )
                self.frame_ready.emit(frame)
            except VisionError as exc:
                self.failed.emit(str(exc))
            remaining = self._interval - (time.monotonic() - started)
            if remaining > 0 and self._stop.wait(remaining):
                break


class VisionEngine(QObject):
    """One-shot and continuous screen capture."""

    frame_ready = Signal(object)  # CaptureFrame
    error = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        sct_factory: Callable[[], object] | None = None,
        window_geometry_fn: Callable[[], tuple[int, int, int, int] | None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(parent)
        self._sct_factory = sct_factory or mss.mss
        self._window_geometry_fn = window_geometry_fn or active_window_geometry
        self._clock = clock
        self._thread: QThread | None = None
        self._worker: CaptureWorker | None = None

    # ---------------------------------------------------------- capture

    def list_monitors(self) -> list[dict]:
        """All monitors: index 0 is the virtual desktop, 1..N physical."""
        try:
            sct = self._sct_factory()
        except Exception as exc:  # noqa: BLE001 - mss raises platform errors
            raise VisionError(f"Screen capture failed: {exc}") from exc
        try:
            monitors = sct.monitors
        finally:
            close = getattr(sct, "close", None)
            if callable(close):
                close()
        return [
            {
                "index": index,
                "left": monitor["left"],
                "top": monitor["top"],
                "width": monitor["width"],
                "height": monitor["height"],
            }
            for index, monitor in enumerate(monitors)
        ]

    def grab(self, monitor: int = 0, window_only: bool = False) -> CaptureFrame:
        """Single capture as QImage + PIL image (fast enough for callers)."""
        region = None
        mode = MODE_DESKTOP
        if window_only:
            geometry = self._window_geometry_fn()
            if geometry is not None:
                region = {
                    "left": geometry[0],
                    "top": geometry[1],
                    "width": geometry[2],
                    "height": geometry[3],
                }
                mode = MODE_WINDOW
        try:
            sct = self._sct_factory()
            try:
                if region is not None:
                    shot = sct.grab(region)
                else:
                    monitors = sct.monitors
                    target = (
                        monitors[monitor]
                        if 0 <= monitor < len(monitors)
                        else monitors[0]
                    )
                    shot = sct.grab(target)
            finally:
                close = getattr(sct, "close", None)
                if callable(close):
                    close()
        except Exception as exc:  # noqa: BLE001 - mss raises platform errors
            raise VisionError(f"Screen capture failed: {exc}") from exc

        width, height = shot.width, shot.height
        rgb = bytes(shot.rgb)
        pil_image = Image.frombytes("RGB", (width, height), rgb)
        qimage = QImage(
            rgb, width, height, width * 3, QImage.Format.Format_RGB888
        ).copy()
        return CaptureFrame(
            qimage,
            pil_image,
            monitor,
            (shot.left, shot.top, width, height),
            self._clock(),
            mode,
        )

    # ---------------------------------------------------------- stream

    @property
    def is_streaming(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start_stream(
        self,
        mode: str = MODE_DESKTOP,
        monitor: int = 0,
        interval_ms: int = DEFAULT_INTERVAL_MS,
    ) -> bool:
        """Start (or restart) continuous capture; frames arrive via signal."""
        self.stop_stream()
        thread = QThread()
        worker = CaptureWorker(self, mode, monitor, interval_ms)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.frame_ready.connect(self.frame_ready)
        worker.failed.connect(self.error)
        thread.finished.connect(lambda t=thread: self._on_thread_finished(t))

        self._thread = thread
        self._worker = worker
        thread.start()
        return True

    def stop_stream(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(1500)
        self._discard_thread()

    def shutdown(self) -> None:
        self.stop_stream()

    def _on_thread_finished(self, thread: QThread) -> None:
        """Only reap the generation that just finished (restart-safe)."""
        if thread is self._thread:
            self._discard_thread()
        else:
            thread.deleteLater()

    def _discard_thread(self) -> None:
        thread = self._thread
        worker = self._worker
        self._thread = None
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            if thread.isRunning():
                thread.quit()
                thread.wait(500)
            if not thread.isRunning():
                thread.deleteLater()
