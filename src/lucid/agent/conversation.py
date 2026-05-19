"""Persistent multi-turn conversation for Answer mode.

Survives overlay open/close so the user can ask follow-ups without re-typing
context. Only the latest user turn carries its screenshot; earlier turns keep
text only to save tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time

from PIL import Image


@dataclass
class Turn:
    role: str
    text: str = ""
    image: Image.Image | None = None
    at: float = field(default_factory=time)


class Conversation:
    def __init__(self, max_turns: int = 20) -> None:
        self.turns: list[Turn] = []
        self.max_turns = max_turns

    def append_user(self, text: str, image: Image.Image | None = None) -> None:
        self.turns.append(Turn(role="user", text=text, image=image))
        self._trim()

    def append_assistant(self, text: str) -> None:
        if not text:
            return
        self.turns.append(Turn(role="assistant", text=text))
        self._trim()

    def clear(self) -> None:
        self.turns.clear()

    def is_empty(self) -> bool:
        return not self.turns

    def transcript(self) -> str:
        lines = []
        for t in self.turns:
            prefix = "You" if t.role == "user" else "Lucid"
            lines.append(f"{prefix}: {t.text.strip()}")
        return "\n\n".join(lines)

    def to_messages(self, provider) -> list:
        """Build provider messages. Only the latest user turn carries the image."""
        from lucid.llm.provider import Message

        if not self.turns:
            return []

        last_user_idx = -1
        for i, t in enumerate(self.turns):
            if t.role == "user":
                last_user_idx = i

        msgs: list[Message] = []
        for i, t in enumerate(self.turns):
            content = []
            if t.role == "user" and i == last_user_idx and t.image is not None:
                content.append(provider.image_block(t.image))
            content.append(provider.text_block(t.text))
            msgs.append(Message(role=t.role, content=content))
        return msgs

    def _trim(self) -> None:
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]
