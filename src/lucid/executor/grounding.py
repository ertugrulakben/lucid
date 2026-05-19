"""Verify a predicted pixel coordinate against the live accessibility tree.

Called before a click to warn when the LLM's coordinate appears to land on
nothing clickable, which often indicates a hallucinated position.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("lucid.executor.grounding")

try:
    if sys.platform == "win32":
        import uiautomation as auto
    else:
        auto = None  # type: ignore[assignment]
except ImportError:
    auto = None  # type: ignore[assignment]


def element_at(x: int, y: int) -> dict | None:
    if auto is None:
        return None
    try:
        node = auto.ControlFromPoint(x, y)
        if node is None:
            return None
        return {
            "name": getattr(node, "Name", "") or "",
            "role": getattr(node, "ControlTypeName", "") or "",
            "automation_id": getattr(node, "AutomationId", "") or "",
        }
    except Exception as exc:
        log.debug("element_at failed: %s", exc)
        return None


def is_click_safe(x: int, y: int) -> bool:
    el = element_at(x, y)
    if el is None:
        return True
    role = (el.get("role") or "").lower()
    return role not in {"window"}
