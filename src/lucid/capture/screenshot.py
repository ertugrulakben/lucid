"""Multi-monitor screenshot grabber built on `mss`."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import mss
from PIL import Image

log = logging.getLogger("lucid.capture.screenshot")


class ScreenshotGrabber:
    """Grabs a PIL Image of the active monitor, optionally downscaled."""

    def __init__(self, max_width: int = 1280) -> None:
        self.max_width = max_width

    def grab(
        self, monitor_index: int | None = None
    ) -> tuple[Image.Image, int, tuple[int, int, int, int]]:
        """Return ``(image, monitor_index, monitor_bounds_in_screen_coords)``.

        ``monitor_bounds`` is ``(left, top, width, height)`` in absolute screen
        coordinates so coordinates produced by the LLM against the downscaled
        image can be mapped back to real pixels for multi-monitor setups.
        """
        with mss.mss() as sct:
            idx = monitor_index if monitor_index is not None else self._active_monitor(sct)
            mon = sct.monitors[idx]
            bounds = (int(mon["left"]), int(mon["top"]), int(mon["width"]), int(mon["height"]))
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.rgb)
        if self.max_width and img.width > self.max_width:
            ratio = self.max_width / img.width
            new_size = (self.max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        return img, idx, bounds

    def blank(self) -> Image.Image:
        return Image.new("RGB", (16, 16), (0, 0, 0))

    def _active_monitor(self, sct: mss.base.MSSBase) -> int:
        """Return the monitor index containing the mouse cursor.

        Cursor position is the most reliable signal: it tracks whichever
        screen the user is actively working on, regardless of focus state
        (our overlay grabs focus during capture, which poisons
        ``GetForegroundWindow`` based detection).
        """
        try:
            cx, cy = self._cursor_pos()
            for i, mon in enumerate(sct.monitors[1:], start=1):
                if (
                    mon["left"] <= cx < mon["left"] + mon["width"]
                    and mon["top"] <= cy < mon["top"] + mon["height"]
                ):
                    return i
        except Exception as exc:
            log.debug("cursor monitor detection failed: %s", exc)
        return 1 if len(sct.monitors) > 1 else 0

    @staticmethod
    def _cursor_pos() -> tuple[int, int]:
        try:
            import win32api  # type: ignore[import-not-found]

            return win32api.GetCursorPos()
        except ImportError:
            pass
        try:
            from PySide6.QtGui import QCursor

            p = QCursor.pos()
            return p.x(), p.y()
        except Exception:
            return (0, 0)


def save_image(img: Image.Image, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{int(time.time() * 1000)}.png"
    img.save(path, format="PNG", optimize=True)
    return path
