"""Semantic replay: re-plan each workflow step against the live screen.

Rather than replaying hard-coded coordinates, we feed the LLM the current
screenshot plus the step's ``intent`` + ``selector`` and let it emit a
single computer_use action. This is resilient to UI drift (new button
positions, themes, window sizes) as long as the intent remains
recognisable.

Variable substitution (v1.1): recorded ``text`` fields may contain
``{{placeholder}}`` tokens that were captured when the workflow was
taught. At replay time callers pass a ``variables`` dict (e.g.
``{customer: "Acme Inc."}``) and we substitute before executing.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Iterator
from typing import Any

from lucid.capture import ContextSnapshot
from lucid.config.settings import Settings
from lucid.executor import Actions
from lucid.llm.anthropic_client import build_computer_tool
from lucid.llm.provider import LLMProvider, Message
from lucid.llm.schemas import ActionBlock
from lucid.recorder.workflow import Workflow

log = logging.getLogger("lucid.replayer")

SYSTEM_PROMPT = (
    "You are replaying a recorded workflow. For each step, you receive its "
    "`intent`, the saved `selector`, a live screenshot, and any variables "
    "that have been substituted. Produce exactly one computer_use action "
    "that fulfils the intent on the current screen. Prefer semantic "
    "selectors (accessibility name, role) over raw coordinates. Never skip "
    "destructive confirmations."
)


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def apply_variables(value: Any, variables: dict[str, str]) -> Any:
    """Recursively substitute ``{{name}}`` placeholders inside ``value``."""
    if isinstance(value, str):
        return _PLACEHOLDER_RE.sub(lambda m: str(variables.get(m.group(1), m.group(0))), value)
    if isinstance(value, list):
        return [apply_variables(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: apply_variables(v, variables) for k, v in value.items()}
    return value


class SemanticReplayer:
    def __init__(self, settings: Settings, provider: LLMProvider) -> None:
        self.settings = settings
        self.provider = provider
        self.actions = Actions(settings)

    def run(
        self,
        workflow: Workflow,
        cancel: threading.Event,
        variables: dict[str, str] | None = None,
    ) -> Iterator[str]:
        variables = dict(variables or {})
        yield f"Replaying: {workflow.name} ({len(workflow.steps)} steps)\n"
        if variables:
            rendered = ", ".join(f"{k}={v!r}" for k, v in variables.items())
            yield f"Variables: {rendered}\n"

        for step in workflow.steps:
            if cancel.is_set():
                yield "\n[cancelled]\n"
                return

            resolved_intent = apply_variables(step.intent, variables)
            resolved_text = apply_variables(step.text, variables) if step.text else None
            resolved_selector = apply_variables(step.selector, variables)
            resolved_keys = step.keys
            resolved_fallback = step.fallback_coord

            yield f"\nstep {step.index + 1}: {resolved_intent}\n"
            snapshot = ContextSnapshot.capture(self.settings)
            user_text = (
                f"Intent: {resolved_intent}\n"
                f"Action hint: {step.action}\n"
                f"Selector: {resolved_selector}\n"
                f"Fallback coord: {resolved_fallback}\n"
                f"Text to type (post-substitution): {resolved_text!r}\n"
                f"Keys hint: {resolved_keys}\n"
                "Emit exactly one computer_use action now."
            )
            messages = [
                Message(
                    role="user",
                    content=[
                        self.provider.image_block(snapshot.image),
                        self.provider.text_block(user_text),
                    ],
                )
            ]
            tool = build_computer_tool(snapshot.image.width, snapshot.image.height)

            chosen: ActionBlock | None = None
            for event in self.provider.stream(
                messages,
                system=SYSTEM_PROMPT,
                tools=[tool],
                max_tokens=512,
                model=self.settings.execute_model,
            ):
                if cancel.is_set():
                    return
                if event.kind == "tool_use" and event.tool_use is not None:
                    chosen = ActionBlock.from_tool_use(event.tool_use)
                    break
                if event.kind == "error":
                    yield f"[error] {event.error}\n"
                    return

            if chosen is None:
                yield "  -> no action emitted, skipping\n"
                continue

            # Apply variable substitution to the LLM's chosen action as well
            # (covers the case where it echoes something like "type {{musteri}}").
            chosen_params = apply_variables(chosen.params, variables)
            resolved_action = ActionBlock(id=chosen.id, action=chosen.action, params=chosen_params)

            result = self.actions.run(resolved_action)
            yield f"  -> {resolved_action.action}: {result}\n"
            time.sleep(self.settings.safety.pause_seconds)

        yield "\n[replay done]\n"
