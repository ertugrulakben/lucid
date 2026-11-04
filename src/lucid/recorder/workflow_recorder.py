"""Coordinates the input, accessibility, and video recorders into one workflow."""

from __future__ import annotations

import logging
import threading

from lucid.capture import ContextSnapshot
from lucid.capture.a11y import focused_is_password
from lucid.config.settings import Settings
from lucid.recorder.a11y_recorder import selector_at
from lucid.recorder.input_recorder import InputEvent, InputRecorder
from lucid.recorder.video import VideoRecorder
from lucid.recorder.workflow import Workflow, WorkflowStep, WorkflowVariable

log = logging.getLogger("lucid.recorder")

#: Keys after which the focus may sit in another field.
FOCUS_KEYS = frozenset({"tab", "enter"})


class WorkflowRecorder:
    """Records a taught workflow.

    Keys typed into a password field (UI Automation ``IsPassword``) are not
    recorded: the field becomes one ``{{secret_N}}`` step with a secret
    variable that the user supplies at replay. The field is checked once per
    focus change (click, Tab, Enter), at its first printable key.
    """

    def __init__(self, settings: Settings, name: str) -> None:
        self.settings = settings
        self.workflow = Workflow(name=name)
        self._input = InputRecorder(on_event=self._on_input)
        self._video: VideoRecorder | None = None
        self._running = False
        self._lock = threading.Lock()
        self._secret_field: bool | None = None  # None: focus moved, not checked yet
        self._secret_step_added = False
        self._secret_count = 0

    def start(self, initial_snapshot: ContextSnapshot | None = None) -> None:
        if initial_snapshot and initial_snapshot.active:
            self.workflow.target_app = initial_snapshot.active.process
        if self.settings.recorder.capture_video:
            self._video = VideoRecorder(
                fps=self.settings.recorder.video_fps,
                max_duration_seconds=self.settings.recorder.max_duration_seconds,
            )
            self._video.start()
        self._input.start()
        self._running = True
        log.info("Recording started: %s", self.workflow.name)

    def stop(self) -> Workflow:
        if not self._running:
            return self.workflow
        self._running = False
        self._input.stop()
        if self._video is not None:
            self._video.stop()
            self._video = None
        log.info("Recording stopped: %d steps", len(self.workflow.steps))
        return self.workflow

    def is_running(self) -> bool:
        return self._running

    def _on_input(self, event: InputEvent) -> None:
        with self._lock:
            if event.kind == "key_press" and self._in_secret_field(event):
                return
            step = _event_to_step(event)
            if step is None:
                return
            self.workflow.append(step)
            if event.kind == "mouse_click" or (
                event.kind == "key_press" and event.data.get("key") in FOCUS_KEYS
            ):
                self._secret_field = None

    def _in_secret_field(self, event: InputEvent) -> bool:
        """True when ``event`` is typed into a password field (and so is not recorded)."""
        key = event.data.get("key", "")
        if key in FOCUS_KEYS:
            return False
        if self._secret_field is None and len(key) == 1 and key.isprintable():
            self._secret_field = focused_is_password()
            self._secret_step_added = False
        if not self._secret_field:
            return False
        if not self._secret_step_added:
            self._secret_count += 1
            name = f"secret_{self._secret_count}"
            self.workflow.variables.append(
                WorkflowVariable(
                    name=name,
                    description="Typed into a password field while recording; not saved.",
                    secret=True,
                )
            )
            self.workflow.append(
                WorkflowStep(
                    index=0,
                    action="type",
                    intent=f"Type {{{{{name}}}}} into the password field",
                    text=f"{{{{{name}}}}}",
                    timestamp_ms=event.at_ms,
                    metadata={"secret": True},
                )
            )
            self._secret_step_added = True
        return True


def _event_to_step(event: InputEvent) -> WorkflowStep | None:
    if event.kind == "mouse_click":
        x, y = event.data["x"], event.data["y"]
        selector = selector_at(x, y)
        return WorkflowStep(
            index=0,
            action="click",
            intent=f"Click {selector.get('a11y_name') or f'at ({x},{y})'}",
            selector=selector,
            fallback_coord=[x, y],
            timestamp_ms=event.at_ms,
            metadata={"button": event.data.get("button", "left")},
        )
    if event.kind == "mouse_scroll":
        return WorkflowStep(
            index=0,
            action="scroll",
            intent=f"Scroll by ({event.data.get('dx', 0)}, {event.data.get('dy', 0)})",
            selector={"fallback_coord": [event.data.get("x", 0), event.data.get("y", 0)]},
            timestamp_ms=event.at_ms,
            metadata={"dx": event.data.get("dx", 0), "dy": event.data.get("dy", 0)},
        )
    if event.kind == "key_press":
        key = event.data.get("key", "")
        if len(key) == 1 and key.isprintable():
            return WorkflowStep(
                index=0,
                action="type",
                intent=f"Type {key!r}",
                text=key,
                timestamp_ms=event.at_ms,
            )
        return WorkflowStep(
            index=0,
            action="key",
            intent=f"Press {key}",
            keys=[key],
            timestamp_ms=event.at_ms,
        )
    return None
