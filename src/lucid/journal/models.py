"""Row shapes that the Step Journal persists to disk."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StepRecord(BaseModel):
    """One executed step inside an Execute session.

    Designed to round-trip through ``index.jsonl`` losslessly: every field is
    JSON-serialisable, no Path or PIL objects leak in. The two ``*_thumb``
    fields are filenames relative to the session directory so the journal
    folder remains portable.
    """

    id: int = Field(ge=1)
    ts: float = Field(description="Unix timestamp when the action completed.")
    action_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    outcome: str = ""
    before_thumb: str | None = None
    after_thumb: str | None = None
    monitor_index: int = 0
    coord: tuple[int, int] | None = None

    def outcome_one_line(self, max_chars: int = 120) -> str:
        first = (self.outcome or "").strip().splitlines()[:1]
        text = first[0] if first else ""
        if len(text) > max_chars:
            text = text[: max_chars - 1] + "…"
        return text

    def short_params(self, max_chars: int = 80) -> str:
        """Compact human-readable params summary used in gallery cells."""
        if not self.params:
            return ""
        bits: list[str] = []
        for key in ("element_name", "window_title", "file_path", "keys", "text", "command", "url"):
            value = self.params.get(key)
            if value in (None, "", [], {}):
                continue
            if key == "keys" and isinstance(value, list):
                bits.append("+".join(str(k) for k in value))
            elif key == "text":
                snippet = str(value).replace("\n", " ")
                if len(snippet) > 30:
                    snippet = snippet[:29] + "…"
                bits.append(f"text={snippet!r}")
            else:
                bits.append(f"{key}={value!r}" if key != "element_name" else f"{value!r}")
        if not bits and self.coord:
            bits.append(f"@({self.coord[0]},{self.coord[1]})")
        joined = " ".join(bits)
        if len(joined) > max_chars:
            joined = joined[: max_chars - 1] + "…"
        return joined
