"""Vision tools: screenshot, find_text, inspect_screen (Milestone 3 stack)."""

from __future__ import annotations

from core.memory import MemoryStore
from core.ocr import OcrEngine
from core.safety import ErrorCategory, SafetyLevel, SafetyManager, ToolError
from core.tools import Tool, ToolResult, ToolSpec, enforce_safety
from core.vision import VisionEngine, VisionError


class _VisionTool(Tool):
    def __init__(
        self,
        vision: VisionEngine,
        ocr: OcrEngine,
        safety: SafetyManager,
        memory: MemoryStore | None = None,
    ) -> None:
        self._vision = vision
        self._ocr = ocr
        self._safety = safety
        self._memory = memory

    def _grab(self, arguments: dict):  # noqa: ANN001, ANN202
        try:
            return self._vision.grab(
                monitor=int(arguments.get("monitor") or 0),
                window_only=bool(arguments.get("window_only")),
            )
        except VisionError as exc:
            raise ToolError(str(exc), ErrorCategory.OCR_FAILURE) from exc

    def _detect(self, frame) -> list:  # noqa: ANN001
        try:
            return self._ocr.detect_text(frame.pil_image)
        except Exception as exc:  # noqa: BLE001 - OCR is best-effort here
            raise ToolError(f"OCR failed: {exc}", ErrorCategory.OCR_FAILURE) from exc


class ScreenshotTool(_VisionTool):
    spec = ToolSpec(
        name="screenshot",
        description=(
            "Capture the screen and summarize what is visible (size, position, "
            "readable text)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "monitor": {"type": "integer"},
                "window_only": {"type": "boolean"},
            },
            "required": [],
        },
        safety=SafetyLevel.SAFE,
    )

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(self._safety, self.spec, arguments)
        frame = self._grab(arguments)
        try:
            detections = self._detect(frame)
        except ToolError:
            detections = []
        texts = [d.text for d in detections[:12]]
        path = self._memory.save_screenshot(frame.pil_image) if self._memory else None
        summary = (
            f"Screenshot {frame.geometry[2]}x{frame.geometry[3]} at "
            f"({frame.geometry[0]},{frame.geometry[1]}), mode={frame.mode}. "
            f"Readable text ({len(detections)} items): "
            + (", ".join(texts) if texts else "(none detected)")
        )
        return ToolResult(
            True,
            summary,
            data={
                "geometry": frame.geometry,
                "texts": texts,
                "screenshot": str(path) if path else None,
            },
            display="Captured screen",
        )


class FindTextTool(_VisionTool):
    spec = ToolSpec(
        name="find_text",
        description=(
            "Locate visible text on screen and return its bounding box and "
            "click centre in screen coordinates."
        ),
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        safety=SafetyLevel.SAFE,
    )

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(self._safety, self.spec, arguments)
        needle = str(arguments["text"])
        frame = self._grab(arguments)
        try:
            hit = self._ocr.find_text(needle, frame.pil_image)
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"OCR failed: {exc}", ErrorCategory.OCR_FAILURE) from exc
        if hit is None:
            raise ToolError(
                f"“{needle}” not found on screen.",
                ErrorCategory.TARGET_NOT_FOUND,
            )
        origin_x, origin_y = frame.geometry[0], frame.geometry[1]
        bx, by, bw, bh = hit.bbox
        screen_left, screen_top = origin_x + bx, origin_y + by
        centre = (screen_left + bw // 2, screen_top + bh // 2)
        return ToolResult(
            True,
            f"Found {hit.text!r} at bbox ({screen_left},{screen_top},{bw},{bh}), "
            f"click centre {centre}",
            data={"bbox": [screen_left, screen_top, bw, bh], "center": list(centre)},
            display=f"Found {hit.text}",
        )


class InspectScreenTool(_VisionTool):
    spec = ToolSpec(
        name="inspect_screen",
        description=(
            "Read the screen with OCR: list visible text with positions and a "
            "summary of the layout."
        ),
        input_schema={
            "type": "object",
            "properties": {"max_items": {"type": "integer"}},
            "required": [],
        },
        safety=SafetyLevel.SAFE,
    )

    def execute(self, arguments: dict) -> ToolResult:
        enforce_safety(self._safety, self.spec, arguments)
        limit = int(arguments.get("max_items") or 25)
        frame = self._grab(arguments)
        detections = self._detect(frame)
        items = [
            f"{d.text!r} at {d.bbox} (conf {d.confidence:.2f})"
            for d in detections[:limit]
        ]
        summary = (
            f"Screen shows {len(detections)} text items in a "
            f"{frame.geometry[2]}x{frame.geometry[3]} capture ({frame.mode}). "
            + ("; ".join(items) if items else "No readable text found.")
        )
        return ToolResult(
            True,
            summary[:2000],
            data={"count": len(detections), "items": items},
            display="Inspecting screen",
        )
