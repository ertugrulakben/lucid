"""End-to-end ExecuteMode stream test for the v0.6 features.

Exercises a single tool_use turn through the real loop with a fake provider
and confirms that the three new stream prefixes (`[step]`, `[thought]`,
`[halo]`) all fire, AND that the on-disk Step Journal has the expected
thumbnails + JSONL row.

This is the synthetic counterpart of the canvas E2E checks for Step Gallery,
ThoughtChain, and Cursor Halo.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PIL import Image

from lucid.agent.execute_mode import ExecuteMode
from lucid.llm.provider import LLMProvider
from lucid.llm.schemas import ComputerUseBlock, StreamEvent


class _ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self) -> None:
        self.turns = 0

    def stream(self, messages, *, system=None, tools=None, max_tokens=2048,
               model=None, cache_system=False, cache_tools=False) -> Iterator[StreamEvent]:
        self.turns += 1
        if self.turns == 1:
            # Narrate, then emit a single click action so the loop has work to do.
            yield StreamEvent(kind="text_delta", text="I'll click the Send button.")
            yield StreamEvent(
                kind="tool_use",
                tool_use=ComputerUseBlock(
                    id="t1",
                    action="left_click",
                    coordinate=(120, 80),
                    raw={"input": {"action": "left_click", "coordinate": [120, 80]}},
                ),
            )
            yield StreamEvent(kind="done", stop_reason="tool_use")
        else:
            # Second turn: signal completion so the loop exits.
            yield StreamEvent(kind="done", stop_reason="end_turn")

    def image_block(self, img) -> dict[str, Any]:
        return {"type": "image", "w": img.width, "h": img.height}

    def text_block(self, text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    def tool_result_block(self, tool_use_id, content, is_error=False) -> dict[str, Any]:
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content,
                "is_error": is_error}


class _FakeActive:
    title = "Notepad"
    process = "notepad.exe"

    def matches_blacklist(self, *_args, **_kwargs) -> bool:
        return False


class _FakeSnapshot:
    def __init__(self) -> None:
        self.image = Image.new("RGB", (320, 240), (40, 40, 60))
        self.image_path: Path | None = None
        self.monitor_index = 1
        self.active = _FakeActive()
        self.monitor_bounds: tuple[int, int, int, int] | None = (0, 0, 320, 240)
        self.windows: list = []
        self.a11y_tree: dict | None = None

    def to_prompt_context(self) -> str:
        return "Active window: Notepad (notepad.exe)"

    def image_to_screen(self, x: int, y: int) -> tuple[int, int]:
        return (x, y)


def _run_one_step(tmp_path: Path, monkeypatch) -> tuple[list[str], Path]:
    monkeypatch.setenv("LUCID_DATA_DIR", str(tmp_path))
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    settings = settings_mod.get_settings()
    settings.memory.enabled = False
    settings.safety.pause_seconds = 0.0
    settings.executor.max_steps = 3

    provider = _ScriptedProvider()
    execute = ExecuteMode(settings, provider)

    # We don't want pyautogui to actually click during the test -- intercept the
    # action dispatch at the Actions level.
    with patch("lucid.executor.actions.Actions.run", return_value="clicked (simulated)"):
        with patch.object(ExecuteMode, "_final_proof", return_value=iter(())):
            chunks = list(
                execute.run("Click the Send button.", _FakeSnapshot(), threading.Event())
            )
    journals = list((tmp_path / "journals").iterdir())
    assert journals, "no journal session created"
    return chunks, journals[0]


def test_stream_emits_thought_step_and_halo(tmp_path: Path, monkeypatch) -> None:
    chunks, session_dir = _run_one_step(tmp_path, monkeypatch)
    blob = "".join(chunks)
    assert "[thought]" in blob, blob
    assert "[step]" in blob, blob
    assert "[halo] left_click|120,80" in blob, blob
    assert "🛠 plan" in blob


def test_journal_jsonl_and_webp_written(tmp_path: Path, monkeypatch) -> None:
    _chunks, session_dir = _run_one_step(tmp_path, monkeypatch)
    index = session_dir / "index.jsonl"
    assert index.exists()
    rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["action_name"] == "left_click"
    assert row["coord"] == [120, 80]
    # monitor_index reflects whichever display the live post-action capture
    # landed on; we only require it be a non-negative int.
    assert isinstance(row["monitor_index"], int)
    assert row["monitor_index"] >= 0
    assert (session_dir / row["before_thumb"]).exists()
    assert (session_dir / row["after_thumb"]).exists()


def test_browser_addendum_included_when_enabled(tmp_path: Path, monkeypatch) -> None:
    """When settings.browser.enabled is True, the system prompt grows by the
    web automation block."""
    monkeypatch.setenv("LUCID_DATA_DIR", str(tmp_path))
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    settings = settings_mod.get_settings()
    settings.memory.enabled = False
    settings.browser.enabled = True
    provider = _ScriptedProvider()
    execute = ExecuteMode(settings, provider)
    prompt = execute._system_prompt()
    assert "browser_launch" in prompt
    assert "WEB OTOMASYON" in prompt
