"""Backend strategies: direct API or Claude Code CLI subprocess."""

from lucid.backend.api_backend import APIBackend
from lucid.backend.cli_backend import CLIBackend

__all__ = ["APIBackend", "CLIBackend", "create_backend"]


def create_backend(settings):
    mode = (settings.backend.mode or "api").lower()
    if mode == "cli":
        return CLIBackend(settings)
    return APIBackend(settings)
