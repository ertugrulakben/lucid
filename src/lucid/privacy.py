"""Keep typed text out of what Lucid writes to disk or shows on screen.

Lucid types on the user's behalf, password fields included. The step journal
(``data/journals``), ``logs/lucid.log``, the overlay's action log and Thoughts
panels, and the logs of scheduled runs describe every action, so they must not
repeat what was typed: they keep its length instead.

``journal.record_text: true`` stores typed text verbatim in the journal for
debugging. The log file and the overlay always show the masked form.

The retention settings are enforced here as well (:func:`apply_retention`), at
app start and before every Execute run.
"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lucid.config.settings import Settings

log = logging.getLogger("lucid.privacy")

#: Actions whose ``text`` parameter is content typed into the focused field.
#: The ``key`` action also carries ``text`` (a key combo such as ``ctrl+s``);
#: that is not user content and stays readable.
TEXT_ACTIONS = frozenset({"type", "type_text", "browser_fill"})


def mask_text(text: str) -> str:
    """Placeholder that keeps the length of ``text`` but not its content."""
    return f"[redacted: {len(text)} chars]"


def redact_params(action_name: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """Copy of ``params`` with the typed text masked for text-entry actions."""
    out = dict(params)
    if action_name in TEXT_ACTIONS and isinstance(out.get("text"), str):
        out["text"] = mask_text(out["text"])
    return out


def prune_older_than(directory: Path, max_age_hours: float, *, now: float | None = None) -> int:
    """Delete the files and folders in ``directory`` last modified over ``max_age_hours`` ago.

    ``max_age_hours <= 0`` keeps everything. An entry that cannot be removed
    (in use, no permission) is skipped and retried on the next pass. Returns
    the number of entries removed.
    """
    if max_age_hours <= 0:
        return 0
    limit = (time.time() if now is None else now) - max_age_hours * 3600
    try:
        entries = list(directory.iterdir())
    except OSError:
        return 0
    removed = 0
    for path in entries:
        try:
            if path.stat().st_mtime >= limit:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
        except OSError as exc:
            log.debug("retention: could not remove %s: %s", path.name, exc)
    return removed


def apply_retention(settings: Settings, *, now: float | None = None) -> dict[str, int]:
    """Enforce the retention settings on the data folder; returns removals per folder.

    - ``screenshots/``: ``screenshot.retention_hours``
    - ``proofs/``: ``screenshot.proof_retention_hours``
    - ``journals/``: ``journal.retention_hours`` (0 = only ``journal.max_sessions``)
    - ``schedule_logs/``: ``scheduler.log_retention_days``
    """
    data_dir = settings.data_dir
    plan = {
        "screenshots": (settings.screenshot_dir, settings.screenshot.retention_hours),
        "proofs": (data_dir / "proofs", settings.screenshot.proof_retention_hours),
        "journals": (settings.journals_dir, settings.journal.retention_hours),
        "schedule_logs": (data_dir / "schedule_logs", settings.scheduler.log_retention_days * 24),
    }
    return {name: prune_older_than(path, hours, now=now) for name, (path, hours) in plan.items()}
