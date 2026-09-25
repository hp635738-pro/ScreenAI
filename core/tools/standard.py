"""Builds the standard ScreenAI tool registry from live engines."""

from __future__ import annotations

from dataclasses import dataclass

from core.app_launcher import AppLauncher
from core.automation import Automation
from core.memory import MemoryStore
from core.ocr import OcrEngine
from core.safety import SafetyManager
from core.terminal import TerminalEngine
from core.tools import ToolRegistry
from core.tools.application import (
    CloseApplicationTool,
    OpenApplicationTool,
    ProcessTracker,
)
from core.tools.automation import (
    HotkeyTool,
    MouseClickTool,
    MouseMoveTool,
    PressKeyTool,
    TypeTextTool,
)
from core.tools.terminal import RunTerminalCommandTool
from core.tools.vision import FindTextTool, InspectScreenTool, ScreenshotTool
from core.tools.workflow import (
    ListWorkflowsTool,
    RunWorkflowTool,
    SaveWorkflowTool,
    StartLearningTool,
    StopLearningTool,
    WorkflowService,
)
from core.vision import VisionEngine


@dataclass
class ToolContext:
    launcher: AppLauncher
    automation: Automation
    terminal: TerminalEngine
    vision: VisionEngine
    ocr: OcrEngine
    safety: SafetyManager
    workflows: WorkflowService
    memory: MemoryStore | None = None
    tracker: ProcessTracker | None = None


def build_standard_registry(context: ToolContext) -> ToolRegistry:
    registry = ToolRegistry()
    tracker = context.tracker or ProcessTracker()
    safety = context.safety

    registry.register(OpenApplicationTool(context.launcher, tracker, safety))
    registry.register(CloseApplicationTool(tracker, safety))
    registry.register(RunTerminalCommandTool(context.terminal, safety))
    registry.register(MouseMoveTool(context.automation, safety))
    registry.register(MouseClickTool(context.automation, safety))
    registry.register(TypeTextTool(context.automation, safety))
    registry.register(PressKeyTool(context.automation, safety))
    registry.register(HotkeyTool(context.automation, safety))
    registry.register(ScreenshotTool(context.vision, context.ocr, safety, context.memory))
    registry.register(FindTextTool(context.vision, context.ocr, safety, context.memory))
    registry.register(InspectScreenTool(context.vision, context.ocr, safety, context.memory))
    registry.register(StartLearningTool(context.workflows, safety))
    registry.register(StopLearningTool(context.workflows, safety))
    registry.register(SaveWorkflowTool(context.workflows, safety))
    registry.register(ListWorkflowsTool(context.workflows, safety))
    registry.register(RunWorkflowTool(context.workflows, safety))
    return registry
