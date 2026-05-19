from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from lucid.scheduler.store import (
    ScheduledTask,
    ScheduleStore,
    compute_next_run,
    normalise_every,
)


def test_normalise_every_minutes() -> None:
    assert normalise_every("30m") == "*/30 * * * *"
    assert normalise_every("5m") == "*/5 * * * *"


def test_normalise_every_hours_and_days() -> None:
    assert normalise_every("1h") == "0 */1 * * *"
    assert normalise_every("3h") == "0 */3 * * *"
    assert normalise_every("2d") == "0 0 */2 * *"


def test_normalise_every_rejects_seconds_and_bad_input() -> None:
    with pytest.raises(ValueError):
        normalise_every("45s")
    with pytest.raises(ValueError):
        normalise_every("bla")
    with pytest.raises(ValueError):
        normalise_every("0m")
    with pytest.raises(ValueError):
        normalise_every("90m")


def test_compute_next_run_cron_returns_future_timestamp() -> None:
    task = ScheduledTask(slug="t", prompt="noop", cron="*/5 * * * *")
    now = time.time()
    nxt = compute_next_run(task, reference=now)
    assert nxt is not None and nxt > now
    assert nxt - now <= 5 * 60 + 1


def test_compute_next_run_one_shot_future_returns_same() -> None:
    future = (datetime.now() + timedelta(hours=1)).isoformat(timespec="minutes")
    task = ScheduledTask(slug="t", prompt="noop", run_at=future)
    nxt = compute_next_run(task)
    assert nxt is not None and nxt > time.time()


def test_compute_next_run_one_shot_expired_returns_none_after_run() -> None:
    past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="minutes")
    task = ScheduledTask(slug="t", prompt="noop", run_at=past, run_count=1)
    assert compute_next_run(task) is None


def test_store_upsert_and_list(tmp_path: Path) -> None:
    store = ScheduleStore(tmp_path)
    task = ScheduledTask(slug="sabah_rapor", prompt="Gmail aç özet çıkar", cron="0 9 * * *")
    store.upsert(task)
    all_tasks = store.list_all()
    assert len(all_tasks) == 1 and all_tasks[0].slug == "sabah_rapor"


def test_store_upsert_preserves_run_count(tmp_path: Path) -> None:
    store = ScheduleStore(tmp_path)
    task = ScheduledTask(slug="x", prompt="p", cron="* * * * *")
    store.upsert(task)
    store.mark_fired("x", exit_code=0)
    # Re-upsert with a new prompt; counter should survive.
    updated = ScheduledTask(slug="x", prompt="new prompt", cron="* * * * *")
    store.upsert(updated)
    stored = store.get("x")
    assert stored is not None
    assert stored.run_count == 1
    assert stored.prompt == "new prompt"


def test_store_mark_fired_auto_disables_one_shot(tmp_path: Path) -> None:
    store = ScheduleStore(tmp_path)
    run_at = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="minutes")
    task = ScheduledTask(slug="x", prompt="p", run_at=run_at, enabled=True)
    store.upsert(task)
    store.mark_fired("x", exit_code=0)
    stored = store.get("x")
    assert stored is not None
    assert stored.enabled is False
    assert stored.run_count == 1


def test_store_remove(tmp_path: Path) -> None:
    store = ScheduleStore(tmp_path)
    store.upsert(ScheduledTask(slug="x", prompt="p", cron="* * * * *"))
    assert store.remove("x") is True
    assert store.list_all() == []
    assert store.remove("x") is False


def test_store_set_enabled_flip(tmp_path: Path) -> None:
    store = ScheduleStore(tmp_path)
    store.upsert(ScheduledTask(slug="x", prompt="p", cron="* * * * *", enabled=True))
    assert store.set_enabled("x", False)
    assert store.get("x").enabled is False
    assert store.set_enabled("x", True)
    assert store.get("x").enabled is True


def test_store_get_case_insensitive(tmp_path: Path) -> None:
    store = ScheduleStore(tmp_path)
    store.upsert(ScheduledTask(slug="sabah_rapor", prompt="p", cron="0 9 * * *"))
    assert store.get("SABAH_RAPOR") is not None
    assert store.get("  sabah_rapor  ") is not None
