"""Global hotkey listener.

Uses the `keyboard` library in a daemon thread, then forwards events to the Qt
main thread via a queued signal connection. This is the most reliable approach
on Windows because PyQt/PySide overlays cannot always capture hotkeys when they
lack focus.
"""

from __future__ import annotations

import logging

import keyboard
from PySide6.QtCore import QObject, Signal

log = logging.getLogger("lucid.hotkey")


class HotkeyListener(QObject):
    """Emits `triggered` on the Qt main thread when the hotkey fires."""

    triggered = Signal()

    def __init__(self, combo: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._combo = combo
        self._handle: object | None = None

    def start(self) -> None:
        if self._handle is not None:
            return
        self._handle = keyboard.add_hotkey(
            self._combo,
            self._on_fire,
            suppress=False,
            trigger_on_release=False,
        )
        log.info("Hotkey registered: %s", self._combo)

    def stop(self) -> None:
        if self._handle is None:
            return
        try:
            keyboard.remove_hotkey(self._handle)
        except (KeyError, ValueError):
            pass
        self._handle = None
        log.info("Hotkey unregistered: %s", self._combo)

    def _on_fire(self) -> None:
        log.debug("Hotkey fired")
        self.triggered.emit()
