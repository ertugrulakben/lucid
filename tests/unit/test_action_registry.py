"""Tests for the pluggable action registry."""

from __future__ import annotations

import pytest

from lucid.actions import ActionContext, ActionError, available, get, register_action, run
from lucid.actions.registry import _REGISTRY, reset_for_tests


@pytest.fixture(autouse=True)
def _isolated_registry() -> None:
    reset_for_tests()
    yield
    reset_for_tests()


def test_register_and_run_simple_action() -> None:
    @register_action(name="echo", source="builtin")
    def echo(_ctx: ActionContext, params: dict) -> str:
        return f"echo:{params['msg']}"

    result = run("echo", ActionContext(), {"msg": "hello"})
    assert result == "echo:hello"


def test_unknown_action_raises() -> None:
    with pytest.raises(ActionError):
        run("does-not-exist", ActionContext(), {})


def test_schema_validation_rejects_bad_input() -> None:
    from pydantic import BaseModel

    class S(BaseModel):
        n: int

    @register_action(name="add_one", schema=S, source="builtin")
    def add_one(_ctx: ActionContext, params: S) -> str:
        return str(params.n + 1)

    assert run("add_one", ActionContext(), {"n": 4}) == "5"
    with pytest.raises(ActionError):
        run("add_one", ActionContext(), {"n": "not a number"})


def test_higher_priority_source_overrides_builtin() -> None:
    @register_action(name="thing", source="builtin")
    def builtin(_ctx: ActionContext, _params=None) -> str:
        return "builtin"

    @register_action(name="thing", source="entry_point")
    def plugin(_ctx: ActionContext, _params=None) -> str:
        return "plugin"

    assert run("thing", ActionContext(), None) == "plugin"


def test_lower_priority_does_not_override() -> None:
    @register_action(name="thing", source="entry_point")
    def plugin(_ctx: ActionContext, _params=None) -> str:
        return "plugin"

    @register_action(name="thing", source="builtin")
    def builtin(_ctx: ActionContext, _params=None) -> str:
        return "builtin"

    assert run("thing", ActionContext(), None) == "plugin"


def test_available_returns_sorted_names() -> None:
    @register_action(name="z_action", source="builtin")
    def _z(_ctx, _p=None) -> str:
        return "z"

    @register_action(name="a_action", source="builtin")
    def _a(_ctx, _p=None) -> str:
        return "a"

    names = available()
    assert names.index("a_action") < names.index("z_action")


def test_get_returns_action_record() -> None:
    @register_action(name="meta", summary="example", source="builtin")
    def meta(_ctx, _p=None) -> str:
        return "ok"

    a = get("meta")
    assert a.name == "meta"
    assert a.summary == "example"
    assert a.source == "builtin"


def test_builtin_actions_are_discovered() -> None:
    """Importing the registry should auto-load lucid.actions.builtin."""
    reset_for_tests()
    names = available()
    for expected in ("focus_window", "click_element", "type_text", "wait", "file_dialog_paste"):
        assert expected in names, f"missing built-in action: {expected}"


def test_action_context_carries_extras() -> None:
    captured: dict[str, str] = {}

    @register_action(name="record", source="builtin")
    def record(ctx: ActionContext, _p=None) -> str:
        captured["value"] = ctx.extras.get("value", "")
        return "ok"

    run("record", ActionContext(extras={"value": "42"}), None)
    assert captured["value"] == "42"


def test_registry_state_is_isolated_between_tests() -> None:
    """Sanity: the autouse fixture must really clear state."""
    assert "thing" not in _REGISTRY
