"""Teach mode never records what is typed into a password field.

UI Automation, the keyboard, the screen and the model are all faked.
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from lucid.config.settings import Settings
from lucid.recorder import workflow_recorder
from lucid.recorder.input_recorder import InputEvent
from lucid.recorder.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowVariable,
    load_workflow,
    merge_variables,
)
from lucid.replayer import semantic_replay
from lucid.replayer.semantic_replay import SemanticReplayer, shown_variables

TYPED = "hunter2"


def _press(key: str) -> InputEvent:
    return InputEvent(kind="key_press", at_ms=1, data={"key": key})


def _record(monkeypatch: pytest.MonkeyPatch) -> tuple[Workflow, list[bool]]:
    """Click the user field, type 'ea', Tab, type the password with a correction, Enter."""
    answers = iter([False, True])  # user field, then password field
    asked: list[bool] = []

    def focused_is_password() -> bool:
        asked.append(next(answers))
        return asked[-1]

    monkeypatch.setattr(workflow_recorder, "focused_is_password", focused_is_password)
    monkeypatch.setattr(workflow_recorder, "selector_at", lambda x, y: {"a11y_name": "User"})
    recorder = workflow_recorder.WorkflowRecorder(Settings(), name="login")
    events = [InputEvent(kind="mouse_click", at_ms=1, data={"x": 10, "y": 20})]
    events += [_press(c) for c in "ea"] + [_press("tab")]
    events += [_press(c) for c in TYPED] + [_press("backspace"), _press("x"), _press("enter")]
    for event in events:
        recorder._on_input(event)
    return recorder.workflow, asked


def test_password_field_keys_are_not_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, _ = _record(monkeypatch)
    assert [s.action for s in workflow.steps] == ["click", "type", "type", "key", "type", "key"]
    assert [s.text for s in workflow.steps if s.action == "type"] == ["e", "a", "{{secret_1}}"]
    assert workflow.steps[4].metadata == {"secret": True}
    assert [(v.name, v.secret) for v in workflow.variables] == [("secret_1", True)]
    assert "hunter" not in workflow.to_json()


def test_password_field_is_checked_once_per_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _, asked = _record(monkeypatch)
    assert asked == [False, True]


def test_secret_variable_survives_save_and_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workflow, _ = _record(monkeypatch)
    loaded = load_workflow(workflow.save(tmp_path))
    assert loaded.variables[0].secret is True
    assert loaded.steps[4].metadata == {"secret": True}


def test_summary_variables_keep_the_secret_ones() -> None:
    recorded = [WorkflowVariable(name="secret_1", secret=True)]
    proposed = [WorkflowVariable(name="customer"), WorkflowVariable(name="secret_1")]
    merged = merge_variables(recorded, proposed)
    assert [(v.name, v.secret) for v in merged] == [("secret_1", True), ("customer", False)]


class FakeProvider:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def image_block(self, image: object) -> dict:
        return {"type": "image"}

    def text_block(self, text: str) -> dict:
        self.texts.append(text)
        return {"type": "text", "text": text}

    def stream(self, *args: object, **kwargs: object):
        yield SimpleNamespace(kind="error", error="stop here", tool_use=None)


def _replayer(monkeypatch: pytest.MonkeyPatch) -> tuple[SemanticReplayer, FakeProvider, list]:
    provider = FakeProvider()
    replayer = SemanticReplayer(Settings(), provider)  # type: ignore[arg-type]
    runs: list = []
    replayer.actions = SimpleNamespace(  # type: ignore[assignment]
        run=lambda action: runs.append(action) or f"pasted {len(action.params['text'])} chars"
    )
    monkeypatch.setattr(semantic_replay.time, "sleep", lambda _s: None)
    screen = SimpleNamespace(image=SimpleNamespace(width=100, height=50))
    monkeypatch.setattr(semantic_replay.ContextSnapshot, "capture", staticmethod(lambda _s: screen))
    return replayer, provider, runs


def _login_workflow() -> Workflow:
    workflow = Workflow(name="login", variables=[WorkflowVariable(name="secret_1", secret=True)])
    workflow.append(
        WorkflowStep(
            index=0,
            action="type",
            intent="Type {{secret_1}} into the password field",
            text="{{secret_1}}",
            metadata={"secret": True},
        )
    )
    workflow.append(WorkflowStep(index=0, action="click", intent="Sign in, {{secret_1}} typed"))
    return workflow


def test_replay_types_the_secret_without_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    replayer, provider, runs = _replayer(monkeypatch)
    out = "".join(replayer.run(_login_workflow(), threading.Event(), {"secret_1": TYPED}))
    assert runs[0].action == "type"
    assert runs[0].params == {"text": TYPED}
    assert TYPED not in out
    assert "secret_1='[redacted: 7 chars]'" in out
    assert provider.texts  # the next step was planned by the model ...
    assert all(TYPED not in text for text in provider.texts)  # ... without the secret


def test_routed_workflow_shows_secret_variables_masked() -> None:
    shown = shown_variables({"secret_1": TYPED, "customer": "Acme"}, _login_workflow())
    assert shown == {"secret_1": "[redacted: 7 chars]", "customer": "Acme"}


def test_replay_stops_when_the_secret_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    replayer, provider, runs = _replayer(monkeypatch)
    out = "".join(replayer.run(_login_workflow(), threading.Event(), {}))
    assert runs == []
    assert "replay stopped" in out
    assert provider.texts == []
