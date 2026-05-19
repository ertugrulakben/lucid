from __future__ import annotations

from lucid.executor.safety import SafetyGuard
from lucid.llm.schemas import ActionBlock


def test_destructive_text_detected(tmp_settings) -> None:
    guard = SafetyGuard(tmp_settings)
    action = ActionBlock(id="1", action="type", params={"text": "rm -rf /"})
    decision = guard.evaluate(action)
    assert decision.requires_confirm is True
    assert "rm" in decision.reason.lower()


def test_benign_text_allowed(tmp_settings) -> None:
    guard = SafetyGuard(tmp_settings)
    action = ActionBlock(id="1", action="type", params={"text": "Hello world"})
    decision = guard.evaluate(action)
    assert decision.requires_confirm is False


def test_disabled_confirm_lets_destructive_through(tmp_settings) -> None:
    tmp_settings.safety.destructive_confirm = False
    guard = SafetyGuard(tmp_settings)
    action = ActionBlock(id="1", action="type", params={"text": "DROP TABLE users"})
    decision = guard.evaluate(action)
    assert decision.requires_confirm is False


def test_destructive_key_combo_detected(tmp_settings) -> None:
    guard = SafetyGuard(tmp_settings)
    action = ActionBlock(id="1", action="key", params={"keys": ["ctrl", "shift", "delete"]})
    decision = guard.evaluate(action)
    assert decision.requires_confirm is True
