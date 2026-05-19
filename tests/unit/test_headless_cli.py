"""Smoke tests for the ``lucid`` CLI entry points (no Anthropic calls)."""

from __future__ import annotations

import subprocess
import sys


def _run_cli(*args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-m", "lucid", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


def test_version_flag() -> None:
    rc, out, _ = _run_cli("--version")
    assert rc == 0
    assert out.lower().startswith("lucid")


def test_templates_list_includes_send_gmail() -> None:
    rc, out, _ = _run_cli("templates")
    assert rc == 0
    assert "send_gmail" in out


def test_exec_without_prompt_or_template_errors() -> None:
    rc, out, _ = _run_cli("exec")
    assert rc == 2
    assert "template" in out.lower() or "prompt" in out.lower()
