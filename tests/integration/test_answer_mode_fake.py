"""Integration-ish: exercise AnswerMode with a fake LLM provider."""

from __future__ import annotations

import threading
from collections.abc import Iterator

from PIL import Image

from lucid.agent.answer_mode import AnswerMode
from lucid.agent.conversation import Conversation
from lucid.llm.provider import LLMProvider
from lucid.llm.schemas import StreamEvent


class FakeProvider(LLMProvider):
    name = "fake"

    def stream(
        self, messages, *, system=None, tools=None, max_tokens=2048, model=None
    ) -> Iterator[StreamEvent]:
        yield StreamEvent(kind="text_delta", text="42")
        yield StreamEvent(kind="done", stop_reason="end_turn")

    def image_block(self, img):
        return {"type": "image"}

    def text_block(self, text):
        return {"type": "text", "text": text}

    def tool_result_block(self, tool_use_id, content, is_error=False):
        return {"type": "tool_result"}


def test_answer_mode_streams_text() -> None:
    provider = FakeProvider()
    mode = AnswerMode(provider)
    conv = Conversation()
    conv.append_user("What is the meaning of life?", image=Image.new("RGB", (32, 32)))
    chunks = list(mode.run(conv, threading.Event()))
    assert "".join(chunks) == "42"


def test_answer_mode_is_multi_turn() -> None:
    provider = FakeProvider()
    mode = AnswerMode(provider)
    conv = Conversation()
    conv.append_user("Q1", image=Image.new("RGB", (32, 32)))
    conv.append_assistant("A1")
    conv.append_user("Q2 follow-up")
    list(mode.run(conv, threading.Event()))
    assert len(conv.turns) == 3
