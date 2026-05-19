"""Bring a window matching the given title substring to the foreground."""

from __future__ import annotations

from lucid.actions.registry import ActionContext, ActionError, register_action
from lucid.actions.schemas import FocusWindowParams


@register_action(
    name="focus_window",
    schema=FocusWindowParams,
    summary="Activate a top-level window whose title contains the given substring.",
)
def focus_window(ctx: ActionContext, params: FocusWindowParams) -> str:
    needle = params.title if params.case_sensitive else params.title.lower()

    try:
        import pygetwindow as gw  # type: ignore
    except ImportError as exc:
        raise ActionError("pygetwindow is required for focus_window") from exc

    candidates = []
    for win in gw.getAllWindows():
        title = win.title or ""
        haystack = title if params.case_sensitive else title.lower()
        if needle in haystack:
            candidates.append(win)
    if not candidates:
        raise ActionError(f"no window matching {params.title!r}")

    candidates.sort(key=lambda w: len(w.title or ""))
    target = candidates[0]
    try:
        target.activate()
    except Exception as exc:  # noqa: BLE001 -- pygetwindow surfaces several Win32 errors
        raise ActionError(f"could not activate window: {exc}") from exc
    return f"focused: {target.title!r}"
