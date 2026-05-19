"""Scheduled task runner — cron + one-shot timers for Execute prompts.

Everything lives under ``data/scheduled_tasks.json`` so the catalogue is
portable just like the rest of Lucid. When the tray app is running, a
background thread polls the store every 30 s and spawns ``python -m
lucid exec`` as a subprocess for any task whose ``next_run_at`` has
elapsed. ``croniter`` handles the cron maths.
"""

from lucid.scheduler.daemon import SchedulerDaemon, run_once_now
from lucid.scheduler.store import (
    ScheduledTask,
    ScheduleStore,
    compute_next_run,
    normalise_every,
)

__all__ = [
    "ScheduleStore",
    "ScheduledTask",
    "SchedulerDaemon",
    "compute_next_run",
    "normalise_every",
    "run_once_now",
]
