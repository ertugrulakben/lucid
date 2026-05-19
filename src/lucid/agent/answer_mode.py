"""Mode A: vision prompt returns a direct textual answer.

The mode is multi-turn: it consumes the full ``Conversation`` so follow-up
questions have prior context without the user repeating themselves.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator

from lucid.agent.conversation import Conversation
from lucid.llm.provider import LLMProvider

log = logging.getLogger("lucid.agent.answer")

SYSTEM_PROMPT = (
    "You are Lucid, a desktop AI assistant. The user has attached a screenshot of "
    "their current screen (only in the latest user turn to save tokens). Continue "
    "the conversation naturally: you may reference earlier turns. Answer directly "
    "and concisely; reference specific elements you see when relevant. Return "
    "formulas, commands, or snippets inside fenced code blocks. Do not restate "
    "the question. Do not apologize for being an AI."
)


class AnswerMode:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def run(
        self,
        conversation: Conversation,
        cancel: threading.Event,
    ) -> Iterator[str]:
        messages = conversation.to_messages(self.provider)
        if not messages:
            return

        for event in self.provider.stream(messages, system=SYSTEM_PROMPT, max_tokens=1024):
            if cancel.is_set():
                return
            if event.kind == "text_delta":
                yield event.text
            elif event.kind == "error":
                yield f"\n[error] {event.error}"
                return
            elif event.kind == "done":
                return
