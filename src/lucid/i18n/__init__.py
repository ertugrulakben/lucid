"""Internationalization (i18n) for Lucid.

Public API:
    init(locale: str | None = None) -> None
    set_locale(locale: str) -> None
    get_locale() -> str
    available_locales() -> list[str]
    _(key: str, **kwargs) -> str

Bootstrap order (critical):
    Call ``i18n.init()`` BEFORE importing Qt or building argparse / Typer
    parsers. ``init()`` resolves the active locale in this order:

        1. ``LUCID_LOCALE`` env var
        2. ``settings.locale`` (if settings already loaded)
        3. ``QLocale.system().name()`` short form (best-effort)
        4. ``"en"``

The translation function ``_`` is a thin wrapper around the active
``FluentLocalization`` instance. Missing keys fall back to English; if
even English is missing, the key itself is returned so the UI never
shows blanks during development.
"""

from __future__ import annotations

import os
from typing import Any

from .loader import (
    FluentBundleManager,
    available_locales,
    resolve_system_locale,
)

_manager: FluentBundleManager | None = None
_current_locale: str = "en"


def init(locale: str | None = None) -> None:
    """Initialise the bundle manager. Idempotent."""
    global _manager, _current_locale
    if locale is None:
        locale = (
            os.environ.get("LUCID_LOCALE")
            or _try_settings_locale()
            or resolve_system_locale()
            or "en"
        )
    locale = _normalise(locale)
    _manager = FluentBundleManager()
    _manager.load(locale)
    _current_locale = locale


def set_locale(locale: str) -> None:
    """Switch the active locale at runtime."""
    global _current_locale
    if _manager is None:
        init(locale)
        return
    locale = _normalise(locale)
    _manager.load(locale)
    _current_locale = locale


def get_locale() -> str:
    return _current_locale


def _(key: str, **kwargs: Any) -> str:
    """Translate a key. Missing keys fall back to English, then to the key."""
    if _manager is None:
        init()
    assert _manager is not None
    return _manager.format(key, kwargs)


def _try_settings_locale() -> str | None:
    """Best-effort read of ``settings.locale`` without forcing a circular import."""
    try:
        from lucid.config.settings import get_settings
    except Exception:  # -- settings not importable during early bootstrap
        return None
    try:
        value = getattr(get_settings(), "locale", None)
        return str(value) if value else None
    except Exception:
        return None


def _normalise(locale: str) -> str:
    """Normalise ``en_US`` / ``en-US`` / ``EN`` to a short code we ship locales for."""
    if not locale:
        return "en"
    code = locale.replace("_", "-").split("-")[0].lower()
    if code in available_locales():
        return code
    return "en"


__all__ = [
    "init",
    "set_locale",
    "get_locale",
    "available_locales",
    "_",
]
