"""Typed text stays out of the journal, the log line and the overlay panels."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from lucid.agent import execute_mode
from lucid.agent.execute_mode import _fmt_action_for_log, _fmt_plan
from lucid.config.settings import Settings
from lucid.executor.actions import _summarize_params
from lucid.journal import StepJournal
from lucid.llm.schemas import ActionBlock
from lucid.privacy import mask_text, redact_params

TYPED = "hunter2-Parola!"


@pytest.mark.parametrize("action", ["type", "type_text", "browser_fill"])
def test_redact_params_masks_typed_text(action: str) -> None:
    params = {"text": TYPED, "selector": "#password"}
    out = redact_params(action, params)
    assert out["text"] == f"[redacted: {len(TYPED)} chars]"
    assert out["selector"] == "#password"
    assert params["text"] == TYPED


def test_redact_params_keeps_key_combo_and_other_actions() -> None:
    assert redact_params("key", {"text": "ctrl+s"}) == {"text": "ctrl+s"}
    assert redact_params("left_click", {"coordinate": [1, 2]}) == {"coordinate": [1, 2]}


def test_journal_masks_typed_text_by_default(tmp_path: Path) -> None:
    journal = StepJournal.open_session(tmp_path, goal="login")
    journal.record(
        action_name="type",
        params={"text": TYPED},
        before_image=None,
        after_image=None,
        outcome="pasted 14 chars",
    )
    raw = (journal.session_dir / "index.jsonl").read_text(encoding="utf-8")
    assert TYPED not in raw
    assert json.loads(raw)["params"]["text"] == mask_text(TYPED)


def test_journal_stores_text_when_record_text_is_on(tmp_path: Path) -> None:
    journal = StepJournal.open_session(tmp_path, goal="debug", record_text=True)
    journal.record(
        action_name="type",
        params={"text": TYPED},
        before_image=None,
        after_image=None,
        outcome="pasted 14 chars",
    )
    raw = (journal.session_dir / "index.jsonl").read_text(encoding="utf-8")
    assert json.loads(raw)["params"]["text"] == TYPED


def test_record_text_is_off_by_default() -> None:
    assert Settings().journal.record_text is False


def test_log_line_masks_typed_text() -> None:
    assert TYPED not in str(_summarize_params("type", {"text": TYPED}))
    assert _summarize_params("key", {"text": "ctrl+s"}) == {"text": "ctrl+s"}
    assert _summarize_params("key", {"text": "x" * 50})["text"] == "x" * 40 + "…"


def test_overlay_panels_mask_typed_text() -> None:
    line = _fmt_action_for_log("type", {"text": TYPED}, "pasted 14 chars")
    assert TYPED not in line
    assert "redacted" in line
    plan = _fmt_plan(ActionBlock(id="t1", action="type", params={"text": TYPED}))
    assert TYPED not in plan
    assert "redacted" in plan


def test_browser_fill_outcome_reports_length_only(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("playwright")
    from lucid.actions.browser import ops

    filled: list[str] = []
    locator = SimpleNamespace(first=SimpleNamespace(fill=filled.append))
    page = SimpleNamespace(locator=lambda selector: locator)
    monkeypatch.setattr(ops, "_runtime", lambda ctx: SimpleNamespace(page=lambda: page))
    out = ops.browser_fill(None, ops.BrowserFillParams(selector="#pw", text=TYPED))
    assert filled == [TYPED]
    assert TYPED not in out
    assert f"({len(TYPED)} chars)" in out


def _proof_owner(data_dir: Path, persist: bool) -> SimpleNamespace:
    settings = Settings(data_dir=data_dir)
    settings.screenshot.persist = persist
    return SimpleNamespace(settings=settings, _current_goal="open notepad", store=None)


def test_final_proof_not_taken_when_persist_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_capture(_settings: Settings) -> None:
        raise AssertionError("screen captured although screenshot.persist is off")

    monkeypatch.setattr(execute_mode.ContextSnapshot, "capture", staticmethod(no_capture))
    owner = _proof_owner(tmp_path, persist=False)
    assert list(execute_mode.ExecuteMode._final_proof(owner, None)) == []
    assert not (tmp_path / "proofs").exists()


def test_final_proof_saved_when_persist_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = SimpleNamespace(image=Image.new("RGB", (32, 16)))
    monkeypatch.setattr(execute_mode.ContextSnapshot, "capture", staticmethod(lambda _s: final))
    owner = _proof_owner(tmp_path, persist=True)
    out = "".join(execute_mode.ExecuteMode._final_proof(owner, None))
    assert "final screenshot saved" in out
    assert len(list((tmp_path / "proofs").glob("*.png"))) == 1
