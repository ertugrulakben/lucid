"""Direct SDK backend. Thin wrapper over the provider layer.

Used by the agent when we need low-latency streaming and fine-grained tool
control. This is the default.
"""

from __future__ import annotations

from lucid.config.settings import Settings
from lucid.llm.provider import LLMProvider, create_provider


class APIBackend:
    name = "api"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._provider: LLMProvider | None = None

    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider = create_provider(self.settings)
        return self._provider
