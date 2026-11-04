"""Keep typed text out of what Lucid writes to disk or shows on screen.

Lucid types on the user's behalf, password fields included. The step journal
(``data/journals``), ``logs/lucid.log``, the overlay's action log and Thoughts
panels, and the logs of scheduled runs describe every action, so they must not
repeat what was typed: they keep its length instead.

``journal.record_text: true`` stores typed text verbatim in the journal for
debugging. The log file and the overlay always show the masked form.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
