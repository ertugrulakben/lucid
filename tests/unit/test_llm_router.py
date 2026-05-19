"""Tests for the multi-agent planner+verifier router."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterable

from PIL import Image

from lucid.llm.provider import LLMProvider, Message
from lucid.llm.router import MultiAgentRouter
from lucid.llm.schemas import StreamEvent


class _ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, label: str, scripted_text: str) -> None:
        self.label = label
        self.text = scripted_text
        self.calls: list[dict[str, Any]] = []

    def stream(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2048,
        model: str | None = None,
        cache_system: bool = False,
        cache_tools: bool = False,
    ) -> Iterable[StreamEvent]:
        self.calls.append({"model": model, "system": system, "max_tokens": max_tokens})
        yield StreamEvent(kind="text_delta", text=self.text)
        yield StreamEvent(kind="done", stop_reason="end_turn")

    def image_block(self, img: Image.Image) -> dict[str, Any]:
        return {"type": "image"}

    def text_block(self, text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    def tool_result_block(
        self,
        tool_use_id: str,
        content: Any,
        is_error: bool = False,
    ) -> dict[str, Any]:
        return {"type": "tool_result", "id": tool_use_id}


def _settings(escalate: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        model="planner-model",
        execute_subagent_model="verifier-model",
        subagent_escalate_on_low_confidence=escalate,
    )


def _factory_pair(planner_text: str = "ok", verifier_text: str = "verified"):
    planner = _ScriptedProvider("planner", planner_text)
    verifier = _ScriptedProvider("verifier", verifier_text)

    def planner_factory(_settings: Any, _model: str) -> _ScriptedProvider:
        return planner

    def verifier_factory(_settings: Any, _model: str) -> _ScriptedProvider:
        return verifier

    return planner, verifier, planner_factory, verifier_factory


def test_plan_stream_uses_planner_model() -> None:
    planner, verifier, pf, vf = _factory_pair()
    router = MultiAgentRouter(_settings(), planner_factory=pf, verifier_factory=vf)
    out = list(router.stream_plan([Message(role="user", content=[])]))
    assert any(e.kind == "text_delta" for e in out)
    assert len(planner.calls) == 1
    assert len(verifier.calls) == 0
    assert planner.calls[0]["model"] == "planner-model"
    assert router.last_decision.role == "planner"


def test_verify_stream_uses_verifier_model() -> None:
    planner, verifier, pf, vf = _factory_pair()
    router = MultiAgentRouter(_settings(), planner_factory=pf, verifier_factory=vf)
    list(router.stream_verify([Message(role="user", content=[])]))
    assert len(verifier.calls) == 1
    assert verifier.calls[0]["model"] == "verifier-model"
    assert router.last_decision.role == "verifier"


def test_low_confidence_escalates_to_planner() -> None:
    planner, verifier, pf, vf = _factory_pair(
        planner_text="confident", verifier_text="I'm not sure, please retry."
    )
    router = MultiAgentRouter(_settings(escalate=True), planner_factory=pf, verifier_factory=vf)
    list(router.stream_verify([Message(role="user", content=[])]))
    assert len(verifier.calls) == 1
    assert len(planner.calls) == 1
    assert router.last_decision.role == "planner"
    assert router.last_decision.escalated is True


def test_escalation_disabled_keeps_verifier_reply() -> None:
    planner, verifier, pf, vf = _factory_pair(verifier_text="<low_confidence> idk")
    router = MultiAgentRouter(_settings(escalate=False), planner_factory=pf, verifier_factory=vf)
    list(router.stream_verify([Message(role="user", content=[])]))
    assert len(planner.calls) == 0
    assert router.last_decision.role == "verifier"
    assert router.last_decision.escalated is False


def test_planner_and_verifier_providers_cached() -> None:
    """Calling stream_plan twice should not rebuild the provider."""
    instance_counts = {"planner": 0, "verifier": 0}

    def planner_factory(_s: Any, _m: str) -> _ScriptedProvider:
        instance_counts["planner"] += 1
        return _ScriptedProvider("p", "")

    def verifier_factory(_s: Any, _m: str) -> _ScriptedProvider:
        instance_counts["verifier"] += 1
        return _ScriptedProvider("v", "")

    router = MultiAgentRouter(
        _settings(), planner_factory=planner_factory, verifier_factory=verifier_factory
    )
    list(router.stream_plan([Message(role="user", content=[])]))
    list(router.stream_plan([Message(role="user", content=[])]))
    assert instance_counts["planner"] == 1
