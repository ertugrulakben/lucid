"""Prompt input line edit with Enter/Esc handling."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit


class PromptBar(QLineEdit):
    submitted = Signal(str)
    cancelled = Signal()
    cycle_mode_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LucidPromptBar")
        self.setPlaceholderText("Ask Lucid…  (Ctrl+1/2/3 switch modes, Tab cycles)")
        self.setMinimumWidth(620)
        self.returnPressed.connect(self._emit_submit)

    def _emit_submit(self) -> None:
        text = self.text().strip()
        if text:
            self.clear()
            self.submitted.emit(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        if event.key() == Qt.Key.Key_Tab:
            self.cycle_mode_requested.emit()
            return
        super().keyPressEvent(event)
