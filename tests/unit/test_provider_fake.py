from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from lucid.llm.provider import LLMProvider, Message
from lucid.llm.schemas import ComputerUseBlock, StreamEvent


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, events: list[StreamEvent]) -> None:
        self.events = events
        self.last_messages: list[Message] = []

    def stream(
        self, messages, *, system=None, tools=None, max_tokens=2048, model=None
    ) -> Iterator[StreamEvent]:
        self.last_messages = list(messages)
        yield from self.events

    def image_block(self, img) -> dict[str, Any]:
        return {"type": "image", "source": "fake"}

    def text_block(self, text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    def tool_result_block(self, tool_use_id, content, is_error=False) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": is_error,
        }


def test_fake_provider_yields_events() -> None:
    events = [
        StreamEvent(kind="text_delta", text="Hello "),
        StreamEvent(kind="text_delta", text="world"),
        StreamEvent(
            kind="tool_use",
            tool_use=ComputerUseBlock(
                id="t1", action="left_click", coordinate=(5, 5), raw={"input": {}}
            ),
        ),
        StreamEvent(kind="done", stop_reason="tool_use"),
    ]
    provider = FakeProvider(events)
    messages = [Message(role="user", content=[provider.text_block("hi")])]
    out = list(provider.stream(messages))
    assert out[0].text == "Hello "
    assert out[2].tool_use is not None
    assert out[3].kind == "done"
