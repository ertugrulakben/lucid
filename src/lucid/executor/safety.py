"""Guardrails: destructive action detection and the global kill switch."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass

import keyboard

from lucid.capture.a11y import focused_is_password
from lucid.config.settings import Settings
from lucid.llm.schemas import ActionBlock

log = logging.getLogger("lucid.executor.safety")


DESTRUCTIVE_TEXT_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdrop\s+table\b",
    r"\bformat\s+[a-z]:",
    r"\bdel\s+/[qsf]\b",
    r"\bDELETE\s+FROM\b",
]
DESTRUCTIVE_KEY_COMBOS = [
    {"ctrl", "shift", "delete"},
    {"ctrl", "alt", "delete"},
]


def _short_action_detail(action: ActionBlock) -> str:
    """Return a human-sized JSON summary of an action (for modal display)."""
    summary: dict = {"action": action.action}
    for key in ("text", "keys", "coordinate", "element_name", "window_title", "file_path"):
        value = action.params.get(key)
        if value is None:
            continue
        if isinstance(value, str) and len(value) > 80:
            summary[key] = value[:77] + "..."
        else:
            summary[key] = value
    try:
        return json.dumps(summary, ensure_ascii=False)
    except Exception:
        return str(summary)


@dataclass
class SafetyDecision:
    requires_confirm: bool
    reason: str = ""
    user_allowed: bool | None = None  # None = not asked; True/False = user answer


class SafetyGuard:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(self, action: ActionBlock) -> SafetyDecision:
        if not self.settings.safety.destructive_confirm:
            return SafetyDecision(False)

        text = action.params.get("text") or ""
        if isinstance(text, str) and text:
            for pattern in DESTRUCTIVE_TEXT_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    return SafetyDecision(True, f"destructive text pattern: {pattern}")

        keys = action.params.get("keys") or []
        if isinstance(keys, list) and keys:
            lower = {str(k).lower() for k in keys}
            for combo in DESTRUCTIVE_KEY_COMBOS:
                if combo.issubset(lower):
                    return SafetyDecision(True, f"destructive key combo: {combo}")

        if action.action == "type" and text and focused_is_password():
            return SafetyDecision(True, "typing into password field")

        return SafetyDecision(False)

    def ask_user(self, action: ActionBlock, reason: str) -> bool | None:
        """Prompt the user via the confirm modal (if available).

        Returns ``True`` if the user approves, ``False`` if they deny, or
        ``None`` if the broker is not installed (e.g. headless runs) — the
        caller should decide a default in that case.
        """
        try:
            from lucid.ui.confirm_modal import get_broker
        except Exception:
            return None
        broker = get_broker()
        if broker is None:
            return None
        detail = _short_action_detail(action)
        result = broker.ask(kind=action.action, reason=reason, detail=detail)
        return result.allowed


def install_kill_switch(combo: str, cancel: threading.Event) -> Callable[[], None] | None:
    try:
        handle = keyboard.add_hotkey(combo, cancel.set, suppress=False, trigger_on_release=False)
    except Exception as exc:
        log.warning("kill switch registration failed: %s", exc)
        return None

    def unregister() -> None:
        try:
            keyboard.remove_hotkey(handle)
        except (KeyError, ValueError):
            pass

    log.info("kill switch armed: %s", combo)
    return unregister
