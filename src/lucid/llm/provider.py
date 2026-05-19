"""Abstract LLM provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from lucid.llm.schemas import StreamEvent


@dataclass
class Message:
    role: str
    content: list[dict[str, Any]] = field(default_factory=list)


class LLMProvider(ABC):
    """Provider-neutral interface. Implementations stream ``StreamEvent``s."""

    name: str = "abstract"

    @abstractmethod
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
    ) -> Iterator[StreamEvent]:
        """Stream a completion, yielding text deltas and tool-use blocks.

        ``cache_system`` / ``cache_tools`` are Anthropic prompt-caching
        hints; providers that do not support caching must accept and
        ignore them.
        """

    @abstractmethod
    def image_block(self, img: Image.Image) -> dict[str, Any]:
        """Return a provider-specific image content block."""

    @abstractmethod
    def text_block(self, text: str) -> dict[str, Any]:
        """Return a provider-specific text content block."""

    @abstractmethod
    def tool_result_block(
        self,
        tool_use_id: str,
        content: list[dict[str, Any]] | str,
        is_error: bool = False,
    ) -> dict[str, Any]:
        """Return a provider-specific tool-result content block."""


def create_provider(settings) -> LLMProvider:
    """Resolve the configured backend through the provider registry.

    ``settings.backend.mode`` overrides ``settings.provider``. Plugins
    registered via the ``lucid.llm.providers`` entry-point are visible
    here without code changes in this module.
    """
    from lucid.llm.registry import available_providers, create_provider_by_name

    mode = (getattr(settings.backend, "mode", "") or "").lower()
    name = mode or settings.provider.lower()
    try:
        return create_provider_by_name(name, settings)
    except ValueError as exc:
        raise ValueError(
            f"{exc}. Available providers: {', '.join(available_providers())}"
        ) from exc
