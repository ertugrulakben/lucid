"""Provider-neutral message and response types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TextBlock:
    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ComputerUseBlock:
    """A tool-use block describing a desktop action the LLM wants to take."""

    action: str
    id: str = ""
    coordinate: tuple[int, int] | None = None
    text: str | None = None
    keys: list[str] | None = None
    duration_ms: int | None = None
    scroll_direction: str | None = None
    scroll_amount: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    type: Literal["computer_use"] = "computer_use"


ResponseBlock = TextBlock | ComputerUseBlock


@dataclass
class ActionBlock:
    """Simplified representation used outside the LLM layer."""

    id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_tool_use(cls, block: ComputerUseBlock) -> ActionBlock:
        params: dict[str, Any] = dict(block.raw.get("input", {}))
        if block.coordinate and "coordinate" not in params:
            params["coordinate"] = list(block.coordinate)
        if block.text and "text" not in params:
            params["text"] = block.text
        return cls(id=block.id or "", action=block.action, params=params)


@dataclass
class StreamEvent:
    kind: Literal["text_delta", "tool_use", "done", "error"]
    text: str = ""
    tool_use: ComputerUseBlock | None = None
    stop_reason: str | None = None
    error: str | None = None
