"""Provider lookup with entry-point discovery, mirroring action registry.

Built-in backends register themselves on first ``create_provider`` call.
Third-party packages publish providers through the
``lucid.llm.providers`` entry-point group; the value is a callable that
takes the loaded ``Settings`` object and returns an
:class:`~lucid.llm.provider.LLMProvider` instance.
"""

from __future__ import annotations

import logging
from importlib import metadata
from typing import Any, Callable, Dict, Iterable

log = logging.getLogger("lucid.llm.registry")

ENTRY_POINT_GROUP = "lucid.llm.providers"

ProviderFactory = Callable[[Any], Any]

_FACTORIES: Dict[str, ProviderFactory] = {}
_DISCOVERED = False


def register_provider(name: str, factory: ProviderFactory) -> None:
    _FACTORIES[name] = factory


def create_provider_by_name(name: str, settings: Any) -> Any:
    _ensure_discovered()
    if name not in _FACTORIES:
        raise ValueError(f"unknown provider: {name}")
    return _FACTORIES[name](settings)


def available_providers() -> list[str]:
    _ensure_discovered()
    return sorted(_FACTORIES.keys())


def reset_for_tests() -> None:
    global _DISCOVERED
    _FACTORIES.clear()
    _DISCOVERED = False


def _ensure_discovered() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    _register_builtins()
    _load_entry_points()


def _register_builtins() -> None:
    """Register the backends shipped with Lucid."""
    register_provider("anthropic", _make_anthropic)
    register_provider("api", _make_anthropic)  # backend.mode = "api" alias
    register_provider("cli", _make_cli)
    register_provider("lm_studio", _make_lm_studio)


def _make_anthropic(settings: Any) -> Any:
    from lucid.llm.anthropic_client import AnthropicProvider

    return AnthropicProvider(model=settings.model)


def _make_cli(settings: Any) -> Any:
    from lucid.backend.cli_backend import CLIBackend

    return CLIBackend(settings)


def _make_lm_studio(settings: Any) -> Any:
    from lucid.backend.lm_studio_backend import LMStudioProvider

    cfg = settings.backend
    return LMStudioProvider(
        base_url=cfg.lm_studio_url,
        api_key=cfg.lm_studio_api_key,
        model=cfg.lm_studio_model,
    )


def _load_entry_points() -> None:
    try:
        eps: Iterable[Any] = metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        eps = metadata.entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[union-attr]
    for ep in eps:
        try:
            factory = ep.load()
        except Exception as exc:  # noqa: BLE001
            log.warning("provider plugin %r failed to load: %s", getattr(ep, "name", "?"), exc)
            continue
        if callable(factory):
            register_provider(ep.name, factory)
        else:
            log.warning("provider plugin %r did not expose a callable factory", ep.name)
