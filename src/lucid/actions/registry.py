"""Decorator-based action registry with entry-point and user-plugin discovery.

Conceptually:

    @register_action(name="open_url", schema=OpenUrlParams)
    def open_url(ctx: ActionContext, params: OpenUrlParams) -> str: ...

The registry stores an :class:`Action` record per name. Callers do not
need to know the difference between built-in actions and plugins -- both
travel through the same dispatch path. ``run("open_url", ctx, params)``
either returns the action's status string or raises :class:`ActionError`.

Plugin discovery happens in three steps, each isolated so a broken
plugin can never take down the whole system:

    1. Built-ins under ``lucid.actions.builtin`` are imported eagerly.
    2. ``importlib.metadata.entry_points(group="lucid.actions")`` is
       walked. Each entry point is loaded; failures are logged and the
       plugin is skipped.
    3. ``~/.lucid/plugins/*.py`` is scanned for single-file plugins.

The first two are loaded on first call to :func:`available` or
:func:`run`; user plugins are loaded only when ``LUCID_USER_PLUGINS=1``
to avoid surprising behaviour from drive-by .py files.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

log = logging.getLogger("lucid.actions")

ENTRY_POINT_GROUP = "lucid.actions"
USER_PLUGIN_DIR = Path.home() / ".lucid" / "plugins"

ActionFn = Callable[..., str]


class ActionError(Exception):
    """Raised when a registered action signals failure or is missing."""


@dataclass
class ActionContext:
    """Container that an action receives as its first argument.

    Carries everything an action might need without forcing the caller
    to thread settings, executor, and provider through every call.
    Treat this as immutable from the action's side.
    """

    settings: Any = None
    executor: Any = None
    provider: Any = None
    snapshot: Any = None
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    name: str
    fn: ActionFn
    schema: Optional[type] = None
    summary: str = ""
    source: str = "builtin"  # "builtin" | "entry_point" | "user_plugin"

    def __call__(self, ctx: ActionContext, params: Any = None) -> str:
        if self.schema is not None and params is not None and not isinstance(params, self.schema):
            try:
                params = self.schema(**params) if isinstance(params, dict) else self.schema(params)
            except (TypeError, ValueError) as exc:
                raise ActionError(f"action {self.name}: invalid params ({exc})") from exc
        return self.fn(ctx, params)


_REGISTRY: Dict[str, Action] = {}
_DISCOVERED = False


def register_action(
    name: str,
    *,
    schema: Optional[type] = None,
    summary: str = "",
    source: str = "builtin",
) -> Callable[[ActionFn], ActionFn]:
    """Decorator. Names must be unique; later registrations win silently
    only when their ``source`` strictly outranks the existing one
    (entry_point > builtin, user_plugin > entry_point), to let users
    override a built-in with a more capable plugin.
    """

    def _decorator(fn: ActionFn) -> ActionFn:
        existing = _REGISTRY.get(name)
        new_action = Action(name=name, fn=fn, schema=schema, summary=summary, source=source)
        if existing is None or _rank(source) >= _rank(existing.source):
            if existing is not None and source != existing.source:
                log.info("action %r overridden by %s (was %s)", name, source, existing.source)
            _REGISTRY[name] = new_action
        else:
            log.debug("ignored lower-priority registration of %r from %s", name, source)
        return fn

    return _decorator


def _rank(source: str) -> int:
    return {"builtin": 0, "entry_point": 1, "user_plugin": 2}.get(source, -1)


def available() -> list[str]:
    _ensure_discovered()
    return sorted(_REGISTRY.keys())


def get(name: str) -> Action:
    _ensure_discovered()
    if name not in _REGISTRY:
        raise ActionError(f"unknown action: {name}")
    return _REGISTRY[name]


def run(name: str, ctx: ActionContext, params: Any = None) -> str:
    return get(name)(ctx, params)


def reset_for_tests() -> None:
    """Clear the registry. Tests use this; production never calls it."""
    global _DISCOVERED
    _REGISTRY.clear()
    _DISCOVERED = False
    for mod_name in [m for m in list(sys.modules) if m.startswith("lucid.actions.builtin")]:
        sys.modules.pop(mod_name, None)


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #


def _ensure_discovered() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    _load_builtins()
    _load_entry_points()
    if os.environ.get("LUCID_USER_PLUGINS") == "1":
        _load_user_plugins()


def _load_builtins() -> None:
    try:
        importlib.import_module("lucid.actions.builtin")
    except ImportError as exc:
        log.debug("no builtin action package present: %s", exc)


def _load_entry_points() -> None:
    try:
        eps: Iterable[Any] = metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # python < 3.10 select() shape
        eps = metadata.entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[union-attr]
    for ep in eps:
        try:
            ep.load()
        except Exception as exc:  # noqa: BLE001 -- one bad plugin must not down the system
            log.warning("plugin %r failed to load: %s", getattr(ep, "name", "?"), exc)


def _load_user_plugins() -> None:
    if not USER_PLUGIN_DIR.exists():
        return
    for path in sorted(USER_PLUGIN_DIR.glob("*.py")):
        spec_name = f"_lucid_user_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(spec_name, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec_name] = mod
            spec.loader.exec_module(mod)
        except Exception as exc:  # noqa: BLE001
            log.warning("user plugin %s failed to load: %s", path.name, exc)
