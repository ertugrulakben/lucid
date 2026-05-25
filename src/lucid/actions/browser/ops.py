"""Browser actions exposed to ExecuteMode.

Eight actions cover the core DOM workflow: launch, navigate, click, fill,
press, wait, screenshot, close. Each one delegates to a shared
``BrowserRuntime`` so multiple actions in the same Execute run share a single
Chromium tab without re-launching for every step.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from lucid.actions.registry import ActionContext, ActionError, register_action

from .runtime import BrowserRuntime

log = logging.getLogger("lucid.actions.browser.ops")


# --------------------------------------------------------------------------- #
# parameter schemas
# --------------------------------------------------------------------------- #


class BrowserLaunchParams(BaseModel):
    headless: Optional[bool] = None  # falls back to settings.browser.headless


class BrowserGotoParams(BaseModel):
    url: str = Field(..., min_length=1)
    wait_until: str = Field("load", description="One of 'load' | 'domcontentloaded' | 'networkidle'.")


class BrowserClickParams(BaseModel):
    selector: str = Field(..., min_length=1)
    timeout_ms: int = Field(5000, ge=100, le=120_000)


class BrowserFillParams(BaseModel):
    selector: str = Field(..., min_length=1)
    text: str = ""


class BrowserPressParams(BaseModel):
    key: str = Field(..., min_length=1)


class BrowserWaitParams(BaseModel):
    selector: str = Field(..., min_length=1)
    state: str = Field("visible", description="One of 'attached' | 'detached' | 'visible' | 'hidden'.")
    timeout_ms: int = Field(8000, ge=100, le=120_000)


class BrowserScreenshotParams(BaseModel):
    full_page: bool = False
    path: Optional[str] = None  # if set, save to disk under data/screenshots


class BrowserNoParams(BaseModel):
    pass


# --------------------------------------------------------------------------- #
# actions
# --------------------------------------------------------------------------- #


def _runtime(ctx: ActionContext) -> BrowserRuntime:
    settings = ctx.settings
    if settings is None:
        raise ActionError("browser action: ActionContext.settings is required")
    cfg = getattr(settings, "browser", None)
    if cfg is None or not getattr(cfg, "enabled", False):
        raise ActionError(
            "browser actions are disabled -- flip settings.browser.enabled to True"
        )
    return BrowserRuntime.get(settings)


@register_action(
    name="browser_launch",
    schema=BrowserLaunchParams,
    summary="Boot a shared Chromium instance and open a blank page.",
)
def browser_launch(ctx: ActionContext, params: BrowserLaunchParams) -> str:
    runtime = _runtime(ctx)
    if params.headless is not None:
        runtime.settings.browser.headless = bool(params.headless)
    page = runtime.ensure_page()
    return f"browser launched ({'headless' if runtime.settings.browser.headless else 'headed'}); page: {page.url or 'about:blank'}"


@register_action(
    name="browser_goto",
    schema=BrowserGotoParams,
    summary="Navigate the current browser page to a URL.",
)
def browser_goto(ctx: ActionContext, params: BrowserGotoParams) -> str:
    runtime = _runtime(ctx)
    page = runtime.ensure_page()
    response = page.goto(params.url, wait_until=params.wait_until)
    status = response.status if response is not None else "?"
    title = (page.title() or "").strip()
    return f"navigated -> {page.url} (status={status}) title={title!r}"


@register_action(
    name="browser_click_selector",
    schema=BrowserClickParams,
    summary="Click the first element matching the given CSS/text selector.",
)
def browser_click_selector(ctx: ActionContext, params: BrowserClickParams) -> str:
    runtime = _runtime(ctx)
    page = runtime.page()
    locator = page.locator(params.selector)
    locator.first.click(timeout=params.timeout_ms)
    return f"clicked {params.selector!r}"


@register_action(
    name="browser_fill",
    schema=BrowserFillParams,
    summary="Fill an input/textarea matching the selector with the given text.",
)
def browser_fill(ctx: ActionContext, params: BrowserFillParams) -> str:
    runtime = _runtime(ctx)
    page = runtime.page()
    page.locator(params.selector).first.fill(params.text)
    snippet = params.text[:30] + ("…" if len(params.text) > 30 else "")
    return f"filled {params.selector!r} with {snippet!r}"


@register_action(
    name="browser_press",
    schema=BrowserPressParams,
    summary="Send a single key (e.g. Enter, Tab, ArrowDown) to the active page.",
)
def browser_press(ctx: ActionContext, params: BrowserPressParams) -> str:
    runtime = _runtime(ctx)
    page = runtime.page()
    page.keyboard.press(params.key)
    return f"pressed {params.key!r}"


@register_action(
    name="browser_wait_for",
    schema=BrowserWaitParams,
    summary="Wait until a selector reaches the requested state.",
)
def browser_wait_for(ctx: ActionContext, params: BrowserWaitParams) -> str:
    runtime = _runtime(ctx)
    page = runtime.page()
    page.locator(params.selector).first.wait_for(state=params.state, timeout=params.timeout_ms)
    return f"selector {params.selector!r} reached state {params.state!r}"


@register_action(
    name="browser_screenshot",
    schema=BrowserScreenshotParams,
    summary="Capture a screenshot of the current page (full_page optional).",
)
def browser_screenshot(ctx: ActionContext, params: BrowserScreenshotParams) -> str:
    runtime = _runtime(ctx)
    page = runtime.page()
    if params.path:
        target = Path(params.path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        screenshots = ctx.settings.screenshot_dir if ctx.settings is not None else Path(".")
        screenshots.mkdir(parents=True, exist_ok=True)
        import time as _t

        target = screenshots / f"browser-{_t.strftime('%Y%m%d-%H%M%S')}.png"
    page.screenshot(path=str(target), full_page=params.full_page)
    return f"screenshot saved: {target}"


@register_action(
    name="browser_close",
    schema=BrowserNoParams,
    summary="Tear down the browser runtime (page, context, browser, playwright).",
)
def browser_close(ctx: ActionContext, params: BrowserNoParams) -> str:
    BrowserRuntime.reset()
    return "browser runtime closed"
