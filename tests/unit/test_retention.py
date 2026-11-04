"""Retention settings are enforced on the data folder (lucid.privacy.apply_retention)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

from lucid.agent.execute_mode import ExecuteMode
from lucid.config.settings import Settings
from lucid.privacy import apply_retention, prune_older_than

HOUR = 3600.0


def _make(path: Path, age_hours: float, now: float, *, folder: bool = False) -> Path:
    if folder:
        path.mkdir(parents=True)
        (path / "index.jsonl").write_text("{}", encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    stamp = now - age_hours * HOUR
    os.utime(path, (stamp, stamp))
    return path


def test_prune_older_than_removes_old_files_and_folders(tmp_path: Path) -> None:
    now = time.time()
    old_file = _make(tmp_path / "old.png", 30, now)
    old_dir = _make(tmp_path / "old-session", 30, now, folder=True)
    new_file = _make(tmp_path / "new.png", 1, now)
    assert prune_older_than(tmp_path, 24, now=now) == 2
    assert not old_file.exists()
    assert not old_dir.exists()
    assert new_file.exists()


def test_prune_older_than_zero_keeps_everything(tmp_path: Path) -> None:
    now = time.time()
    old = _make(tmp_path / "old.png", 1000, now)
    assert prune_older_than(tmp_path, 0, now=now) == 0
    assert old.exists()


def test_prune_older_than_missing_folder(tmp_path: Path) -> None:
    assert prune_older_than(tmp_path / "missing", 24) == 0


def test_apply_retention_uses_each_setting(tmp_path: Path) -> None:
    now = time.time()
    settings = Settings(data_dir=tmp_path)
    shot_old = _make(settings.screenshot_dir / "1.png", 25, now)
    shot_new = _make(settings.screenshot_dir / "2.png", 23, now)
    proof_old = _make(tmp_path / "proofs" / "p.png", 25, now)
    journal_old = _make(settings.journals_dir / "20260101-000000-demo", 1000, now, folder=True)
    log_old = _make(tmp_path / "schedule_logs" / "a.log", 15 * 24, now)
    log_new = _make(tmp_path / "schedule_logs" / "b.log", 13 * 24, now)
    removed = apply_retention(settings, now=now)
    assert removed == {"screenshots": 1, "proofs": 1, "journals": 0, "schedule_logs": 1}
    assert not shot_old.exists()
    assert shot_new.exists()
    assert not proof_old.exists()
    assert journal_old.exists()  # journal.retention_hours defaults to 0: count cap only
    assert not log_old.exists()
    assert log_new.exists()


def test_journal_retention_hours_opt_in(tmp_path: Path) -> None:
    now = time.time()
    settings = Settings(data_dir=tmp_path)
    settings.journal.retention_hours = 48
    old = _make(settings.journals_dir / "20260101-000000-demo", 49, now, folder=True)
    new = _make(settings.journals_dir / "20260102-000000-demo", 47, now, folder=True)
    assert apply_retention(settings, now=now)["journals"] == 1
    assert not old.exists()
    assert new.exists()


def test_execute_retention_pass_uses_run_settings(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    old = _make(settings.screenshot_dir / "old.png", 25, time.time())
    ExecuteMode._apply_retention(SimpleNamespace(settings=settings))
    assert not old.exists()
