"""Anthropic Claude provider with streaming and computer_use tool."""

from __future__ import annotations

import base64
import io
import logging
import random
import time
from collections.abc import Iterator
from typing import Any

from PIL import Image

from lucid.config.secrets import ANTHROPIC_KEY, get_secret
from lucid.llm.provider import LLMProvider, Message
from lucid.llm.schemas import ComputerUseBlock, StreamEvent

log = logging.getLogger("lucid.llm.anthropic")

# Streaming retry policy: exponential backoff with full jitter, capped attempts.
# Only retried for transient classes (rate limit, network, server). Auth and
# bad-request style errors fail fast.
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0
_RETRY_MAX_DELAY = 30.0


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str = "claude-opus-4-7") -> None:
        self.model = model
        self._client = None

    def _client_lazy(self):
        if self._client is None:
            from anthropic import Anthropic

            api_key = get_secret(ANTHROPIC_KEY)
            if not api_key:
                raise RuntimeError(
                    "Anthropic API key is not set. Run `lucid setup` or set "
                    "LUCID_ANTHROPIC_API_KEY."
                )
            self._client = Anthropic(api_key=api_key)
        return self._client

    def stream(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2048,
        model: str | None = None,
        cache_system: bool = False,
        cache_tools: bool = False,
    ) -> Iterator[StreamEvent]:
        client = self._client_lazy()
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            if cache_system:
                # Anthropic prompt caching: marking the system block ephemeral
                # tells the API to cache it for 5 minutes. Subsequent calls
                # within the window pay ~10% of input tokens for this slice.
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                kwargs["system"] = system
        if tools:
            if cache_tools and tools:
                # Tools inherit cache_control from the LAST tool in the list.
                # We clone to avoid mutating the caller's dict.
                tools = [dict(t) for t in tools]
                tools[-1] = dict(tools[-1])
                tools[-1].setdefault("cache_control", {"type": "ephemeral"})
            kwargs["tools"] = tools

        attempt = 0
        while True:
            attempt += 1
            try:
                yield from self._stream_once(client, kwargs)
                return
            except _RetriableAnthropicError as exc:
                if attempt >= _RETRY_MAX_ATTEMPTS:
                    log.warning("Anthropic stream giving up after %d attempts: %s", attempt, exc)
                    yield StreamEvent(kind="error", error=str(exc))
                    return
                delay = min(_RETRY_MAX_DELAY, _RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                delay *= random.uniform(0.5, 1.0)
                log.info(
                    "Anthropic stream attempt %d failed (%s); retrying in %.1fs",
                    attempt,
                    type(exc.__cause__ or exc).__name__,
                    delay,
                )
                time.sleep(delay)
            except _FatalAnthropicError as exc:
                log.exception("Anthropic stream failed (non-retriable)")
                yield StreamEvent(kind="error", error=str(exc))
                return

    def _stream_once(self, client: Any, kwargs: dict[str, Any]) -> Iterator[StreamEvent]:
        try:
            from anthropic import (
                APIConnectionError,
                APITimeoutError,
                AuthenticationError,
                BadRequestError,
                InternalServerError,
                NotFoundError,
                PermissionDeniedError,
                RateLimitError,
            )
        except ImportError:  # very old anthropic SDKs
            APIConnectionError = APITimeoutError = RateLimitError = type("_Stub", (Exception,), {})  # type: ignore[assignment]
            AuthenticationError = BadRequestError = NotFoundError = type("_Stub", (Exception,), {})  # type: ignore[assignment]
            InternalServerError = PermissionDeniedError = type("_Stub", (Exception,), {})  # type: ignore[assignment]

        try:
            with client.messages.stream(**kwargs) as stream:
                pending_tool: dict[str, Any] = {}
                input_buffers: dict[int, str] = {}
                for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "content_block_start":
                        block = getattr(event, "content_block", None)
                        if block is not None and getattr(block, "type", "") == "tool_use":
                            pending_tool = {
                                "id": getattr(block, "id", ""),
                                "name": getattr(block, "name", ""),
                                "input_index": getattr(event, "index", 0),
                            }
                    elif etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        dtype = getattr(delta, "type", "") if delta is not None else ""
                        if dtype == "text_delta":
                            yield StreamEvent(kind="text_delta", text=delta.text)
                        elif dtype == "input_json_delta":
                            idx = getattr(event, "index", 0)
                            input_buffers[idx] = input_buffers.get(idx, "") + delta.partial_json
                    elif etype == "content_block_stop" and pending_tool:
                        idx = pending_tool.get("input_index", 0)
                        raw_input = _safe_json(input_buffers.get(idx, "{}"))
                        yield StreamEvent(
                            kind="tool_use",
                            tool_use=_build_tool_use_block(pending_tool, raw_input),
                        )
                        pending_tool = {}
                final = stream.get_final_message()
                yield StreamEvent(kind="done", stop_reason=getattr(final, "stop_reason", None))
        except (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError) as exc:
            raise _RetriableAnthropicError(str(exc)) from exc
        except (AuthenticationError, BadRequestError, NotFoundError, PermissionDeniedError) as exc:
            raise _FatalAnthropicError(str(exc)) from exc
        except Exception as exc:  # -- last-resort, treat as fatal
            raise _FatalAnthropicError(str(exc)) from exc


    def image_block(self, img: Image.Image) -> dict[str, Any]:
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        }

    def text_block(self, text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    def tool_result_block(
        self,
        tool_use_id: str,
        content: list[dict[str, Any]] | str,
        is_error: bool = False,
    ) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": is_error,
        }


