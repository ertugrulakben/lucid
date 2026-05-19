"""Click a UI element identified by its accessibility name (and optional role).

This is the semantic alternative to pixel-coordinate clicks. The UI
Automation tree of the foreground window is searched, the first match's
bounding rectangle centre is computed, and a click is dispatched there.
"""

from __future__ import annotations

from lucid.actions.registry import ActionContext, ActionError, register_action
from lucid.actions.schemas import ClickElementParams


@register_action(
    name="click_element",
    schema=ClickElementParams,
    summary="Activate a UI element by accessibility name (substring) plus optional role.",
)
def click_element(ctx: ActionContext, params: ClickElementParams) -> str:
    try:
        import uiautomation as auto  # type: ignore
    except ImportError as exc:
        raise ActionError("uiautomation is required for click_element") from exc

    needle = params.name.lower()
    role = params.role

    root = auto.GetForegroundControl() or auto.GetRootControl()
    if root is None:
        raise ActionError("no foreground control available")

    match = _find_match(root, needle, role)
    if match is None:
        raise ActionError(f"no element matching name~={params.name!r} role={role!r}")

    rect = match.BoundingRectangle
    if rect is None or rect.width() <= 0 or rect.height() <= 0:
        raise ActionError("matched element has no usable bounding rectangle")

    cx = rect.left + rect.width() // 2
    cy = rect.top + rect.height() // 2

    try:
        import pyautogui  # type: ignore
    except ImportError as exc:
        raise ActionError("pyautogui is required for click_element") from exc

    pyautogui.click(cx, cy)
    return f"clicked: {match.Name or '<unnamed>'} at ({cx},{cy})"


def _find_match(root, needle: str, role: str | None):
    stack = [root]
    while stack:
        node = stack.pop()
        try:
            name = (node.Name or "").lower()
        except Exception:  # noqa: BLE001 -- some nodes raise when Name is queried
            name = ""
        if needle in name:
            if role is None or _role_matches(node, role):
                return node
        try:
            for child in node.GetChildren():
                stack.append(child)
        except Exception:  # noqa: BLE001
            continue
    return None


def _role_matches(node, role: str) -> bool:
    role = role.lower()
    try:
        ctype = (getattr(node, "ControlTypeName", "") or "").lower()
    except Exception:  # noqa: BLE001
        ctype = ""
    return role in ctype
