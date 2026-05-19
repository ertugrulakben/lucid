"""Accessibility selector capture at the moment of each input event.

Given a click at (x, y), return the accessibility element under the cursor so
the recorded step prefers a semantic selector over raw coordinates.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

log = logging.getLogger("lucid.recorder.a11y")

try:
    if sys.platform == "win32":
        import uiautomation as auto
    else:
        auto = None  # type: ignore[assignment]
except ImportError:
    auto = None  # type: ignore[assignment]


def selector_at(x: int, y: int) -> dict[str, Any]:
    if auto is None:
        return {"fallback_coord": [x, y]}
    try:
        node = auto.ControlFromPoint(x, y)
        if node is None:
            return {"fallback_coord": [x, y]}
        name = (getattr(node, "Name", "") or "").strip()
        role = getattr(node, "ControlTypeName", "") or ""
        automation_id = getattr(node, "AutomationId", "") or ""
        class_name = getattr(node, "ClassName", "") or ""
        selector: dict[str, Any] = {"fallback_coord": [x, y]}
        if name:
            selector["a11y_name"] = name
        if role:
            selector["role"] = role
        if automation_id:
            selector["automation_id"] = automation_id
        if class_name:
            selector["class_name"] = class_name
        return selector
    except Exception as exc:
        log.debug("selector_at failed: %s", exc)
        return {"fallback_coord": [x, y]}
