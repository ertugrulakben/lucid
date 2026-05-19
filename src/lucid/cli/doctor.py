"""``lucid doctor`` -- self-diagnostic for the most common install issues.

Each check returns one of three levels:
    OK   -> green, no action needed
    WARN -> yellow, Lucid will probably still work but the user should know
    FAIL -> red, Lucid will not work as expected until the user fixes it

The check list is deliberately short and targets the issues that cause
the bulk of first-run support tickets:
    1. API key for the configured backend is reachable
    2. The global hotkey is not already claimed by another app
    3. Per-monitor DPI awareness is enabled (Windows)
    4. The data directory is writable
    5. The configured execute model can actually be requested
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from lucid import i18n

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass
class CheckResult:
    name: str
    label: str
    level: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "label": self.label,
            "level": self.level,
            "detail": self.detail,
        }


def run_doctor(json_output: bool = False) -> int:
    checks: list[CheckResult] = []

    for name, label_key, fn in (
        ("api_key", "doctor-check-api-key", _check_api_key),
        ("hotkey", "doctor-check-hotkey", _check_hotkey),
        ("dpi", "doctor-check-dpi", _check_dpi),
        ("permissions", "doctor-check-permissions", _check_data_dir),
        ("model", "doctor-check-model", _check_model),
    ):
        try:
            level, detail = fn()
        except Exception as exc:  # -- diagnostics must never crash
            level, detail = WARN, f"check raised {type(exc).__name__}: {exc}"
        checks.append(CheckResult(name=name, label=i18n._(label_key), level=level, detail=detail))

    if json_output:
        sys.stdout.write(json.dumps({"checks": [c.to_dict() for c in checks]}, indent=2))
        sys.stdout.write("\n")
    else:
        _print_human(checks)

    failed = sum(1 for c in checks if c.level == FAIL)
    return 0 if failed == 0 else 1


def _print_human(checks: list[CheckResult]) -> None:
    sys.stdout.write(i18n._("doctor-header") + "\n")
    sys.stdout.write("-" * 32 + "\n")
    badge = {
        OK: i18n._("doctor-ok"),
        WARN: i18n._("doctor-warn"),
        FAIL: i18n._("doctor-fail"),
    }
    for c in checks:
        line = f"[{badge[c.level]:>7}]  {c.label}"
        if c.detail:
            line += f"  -- {c.detail}"
        sys.stdout.write(line + "\n")
    failed = any(c.level == FAIL for c in checks)
    sys.stdout.write("-" * 32 + "\n")
    sys.stdout.write(i18n._("doctor-summary-fail" if failed else "doctor-summary-pass") + "\n")


# --------------------------------------------------------------------------- #
# individual checks
# --------------------------------------------------------------------------- #


def _check_api_key() -> tuple[str, str]:
    from lucid.config.settings import get_settings

    cfg = get_settings()
    mode = cfg.backend.mode
    if mode == "cli":
        return OK, "backend=cli (uses Claude Code subscription)"
    if mode == "lm_studio":
        return OK, f"backend=lm_studio at {cfg.backend.lm_studio_url}"
    if mode == "api":
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LUCID_ANTHROPIC_API_KEY"):
            return OK, "ANTHROPIC_API_KEY visible"
        try:
            from lucid.config.secrets import has_anthropic_key

            if has_anthropic_key():
                return OK, "key stored in keyring"
        except Exception:
            pass
        return FAIL, "no API key configured (run `lucid setup`)"
    return WARN, f"unknown backend mode: {mode}"


def _check_hotkey() -> tuple[str, str]:
    from lucid.config.settings import get_settings

    hotkey = get_settings().hotkey
    if not hotkey:
        return FAIL, "no hotkey configured"
    try:
        import keyboard  # type: ignore
    except Exception:
        return WARN, "`keyboard` package not installed (used to register hotkey)"
    try:
        handle = keyboard.add_hotkey(hotkey, lambda: None, suppress=False)
        keyboard.remove_hotkey(handle)
        return OK, f"`{hotkey}` is free"
    except Exception as exc:
        return WARN, f"could not test hotkey ({exc})"


def _check_dpi() -> tuple[str, str]:
    if sys.platform != "win32":
        return OK, "non-Windows; DPI awareness not required"
    try:
        import ctypes

        awareness = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
        if awareness.value >= 1:
            return OK, f"DPI awareness level {awareness.value}"
        return WARN, "process is DPI-unaware; clicks may miss on scaled displays"
    except Exception as exc:
        return WARN, f"could not query DPI awareness ({exc})"


def _check_data_dir() -> tuple[str, str]:
    from lucid.config.settings import get_settings

    data_dir = get_settings().data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return OK, f"writable: {data_dir}"
    except OSError as exc:
        return FAIL, f"cannot write to {data_dir} ({exc})"


def _check_model() -> tuple[str, str]:
    from lucid.config.settings import get_settings

    cfg = get_settings()
    model = cfg.execute_model or cfg.model
    if not model:
        return FAIL, "no model configured"
    if cfg.backend.mode in ("cli", "lm_studio"):
        return OK, f"backend={cfg.backend.mode}; model resolution deferred to backend"
    # Third-party / plugin backends manage their own model checks.
    from lucid.llm.registry import available_providers

    if cfg.backend.mode in available_providers() and cfg.backend.mode not in ("api", "anthropic"):
        return OK, f"backend={cfg.backend.mode}; model resolution deferred to backend"
    try:
        from anthropic import Anthropic  # type: ignore

        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LUCID_ANTHROPIC_API_KEY")
        if not api_key:
            return WARN, "skipping model probe (no API key visible to this process)"
        client = Anthropic(api_key=api_key)
        client.messages.create(
            model=model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return OK, f"model `{model}` is reachable"
    except Exception as exc:
        text = str(exc).lower()
        if "not_found" in text or "model" in text and "not" in text:
            return FAIL, f"model `{model}` rejected by API: {exc}"
        return WARN, f"could not verify model `{model}` ({type(exc).__name__})"


__all__ = ["run_doctor"]


# Compatibility shim: tests can supply a simple lambda by setting attribute names.
_check_api_key_fn: Callable[[], tuple[str, str]] | None = None
