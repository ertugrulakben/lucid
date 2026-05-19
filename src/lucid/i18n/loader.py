"""FluentBundleManager — wraps fluent.runtime with English fallback chain.

We intentionally keep this module dependency-light so the i18n layer can
boot before the rest of Lucid (logging, Qt, settings). When
``fluent.runtime`` is not yet installed (developer first-clone), the
manager degrades gracefully: ``format()`` returns the key.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
DEFAULT_LOCALE = "en"
RESOURCE_FILES = ("ui.ftl", "modes.ftl", "cli.ftl", "prompts.ftl", "errors.ftl")


@lru_cache(maxsize=1)
def available_locales() -> tuple[str, ...]:
    if not LOCALES_DIR.exists():
        return (DEFAULT_LOCALE,)
    found: list[str] = []
    for child in sorted(LOCALES_DIR.iterdir()):
        if child.is_dir() and (child / "ui.ftl").exists():
            found.append(child.name)
    if DEFAULT_LOCALE not in found:
        found.insert(0, DEFAULT_LOCALE)
    return tuple(found)


def resolve_system_locale() -> str | None:
    """Return the OS locale short code if we can determine one."""
    try:
        from PySide6.QtCore import QLocale  # type: ignore
    except Exception:
        return None
    try:
        return QLocale.system().name()
    except Exception:
        return None


class FluentBundleManager:
    """Active locale bundle + English fallback bundle."""

    def __init__(self) -> None:
        self._active: Any = None
        self._fallback: Any = None
        self._active_locale: str = DEFAULT_LOCALE

    def load(self, locale: str) -> None:
        self._active_locale = locale
        self._active = self._build_localization(locale)
        if locale == DEFAULT_LOCALE:
            self._fallback = self._active
        else:
            self._fallback = self._build_localization(DEFAULT_LOCALE)

    def format(self, key: str, args: dict[str, Any] | None = None) -> str:
        args = args or {}
        for source in (self._active, self._fallback):
            if source is None:
                continue
            try:
                rendered = source.format_value(key, args)
            except Exception:  # -- fluent raises various error subclasses
                rendered = None
            if rendered and rendered != key:
                return rendered
        return key

    def _build_localization(self, locale: str) -> Any:
        try:
            from fluent.runtime import FluentLocalization, FluentResourceLoader  # type: ignore
        except Exception:  # -- fluent.runtime not installed yet
            return None
        roots = [str(LOCALES_DIR / "{locale}")]
        loader = FluentResourceLoader(roots[0])
        return FluentLocalization([locale, DEFAULT_LOCALE], list(RESOURCE_FILES), loader)
