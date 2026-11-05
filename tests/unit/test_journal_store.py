"""Unit tests for the Step Journal disk store."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

from lucid import privacy
from lucid.journal import StepJournal, iter_sessions
from lucid.journal.store import prune_old_sessions, read_session


def _link_dir(link: Path, target: Path) -> None:
    """A junction on Windows (no privilege needed), a symlink elsewhere; skips when not allowed."""
    try:
        if sys.platform == "win32":
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)
    except (OSError, ImportError, AttributeError) as exc:
        pytest.skip(f"cannot create a directory link here: {exc}")


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
    # record_text keeps typed text verbatim; by default it is masked (test_privacy.py)
    journal = StepJournal.open_session(tmp_path, goal="round trip", record_text=True)
    journal.record(
        action_name="type",
        params={"text": "hello"},
        before_image=_img(),
        after_image=_img(),
        outcome="typed",
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


def test_session_cap_leaves_other_folders_alone(tmp_path: Path) -> None:
    """journals/ can share a folder with the user's files: only Lucid's sessions count and go."""
    journals_dir = tmp_path / "journals"
    journals_dir.mkdir()
    (journals_dir / "2019").mkdir()
    (journals_dir / "2019" / "diary.txt").write_text("x", encoding="utf-8")
    (journals_dir / "Archive").mkdir()
    for name in ("20260101-000000-demo", "20260102-000000-demo", "20260103-000000-demo"):
        (journals_dir / name).mkdir()
    assert prune_old_sessions(journals_dir, keep=2) == 1
    assert {p.name for p in journals_dir.iterdir()} == {
        "2019",
        "Archive",
        "20260102-000000-demo",
        "20260103-000000-demo",
    }
    assert (journals_dir / "2019" / "diary.txt").exists()
    assert [p.name for p in iter_sessions(journals_dir)] == [
        "20260103-000000-demo",
        "20260102-000000-demo",
    ]


def test_session_cap_ignores_links_files_and_foreign_names(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("x", encoding="utf-8")
    journals_dir = tmp_path / "journals"
    journals_dir.mkdir()
    _link_dir(journals_dir / "20190101-000000-linked", outside)
    (journals_dir / "20190102-000000-file").write_text("x", encoding="utf-8")
    (journals_dir / "20190103-120000-holiday photos").mkdir()  # shares the prefix only
    for name in ("20260101-000000-a", "20260102-000000-b"):
        (journals_dir / name).mkdir()
    assert prune_old_sessions(journals_dir, keep=1) == 1
    assert not (journals_dir / "20260101-000000-a").exists()
    assert (journals_dir / "20190101-000000-linked").exists()
    assert (journals_dir / "20190102-000000-file").exists()
    assert (journals_dir / "20190103-120000-holiday photos").exists()
    assert (outside / "keep.txt").exists()
    assert [p.name for p in iter_sessions(journals_dir)] == ["20260102-000000-b"]


def test_session_cap_does_not_enter_a_linked_journals_folder(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    for name in ("20260101-000000-a", "20260102-000000-b", "20260103-000000-c"):
        (real / name).mkdir()
    _link_dir(tmp_path / "journals", real)
    assert prune_old_sessions(tmp_path / "journals", keep=1) == 0
    assert len(list(real.iterdir())) == 3


def test_session_cap_deletes_through_remove_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        privacy, "remove_entry", lambda path, folder: calls.append((path.name, folder))
    )
    journals_dir = tmp_path / "journals"
    journals_dir.mkdir()
    for name in ("20260101-000000-a", "20260102-000000-b"):
        (journals_dir / name).mkdir()
    assert prune_old_sessions(journals_dir, keep=1) == 1
    assert calls == [("20260101-000000-a", True)]


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
        id=1,
        ts=0.0,
        action_name="click_element",
        params={"element_name": "Send", "element_role": "Button"},
        outcome="ok",
    )
    short = record.short_params()
    assert "Send" in short


def test_outcome_one_line_truncates() -> None:
    from lucid.journal.models import StepRecord

    record = StepRecord(
        id=1,
        ts=0.0,
        action_name="x",
        params={},
        outcome=("a" * 500) + "\nsecond line",
    )
    line = record.outcome_one_line(max_chars=80)
    assert len(line) == 80
    assert line.endswith("…")
    assert "\n" not in line
