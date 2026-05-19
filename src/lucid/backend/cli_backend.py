"""Claude Code CLI backend — uses the user's existing ``claude`` subscription.

This turns Claude Code (the CLI) into an ``LLMProvider`` so Lucid's Answer
mode can run without touching the paid Anthropic API endpoint directly.

**Scope:** Answer + Teach summarisation work today. Execute mode (which
requires a custom ``computer`` tool for tool-use streaming) does NOT work
on this backend yet — the CLI doesn't expose arbitrary user-defined tools
through its JSON stream protocol. We detect a ``tools=`` argument to
``stream()`` and fall through with a clear error so the caller can either
flip back to the API backend or change strategy.

Spawning strategy:
- We invoke ``claude -p "<prompt>" --output-format stream-json``; each line
  on stdout is a JSON event from the Claude Agent protocol (assistant
  message deltas, tool_use, result).
- Prompts > ``MAX_STDIN_INLINE_BYTES`` are written to a tmp file and
  referenced via ``--input-file`` (workaround for GitHub issue #7263 where
  very long stdin payloads hang the CLI).

Env vars the CLI respects are inherited; the user is expected to have
already run ``claude /login`` once.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from PIL import Image

from lucid.config.settings import Settings
from lucid.llm.provider import LLMProvider, Message
from lucid.llm.schemas import StreamEvent

log = logging.getLogger("lucid.backend.cli")

MAX_STDIN_INLINE_BYTES = 6000


class CLIBackend(LLMProvider):
    """LLMProvider implementation backed by the Claude Code CLI."""

    name = "cli"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cli_path: str | None = settings.backend.cli_path or self._find_cli()

    # ---------- discovery ----------

    def _find_cli(self) -> str | None:
        exe_names = ("claude.cmd", "claude.exe") if sys.platform == "win32" else ("claude",)
        for path in os.environ.get("PATH", "").split(os.pathsep):
            for exe in exe_names:
                candidate = Path(path) / exe
                if candidate.exists():
                    return str(candidate)
        return None

    # ---------- LLMProvider interface ----------

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
        del max_tokens, cache_system, cache_tools  # not applicable to CLI
        if tools:
            yield StreamEvent(
                kind="error",
                error=(
                    "CLI backend does not yet expose user-defined tools. "
                    "Switch backend.mode to 'api' for Execute mode, or "
                    "unset tools for a plain Answer call."
                ),
            )
            return

        if self.cli_path is None:
            yield StreamEvent(
                kind="error",
                error=(
                    "claude CLI not found on PATH. Install Claude Code or "
                    "set backend.cli_path in settings.yaml."
                ),
            )
            return

        prompt = self._flatten_messages(messages, system=system)
        cmd = self._build_command(prompt, model=model)
        log.info("launching claude CLI: %s", cmd[0])

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
        except OSError as exc:
            yield StreamEvent(kind="error", error=f"failed to spawn claude CLI: {exc}")
            return

        assert proc.stdout is not None

        # Drain stderr on a side thread so the buffer doesn't fill.
        stderr_lines: list[str] = []

        def _drain_stderr() -> None:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stderr_lines.append(line)

        t = threading.Thread(target=_drain_stderr, daemon=True)
        t.start()

        stop_reason: str | None = None
        try:
            for raw in proc.stdout:
                line = raw.strip()
                if not line:
                    continue
                event = self._parse_line(line)
                if event is None:
                    continue
                yield event
                if event.kind == "done":
                    stop_reason = event.stop_reason
                    break
                if event.kind == "error":
                    break
        finally:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        if proc.returncode not in (0, None) and stop_reason is None:
            err = ("".join(stderr_lines)[:1200]).strip() or f"exit code {proc.returncode}"
            yield StreamEvent(kind="error", error=f"claude CLI: {err}")

    def image_block(self, img: Image.Image) -> dict[str, Any]:
        """CLI backend cannot stream images; return a placeholder text block."""
        return {"type": "text", "text": "[image omitted — CLI backend does not carry screenshots]"}

    def text_block(self, text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    def tool_result_block(
        self,
        tool_use_id: str,
        content: list[dict[str, Any]] | str,
        is_error: bool = False,
    ) -> dict[str, Any]:
        """Not used in the no-tools CLI code path, but present for interface parity."""
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": is_error,
        }

    # ---------- helpers ----------

    def _build_command(self, prompt: str, model: str | None) -> list[str]:
        cmd = [self.cli_path or "claude", "-p", "--output-format", "stream-json", "--verbose"]
        if model:
            cmd.extend(["--model", model])
        payload_bytes = len(prompt.encode("utf-8"))
        if payload_bytes > MAX_STDIN_INLINE_BYTES:
            tmp_dir = self.settings.data_dir / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp = tmp_dir / "cli-prompt.txt"
            tmp.write_text(prompt, encoding="utf-8")
            cmd.extend(["--input-file", str(tmp)])
        else:
            cmd.append(prompt)
        return cmd

    @staticmethod
    def _flatten_messages(messages: list[Message], system: str | None) -> str:
        """Collapse multi-turn messages into a single prompt string.

        The CLI treats its ``-p`` argument as a single user prompt; it has
        no notion of an assistant history. We approximate by concatenating
        with clear role headers, dropping anything that isn't text.
        """
        parts: list[str] = []
        if system:
            parts.append(f"<system>\n{system}\n</system>")
        for m in messages:
            role = m.role.upper()
            content = m.content
            if isinstance(content, str):
                parts.append(f"<{role}>\n{content}\n</{role}>")
                continue
            text_fragments: list[str] = []
            for block in content or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_fragments.append(str(block.get("text", "")))
            if text_fragments:
                parts.append(f"<{role}>\n" + "\n".join(text_fragments) + f"\n</{role}>")
        return "\n\n".join(parts).strip()

    @staticmethod
    def _parse_line(line: str) -> StreamEvent | None:
        """Map a single Claude Agent stream-json line into our StreamEvent."""
        if not line.startswith("{"):
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None

        msg_type = data.get("type")
        if msg_type == "assistant":
            message = data.get("message") or {}
            content = message.get("content") or []
            text_pieces: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_pieces.append(str(block.get("text", "")))
            if text_pieces:
                return StreamEvent(kind="text_delta", text="".join(text_pieces))
        elif msg_type == "result":
            return StreamEvent(kind="done", stop_reason=data.get("subtype") or "end_turn")
        elif msg_type == "error":
            return StreamEvent(
                kind="error", error=str(data.get("message") or data.get("error") or "cli error")
            )
        return None
