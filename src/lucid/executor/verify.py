"""Focus and action verification helpers.

Two questions we want to answer in the Execute loop:

1. **Before** we send keystrokes anywhere — is the target window still the
   thing we expect? If the user clicked into another app while Claude was
   thinking, typing there would be noise (or dangerous).
2. **After** an action — did anything observable actually change? A click
   on dead space looks the same as a click on a button; without a diff
   signal Claude keeps retrying the same coordinate (we saw this in the
   Kaspersky test: 20+ clicks on the same (720, 341)).

All helpers are best-effort and fail soft on non-Windows or missing deps.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

log = logging.getLogger("lucid.executor.verify")


@dataclass
class ScreenState:
    """Small fingerprint of the current UI focus for before/after diffs."""

    foreground_hwnd: int = 0
    foreground_title: str = ""
    foreground_process: str = ""
    focused_name: str = ""
    focused_role: str = ""
    focused_value: str = ""
    cursor_xy: tuple[int, int] = (0, 0)

    def key(self) -> tuple:
        return (
            self.foreground_hwnd,
            self.focused_name,
            self.focused_role,
            self.focused_value[:120],
        )


def snapshot() -> ScreenState:
    """Capture a lightweight fingerprint of current foreground + focused element."""
    if sys.platform != "win32":
        return ScreenState()

    state = ScreenState()
    try:
        import win32api  # type: ignore[import-not-found]
        import win32gui  # type: ignore[import-not-found]
        import win32process  # type: ignore[import-not-found]

        try:
            state.cursor_xy = win32api.GetCursorPos()
        except Exception:
            pass
        hwnd = win32gui.GetForegroundWindow()
        state.foreground_hwnd = int(hwnd) if hwnd else 0
        if hwnd:
            state.foreground_title = win32gui.GetWindowText(hwnd) or ""
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                import psutil  # type: ignore[import-not-found]

                state.foreground_process = psutil.Process(pid).name()
            except Exception:
                pass
    except Exception as exc:
        log.debug("win32 snapshot failed: %s", exc)

    try:
        import uiautomation as auto  # type: ignore[import-not-found]

        node = auto.GetFocusedControl()
        if node is not None:
            state.focused_name = (getattr(node, "Name", "") or "").strip()[:200]
            state.focused_role = (getattr(node, "ControlTypeName", "") or "").strip()[:80]
            try:
                pattern = node.GetValuePattern()
                state.focused_value = (getattr(pattern, "Value", "") or "").strip()[:200]
            except Exception:
                state.focused_value = ""
    except Exception as exc:
        log.debug("a11y focus snapshot failed: %s", exc)

    return state


def require_foreground(expected_hwnd: int) -> bool:
    """Return True if the expected window is still in the foreground."""
    if not expected_hwnd or sys.platform != "win32":
        return True
    try:
        import win32gui  # type: ignore[import-not-found]

        return int(win32gui.GetForegroundWindow()) == int(expected_hwnd)
    except Exception:
        return True


def focused_is_password() -> bool:
    """Delegates to the capture-side implementation for a single source of truth."""
    try:
        from lucid.capture.a11y import focused_is_password as _impl

        return _impl()
    except Exception:
        return False


def diff(before: ScreenState, after: ScreenState) -> str | None:
    """Return a human-readable description of what changed, or None if identical.

    This is the signal that prevents same-coordinate retry loops: if
    ``diff() is None`` after an action that was supposed to do something,
    escalate (retry with another strategy) instead of repeating.
    """
    changes: list[str] = []
    if before.foreground_hwnd != after.foreground_hwnd:
        changes.append(
            f"foreground window changed: "
            f"{before.foreground_title!r} → {after.foreground_title!r}"
        )
    if before.focused_name != after.focused_name or before.focused_role != after.focused_role:
        changes.append(
            f"focus moved: "
            f"{before.focused_role} {before.focused_name!r} → "
            f"{after.focused_role} {after.focused_name!r}"
        )
    if before.focused_value != after.focused_value:
        changes.append(
            f"focused value changed: len {len(before.focused_value)} → "
            f"{len(after.focused_value)}"
        )
    if before.cursor_xy != after.cursor_xy:
        changes.append(f"cursor moved {before.cursor_xy} → {after.cursor_xy}")
    return "; ".join(changes) if changes else None
