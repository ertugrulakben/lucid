"""Shared Playwright runtime: one Chromium per process, reused across actions.

The actions package keeps state out of the registry — every action is a free
function. So we park the browser lifecycle behind a module-level singleton
that the ops module reaches into via :meth:`BrowserRuntime.get`.

Threading: Lucid's executor runs actions on a worker thread (the same one as
the Execute loop). Playwright's *sync* API is happy with that as long as we
never poke the same Playwright objects from another thread. The lock here
guards lazy launch; once ``_page`` is set, every action runs sequentially on
the executor thread anyway.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from playwright.sync_api import (  # type: ignore[import-not-found]
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

log = logging.getLogger("lucid.actions.browser.runtime")


class BrowserRuntime:
    """Lazy-init Chromium wrapper. One instance per process, reset on demand."""

    _instance: "BrowserRuntime | None" = None
    _instance_lock = threading.Lock()

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ------------------------- singleton plumbing -------------------------

    @classmethod
    def get(cls, settings: Any) -> "BrowserRuntime":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(settings)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Tear down the singleton -- ExecuteMode.reset() and shutdown call this."""
        with cls._instance_lock:
            inst = cls._instance
            cls._instance = None
        if inst is not None:
            try:
                inst.shutdown()
            except Exception as exc:  # noqa: BLE001
                log.debug("browser runtime shutdown failed: %s", exc)

    # ------------------------- lifecycle -------------------------

    def ensure_page(self) -> Page:
        """Return the live page, launching the browser on first call."""
        with self._lock:
            if self._page is not None:
                return self._page
            cfg = getattr(self.settings, "browser", None)
            headless = bool(getattr(cfg, "headless", False))
            viewport = {
                "width": int(getattr(cfg, "viewport_width", 1280)),
                "height": int(getattr(cfg, "viewport_height", 800)),
            }
            timeout = int(getattr(cfg, "default_timeout_ms", 8000))
            locale = str(getattr(cfg, "locale", "tr-TR"))
            user_agent = getattr(cfg, "user_agent", None) or None

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=headless)
            ctx_kwargs: dict[str, Any] = {"viewport": viewport, "locale": locale}
            if user_agent:
                ctx_kwargs["user_agent"] = user_agent
            self._context = self._browser.new_context(**ctx_kwargs)
            self._context.set_default_timeout(timeout)
            self._page = self._context.new_page()
            log.info(
                "browser runtime up: headless=%s viewport=%sx%s",
                headless,
                viewport["width"],
                viewport["height"],
            )
            return self._page

    def page(self) -> Page:
        """Return the current page or raise if the runtime is not launched yet."""
        if self._page is None:
            raise RuntimeError("browser runtime not launched -- call browser_launch first")
        return self._page

    def is_active(self) -> bool:
        return self._page is not None

    def shutdown(self) -> None:
        """Close the page, context, browser, and playwright instance in order."""
        with self._lock:
            errors: list[str] = []
            for resource, name in (
                (self._page, "page"),
                (self._context, "context"),
                (self._browser, "browser"),
            ):
                if resource is None:
                    continue
                try:
                    resource.close()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{name}: {exc}")
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"playwright: {exc}")
            self._page = None
            self._context = None
            self._browser = None
            self._pw = None
            if errors:
                log.debug("browser shutdown soft-errors: %s", "; ".join(errors))
