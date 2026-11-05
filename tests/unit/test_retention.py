"""Retention settings are enforced on the data folder (lucid.privacy.apply_retention).

Pruning removes only the files and folders Lucid named itself and never follows links:
``data_dir`` can point at a folder that also holds the user's own files.
"""

from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from lucid import privacy
from lucid.agent.execute_mode import ExecuteMode
from lucid.config.settings import Settings
from lucid.privacy import LUCID_NAMES, apply_retention, is_link, prune_older_than

HOUR = 3600.0
SHOT = "1767225600000.png"  # capture.screenshot.save_image: epoch milliseconds
BROWSER_SHOT = "browser-20260101-000000.png"
PROOF = "20260101-000000-open_notepad.png"
SESSION = "20260101-000000-open_notepad"
RUN_LOG = "20260101-000000-nightly.log"


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


@pytest.mark.parametrize(
    "folder, name",
    [
        ("screenshots", SHOT),
        ("screenshots", BROWSER_SHOT),
        ("proofs", PROOF),
        ("proofs", "20260101-000000-şifre_değiştir.png"),
        ("journals", SESSION),
        ("journals", SESSION + "-2"),
        ("schedule_logs", RUN_LOG),
        ("schedule_logs", "20260101-000000-.log"),  # a task saved without a slug
    ],
)
def test_lucid_names_match_what_lucid_writes(folder: str, name: str) -> None:
    assert LUCID_NAMES[folder].fullmatch(name)


@pytest.mark.parametrize(
    "folder, name",
    [
        ("screenshots", "Screenshot 2026-11-05 101010.png"),
        ("screenshots", "holiday.png"),
        ("screenshots", "1767225600000.jpg"),
        ("screenshots", "١" * 13 + ".png"),  # Arabic-Indic digits are not Lucid's
        ("screenshots", SHOT + "\n"),
        ("proofs", "proof.png"),
        ("schedule_logs", "lucid.log"),
        ("journals", "notes"),
        ("journals", "20190101-120000-My Holiday Photos"),
        ("journals", "20190101-120000-"),
    ],
)
def test_lucid_names_reject_foreign_names(folder: str, name: str) -> None:
    assert not LUCID_NAMES[folder].fullmatch(name)


def test_prune_removes_old_lucid_files_only(tmp_path: Path) -> None:
    now = time.time()
    old = _make(tmp_path / SHOT, 30, now)
    new = _make(tmp_path / "1767225700000.png", 1, now)
    foreign = _make(tmp_path / "Screenshot (1).png", 1000, now)
    foreign_dir = _make(tmp_path / "Holiday", 1000, now, folder=True)
    removed = prune_older_than(tmp_path, 24, names=LUCID_NAMES["screenshots"], now=now)
    assert removed == 1
    assert not old.exists()
    assert new.exists()
    assert foreign.exists()
    assert foreign_dir.exists()


def _spy_remove(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, bool]]:
    """Record what pruning would delete (privacy._remove is its only deletion point)."""
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(privacy, "_remove", lambda path, folder: calls.append((path.name, folder)))
    return calls


@pytest.mark.parametrize(
    "mode, tag, expected",
    [
        (stat.S_IFLNK, 0, True),  # symlink
        (stat.S_IFDIR, 0xA0000003, True),  # junction (mount point reparse tag)
        (stat.S_IFREG, 0xA000000C, True),  # symlink reparse tag
        (stat.S_IFREG, 0x9000601A, False),  # cloud-file placeholder (OneDrive)
        (stat.S_IFREG, 0, False),
    ],
)
def test_is_link_counts_only_name_surrogates(mode: int, tag: int, expected: bool) -> None:
    assert is_link(SimpleNamespace(st_mode=mode, st_reparse_tag=tag)) is expected  # type: ignore[arg-type]


def test_prune_skips_entries_of_the_wrong_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = time.time()
    folder_named_like_a_shot = _make(tmp_path / SHOT, 30, now, folder=True)
    file_named_like_a_session = _make(tmp_path / "journals" / SESSION, 30, now)
    calls = _spy_remove(monkeypatch)
    assert prune_older_than(tmp_path, 24, names=LUCID_NAMES["screenshots"], now=now) == 0
    journals = tmp_path / "journals"
    assert prune_older_than(journals, 24, names=LUCID_NAMES["journals"], folders=True, now=now) == 0
    assert calls == []  # the type check stops them before any deletion is tried
    assert folder_named_like_a_shot.exists()
    assert file_named_like_a_session.exists()


def test_prune_zero_keeps_everything(tmp_path: Path) -> None:
    now = time.time()
    old = _make(tmp_path / SHOT, 1000, now)
    assert prune_older_than(tmp_path, 0, names=LUCID_NAMES["screenshots"], now=now) == 0
    assert old.exists()


