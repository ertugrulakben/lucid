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
from lucid.privacy import is_secret_name, mask_text, redact_params

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


@pytest.mark.parametrize(
    "name",
    ["password", "apiKey", "api_key", "X-Api-Key", "access_token", "clientSecret", "Authorization"],
)
def test_secret_names(name: str) -> None:
    assert is_secret_name(name)


@pytest.mark.parametrize("name", ["keys", "keyboard", "passport", "query", "to", "body"])
def test_ordinary_names(name: str) -> None:
    assert not is_secret_name(name)


def test_mcp_secret_arguments_are_masked_nested() -> None:
    params = {
        "to": "ea@example.com",
        "password": TYPED,
        "auth": {"user": "ea"},
        "config": {"apiKey": TYPED, "region": "eu"},
        "items": [{"token": TYPED}],
        "count": 3,
    }
    out = redact_params("mcp_mail_send", params)
    assert out["to"] == "ea@example.com"
    assert out["count"] == 3
    assert out["password"] == mask_text(TYPED)
    assert out["auth"] == "[redacted]"
    assert out["config"] == {"apiKey": mask_text(TYPED), "region": "eu"}
    assert out["items"] == [{"token": mask_text(TYPED)}]
    assert params["password"] == TYPED


def test_builtin_key_parameter_stays_readable() -> None:
    assert redact_params("browser_press", {"key": "Enter"}) == {"key": "Enter"}


def test_journal_masks_mcp_secrets_unless_record_text(tmp_path: Path) -> None:
    for record_text in (False, True):
        journal = StepJournal.open_session(tmp_path, goal="mail", record_text=record_text)
        journal.record(
            action_name="mcp_mail_login",
            params={"user": "ea", "password": TYPED},
            before_image=None,
            after_image=None,
            outcome="ok",
        )
        stored = json.loads((journal.session_dir / "index.jsonl").read_text(encoding="utf-8"))
        assert stored["params"]["user"] == "ea"
        assert (stored["params"]["password"] == TYPED) is record_text


def test_screenshot_defaults_keep_steps_off_disk_and_proofs_on() -> None:
    shot = Settings().screenshot
    assert shot.persist is False
    assert shot.save_proof is True
    assert shot.proof_retention_hours == 24


def _proof_owner(data_dir: Path, save_proof: bool) -> SimpleNamespace:
    settings = Settings(data_dir=data_dir)
    settings.screenshot.save_proof = save_proof
    return SimpleNamespace(settings=settings, _current_goal="open notepad", store=None)


def test_final_proof_not_taken_when_save_proof_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_capture(_settings: Settings) -> None:
        raise AssertionError("screen captured although screenshot.save_proof is off")

    monkeypatch.setattr(execute_mode.ContextSnapshot, "capture", staticmethod(no_capture))
    owner = _proof_owner(tmp_path, save_proof=False)
    assert list(execute_mode.ExecuteMode._final_proof(owner, None)) == []
    assert not (tmp_path / "proofs").exists()


def test_final_proof_saved_by_default_even_with_persist_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = SimpleNamespace(image=Image.new("RGB", (32, 16)))
    monkeypatch.setattr(execute_mode.ContextSnapshot, "capture", staticmethod(lambda _s: final))
    owner = _proof_owner(tmp_path, save_proof=True)
    assert owner.settings.screenshot.persist is False
    out = "".join(execute_mode.ExecuteMode._final_proof(owner, None))
    assert "final screenshot saved" in out
    assert len(list((tmp_path / "proofs").glob("*.png"))) == 1
