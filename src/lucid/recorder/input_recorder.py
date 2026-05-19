"""Mouse and keyboard input recorder built on `pynput`."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from pynput import keyboard, mouse

log = logging.getLogger("lucid.recorder.input")


@dataclass
class InputEvent:
    kind: str
    at_ms: int
    data: dict = field(default_factory=dict)


class InputRecorder:
    def __init__(self, on_event: Callable[[InputEvent], None] | None = None) -> None:
        self.on_event = on_event
        self.events: list[InputEvent] = []
        self._start_time: float | None = None
        self._mouse: mouse.Listener | None = None
        self._kbd: keyboard.Listener | None = None
        self._lock = threading.Lock()
        self._last_move_ms = 0

    def start(self) -> None:
        self._start_time = time.monotonic()
        self._mouse = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
            on_move=self._on_move,
        )
        self._kbd = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._mouse.start()
        self._kbd.start()

    def stop(self) -> list[InputEvent]:
        if self._mouse is not None:
            self._mouse.stop()
        if self._kbd is not None:
            self._kbd.stop()
        self._mouse = None
        self._kbd = None
        return list(self.events)

    def _now_ms(self) -> int:
        if self._start_time is None:
            return 0
        return int((time.monotonic() - self._start_time) * 1000)

    def _emit(self, event: InputEvent) -> None:
        with self._lock:
            self.events.append(event)
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:
                log.debug("on_event callback failed", exc_info=True)

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if not pressed:
            return
        self._emit(
            InputEvent(
                kind="mouse_click",
                at_ms=self._now_ms(),
                data={"x": x, "y": y, "button": str(button).replace("Button.", "")},
            )
        )

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._emit(
            InputEvent(
                kind="mouse_scroll",
                at_ms=self._now_ms(),
                data={"x": x, "y": y, "dx": dx, "dy": dy},
            )
        )

    def _on_move(self, x: int, y: int) -> None:
        now = self._now_ms()
        if now - self._last_move_ms < 100:
            return
        self._last_move_ms = now
        self._emit(InputEvent(kind="mouse_move", at_ms=now, data={"x": x, "y": y}))

    def _on_press(self, key) -> None:
        self._emit(InputEvent(kind="key_press", at_ms=self._now_ms(), data={"key": _key_name(key)}))

    def _on_release(self, key) -> None:
        self._emit(
            InputEvent(kind="key_release", at_ms=self._now_ms(), data={"key": _key_name(key)})
        )


def _key_name(key) -> str:
    try:
        return key.char  # type: ignore[attr-defined]
    except AttributeError:
        return str(key).replace("Key.", "")
