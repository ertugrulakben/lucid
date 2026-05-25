"""Playwright-backed `browser_*` action group.

This sub-package is loaded eagerly by :mod:`lucid.actions.builtin` whenever
Playwright is importable. If Playwright is not installed the import is a
silent no-op so vanilla installs keep working untouched.

The action set sits next to the desktop automation actions and gives Lucid a
DOM-level path for web tasks: CSS selectors, ``page.fill``, network waiters,
and so on. ExecuteMode treats them like any other registered action.
"""

from __future__ import annotations

import logging

log = logging.getLogger("lucid.actions.browser")

try:  # pragma: no cover -- import guarded so missing extra never crashes
    from . import ops as _ops  # noqa: F401 -- import triggers @register_action
    from .runtime import BrowserRuntime

    AVAILABLE = True
except Exception as exc:  # noqa: BLE001 -- any import failure means no playwright
    log.debug("browser action group unavailable: %s", exc)
    BrowserRuntime = None  # type: ignore[assignment]
    AVAILABLE = False


__all__ = ["AVAILABLE", "BrowserRuntime"]
