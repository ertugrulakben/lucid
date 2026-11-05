"""Disk store for Step Journal sessions.

One session = one Execute run. Layout::

    data/journals/
    └── 20260526-143012-open_notepad/
        ├── index.jsonl
        ├── step-001-before.webp
        ├── step-001-after.webp
        ├── step-002-before.webp
        └── ...

``index.jsonl`` is append-only, one JSON object per line. The store keeps
``settings.journal.max_sessions`` directories on disk, deleting the oldest
sessions atomically when the cap is exceeded. Only folders named by
:meth:`StepJournal.open_session` count as sessions; anything else in
``journals/`` is neither listed nor deleted, and links are never followed.

Typed text (``type``, ``type_text``, ``browser_fill``) is stored masked, length
only, unless ``settings.journal.record_text`` is on: it can be a password.
"""

from __future__ import annotations

import json
import logging
import re
import stat
import threading
import time
from pathlib import Path
from typing import Any, Iterator

from PIL import Image

from lucid import privacy
from lucid.privacy import LUCID_NAMES, is_link, redact_params

from .models import StepRecord

log = logging.getLogger("lucid.journal")

_SAFE_SLUG_RE = re.compile(r"[^A-Za-z0-9_\-]+")


class StepJournal:
    """Append-only writer for one Execute session.

    Construct one instance per run via :meth:`open_session`. The journal
    creates its directory eagerly so the gallery has something to scroll
    even when the first action hasn't finished yet.
    """

    def __init__(
        self,
        session_dir: Path,
        thumb_width: int = 480,
        webp_quality: int = 70,
        record_text: bool = False,
    ) -> None:
        self.session_dir = session_dir
        self.thumb_width = max(120, int(thumb_width))
        self.webp_quality = max(10, min(100, int(webp_quality)))
        self.record_text = bool(record_text)
        self._lock = threading.Lock()
        self._step_id = 0
        self._index_path = session_dir / "index.jsonl"
        session_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def open_session(
        cls,
        journals_dir: Path,
        goal: str,
        *,
        thumb_width: int = 480,
        webp_quality: int = 70,
        max_sessions: int = 30,
        record_text: bool = False,
    ) -> "StepJournal":
        """Create a fresh session folder under ``journals_dir`` and prune old ones."""
        journals_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        slug = _slugify(goal)
        session_dir = journals_dir / f"{stamp}-{slug}"
        # If two sessions land in the same second (unlikely but possible in tests)
        # disambiguate by suffix so we never overwrite history.
        suffix = 1
        while session_dir.exists():
            suffix += 1
            session_dir = journals_dir / f"{stamp}-{slug}-{suffix}"
        journal = cls(
            session_dir,
            thumb_width=thumb_width,
            webp_quality=webp_quality,
            record_text=record_text,
        )
        try:
            prune_old_sessions(journals_dir, keep=max_sessions)
        except Exception as exc:
            log.debug("journal prune failed: %s", exc)
        return journal

    @property
    def last_step_id(self) -> int:
        return self._step_id

    def record(
        self,
        *,
        action_name: str,
        params: dict[str, Any] | None,
        before_image: Image.Image | None,
        after_image: Image.Image | None,
        outcome: str,
        monitor_index: int = 0,
    ) -> StepRecord:
        """Persist one step. Thread-safe: serialised by an internal lock."""
        with self._lock:
            self._step_id += 1
            step_id = self._step_id
            before_name = (
                self._save_thumb(before_image, f"step-{step_id:03d}-before.webp")
                if before_image is not None
                else None
            )
            after_name = (
                self._save_thumb(after_image, f"step-{step_id:03d}-after.webp")
                if after_image is not None
                else None
            )
            stored = params or {}
            if not self.record_text:
                stored = redact_params(action_name, stored)
            record = StepRecord(
                id=step_id,
                ts=time.time(),
                action_name=action_name,
                params=_jsonable_params(stored),
                outcome=outcome or "",
                before_thumb=before_name,
                after_thumb=after_name,
                monitor_index=int(monitor_index),
                coord=_pick_coord(params or {}),
            )
            line = record.model_dump_json()
            with self._index_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            return record

    def _save_thumb(self, image: Image.Image, filename: str) -> str | None:
        try:
            target = self.session_dir / filename
            scaled = image.copy()
            if scaled.width > self.thumb_width:
                ratio = self.thumb_width / float(scaled.width)
                new_h = max(1, int(scaled.height * ratio))
                scaled = scaled.resize((self.thumb_width, new_h), Image.Resampling.LANCZOS)
            if scaled.mode not in ("RGB", "RGBA"):
                scaled = scaled.convert("RGB")
            scaled.save(target, format="WEBP", quality=self.webp_quality, method=4)
            return filename
        except Exception as exc:
            log.warning("step thumbnail save failed (%s): %s", filename, exc)
            return None


