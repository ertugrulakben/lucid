"""Optional UI Automation accessibility tree snapshot.

Used to enrich the LLM prompt with semantic UI structure, making selectors in
teach-mode workflows robust to UI pixel changes.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

log = logging.getLogger("lucid.capture.a11y")

try:
    if sys.platform == "win32":
        import uiautomation as auto
    else:
        auto = None  # type: ignore[assignment]
except ImportError:
    auto = None  # type: ignore[assignment]


MAX_DEPTH = 4
MAX_CHILDREN = 20


def capture_a11y_tree(hwnd: int | None = None) -> dict[str, Any] | None:
    if auto is None:
        return None
    try:
        if hwnd is not None:
            root = auto.ControlFromHandle(hwnd)
        else:
            root = auto.GetFocusedControl() or auto.GetRootControl()
        if root is None:
            return None
        return _walk(root, depth=0)
    except Exception as exc:
        log.debug("a11y tree capture failed: %s", exc)
        return None


def _walk(node: Any, depth: int) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": getattr(node, "Name", "") or "",
        "role": getattr(node, "ControlTypeName", "") or "",
        "automation_id": getattr(node, "AutomationId", "") or "",
        "class_name": getattr(node, "ClassName", "") or "",
    }
    try:
        rect = node.BoundingRectangle
        if rect:
            data["bounds"] = [rect.left, rect.top, rect.right, rect.bottom]
    except Exception:
        pass

    try:
        is_password = bool(getattr(node, "IsPassword", False))
        if is_password:
            data["is_password"] = True
    except Exception:
        pass

    if depth >= MAX_DEPTH:
        return data

    children = []
    try:
        raw_children = node.GetChildren()[:MAX_CHILDREN]
        for c in raw_children:
            children.append(_walk(c, depth + 1))
    except Exception:
        pass
    if children:
        data["children"] = children
    return data


def focused_is_password() -> bool:
    if auto is None:
        return False
    try:
        node = auto.GetFocusedControl()
        if node is None:
            return False
        return bool(getattr(node, "IsPassword", False))
    except Exception:
        return False
