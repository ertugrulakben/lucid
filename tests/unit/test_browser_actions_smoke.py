"""Smoke tests for the `browser_*` action group.

Pure unit-level checks:
- Registry exposes browser actions when Playwright is installed.
- Schemas validate the obvious failure modes (missing URL, empty selector).
- BrowserRuntime singleton clears properly on reset.

Anything that needs a real Chromium is skipped unless ``LUCID_BROWSER_E2E=1``.
The acceptance gate runs that path manually.
"""

from __future__ import annotations

import os

import pytest

playwright = pytest.importorskip("playwright")

from lucid.actions import registry
from lucid.actions.browser import AVAILABLE, BrowserRuntime
from lucid.actions.browser.ops import (
    BrowserClickParams,
    BrowserFillParams,
    BrowserGotoParams,
)
from lucid.config.settings import Settings


def test_browser_module_available() -> None:
    assert AVAILABLE is True


def test_actions_registered() -> None:
    names = set(registry.available())
    expected = {
        "browser_launch",
        "browser_goto",
        "browser_click_selector",
        "browser_fill",
        "browser_press",
        "browser_wait_for",
        "browser_screenshot",
        "browser_close",
    }
    missing = expected - names
    assert not missing, f"missing browser actions: {missing}"


def test_disabled_settings_raises_actionable_error() -> None:
    """When browser.enabled is False (the default), launching must refuse."""
    from lucid.actions.browser.ops import browser_launch, BrowserLaunchParams

    settings = Settings()  # browser.enabled defaults to False
    ctx = registry.ActionContext(settings=settings)
    with pytest.raises(registry.ActionError) as excinfo:
        browser_launch(ctx, BrowserLaunchParams())
    assert "browser actions are disabled" in str(excinfo.value)


def test_goto_schema_requires_url() -> None:
    with pytest.raises(Exception):  # noqa: BLE001 -- pydantic raises ValidationError
        BrowserGotoParams(url="")


def test_click_schema_requires_selector() -> None:
    with pytest.raises(Exception):  # noqa: BLE001
        BrowserClickParams(selector="")


def test_fill_schema_accepts_empty_text() -> None:
    # Empty string is a valid "clear the field" payload.
    params = BrowserFillParams(selector="#email", text="")
    assert params.selector == "#email"
    assert params.text == ""


def test_runtime_singleton_reset() -> None:
    settings = Settings()
    settings.browser.enabled = True
    a = BrowserRuntime.get(settings)
    b = BrowserRuntime.get(settings)
    assert a is b
    BrowserRuntime.reset()
    # After reset a fresh instance is handed out next time.
    c = BrowserRuntime.get(settings)
    assert c is not a


@pytest.mark.skipif(
    os.environ.get("LUCID_BROWSER_E2E") != "1",
    reason="real Chromium E2E -- set LUCID_BROWSER_E2E=1 to enable",
)
def test_real_chromium_navigates_to_example() -> None:
    settings = Settings()
    settings.browser.enabled = True
    settings.browser.headless = True
    BrowserRuntime.reset()
    runtime = BrowserRuntime.get(settings)
    try:
        page = runtime.ensure_page()
        response = page.goto("https://example.com", wait_until="load")
        assert response is not None
        assert "Example Domain" in (page.title() or "")
    finally:
        BrowserRuntime.reset()