def _session_dirs(journals_dir: Path) -> list[Path]:
    """Lucid's own session folders: named by ``open_session``, real folders, not links.

    ``journals/`` can sit in a folder the user also uses (``data_dir`` is
    configurable), so anything else there is left alone.
    """
    sessions = []
    for path in journals_dir.iterdir():
        if not LUCID_NAMES["journals"].fullmatch(path.name):
            continue
        try:
            info = path.lstat()
        except OSError:
            continue
        if stat.S_ISDIR(info.st_mode) and not is_link(info):
            sessions.append(path)
    return sessions


def iter_sessions(journals_dir: Path) -> Iterator[Path]:
    """Yield session directories newest-first (by directory name, which is stamped)."""
    if not journals_dir.exists():
        return
    entries = _session_dirs(journals_dir)
    entries.sort(key=lambda p: p.name, reverse=True)
    yield from entries


def read_session(session_dir: Path) -> list[StepRecord]:
    """Load every step record from ``index.jsonl`` in file order."""
    index = session_dir / "index.jsonl"
    if not index.exists():
        return []
    rows: list[StepRecord] = []
    with index.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
                rows.append(StepRecord.model_validate(payload))
            except (json.JSONDecodeError, ValueError) as exc:
                log.debug("skipping malformed journal row: %s", exc)
    return rows


def prune_old_sessions(journals_dir: Path, keep: int) -> int:
    """Delete oldest sessions until at most ``keep`` remain. Returns count removed.

    Only Lucid's own session folders count and are deleted (``_session_dirs``);
    a ``journals_dir`` that is itself a link is not entered.
    """
    if keep <= 0 or not journals_dir.exists():
        return 0
    try:
        if is_link(journals_dir.lstat()):
            return 0
    except OSError:
        return 0
    sessions = sorted(_session_dirs(journals_dir), key=lambda p: p.name)
    excess = len(sessions) - keep
    if excess <= 0:
        return 0
    removed = 0
    for path in sessions[:excess]:
        try:
            privacy.remove_entry(path, True)
            removed += 1
        except OSError as exc:
            log.debug("could not remove old session %s: %s", path, exc)
    return removed


def _slugify(goal: str) -> str:
    cleaned = _SAFE_SLUG_RE.sub("_", (goal or "session").strip())
    cleaned = cleaned.strip("_")
    return (cleaned[:40] or "session").lower()


def _jsonable_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy that JSON can serialise (drop binary blobs, tuples → lists)."""
    out: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, tuple):
            out[key] = list(value)
        elif isinstance(value, list):
            out[key] = [v if isinstance(v, (str, int, float, bool)) else str(v) for v in value]
        elif isinstance(value, dict):
            out[key] = {
                str(k): v for k, v in value.items() if isinstance(v, (str, int, float, bool))
            }
        else:
            out[key] = str(value)
    return out


def _pick_coord(params: dict[str, Any]) -> tuple[int, int] | None:
    """Pull a (x, y) tuple out of any coordinate-bearing param the action used."""
    for key in ("coordinate", "start_coordinate", "end_coordinate"):
        value = params.get(key)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                return (int(value[0]), int(value[1]))
            except (TypeError, ValueError):
                continue
    return None
