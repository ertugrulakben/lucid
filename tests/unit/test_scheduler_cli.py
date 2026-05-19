"""CLI surface for `lucid schedule` — add / list / remove / enable / disable."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(tmp_data: Path, *args: str) -> tuple[int, str, str]:
    env_path = str(tmp_data)
    import os

    env = os.environ.copy()
    env["LUCID_DATA_DIR"] = env_path
    result = subprocess.run(
        [sys.executable, "-m", "lucid", *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def test_schedule_add_and_list(tmp_path: Path) -> None:
    rc, out, _ = _run(
        tmp_path,
        "schedule",
        "add",
        "--slug",
        "sabah_rapor",
        "--cron",
        "0 9 * * *",
        "--prompt",
        "Gmail'de özet çıkar",
    )
    assert rc == 0
    assert "scheduled" in out

    rc, out, _ = _run(tmp_path, "schedule", "list")
    assert rc == 0
    assert "sabah_rapor" in out
    assert "0 9 * * *" in out


def test_schedule_every_shortcut(tmp_path: Path) -> None:
    rc, out, _ = _run(
        tmp_path,
        "schedule",
        "add",
        "--slug",
        "yarim_saatte",
        "--every",
        "30m",
        "--prompt",
        "bildirim kontrol",
    )
    assert rc == 0
    rc, out, _ = _run(tmp_path, "schedule", "list")
    assert "*/30 * * * *" in out


def test_schedule_requires_a_schedule(tmp_path: Path) -> None:
    rc, out, _ = _run(
        tmp_path,
        "schedule",
        "add",
        "--slug",
        "no_time",
        "--prompt",
        "nothing",
    )
    assert rc == 2
    assert "cron" in out or "every" in out or "at" in out


def test_schedule_rejects_mixed_cron_and_every(tmp_path: Path) -> None:
    rc, out, _ = _run(
        tmp_path,
        "schedule",
        "add",
        "--slug",
        "mix",
        "--cron",
        "0 9 * * *",
        "--every",
        "1h",
        "--prompt",
        "bla",
    )
    assert rc == 2
    assert "cron" in out and "every" in out


def test_schedule_disable_and_enable(tmp_path: Path) -> None:
    _run(tmp_path, "schedule", "add", "--slug", "hello", "--cron", "0 9 * * *", "--prompt", "hi")
    rc, out, _ = _run(tmp_path, "schedule", "disable", "hello")
    assert rc == 0 and "disabled" in out
    rc, out, _ = _run(tmp_path, "schedule", "enable", "hello")
    assert rc == 0 and "enabled" in out


def test_schedule_remove(tmp_path: Path) -> None:
    _run(tmp_path, "schedule", "add", "--slug", "zap", "--cron", "0 * * * *", "--prompt", "p")
    rc, out, _ = _run(tmp_path, "schedule", "remove", "zap")
    assert rc == 0 and "removed" in out
    rc, out, _ = _run(tmp_path, "schedule", "remove", "zap")
    assert rc == 2 and "no scheduled task" in out
