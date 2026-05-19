"""Tests for the LLM provider registry."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lucid.llm.registry import (
    available_providers,
    create_provider_by_name,
    register_provider,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _isolated_registry() -> None:
    reset_for_tests()
    yield
    reset_for_tests()


def _fake_settings(mode: str = "anthropic", model: str = "fake-model") -> SimpleNamespace:
    backend = SimpleNamespace(
        mode=mode,
        cli_path=None,
        lm_studio_url="http://localhost:1234/v1",
        lm_studio_model="",
        lm_studio_api_key="lm-studio",
        kimi_base_url="",
        kimi_model="",
        kimi_vision_model="",
    )
    return SimpleNamespace(
        provider="anthropic",
        model=model,
        backend=backend,
    )


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        create_provider_by_name("does-not-exist", _fake_settings())


def test_register_and_resolve_custom_provider() -> None:
    captured: dict[str, object] = {}

    class _Stub:
        def __init__(self, settings: object) -> None:
            captured["settings"] = settings

    register_provider("stub", _Stub)
    instance = create_provider_by_name("stub", _fake_settings())
    assert isinstance(instance, _Stub)
    assert captured["settings"].provider == "anthropic"


def test_available_providers_includes_builtins() -> None:
    names = available_providers()
    for expected in ("anthropic", "api", "cli", "lm_studio"):
        assert expected in names, f"missing built-in provider: {expected}"


def test_create_provider_dispatches_through_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    from lucid.llm.provider import create_provider

    # Trigger discovery before overriding so we win the rank race.
    available_providers()

    sentinel = object()
    register_provider("anthropic", lambda _s: sentinel)

    settings = _fake_settings(mode="anthropic")
    assert create_provider(settings) is sentinel


def test_provider_resolution_falls_back_to_settings_provider() -> None:
    """Empty backend.mode should fall back to settings.provider."""
    available_providers()  # ensure registry is populated first
    sentinel = object()
    register_provider("anthropic", lambda _s: sentinel)

    from lucid.llm.provider import create_provider

    settings = _fake_settings(mode="")
    assert create_provider(settings) is sentinel


def test_create_provider_unknown_raises_with_listing() -> None:
    from lucid.llm.provider import create_provider

    register_provider("anthropic", lambda _s: object())

    settings = _fake_settings(mode="not-a-real-backend")
    with pytest.raises(ValueError) as excinfo:
        create_provider(settings)
    assert "anthropic" in str(excinfo.value)
