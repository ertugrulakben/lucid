"""Retry escalation ladder for Execute actions.

Claude will happily try to click the same dead pixel 20 times in a row. This
module short-circuits that: each ``(action_name, coord_or_selector)`` pair
gets a bounded attempt budget. When exhausted, we force Claude to take a
different route on the next turn by surfacing the exhaustion in the
``tool_result`` text it sees.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("lucid.executor.retry")


NEAR_DUP_PIXEL_RADIUS = 30  # coord fp-snap grid (pikseli yakınsa aynı sayılır)


def _action_fingerprint(action_name: str, params: dict[str, Any]) -> tuple:
    """Stable key for "I've tried this exact thing before".

    - Coordinates are snapped to a 30-pixel grid so that near-identical
      clicks ([1337,426] vs [1340,420]) collapse onto the same fingerprint.
      Without snapping, Claude's habit of emitting a "slightly different"
      pixel on failure bypasses the retry budget entirely.
    - Key combos are order-normalised: ['ctrl','shift','s'] and
      ['shift','ctrl','s'] now hit the same bucket, so 4 consecutive
      Win+Shift+S attempts actually trigger the retry guard.
    """
    coord = params.get("coordinate") or params.get("start_coordinate")
    coord_tuple: tuple[int, int] | None
    if isinstance(coord, (list, tuple)) and len(coord) == 2:
        coord_tuple = (
            int(coord[0]) // NEAR_DUP_PIXEL_RADIUS,
            int(coord[1]) // NEAR_DUP_PIXEL_RADIUS,
        )
    else:
        coord_tuple = None
    name = (params.get("element_name") or "").strip().lower()
    text = (params.get("text") or "")[:40]
    raw_keys = params.get("keys") or []
    keys = tuple(sorted(str(k).lower() for k in raw_keys)) if raw_keys else ()
    return (action_name, coord_tuple, name, text, keys)


LOOP_WINDOW = 4  # Look back this many actions
LOOP_UNIQUE_MIN = 2  # If fewer than this many unique fingerprints → loop


@dataclass
class RetryBudget:
    """Per-loop attempt accounting. One instance per Execute run."""

    max_attempts: int = 2
    attempts: dict[tuple, int] = field(default_factory=dict)
    last_action: tuple | None = None
    last_action_had_no_effect: bool = False
    recent: list[tuple] = field(default_factory=list)  # sliding window of fingerprints

    def reset(self) -> None:
        self.attempts.clear()
        self.last_action = None
        self.last_action_had_no_effect = False
        self.recent.clear()

    def register(self, action_name: str, params: dict[str, Any]) -> int:
        fp = _action_fingerprint(action_name, params)
        self.attempts[fp] = self.attempts.get(fp, 0) + 1
        self.last_action = fp
        self.recent.append(fp)
        if len(self.recent) > LOOP_WINDOW:
            self.recent.pop(0)
        return self.attempts[fp]

    def is_looping(self) -> bool:
        """True when the last N actions are collapsing to 1 fingerprint.

        Catches the 'Win+Shift+S four times in a row' pattern that retry
        thresholds alone miss when the action has no observable effect and
        the model keeps re-trying at the same fingerprint bucket.
        """
        if len(self.recent) < LOOP_WINDOW:
            return False
        return len({fp for fp in self.recent}) < LOOP_UNIQUE_MIN

    def attempts_for(self, action_name: str, params: dict[str, Any]) -> int:
        return self.attempts.get(_action_fingerprint(action_name, params), 0)

    def exhausted(self, action_name: str, params: dict[str, Any]) -> bool:
        return self.attempts_for(action_name, params) >= self.max_attempts

    def mark_no_effect(self) -> None:
        self.last_action_had_no_effect = True

    def mark_effective(self) -> None:
        self.last_action_had_no_effect = False


def suggest_alternative(action_name: str, params: dict[str, Any]) -> str:
    """Human-readable hint we append to the tool_result when retries exhaust.

    The goal is to nudge Claude toward a different strategy on the next turn:
    from coordinate click → accessibility click → keyboard shortcut.
    """
    if action_name in ("left_click", "double_click", "right_click", "triple_click"):
        if params.get("element_name"):
            return (
                "Click by element name failed repeatedly. Try a keyboard shortcut "
                "(Tab / Enter / access key) or, if the target has a visible "
                "label, use `click_element` with a shorter/differently spelt "
                "element_name."
            )
        return (
            "Clicking at this coordinate has failed multiple times. Switch "
            "strategy: use `click_element` with the visible label, or a "
            "keyboard shortcut (Tab, Enter, Alt+<underlined letter>)."
        )
    if action_name == "type":
        return (
            "Typing did not seem to change the focused field. Verify the "
            "target is focused first (Tab from a known anchor), or use "
            "`click_element` on the input and try again."
        )
    if action_name == "key":
        return (
            "This key combo did not produce a visible change. Try the action "
            "through a different path (menu item via click_element, or a "
            "different shortcut)."
        )
    return (
        "The last action produced no observable change. Plan a different "
        "approach instead of repeating it."
    )


def decorate_result(
    text: str, budget: RetryBudget, action_name: str, params: dict[str, Any]
) -> str:
    """Append an escalation hint to a stale-looking tool_result."""
    if budget.is_looping():
        return (
            text + "\n[retry-guard] LOOP DETECTED — the last "
            f"{len(budget.recent)} actions collapsed to the same bucket. "
            "STOP repeating. Pick a fundamentally different approach: try "
            "focus_window + click_element, a keyboard shortcut via the "
            "application's menu key, or ask the user via a short progress "
            "line if you're stuck."
        )
    if budget.exhausted(action_name, params):
        return (
            text + "\n[retry-guard] This exact action has been attempted "
            f"{budget.attempts_for(action_name, params)} times. "
            + suggest_alternative(action_name, params)
        )
    if budget.last_action_had_no_effect:
        return (
            text
            + "\n[retry-guard] No observable change. "
            + suggest_alternative(action_name, params)
        )
    return text
