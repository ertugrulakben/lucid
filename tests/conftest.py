"""Shared pytest fixtures and env setup."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect settings and screenshot dirs into a tmp folder for every test."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path / "tmp"))
    monkeypatch.setenv("LUCID_ANTHROPIC_API_KEY", "test-key")
    (tmp_path / "tmp").mkdir(parents=True, exist_ok=True)
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()


@pytest.fixture
def tmp_settings(tmp_path: Path):
    from lucid.config.settings import Settings

    s = Settings(config_path=tmp_path / "settings.yaml", data_dir=tmp_path)
    return s
