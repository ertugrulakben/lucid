"""`lucid replay <path>` and `lucid run <slug>` implementations.

``run_replay`` handles both modes: if the first argument resolves to an
existing file we replay that path; otherwise we look it up in the
registry as a slug / alias. Variables from the command line are merged
with any defaults the workflow itself declares.
"""

from __future__ import annotations

import json
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any


def _emit(text: str, json_output: bool, stream: str = "progress") -> None:
    if not text:
        return
    if json_output:
        print(json.dumps({"stream": stream, "text": text}, ensure_ascii=False), flush=True)
    else:
        sys.stdout.write(text)
        sys.stdout.flush()


def _resolve_workflow(target: str, workflows_dir: Path) -> tuple[Path | None, str | None]:
    """Return ``(path, error)`` for a file path or a registry slug/alias."""
    from lucid.recorder.registry import WorkflowRegistry

    candidate = Path(target)
    if candidate.exists() and candidate.is_file():
        return candidate, None

    registry = WorkflowRegistry(workflows_dir)
    entry = registry.find(target)
    if entry is None:
        return None, f"no workflow matching {target!r} (registry empty or no alias hit)"
    path = workflows_dir / entry.path if not Path(entry.path).is_absolute() else Path(entry.path)
    if not path.exists():
        return None, f"registry entry points at missing file: {path}"
    return path, None


def run_replay(
    workflow_path: Path | str,
    timeout: int = 180,
    json_output: bool = False,
    variables: dict[str, str] | None = None,
) -> int:
    from lucid.config.settings import get_settings
    from lucid.executor import install_kill_switch
    from lucid.llm.provider import create_provider
    from lucid.recorder.workflow import load_workflow
    from lucid.replayer.semantic_replay import SemanticReplayer

    settings = get_settings()
    target_str = str(workflow_path)
    resolved_path, error = _resolve_workflow(target_str, settings.workflows_dir)
    if error or resolved_path is None:
        _emit(f"[error] {error}\n", json_output, stream="error")
        return 1

    try:
        workflow = load_workflow(resolved_path)
    except Exception as exc:
        _emit(f"[error] failed to load workflow: {exc}\n", json_output, stream="error")
        return 1

    merged_vars = dict(variables or {})
    missing = [v.name for v in workflow.variables if v.required and v.name not in merged_vars]
    if missing:
        _emit(
            f"[error] missing required variable(s): {', '.join(missing)}\n"
            f"        pass via --var NAME=VALUE\n",
            json_output,
            stream="error",
        )
        return 2

    provider = create_provider(settings)
    replayer = SemanticReplayer(settings, provider)

    cancel = threading.Event()
    kill_unreg = install_kill_switch(settings.safety.kill_switch_hotkey, cancel)

    def _on_sigint(*_: Any) -> None:
        cancel.set()

    signal.signal(signal.SIGINT, _on_sigint)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _on_sigint)  # type: ignore[attr-defined]

    deadline = time.time() + max(10, int(timeout))

    def _watchdog() -> None:
        while not cancel.is_set():
            if time.time() >= deadline:
                cancel.set()
                return
            time.sleep(0.25)

    threading.Thread(target=_watchdog, daemon=True, name="lucid-replay-watchdog").start()

    exit_code = 0
    try:
        _emit(
            f"[start] replaying {workflow.slug or workflow.name} "
            f"({len(workflow.steps)} steps)\n",
            json_output,
            stream="meta",
        )
        for chunk in replayer.run(workflow, cancel, variables=merged_vars):
            _emit(chunk, json_output)
            if cancel.is_set():
                break
        if cancel.is_set():
            if time.time() >= deadline:
                exit_code = 124
                _emit("\n[timeout]\n", json_output, stream="meta")
            else:
                exit_code = 2
                _emit("\n[cancelled]\n", json_output, stream="meta")
        else:
            _emit("\n[done]\n", json_output, stream="meta")
    except Exception as exc:
        _emit(f"[crash] {exc}\n", json_output, stream="error")
        exit_code = 1
    finally:
        if kill_unreg is not None:
            try:
                kill_unreg()
            except Exception:
                pass
    return exit_code
