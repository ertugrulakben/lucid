"""Keep typed text out of what Lucid writes to disk or shows on screen.

Lucid types on the user's behalf, password fields included. The step journal
(``data/journals``), ``logs/lucid.log``, the overlay's action log and Thoughts
panels, and the logs of scheduled runs describe every action, so they must not
repeat what was typed: they keep its length instead.

MCP tool arguments are free-form, so the ones whose name looks like a secret
(``password``, ``apiKey``, ``access_token``, ``auth`` ...) are masked the same
way, nested objects included.

``journal.record_text: true`` stores both verbatim in the journal for
debugging. The log file and the overlay always show the masked form.

The retention settings are enforced here as well (:func:`apply_retention`), at
app start and before every Execute run. Pruning removes only what Lucid named
itself and never follows links.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
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

#: MCP tools are registered as ``mcp_<server>_<tool>`` actions (lucid.mcp.bridge).
MCP_PREFIX = "mcp_"

#: Words that mark a parameter name as a secret. Whole words only, so ``keys``,
#: ``keyboard`` and ``passport`` stay readable.
SECRET_WORDS = frozenset(
    {
        "apikey",
        "auth",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "credentials",
        "key",
        "otp",
        "pass",
        "passwd",
        "password",
        "pin",
        "pwd",
        "secret",
        "token",
    }
)


def mask_text(text: str) -> str:
    """Placeholder that keeps the length of ``text`` but not its content."""
    return f"[redacted: {len(text)} chars]"


def is_secret_name(name: str) -> bool:
    """True when a parameter name (``api_key``, ``apiKey``, ``X-Api-Key``) names a secret."""
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
    return any(word in SECRET_WORDS for word in re.split(r"[^a-z0-9]+", snake) if word)


def _mask_secrets(name: str, value: Any) -> Any:
    if is_secret_name(name):
        return mask_text(value) if isinstance(value, str) else "[redacted]"
    if isinstance(value, Mapping):
        return {k: _mask_secrets(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_secrets("", v) if isinstance(v, Mapping) else v for v in value]
    return value


def redact_params(action_name: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """Copy of ``params`` with typed text and secret-named MCP arguments masked."""
    out = dict(params)
    if action_name in TEXT_ACTIONS and isinstance(out.get("text"), str):
        out["text"] = mask_text(out["text"])
    if action_name.startswith(MCP_PREFIX):
        out = {key: _mask_secrets(key, value) for key, value in out.items()}
    return out


#: The names Lucid gives what it writes in each folder it prunes, matched in
#: full and with ASCII digits only. Anything else in those folders is left
#: alone: ``data_dir`` is user-configurable and can share a folder with the
#: user's own files (``Pictures\Screenshots`` on Windows, where names are
#: case-insensitive).
LUCID_NAMES = {
    # capture.screenshot.save_image (epoch milliseconds), browser_screenshot
    "screenshots": re.compile(r"(?:[0-9]{13}|browser-[0-9]{8}-[0-9]{6})\.png"),
    # ExecuteMode._final_proof: <stamp>-<goal slug>.png
    "proofs": re.compile(r"[0-9]{8}-[0-9]{6}-.+\.png"),
    # StepJournal.open_session: <stamp>-<slug>[-n] folders; the slug is [a-z0-9_-]
    "journals": re.compile(r"[0-9]{8}-[0-9]{6}-[a-z0-9_-]+"),
    # scheduler daemon run logs: <stamp>-<task slug>.log; the slug may be empty
    "schedule_logs": re.compile(r"[0-9]{8}-[0-9]{6}-.*\.log"),
}


def is_link(info: os.stat_result) -> bool:
    """A symlink, or on Windows any reparse point (junctions included)."""
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse)


def prune_older_than(
    directory: Path,
    max_age_hours: float,
    *,
    names: re.Pattern[str],
    folders: bool = False,
    now: float | None = None,
) -> int:
    """Delete what Lucid wrote in ``directory`` more than ``max_age_hours`` ago.

    Only entries whose whole name matches ``names`` and whose type matches
    ``folders`` (folders for journals, files elsewhere) are candidates. Links
    are never followed or removed, and a ``directory`` that is itself a link is
    not entered. ``max_age_hours <= 0`` keeps everything. An entry that cannot
    be removed (in use, no permission) is retried on the next pass. Returns the
    number of entries removed.
    """
    if max_age_hours <= 0:
        return 0
    limit = (time.time() if now is None else now) - max_age_hours * 3600
    try:
        if is_link(directory.lstat()):
            return 0
        entries = list(directory.iterdir())
    except OSError:
        return 0
    removed = 0
    for path in entries:
        if not names.fullmatch(path.name):
            continue
        try:
            info = path.lstat()
            if is_link(info) or stat.S_ISDIR(info.st_mode) != folders:
                continue
            if info.st_mtime >= limit:
                continue
            if folders:
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
        "screenshots": (settings.screenshot_dir, settings.screenshot.retention_hours, False),
        "proofs": (data_dir / "proofs", settings.screenshot.proof_retention_hours, False),
        "journals": (settings.journals_dir, settings.journal.retention_hours, True),
        "schedule_logs": (
            data_dir / "schedule_logs",
            settings.scheduler.log_retention_days * 24,
            False,
        ),
    }
    return {
        name: prune_older_than(path, hours, names=LUCID_NAMES[name], folders=folders, now=now)
        for name, (path, hours, folders) in plan.items()
    }
