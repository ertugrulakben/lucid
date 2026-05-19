"""Yield the executor for a fixed number of milliseconds."""

from __future__ import annotations

import time

from lucid.actions.registry import ActionContext, register_action
from lucid.actions.schemas import WaitParams


@register_action(
    name="wait",
    schema=WaitParams,
    summary="Sleep for a bounded duration in milliseconds.",
)
def wait(ctx: ActionContext, params: WaitParams) -> str:
    time.sleep(params.duration_ms / 1000.0)
    return f"waited {params.duration_ms}ms"
