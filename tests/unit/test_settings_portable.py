from __future__ import annotations

from pathlib import Path

from lucid.config.settings import Settings, _default_data_dir, _lucid_root


def test_lucid_root_points_at_project() -> None:
    root = _lucid_root()
    assert (root / "pyproject.toml").exists()


def test_default_data_dir_respects_env(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "override"
    monkeypatch.setenv("LUCID_DATA_DIR", str(override))
    # Clear cached settings so the override is honoured.
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    assert _default_data_dir() == override


def test_settings_paths_are_under_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LUCID_DATA_DIR", str(tmp_path))
    from lucid.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    s = Settings()
    assert s.data_dir == tmp_path
    assert s.screenshot_dir.parent == tmp_path
    assert s.memory_db_path.parent == tmp_path
    assert s.workflows_dir.parent == tmp_path
