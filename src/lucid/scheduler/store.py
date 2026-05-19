"""Scheduled task model + JSON persistence.

A single store lives at ``data/scheduled_tasks.json``. Entries carry a
human-friendly ``slug``, the ``prompt`` that will be handed to ``lucid
exec``, optional attachments / template parameters, and either:

- ``cron``   — standard 5-field expression, recurring
- ``run_at`` — ISO-8601 timestamp, one-shot

``next_run_at`` is a Unix epoch float the daemon uses for its due-time
comparison. We recompute it whenever an entry is added, edited, or after
a successful fire.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

SCHEDULE_FILE = "scheduled_tasks.json"


@dataclass
class ScheduledTask:
    slug: str
    prompt: str
    cron: str | None = None
    run_at: str | None = None
    template: str | None = None
    variables: dict[str, str] = field(default_factory=dict)
    attachments: list[str] = field(default_factory=list)
    enabled: bool = True
    timeout_seconds: int = 300
    max_steps: int | None = None
    resilient: bool = False
    last_run_at: float | None = None
    last_exit_code: int | None = None
    next_run_at: float | None = None
    run_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    description: str = ""

    def is_recurring(self) -> bool:
        return bool(self.cron)

    def is_one_shot(self) -> bool:
        return bool(self.run_at) and not self.cron

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ScheduledTask:
        allowed = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in (data or {}).items() if k in allowed}
        task = cls(**{**_defaults(), **clean})
        return task


def _defaults() -> dict:
    return {
        "slug": "",
        "prompt": "",
        "cron": None,
        "run_at": None,
        "template": None,
        "variables": {},
        "attachments": [],
        "enabled": True,
        "timeout_seconds": 300,
        "max_steps": None,
        "resilient": False,
        "last_run_at": None,
        "last_exit_code": None,
        "next_run_at": None,
        "run_count": 0,
        "created_at": time.time(),
        "updated_at": time.time(),
        "description": "",
    }


class ScheduleStore:
    """Thread-safe JSON store with a narrow mutation surface."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / SCHEDULE_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _load_raw(self) -> list[ScheduledTask]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        raw = data.get("tasks") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return []
        return [ScheduledTask.from_dict(item) for item in raw if isinstance(item, dict)]

    def _save_raw(self, tasks: list[ScheduledTask]) -> None:
        payload = {"tasks": [t.to_dict() for t in tasks]}
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list_all(self) -> list[ScheduledTask]:
        with self._lock:
            return self._load_raw()

    def get(self, slug: str) -> ScheduledTask | None:
        slug = (slug or "").strip().lower()
        if not slug:
            return None
        with self._lock:
            for task in self._load_raw():
                if task.slug.lower() == slug:
                    return task
        return None

    def upsert(self, task: ScheduledTask) -> ScheduledTask:
        with self._lock:
            tasks = self._load_raw()
            task.updated_at = time.time()
            for i, existing in enumerate(tasks):
                if existing.slug.lower() == task.slug.lower():
                    task.created_at = existing.created_at
                    task.run_count = existing.run_count
                    tasks[i] = task
                    break
            else:
                tasks.append(task)
            self._save_raw(tasks)
            return task

    def remove(self, slug: str) -> bool:
        slug_lower = (slug or "").strip().lower()
        if not slug_lower:
            return False
        with self._lock:
            tasks = self._load_raw()
            remaining = [t for t in tasks if t.slug.lower() != slug_lower]
            if len(remaining) == len(tasks):
                return False
            self._save_raw(remaining)
            return True

    def set_enabled(self, slug: str, enabled: bool) -> bool:
        with self._lock:
            tasks = self._load_raw()
            hit = False
            for task in tasks:
                if task.slug.lower() == (slug or "").strip().lower():
                    task.enabled = bool(enabled)
                    task.updated_at = time.time()
                    hit = True
                    break
            if hit:
                self._save_raw(tasks)
            return hit

    def mark_fired(self, slug: str, *, exit_code: int | None = None) -> None:
        """Record that ``slug`` ran, bump counters, and advance next_run_at."""
        with self._lock:
            tasks = self._load_raw()
            for task in tasks:
                if task.slug.lower() == (slug or "").strip().lower():
                    now = time.time()
                    task.last_run_at = now
                    task.last_exit_code = exit_code
                    task.run_count += 1
                    task.next_run_at = compute_next_run(task, reference=now)
                    if task.is_one_shot():
                        task.enabled = False
                    task.updated_at = now
                    break
            self._save_raw(tasks)

    def refresh_next_run(self, slug: str) -> ScheduledTask | None:
        """Recompute ``next_run_at`` for a single task after an edit."""
        with self._lock:
            tasks = self._load_raw()
            target = None
            for task in tasks:
                if task.slug.lower() == (slug or "").strip().lower():
                    task.next_run_at = compute_next_run(task, reference=time.time())
                    task.updated_at = time.time()
                    target = task
                    break
            if target is not None:
                self._save_raw(tasks)
            return target


# ---------- cron / schedule helpers ----------

_EVERY_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)


def normalise_every(expr: str) -> str:
    """Turn ``30m``/``1h``/``2d`` into an equivalent 5-field cron string.

    Raises ``ValueError`` on anything it can't parse.
    """
    match = _EVERY_RE.match(expr or "")
    if not match:
        raise ValueError(f"cannot parse --every {expr!r}; use e.g. 30m, 1h, 2d")
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if amount <= 0:
        raise ValueError(f"--every must be positive, got {amount}")
    if unit == "s":
        raise ValueError("sub-minute scheduling is not supported")
    if unit == "m":
        if amount >= 60:
            raise ValueError("use --every <N>h for hourly intervals >= 60")
        return f"*/{amount} * * * *"
    if unit == "h":
        if amount >= 24:
            raise ValueError("use --every <N>d for daily intervals >= 24h")
        return f"0 */{amount} * * *"
    if unit == "d":
        return f"0 0 */{amount} * *"
    raise ValueError(f"unknown time unit: {unit}")


def compute_next_run(task: ScheduledTask, reference: float | None = None) -> float | None:
    """Return the next fire time (Unix epoch, local) or ``None`` if none remains."""
    now = reference if reference is not None else time.time()

    if task.cron:
        try:
            from croniter import croniter  # type: ignore[import-not-found]
        except ImportError:
            return None
        try:
            base = datetime.fromtimestamp(now)
            cron_iter = croniter(task.cron, base)
            nxt = cron_iter.get_next(datetime)
            return nxt.timestamp()
        except Exception:
            return None

    if task.run_at:
        try:
            parsed = datetime.fromisoformat(task.run_at)
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        ts = parsed.timestamp()
        if ts < now and task.run_count > 0:
            return None
        return ts

    return None
