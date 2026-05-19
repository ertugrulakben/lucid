"""`lucid status` implementation.

Prints a short health card: running instance, data paths, memory counts,
current backend/model, and the most recent task patterns. JSON mode
returns the same data as a single dict on stdout.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("lucid.status")


def _running_lucid_processes() -> list[dict[str, Any]]:
    if sys.platform != "win32":
        return []
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return []

    results: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "exe"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "lucid" in cmdline.lower() and "python" in (proc.info.get("name") or "").lower():
            results.append(
                {
                    "pid": proc.info["pid"],
                    "cmdline": cmdline,
                    "exe": proc.info.get("exe"),
                }
            )
    return results


def _memory_counts(settings) -> dict[str, int]:
    if not settings.memory.enabled or not settings.memory_db_path.exists():
        return {}
    try:
        from lucid.memory.store import MemoryStore

        store = MemoryStore(settings.memory_db_path)
        stats = store.stats()
        store.close()
        return stats
    except Exception as exc:  # noqa: BLE001  # diagnostic helper, never fatal
        log.debug("memory stats unavailable: %s", exc)
        return {}


def _workflow_count(settings) -> int:
    d: Path = settings.workflows_dir
    if not d.exists():
        return 0
    return len(list(d.glob("*.json")))


def _collect_status() -> dict[str, Any]:
    from lucid.config.profile import get_profile
    from lucid.config.settings import get_settings

    settings = get_settings()
    profile = get_profile(settings)

    return {
        "version": _lucid_version(),
        "hotkey": settings.hotkey,
        "backend": settings.backend.mode,
        "answer_model": settings.model,
        "execute_model": settings.execute_model,
        "data_dir": str(settings.data_dir),
        "config_path": str(settings.config_path),
        "profile_path": str(settings.profile_path),
        "profile_complete": profile.is_complete(),
        "profile_name": profile.name,
        "memory_enabled": settings.memory.enabled,
        "memory_db": str(settings.memory_db_path) if settings.memory_db_path.exists() else "",
        "memory_counts": _memory_counts(settings),
        "workflows_dir": str(settings.workflows_dir),
        "workflows_count": _workflow_count(settings),
        "running_instances": _running_lucid_processes(),
        "cwd": os.getcwd(),
    }


def _lucid_version() -> str:
    try:
        from lucid import __version__

        return __version__
    except Exception as exc:  # noqa: BLE001
        log.debug("version probe failed: %s", exc)
        return "unknown"


def print_status(json_output: bool = False) -> int:
    data = _collect_status()
    if json_output:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"Lucid {data['version']}")
    print(f"  hotkey:         {data['hotkey']}")
    print(f"  backend:        {data['backend']}")
    print(f"  answer model:   {data['answer_model']}")
    print(f"  execute model:  {data['execute_model']}")
    print(f"  data dir:       {data['data_dir']}")
    print(f"  settings:       {data['config_path']}")
    print(
        f"  profile:        {data['profile_path']}  "
        f"{'(complete)' if data['profile_complete'] else '(placeholder)'}"
    )
    if data["profile_complete"]:
        print(f"  profile name:   {data['profile_name']}")
    print(f"  memory enabled: {data['memory_enabled']}")
    counts = data.get("memory_counts") or {}
    if counts:
        joined = ", ".join(f"{k}={v}" for k, v in counts.items())
        print(f"  memory counts:  {joined}")
    print(f"  workflows:      {data['workflows_count']} in {data['workflows_dir']}")
    running = data.get("running_instances") or []
    if running:
        print(f"  running:        {len(running)} process(es)")
        for proc in running[:5]:
            print(f"    pid {proc['pid']}")
    else:
        print("  running:        none")
    return 0
