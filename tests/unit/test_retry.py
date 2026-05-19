from __future__ import annotations

from lucid.executor.retry import (
    RetryBudget,
    decorate_result,
    suggest_alternative,
)


def test_budget_tracks_attempts_per_action() -> None:
    budget = RetryBudget(max_attempts=2)
    params = {"coordinate": [100, 200]}
    assert budget.attempts_for("left_click", params) == 0
    budget.register("left_click", params)
    assert budget.attempts_for("left_click", params) == 1
    budget.register("left_click", params)
    assert budget.exhausted("left_click", params) is True


def test_different_actions_share_no_state() -> None:
    budget = RetryBudget(max_attempts=2)
    budget.register("left_click", {"coordinate": [10, 10]})
    budget.register("left_click", {"coordinate": [10, 10]})
    assert budget.exhausted("left_click", {"coordinate": [10, 10]}) is True
    assert budget.exhausted("key", {"keys": ["ctrl", "a"]}) is False


def test_decorate_result_adds_retry_guard_when_exhausted() -> None:
    budget = RetryBudget(max_attempts=2)
    params = {"coordinate": [50, 60]}
    budget.register("left_click", params)
    budget.register("left_click", params)
    out = decorate_result("left clicked", budget, "left_click", params)
    assert "[retry-guard]" in out


def test_decorate_result_notes_no_effect() -> None:
    budget = RetryBudget(max_attempts=5)
    params = {"coordinate": [0, 0]}
    budget.register("left_click", params)
    budget.mark_no_effect()
    out = decorate_result("left clicked", budget, "left_click", params)
    assert "No observable change" in out or "[retry-guard]" in out


def test_suggest_alternative_points_to_keyboard() -> None:
    hint = suggest_alternative("left_click", {"coordinate": [10, 10]})
    assert "keyboard" in hint.lower() or "click_element" in hint.lower()
