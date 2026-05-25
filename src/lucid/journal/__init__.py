"""Step Journal: per-session before/after capture archive for Execute mode.

The journal is the disk layer behind the overlay's Step Gallery panel. Every
time the autonomous loop runs a tool, we drop two compact WebP thumbnails
(before / after) into ``data/journals/<session>/`` and append a one-line JSON
record to ``index.jsonl`` describing the action and its outcome.

Public API:
    StepJournal       -- per-session writer
    StepRecord        -- pydantic row shape
    iter_sessions     -- read-side helper, lists archived sessions newest-first
"""

from __future__ import annotations

from .models import StepRecord
from .store import StepJournal, iter_sessions

__all__ = [
    "StepJournal",
    "StepRecord",
    "iter_sessions",
]
