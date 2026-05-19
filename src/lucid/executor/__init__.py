"""Mouse/keyboard executor and safety layer."""

from lucid.executor.actions import Actions
from lucid.executor.retry import RetryBudget, decorate_result, suggest_alternative
from lucid.executor.safety import SafetyDecision, SafetyGuard, install_kill_switch
from lucid.executor.verify import ScreenState, diff, snapshot

__all__ = [
    "Actions",
    "SafetyGuard",
    "SafetyDecision",
    "install_kill_switch",
    "RetryBudget",
    "decorate_result",
    "suggest_alternative",
    "ScreenState",
    "snapshot",
    "diff",
]
