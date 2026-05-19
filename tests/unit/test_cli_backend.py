from __future__ import annotations

from lucid.backend.cli_backend import CLIBackend
from lucid.llm.provider import Message
from lucid.llm.schemas import StreamEvent


def test_parse_line_extracts_text_delta() -> None:
    raw = '{"type":"assistant","message":{"content":[{"type":"text","text":"Merhaba"}]}}'
    event = CLIBackend._parse_line(raw)
    assert isinstance(event, StreamEvent)
    assert event.kind == "text_delta"
    assert event.text == "Merhaba"


def test_parse_line_recognises_result_as_done() -> None:
    raw = '{"type":"result","subtype":"end_turn","total_cost_usd":0}'
    event = CLIBackend._parse_line(raw)
    assert event is not None and event.kind == "done"


def test_parse_line_maps_error() -> None:
    raw = '{"type":"error","message":"boom"}'
    event = CLIBackend._parse_line(raw)
    assert event is not None and event.kind == "error"
    assert "boom" in (event.error or "")


def test_parse_line_ignores_non_json() -> None:
    assert CLIBackend._parse_line("not json") is None


def test_flatten_collapses_text_messages() -> None:
    messages = [
        Message(role="user", content=[{"type": "text", "text": "hi"}]),
        Message(role="assistant", content=[{"type": "text", "text": "hello"}]),
    ]
    out = CLIBackend._flatten_messages(messages, system="SYS")
    assert "<SYSTEM>" in out.upper() or "SYS" in out
    assert "hi" in out and "hello" in out