def test_prune_missing_folder(tmp_path: Path) -> None:
    assert prune_older_than(tmp_path / "missing", 24, names=LUCID_NAMES["screenshots"]) == 0


def test_prune_never_follows_or_removes_a_linked_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    keep = _make(outside / "important.txt", 1000, time.time())
    journals = tmp_path / "journals"
    journals.mkdir()
    _link_dir(journals / SESSION, outside)
    calls = _spy_remove(monkeypatch)
    later = time.time() + 1000 * HOUR  # old enough by age, matching name, right type
    assert (
        prune_older_than(journals, 24, names=LUCID_NAMES["journals"], folders=True, now=later) == 0
    )
    assert calls == []  # the link check stops it; rmtree's own junction guard is never relied on
    assert (journals / SESSION).exists()
    assert keep.exists()


def test_prune_does_not_remove_a_file_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _make(tmp_path / "outside" / "photo.png", 1000, time.time())
    shots = tmp_path / "screenshots"
    shots.mkdir()
    try:
        os.symlink(target, shots / SHOT)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create a file symlink here: {exc}")
    calls = _spy_remove(monkeypatch)
    later = time.time() + 1000 * HOUR
    assert prune_older_than(shots, 24, names=LUCID_NAMES["screenshots"], now=later) == 0
    assert calls == []
    assert os.path.lexists(shots / SHOT)
    assert target.exists()


def test_prune_does_not_enter_a_linked_folder(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    shot = _make(outside / SHOT, 1000, time.time())
    _link_dir(tmp_path / "screenshots", outside)
    later = time.time() + 1000 * HOUR
    pattern = LUCID_NAMES["screenshots"]
    assert prune_older_than(tmp_path / "screenshots", 24, names=pattern, now=later) == 0
    assert shot.exists()


def test_data_dir_in_the_users_pictures_folder(tmp_path: Path) -> None:
    """data_dir set to Pictures: screenshots/ is the user's own Screenshots folder."""
    now = time.time()
    pictures = tmp_path / "Pictures"
    settings = Settings(data_dir=pictures)
    users_own = _make(settings.screenshot_dir / "Screenshot 2026-01-01 090000.png", 1000, now)
    lucids = _make(settings.screenshot_dir / SHOT, 25, now)
    removed = apply_retention(settings, now=now)
    assert removed["screenshots"] == 1
    assert users_own.exists()
    assert not lucids.exists()


def test_apply_retention_uses_each_setting(tmp_path: Path) -> None:
    now = time.time()
    settings = Settings(data_dir=tmp_path)
    shot_old = _make(settings.screenshot_dir / SHOT, 25, now)
    shot_new = _make(settings.screenshot_dir / BROWSER_SHOT, 23, now)
    proof_old = _make(tmp_path / "proofs" / PROOF, 25, now)
    journal_old = _make(settings.journals_dir / SESSION, 1000, now, folder=True)
    log_old = _make(tmp_path / "schedule_logs" / RUN_LOG, 15 * 24, now)
    log_new = _make(tmp_path / "schedule_logs" / "20260102-000000-nightly.log", 13 * 24, now)
    removed = apply_retention(settings, now=now)
    assert removed == {"screenshots": 1, "proofs": 1, "journals": 0, "schedule_logs": 1}
    assert not shot_old.exists()
    assert shot_new.exists()
    assert not proof_old.exists()
    assert journal_old.exists()  # journal.retention_hours defaults to 0: count cap only
    assert not log_old.exists()
    assert log_new.exists()


def test_proofs_have_their_own_retention(tmp_path: Path) -> None:
    now = time.time()
    settings = Settings(data_dir=tmp_path)
    settings.screenshot.retention_hours = 1
    settings.screenshot.proof_retention_hours = 48
    shot = _make(settings.screenshot_dir / SHOT, 2, now)
    proof = _make(tmp_path / "proofs" / PROOF, 25, now)
    removed = apply_retention(settings, now=now)
    assert (removed["screenshots"], removed["proofs"]) == (1, 0)
    assert not shot.exists()
    assert proof.exists()


def test_journal_retention_hours_opt_in(tmp_path: Path) -> None:
    now = time.time()
    settings = Settings(data_dir=tmp_path)
    settings.journal.retention_hours = 48
    old = _make(settings.journals_dir / SESSION, 49, now, folder=True)
    new = _make(settings.journals_dir / "20260102-000000-open_notepad", 47, now, folder=True)
    assert apply_retention(settings, now=now)["journals"] == 1
    assert not old.exists()
    assert new.exists()


def test_execute_retention_pass_uses_run_settings(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    old = _make(settings.screenshot_dir / SHOT, 25, time.time())
    ExecuteMode._apply_retention(SimpleNamespace(settings=settings))
    assert not old.exists()
