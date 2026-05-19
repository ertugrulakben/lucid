"""`--resilient` should nudge the Execute budgets + the prompt prefix."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch


def _make_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        prompt="Do X then Y then Z.",
        template=None,
        var=None,
        image=None,
        timeout=180,
        max_steps=None,
        backend=None,
        json=False,
        no_memory=False,
        profile_ignore=False,
        resilient=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_resilient_raises_timeout_and_max_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LUCID_DATA_DIR", str(tmp_path))
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    from lucid import __main__ as lucid_main

    seen: dict = {}

    def _fake_run(options):
        seen["options"] = options
        return 0

    with patch("lucid.headless.run_headless", _fake_run):
        lucid_main._cmd_exec(_make_args(resilient=True))

    options = seen["options"]
    assert options.timeout == 600
    assert options.max_steps == 200
    assert options.prompt.startswith("[LONG-TASK MODE]")
    assert "Do X then Y then Z." in options.prompt


def test_resilient_respects_explicit_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LUCID_DATA_DIR", str(tmp_path))
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    from lucid import __main__ as lucid_main

    seen: dict = {}

    def _fake_run(options):
        seen["options"] = options
        return 0

    args = _make_args(resilient=True, timeout=900, max_steps=500)
    with patch("lucid.headless.run_headless", _fake_run):
        lucid_main._cmd_exec(args)

    options = seen["options"]
    assert options.timeout == 900
    assert options.max_steps == 500


def test_plain_exec_does_not_add_prefix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LUCID_DATA_DIR", str(tmp_path))
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    from lucid import __main__ as lucid_main

    seen: dict = {}

    def _fake_run(options):
        seen["options"] = options
        return 0

    with patch("lucid.headless.run_headless", _fake_run):
        lucid_main._cmd_exec(_make_args(resilient=False))

    options = seen["options"]
    assert not options.prompt.startswith("[LONG-TASK MODE]")
    assert options.timeout == 180
    assert options.max_steps is None
