"""Multi-agent router: split planning from verification across two models.

Execute mode benefits from a small/fast model for the high-volume,
low-creativity work (verifying that a step succeeded, picking which
candidate element to click given a list, summarising what changed) and
a stronger model for the low-volume, high-creativity work (planning
the next sub-goal, recovering from a stall).

Settings:
    settings.model                    -- planner model (default Opus / Sonnet)
    settings.execute_subagent_model   -- verifier model (default Haiku)
    settings.subagent_escalate_on_low_confidence -- promote uncertain
                                                    Haiku replies to the planner

This module is provider-agnostic: it asks the registry for a fresh
provider for each model name. Tests use the
:class:`~lucid.llm.providers.fake_provider.FakeProvider` to assert
routing without touching the network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from lucid.llm.provider import LLMProvider, Message
from lucid.llm.schemas import StreamEvent

log = logging.getLogger("lucid.llm.router")

LOW_CONFIDENCE_MARKERS = (
    "i'm not sure",
    "im not sure",
    "i am not sure",
    "uncertain",
    "[uncertain]",
    "<low_confidence>",
)


@dataclass
class RouterDecision:
    """Records which model handled a particular call and why."""
    role: str  # "planner" | "verifier"
    model: str
    escalated: bool = False
    reason: str = ""


class MultiAgentRouter:
    """Dispatches LLM calls between a planner and a verifier model."""

    def __init__(
        self,
        settings: Any,
        *,
        planner_factory=None,
        verifier_factory=None,
    ) -> None:
        self.settings = settings
        self.planner_model = getattr(settings, "model", "claude-opus-4-7")
        self.verifier_model = getattr(settings, "execute_subagent_model", "claude-haiku-4-5")
        self.escalate = bool(getattr(settings, "subagent_escalate_on_low_confidence", True))

        self._planner_factory = planner_factory or _default_factory
        self._verifier_factory = verifier_factory or _default_factory
        self._planner_provider: Optional[LLMProvider] = None
        self._verifier_provider: Optional[LLMProvider] = None
        self.last_decision: Optional[RouterDecision] = None

    def planner(self) -> LLMProvider:
        if self._planner_provider is None:
            self._planner_provider = self._planner_factory(self.settings, self.planner_model)
        return self._planner_provider

    def verifier(self) -> LLMProvider:
        if self._verifier_provider is None:
            self._verifier_provider = self._verifier_factory(self.settings, self.verifier_model)
        return self._verifier_provider

    def stream_plan(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2048,
    ) -> Iterator[StreamEvent]:
        self.last_decision = RouterDecision(role="planner", model=self.planner_model)
        yield from self.planner().stream(
            messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            model=self.planner_model,
        )

    def stream_verify(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 512,
    ) -> Iterator[StreamEvent]:
        self.last_decision = RouterDecision(role="verifier", model=self.verifier_model)
        text = ""
        events: list[StreamEvent] = []
        for ev in self.verifier().stream(
            messages,
            system=system,
            max_tokens=max_tokens,
            model=self.verifier_model,
        ):
            events.append(ev)
            if ev.kind == "text_delta" and ev.text:
                text += ev.text
            yield ev

        if self.escalate and _is_low_confidence(text):
            log.info("verifier returned low-confidence reply; escalating to planner")
            self.last_decision = RouterDecision(
                role="planner",
                model=self.planner_model,
                escalated=True,
                reason="low_confidence",
            )
            for ev in self.planner().stream(
                messages,
                system=system,
                max_tokens=max_tokens,
                model=self.planner_model,
            ):
                yield ev


def _default_factory(settings: Any, model: str) -> LLMProvider:
    """Build a provider for the configured backend, swapping in the requested model."""
    from lucid.llm.provider import create_provider

    cloned = _settings_with_model(settings, model)
    return create_provider(cloned)


def _settings_with_model(settings: Any, model: str) -> Any:
    """Return a shallow clone of ``settings`` with ``settings.model = model``.

    Pydantic models support ``model_copy``; tests pass ``SimpleNamespace``
    which lacks that. We support both shapes.
    """
    if hasattr(settings, "model_copy"):
        try:
            return settings.model_copy(update={"model": model})
        except Exception:  # noqa: BLE001
            pass
    from copy import copy

    cloned = copy(settings)
    setattr(cloned, "model", model)
    return cloned


def _is_low_confidence(text: str) -> bool:
    if not text:
        return False
    needle = text.lower()
    return any(marker in needle for marker in LOW_CONFIDENCE_MARKERS)
