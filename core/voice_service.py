"""Voice input service — placeholder for a future milestone."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class VoiceService(QObject):
    notice = Signal(str)
    listening_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listening = False

    @property
    def is_listening(self) -> bool:
        return self._listening

    @Slot()
    def start_listening(self) -> None:
        # Real capture/transcription will live here in a later milestone.
        self.notice.emit("Voice input is not implemented yet (placeholder button).")
