"""Pluggable action system.

A "Lucid action" is a callable that takes a typed context and parameter
object and returns a short status string. Actions are discovered from
two sources:

    1. Built-in modules under ``lucid.actions.builtin`` (loaded
       eagerly when the package is imported).
    2. Third-party plugins published via the
       ``lucid.actions`` entry-point group, e.g.::

           # in their pyproject.toml
           [project.entry-points."lucid.actions"]
           my_thing = "my_pkg.lucid_thing"

The loader is intentionally minimal: every plugin module just needs to
import :func:`register_action` from this package and decorate its
functions. The registry is the single source of truth -- ``available``
returns names, ``get`` returns the callable, ``run`` dispatches.
"""

from __future__ import annotations

from .registry import (
    ActionContext,
    ActionError,
    available,
    get,
    register_action,
    run,
)

__all__ = [
    "ActionContext",
    "ActionError",
    "available",
    "get",
    "register_action",
    "run",
]
