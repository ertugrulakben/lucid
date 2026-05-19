"""Headless Execute runner used by ``lucid exec "<task>"``.

The entry point any external script (or CI job) calls when it wants Lucid
to perform a desktop task without the GUI overlay. We deliberately avoid
importing PySide6 from this path so a Qt-less environment (e.g. CI matrix
run) can still exercise the action pipeline.

Exit codes:
    0 = task completed normally
    1 = Claude or the executor reported an error
    2 = user cancelled via kill-switch
  124 = wall-clock timeout expired
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("lucid.headless")


@dataclass
class HeadlessOptions:
    prompt: str
    timeout: int = 180
    max_steps: int | None = None
    backend: str | None = None
    json_output: bool = False
    disable_memory: bool = False
    disable_profile: bool = False
    show_overlay: bool = False
    # Extra images to attach as visual context alongside the live desktop
    # snapshot — e.g. a reference screenshot the user wants Lucid to
    # reproduce ("do this exact thing").
    attachments: list[Path] = field(default_factory=list)


def _load_dependencies(options: HeadlessOptions):
    """Import heavy deps only now so `lucid --version` stays instant."""
    from lucid.agent.conversation import Conversation  # noqa: F401  (kept for parity)
    from lucid.agent.execute_mode import ExecuteMode
    from lucid.capture import ContextSnapshot
    from lucid.config.settings import get_settings
    from lucid.executor import install_kill_switch
    from lucid.llm.provider import create_provider

    settings = get_settings()
    if options.backend:
        settings.backend.mode = options.backend
    if options.max_steps is not None:
        settings.executor.max_steps = options.max_steps
    if options.disable_memory:
        settings.memory.enabled = False

    provider = create_provider(settings)
    executor_mode = ExecuteMode(settings, provider)
    return settings, provider, executor_mode, ContextSnapshot, install_kill_switch


def _emit(line: str, json_output: bool, stream: str = "progress", **extra: Any) -> None:
    if not line and not extra:
        return
    if json_output:
        payload = {"stream": stream, "text": line}
        if extra:
            payload.update(extra)
        print(json.dumps(payload, ensure_ascii=False), flush=True)
    else:
        sys.stdout.write(line)
        sys.stdout.flush()


def _load_attachments(paths: list[Path], json_output: bool) -> list:
    """Open each attachment as a PIL image. Skip (with a warning) on failure."""
    from PIL import Image, UnidentifiedImageError

    loaded = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            _emit(
                f"[warn] attachment not found: {path}\n",
                json_output,
                stream="warn",
            )
            continue
        try:
            img = Image.open(path).convert("RGB")
            loaded.append((path, img))
        except (UnidentifiedImageError, OSError) as exc:
            _emit(
                f"[warn] could not load attachment {path}: {exc}\n",
                json_output,
                stream="warn",
            )
    return loaded


def run_headless(options: HeadlessOptions) -> int:
    settings, provider, execute_mode, ContextSnapshot, install_kill_switch = _load_dependencies(
        options
    )

    cancel = threading.Event()
    kill_unreg = install_kill_switch(settings.safety.kill_switch_hotkey, cancel)

    def _on_sigint(*_: Any) -> None:
        cancel.set()

    signal.signal(signal.SIGINT, _on_sigint)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _on_sigint)  # type: ignore[attr-defined]

    snapshot = ContextSnapshot.capture(settings)
    attachments = _load_attachments(options.attachments, options.json_output)
    if attachments:
        paths = ", ".join(str(p) for p, _ in attachments)
        _emit(
            f"[attachments] {len(attachments)} image(s) loaded: {paths}\n",
            options.json_output,
            stream="meta",
        )
    attachment_images = [img for _, img in attachments]

    started = time.time()
    deadline = started + max(10, int(options.timeout))

    buffer: list[str] = []
    exit_code = 0
    timed_out = False

    try:

        def _watchdog() -> None:
            while not cancel.is_set():
                if time.time() >= deadline:
                    cancel.set()
                    return
                time.sleep(0.25)

        watchdog = threading.Thread(target=_watchdog, daemon=True, name="lucid-headless-watchdog")
        watchdog.start()

        _emit(f"[start] {options.prompt}\n", options.json_output, stream="meta")
        for chunk in execute_mode.run(
            options.prompt, snapshot, cancel, attachments=attachment_images
        ):
            buffer.append(chunk)
            _emit(chunk, options.json_output)
            if cancel.is_set():
                break

        if cancel.is_set():
            if time.time() >= deadline:
                timed_out = True
                exit_code = 124
                _emit("\n[timeout] max duration exceeded\n", options.json_output, stream="meta")
            else:
                exit_code = 2
                _emit("\n[cancelled] kill switch / SIGINT\n", options.json_output, stream="meta")
        else:
            text = "".join(buffer)
            if "[error]" in text:
                exit_code = 1
            _emit(
                f"\n[done] elapsed {int(time.time() - started)}s\n",
                options.json_output,
                stream="meta",
                timed_out=timed_out,
                exit_code=exit_code,
            )
    except Exception as exc:
        log.exception("headless run failed")
        _emit(f"\n[crash] {exc}\n", options.json_output, stream="error")
        exit_code = 1
    finally:
        if kill_unreg is not None:
            try:
                kill_unreg()
            except Exception:
                pass

    return exit_code
