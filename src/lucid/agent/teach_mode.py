"""Mode B: record user actions, summarise, save as a replayable workflow.

Lifecycle:
1. User submits a prompt in Teach mode. If it matches ``slug: description``
   the slug is captured up-front so the saved workflow is immediately
   addressable by name. Otherwise Claude proposes a slug during the
   post-recording summary.
2. Overlay is hidden by the controller so the recorder can see real user
   activity; mouse + keyboard events are captured via ``WorkflowRecorder``.
3. User presses the global hotkey again (or the kill switch) → ``stop`` is
   called from the UI thread; the run loop unblocks.
4. Claude turns the raw events into (a) a human-readable summary, and
   (b) a JSON block describing ``slug``, ``aliases``, ``variables``,
   ``tags``. Both are parsed defensively.
5. The enriched ``Workflow`` is persisted and registered so it can later
   be replayed by name: ``lucid run fatura_kes --var musteri=...``.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from lucid.capture import ContextSnapshot
from lucid.llm.provider import LLMProvider, Message
from lucid.recorder import WorkflowRecorder
from lucid.recorder.registry import WorkflowRegistry
from lucid.recorder.workflow import Workflow, WorkflowVariable, slugify

log = logging.getLogger("lucid.agent.teach")

SYSTEM_PROMPT = (
    "You are helping a user turn a raw desktop action log (mouse clicks, "
    "typed text, keyboard shortcuts, accessibility events) into a reusable, "
    "named workflow. Preserve accessibility names over raw coordinates and "
    "merge duplicated micro-events.\n\n"
    "Output format — STRICT:\n"
    "1. First a short human summary (2–6 lines) of what the workflow does.\n"
    "2. Then a single fenced ```json ... ``` block with this exact schema:\n"
    "   {\n"
    '     "slug": "short_snake_case_identifier",\n'
    '     "name": "Human readable name",\n'
    '     "aliases": ["create invoice", "new invoice"],\n'
    '     "target_app": "parasut.exe",\n'
    '     "tags": ["finance", "daily"],\n'
    '     "variables": [\n'
    '       {"name": "customer", "description": "Customer name", "example": "Acme Inc.", "required": true}\n'
    "     ]\n"
    "   }\n"
    "Rules:\n"
    "- Variables must cover every CONCRETE text the user typed that would "
    "differ on a future run (names, amounts, dates, file paths). Do NOT "
    "mark constant labels, menu items, or keyboard shortcuts as variables.\n"
    "- Aliases MUST include natural phrases a user would say to trigger the "
    "task (short, imperative, lowercase). Mirror the language the user spoke in.\n"
    "- Keep the slug under 40 characters, ASCII lowercase snake_case.\n"
    "- If the goal string from the user already begins with `<slug>:` then "
    "use that slug verbatim."
)


@dataclass
class _ParsedMetadata:
    slug: str = ""
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    target_app: str = ""
    tags: list[str] = field(default_factory=list)
    variables: list[WorkflowVariable] = field(default_factory=list)


class TeachMode:
    def __init__(self, settings, provider: LLMProvider) -> None:
        self.settings = settings
        self.provider = provider
        self._recorder: WorkflowRecorder | None = None
        self._stop_signal = threading.Event()
        self._running = threading.Event()
        self._cancel_flag = threading.Event()

    def is_recording(self) -> bool:
        return self._running.is_set() and not self._stop_signal.is_set()

    def stop(self) -> None:
        self._stop_signal.set()

    def cancel(self) -> None:
        self._cancel_flag.set()
        self._stop_signal.set()

    def run(
        self,
        prompt: str,
        snapshot: ContextSnapshot,
        cancel: threading.Event,
    ) -> Iterator[str]:
        self._cancel_flag = cancel
        self._stop_signal = threading.Event()
        self._running.set()

        user_slug, human_goal = _split_slug_prefix(prompt)
        if user_slug:
            yield f"Slug locked to: {user_slug}\n"

        yield "Recording started. Do the task now on screen.\n"
        yield f"Press the hotkey again to stop (max {self.settings.recorder.max_duration_seconds}s).\n"

        recorder_name = human_goal or prompt
        self._recorder = WorkflowRecorder(self.settings, name=recorder_name)
        self._recorder.start(initial_snapshot=snapshot)
        started = time.time()
        max_seconds = self.settings.recorder.max_duration_seconds

        try:
            while not cancel.is_set() and not self._stop_signal.is_set():
                if time.time() - started > max_seconds:
                    yield f"\nMax duration ({max_seconds}s) reached. Stopping.\n"
                    break
                time.sleep(0.15)
        finally:
            self._running.clear()

        workflow = self._recorder.stop()
        self._recorder = None

        if cancel.is_set():
            yield "\nRecording cancelled.\n"
            return

        yield f"\nCaptured {len(workflow.steps)} raw step(s). Summarising with Claude…\n\n"

        summary_buffer: list[str] = []
        for chunk in self._summarise(human_goal or prompt, workflow, cancel):
            summary_buffer.append(chunk)
            yield chunk

        summary_text = "".join(summary_buffer)
        metadata = _parse_metadata_block(summary_text)

        # Apply metadata onto the workflow.
        if metadata.name:
            workflow.name = metadata.name
        if user_slug:
            workflow.slug = user_slug
        elif metadata.slug:
            workflow.slug = slugify(metadata.slug) or slugify(metadata.name)
        else:
            workflow.slug = slugify(workflow.name)
        if metadata.aliases:
            workflow.aliases = metadata.aliases
        if metadata.target_app and not workflow.target_app:
            workflow.target_app = metadata.target_app
        if metadata.tags:
            workflow.tags = metadata.tags
        if metadata.variables:
            workflow.variables = metadata.variables

        path = workflow.save(self.settings.workflows_dir)
        try:
            registry = WorkflowRegistry(self.settings.workflows_dir)
            registry.add(workflow, path)
        except Exception as exc:
            log.debug("registry add failed: %s", exc)

        yield "\n\n"
        yield f"Workflow saved: {path}\n"
        yield f"Slug:          {workflow.slug}\n"
        if workflow.aliases:
            yield f"Aliases:       {', '.join(workflow.aliases)}\n"
        if workflow.variables:
            yield "Variables:\n"
            for v in workflow.variables:
                line = f"  - {v.name}: {v.description or '(no description)'}"
                if v.example:
                    line += f"  | example: {v.example}"
                yield line + "\n"
        example_cmd = "lucid run " + workflow.slug
        if workflow.variables:
            first = workflow.variables[0]
            example_cmd += f" --var {first.name}=\"{first.example or '…'}\""
        yield f"Run it with:  {example_cmd}\n"

    def _summarise(
        self,
        prompt: str,
        workflow: Workflow,
        cancel: threading.Event,
    ) -> Iterator[str]:
        if not workflow.steps:
            yield "(nothing recorded — no mouse or keyboard activity was captured)\n"
            return
        user_text = (
            f"User goal (as typed): {prompt}\n\n"
            f"Raw workflow JSON (trimmed to 20kB):\n{workflow.to_json()[:20000]}"
        )
        messages = [Message(role="user", content=[self.provider.text_block(user_text)])]
        for event in self.provider.stream(messages, system=SYSTEM_PROMPT, max_tokens=2048):
            if cancel.is_set():
                return
            if event.kind == "text_delta":
                yield event.text
            elif event.kind == "error":
                yield f"\n[error] {event.error}"
                return
            elif event.kind == "done":
                return


# ---------- helpers ----------

_SLUG_PREFIX_RE = re.compile(r"^\s*([a-zA-Z0-9_\-]{2,40})\s*:\s*(.+)$", re.DOTALL)


def _split_slug_prefix(prompt: str) -> tuple[str, str]:
    """Return ``(slug, remainder)`` when the prompt begins with ``slug: ``."""
    match = _SLUG_PREFIX_RE.match(prompt or "")
    if not match:
        return "", (prompt or "").strip()
    candidate = slugify(match.group(1))
    if not candidate:
        return "", (prompt or "").strip()
    return candidate, match.group(2).strip()


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_metadata_block(text: str) -> _ParsedMetadata:
    """Extract the last ```json { … } ``` block from Claude's summary."""
    matches = list(_JSON_BLOCK_RE.finditer(text or ""))
    if not matches:
        return _ParsedMetadata()
    raw = matches[-1].group(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _ParsedMetadata()
    if not isinstance(data, dict):
        return _ParsedMetadata()

    aliases = data.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = []
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []

    variables: list[WorkflowVariable] = []
    variables_raw = data.get("variables") or []
    if isinstance(variables_raw, list):
        for entry in variables_raw:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            variables.append(
                WorkflowVariable(
                    name=name,
                    description=str(entry.get("description") or "").strip(),
                    example=str(entry.get("example") or "").strip(),
                    required=bool(entry.get("required", True)),
                )
            )

    return _ParsedMetadata(
        slug=str(data.get("slug") or "").strip(),
        name=str(data.get("name") or "").strip(),
        aliases=[str(a).strip() for a in aliases if str(a).strip()],
        target_app=str(data.get("target_app") or "").strip(),
        tags=[str(t).strip() for t in tags if str(t).strip()],
        variables=variables,
    )
