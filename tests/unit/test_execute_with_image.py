"""ExecuteMode attachment path — ensures reference images ride along in the first user turn."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PIL import Image

from lucid.agent.execute_mode import ExecuteMode
from lucid.llm.provider import LLMProvider
from lucid.llm.schemas import StreamEvent


class _CapturingProvider(LLMProvider):
    name = "capture"

    def __init__(self) -> None:
        self.streams: list[list] = []

    def stream(
        self,
        messages,
        *,
        system=None,
        tools=None,
        max_tokens=2048,
        model=None,
        cache_system=False,
        cache_tools=False,
    ) -> Iterator[StreamEvent]:
        # Deep-copy the message content so later mutations in the caller
        # don't affect what this test captured.
        self.streams.append([list(m.content) for m in messages])
        # No tool_use → Execute loop exits cleanly after one turn.
        yield StreamEvent(kind="text_delta", text="ok")
        yield StreamEvent(kind="done", stop_reason="end_turn")

    def image_block(self, img) -> dict[str, Any]:
        return {"type": "image", "w": img.width, "h": img.height}

    def text_block(self, text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    def tool_result_block(self, tool_use_id, content, is_error=False):
        return {"type": "tool_result"}


class _FakeActive:
    title = "Chrome"
    process = "chrome.exe"

    def matches_blacklist(self, *_args, **_kwargs) -> bool:
        return False


class _FakeSnapshot:
    def __init__(self) -> None:
        self.image = Image.new("RGB", (32, 24), (20, 20, 30))
        self.image_path: Path | None = None
        self.monitor_index = 0
        self.active = _FakeActive()
        self.monitor_bounds: tuple[int, int, int, int] | None = (0, 0, 32, 24)
        self.windows: list = []
        self.a11y_tree: dict | None = None

    def to_prompt_context(self) -> str:
        return "Active window: Chrome (chrome.exe)"

    def image_to_screen(self, x: int, y: int) -> tuple[int, int]:
        return (x, y)


def _captured_first_user_content(provider: _CapturingProvider) -> list:
    assert provider.streams, "provider never reached stream()"
    first_messages = provider.streams[0]
    # First message is always the initial user turn in a fresh Execute loop.
    return first_messages[0]


def test_attachments_land_after_live_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LUCID_DATA_DIR", str(tmp_path))
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    settings = settings_mod.get_settings()
    settings.memory.enabled = False

    ref_a = Image.new("RGB", (40, 50), (255, 0, 0))
    ref_b = Image.new("RGB", (60, 70), (0, 255, 0))

    provider = _CapturingProvider()
    execute = ExecuteMode(settings, provider)
    snapshot = _FakeSnapshot()

    # Skip the final proof capture (touches real screen / mss).
    with patch.object(ExecuteMode, "_final_proof", return_value=iter(())):
        list(
            execute.run(
                "Match this reference.", snapshot, threading.Event(), attachments=[ref_a, ref_b]
            )
        )

    content = _captured_first_user_content(provider)
    # Structure: [live snapshot image, ref_a, ref_b, text block].
    image_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
    text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
    assert len(image_blocks) == 3
    assert (image_blocks[0]["w"], image_blocks[0]["h"]) == (32, 24)  # live desktop first
    assert (image_blocks[1]["w"], image_blocks[1]["h"]) == (40, 50)  # ref_a second
    assert (image_blocks[2]["w"], image_blocks[2]["h"]) == (60, 70)  # ref_b third
    assert text_blocks, "text block missing"
    assert "2 reference image(s)" in text_blocks[0]["text"]


def test_attachments_omitted_when_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LUCID_DATA_DIR", str(tmp_path))
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    settings = settings_mod.get_settings()
    settings.memory.enabled = False

    provider = _CapturingProvider()
    execute = ExecuteMode(settings, provider)

    with patch.object(ExecuteMode, "_final_proof", return_value=iter(())):
        list(execute.run("Plain task.", _FakeSnapshot(), threading.Event()))

    content = _captured_first_user_content(provider)
    image_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
    text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
    assert len(image_blocks) == 1
    assert "reference image" not in text_blocks[0]["text"].lower()
