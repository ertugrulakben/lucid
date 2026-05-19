"""Low-FPS frame buffer writer for optional teach-mode video reference.

We intentionally record at a low frame rate (default 4 FPS) and keep frames in
memory as JPEG bytes. This keeps the recording light enough for the LLM to use
as a visual reference when summarizing the workflow, without producing giant
video files.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from dataclasses import dataclass, field

import mss
from PIL import Image

log = logging.getLogger("lucid.recorder.video")


@dataclass
class FrameBuffer:
    fps: int = 4
    max_frames: int = 1200
    frames: list[tuple[int, bytes]] = field(default_factory=list)


class VideoRecorder:
    def __init__(self, fps: int = 4, max_duration_seconds: int = 300) -> None:
        self.buffer = FrameBuffer(fps=fps, max_frames=fps * max_duration_seconds)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started: float | None = None

    def start(self) -> None:
        self._stop.clear()
        self._started = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True, name="lucid-video")
        self._thread.start()

    def stop(self) -> FrameBuffer:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        return self.buffer

    def _run(self) -> None:
        interval = 1.0 / max(1, self.buffer.fps)
        with mss.mss() as sct:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            while not self._stop.is_set():
                try:
                    raw = sct.grab(mon)
                    img = Image.frombytes("RGB", raw.size, raw.rgb)
                    if img.width > 960:
                        ratio = 960 / img.width
                        img = img.resize((960, int(img.height * ratio)), Image.Resampling.BILINEAR)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=60)
                    at_ms = int((time.monotonic() - (self._started or 0)) * 1000)
                    self.buffer.frames.append((at_ms, buf.getvalue()))
                    if len(self.buffer.frames) > self.buffer.max_frames:
                        self.buffer.frames.pop(0)
                except Exception as exc:
                    log.debug("frame capture failed: %s", exc)
                self._stop.wait(interval)
