from __future__ import annotations

from pathlib import Path

from lucid.recorder.workflow import Workflow, WorkflowStep, load_workflow


def test_workflow_roundtrip(tmp_path: Path) -> None:
    wf = Workflow(name="Test Workflow", target_app="notepad.exe")
    wf.append(
        WorkflowStep(
            index=0,
            action="click",
            intent="Click File menu",
            selector={"a11y_name": "File", "role": "MenuItem"},
            fallback_coord=[12, 34],
            timestamp_ms=100,
        )
    )
    wf.append(
        WorkflowStep(
            index=0,
            action="type",
            intent="Type filename",
            text="hello.txt",
            timestamp_ms=500,
        )
    )
    path = wf.save(tmp_path)
    assert path.exists()

    reloaded = load_workflow(path)
    assert reloaded.name == "Test Workflow"
    assert reloaded.target_app == "notepad.exe"
    assert len(reloaded.steps) == 2
    assert reloaded.steps[0].selector["a11y_name"] == "File"
    assert reloaded.steps[1].text == "hello.txt"


def test_workflow_indexes_are_reassigned_on_append() -> None:
    wf = Workflow(name="x")
    wf.append(WorkflowStep(index=99, action="click"))
    wf.append(WorkflowStep(index=99, action="click"))
    assert wf.steps[0].index == 0
    assert wf.steps[1].index == 1
