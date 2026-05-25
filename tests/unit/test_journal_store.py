"""Unit tests for the Step Journal disk store."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from lucid.journal import StepJournal, iter_sessions
from lucid.journal.store import prune_old_sessions, read_session


def _img(color: tuple[int, int, int] = (10, 20, 30)) -> Image.Image:
    return Image.new("RGB", (640, 360), color=color)


def test_open_session_creates_directory(tmp_path: Path) -> None:
    journals_dir = tmp_path / "journals"
    journal = StepJournal.open_session(journals_dir, goal="open notepad")
    assert journal.session_dir.exists()
    assert journal.session_dir.parent == journals_dir
    assert "open_notepad" in journal.session_dir.name


def test_record_appends_jsonl_and_thumbs(tmp_path: Path) -> None:
    journal = StepJournal.open_session(tmp_path, goal="demo")
    record = journal.record(
        action_name="left_click",
        params={"coordinate": [120, 80]},
        before_image=_img((10, 10, 10)),
        after_image=_img((200, 200, 200)),
        outcome="clicked something",
        monitor_index=1,
    )
    assert record.id == 1
    assert record.before_thumb == "step-001-before.webp"
    assert record.after_thumb == "step-001-after.webp"
    assert (journal.session_dir / "step-001-before.webp").exists()
    assert (journal.session_dir / "step-001-after.webp").exists()

    index = journal.session_dir / "index.jsonl"
    payload = json.loads(index.read_text(encoding="utf-8").strip())
    assert payload["action_name"] == "left_click"
    assert payload["coord"] == [120, 80]
    assert payload["monitor_index"] == 1


def test_record_increments_step_id(tmp_path: Path) -> None:
    journal = StepJournal.open_session(tmp_path, goal="multi")
    journal.record(
        action_name="a", params={}, before_image=_img(), after_image=_img(), outcome="ok"
    )
    second = journal.record(
        action_name="b", params={}, before_image=_img(), after_image=_img(), outcome="ok"
    )
    assert second.id == 2
    assert journal.last_step_id == 2


def test_read_session_round_trip(tmp_path: Path) -> None:
    journal = StepJournal.open_session(tmp_path, goal="round trip")
    journal.record(
        action_name="type", params={"text": "hello"},
        before_image=_img(), after_image=_img(), outcome="typed",
    )
    records = read_session(journal.session_dir)
    assert len(records) == 1
    assert records[0].action_name == "type"
    assert records[0].params == {"text": "hello"}


def test_prune_old_sessions_keeps_newest(tmp_path: Path) -> None:
    # Create 5 dummy sessions with stamped names so sort is deterministic.
    journals_dir = tmp_path / "journals"
    journals_dir.mkdir()
    for i in range(5):
        (journals_dir / f"2026010{i}-000000-demo").mkdir()
    removed = prune_old_sessions(journals_dir, keep=2)
    assert removed == 3
    remaining = sorted(p.name for p in journals_dir.iterdir())
    assert remaining == ["20260103-000000-demo", "20260104-000000-demo"]


def test_iter_sessions_newest_first(tmp_path: Path) -> None:
    journals_dir = tmp_path / "journals"
    journals_dir.mkdir()
    for name in ("20260101-000000-a", "20260203-101010-b", "20260102-120000-c"):
        (journals_dir / name).mkdir()
    ordered = [p.name for p in iter_sessions(journals_dir)]
    assert ordered == ["20260203-101010-b", "20260102-120000-c", "20260101-000000-a"]


def test_short_params_extracts_useful_keys() -> None:
    from lucid.journal.models import StepRecord

    record = StepRecord(
        id=1, ts=0.0, action_name="click_element",
        params={"element_name": "Send", "element_role": "Button"},
        outcome="ok",
    )
    short = record.short_params()
    assert "Send" in short


def test_outcome_one_line_truncates() -> None:
    from lucid.journal.models import StepRecord

    record = StepRecord(
        id=1, ts=0.0, action_name="x", params={},
        outcome=("a" * 500) + "\nsecond line",
    )
    line = record.outcome_one_line(max_chars=80)
    assert len(line) == 80
    assert line.endswith("…")
    assert "\n" not in line
