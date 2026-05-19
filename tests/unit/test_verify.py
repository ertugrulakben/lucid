from __future__ import annotations

from lucid.executor.verify import ScreenState, diff


def test_identical_states_have_no_diff() -> None:
    a = ScreenState(foreground_hwnd=1, focused_name="A", focused_role="Button")
    b = ScreenState(foreground_hwnd=1, focused_name="A", focused_role="Button")
    assert diff(a, b) is None


def test_foreground_change_reported() -> None:
    a = ScreenState(foreground_hwnd=1, foreground_title="A")
    b = ScreenState(foreground_hwnd=2, foreground_title="B")
    msg = diff(a, b)
    assert msg is not None and "foreground" in msg


def test_focus_name_change_reported() -> None:
    a = ScreenState(focused_name="input_A", focused_role="Edit")
    b = ScreenState(focused_name="input_B", focused_role="Edit")
    assert "focus" in (diff(a, b) or "")


def test_value_length_change_reported() -> None:
    a = ScreenState(focused_value="hello")
    b = ScreenState(focused_value="hello world")
    assert "len" in (diff(a, b) or "")


def test_cursor_move_only_reported_when_something_else_identical() -> None:
    a = ScreenState(cursor_xy=(0, 0))
    b = ScreenState(cursor_xy=(10, 10))
    assert "cursor" in (diff(a, b) or "")