class _RetriableAnthropicError(Exception):
    """Wraps Anthropic SDK errors that justify retrying with backoff."""


class _FatalAnthropicError(Exception):
    """Wraps Anthropic SDK errors where retrying would not help."""


def _safe_json(raw: str) -> dict[str, Any]:
    import json

    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def _build_tool_use_block(meta: dict[str, Any], raw_input: dict[str, Any]) -> ComputerUseBlock:
    coord = raw_input.get("coordinate")
    coord_tuple = tuple(coord) if isinstance(coord, (list, tuple)) and len(coord) == 2 else None
    return ComputerUseBlock(
        id=meta.get("id", ""),
        action=str(raw_input.get("action", meta.get("name", ""))),
        coordinate=coord_tuple,  # type: ignore[arg-type]
        text=raw_input.get("text"),
        keys=list(raw_input["keys"]) if isinstance(raw_input.get("keys"), list) else None,
        duration_ms=raw_input.get("duration_ms"),
        scroll_direction=raw_input.get("scroll_direction"),
        scroll_amount=raw_input.get("scroll_amount"),
        raw={"input": raw_input, "name": meta.get("name", "")},
    )


def build_computer_tool(display_width: int, display_height: int) -> dict[str, Any]:
    """Custom `computer` tool (portable across models, no beta flag required).

    Anthropic's built-in ``computer_20250124`` tool is restricted to specific
    models. We emit an equivalent user-defined tool so Lucid works on any
    vision-capable Claude.
    """
    return {
        "name": "computer",
        "description": (
            "Control the user's mouse and keyboard on a "
            f"{display_width}x{display_height} screen. Emit exactly one action at "
            "a time, then wait for the next screenshot before deciding the next "
            "step. Coordinates are in pixels with origin at top-left."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "left_click",
                        "right_click",
                        "double_click",
                        "triple_click",
                        "left_click_drag",
                        "mouse_move",
                        "type",
                        "key",
                        "hold_key",
                        "scroll",
                        "wait",
                        "screenshot",
                        "focus_window",
                        "click_element",
                        "scroll_into_view",
                        "file_dialog_paste",
                        "solve_captcha",
                        "screenshot_to_clipboard",
                        "run_shell",
                        "focus_monitor",
                    ],
                    "description": "The action to perform.",
                },
                "window_title": {
                    "type": "string",
                    "description": (
                        "Substring of the target window title for `focus_window` "
                        "(case-insensitive, shortest title wins)."
                    ),
                },
                "element_name": {
                    "type": "string",
                    "description": (
                        "Accessibility name substring for `click_element` or "
                        "`scroll_into_view`. The live UI Automation tree is "
                        "searched and the matching element's bounding-rect "
                        "centre is targeted. MUCH more reliable than pixel "
                        "coordinates."
                    ),
                },
                "element_role": {
                    "type": "string",
                    "description": (
                        "Optional role filter for `click_element` (e.g. "
                        "'Button', 'MenuItem', 'Hyperlink')."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Absolute path for `file_dialog_paste`. Lucid focuses "
                        "the File-name field of the foreground File Open/Save "
                        "dialog, pastes this path, and presses Enter."
                    ),
                },
                "submit": {
                    "type": "boolean",
                    "description": (
                        "If true (default), `file_dialog_paste` presses Enter "
                        "after pasting. Set false to only navigate."
                    ),
                },
                "coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[x, y] pixel coordinate for click / move / scroll.",
                },
                "start_coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "Starting [x, y] for drag actions.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type with `type`.",
                },
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Key names for `key` or `hold_key` " "(e.g. ['ctrl','t'] or ['return'])."
                    ),
                },
                "scroll_direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "Notches to scroll (each ~3 lines).",
                },
                "duration_ms": {
                    "type": "integer",
                    "description": "Duration in ms for wait/hold_key.",
                },
                "monitor": {
                    "type": "integer",
                    "description": (
                        "Monitor index for `screenshot_to_clipboard` "
                        "(0 = all monitors, 1..N = specific screen)."
                    ),
                },
                "region": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": (
                        "Optional [x, y, w, h] crop region for " "`screenshot_to_clipboard`."
                    ),
                },
                "command": {
                    "type": "string",
                    "description": (
                        "Read-only shell command for `run_shell` (e.g. "
                        "'dir E:\\\\locker', 'Get-Process chrome', "
                        "'where.exe python'). Destructive patterns "
                        "(rm/del/format/shutdown/redirection) are rejected."
                    ),
                },
                "shell": {
                    "type": "string",
                    "enum": ["cmd", "powershell", "bash"],
                    "description": (
                        "Shell for `run_shell`. Default: cmd on Windows, " "bash elsewhere."
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": ("Seconds before `run_shell` aborts (1..30, default 10)."),
                },
                "index": {
                    "type": "integer",
                    "description": (
                        "Monitor index for `focus_monitor` (1..N, matching "
                        "the numbers printed in the snapshot's Monitors list)."
                    ),
                },
                "position": {
                    "type": "string",
                    "enum": ["primary", "left", "right", "above", "below"],
                    "description": (
                        "Alternative to `index` for `focus_monitor` — picks "
                        "the monitor by relative position to the primary "
                        "display."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": "One-line explanation for this action (for logs).",
                },
            },
            "required": ["action"],
        },
    }


# Backwards-compat alias. Callers should prefer ``build_computer_tool``.
COMPUTER_USE_TOOL: dict[str, Any] = build_computer_tool(1280, 800)
