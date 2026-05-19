from __future__ import annotations

import yaml

from lucid.config.settings import Settings, get_settings, write_settings


def test_default_settings_has_hotkey() -> None:
    s = Settings()
    assert s.hotkey == "ctrl+alt+j"
    assert s.provider == "anthropic"
    assert s.screenshot.max_width > 0


def test_get_settings_creates_yaml(tmp_path) -> None:
    s = get_settings()
    assert s.config_path.exists()
    data = yaml.safe_load(s.config_path.read_text(encoding="utf-8"))
    assert data["hotkey"] == "ctrl+alt+j"


def test_write_settings_roundtrip(tmp_path) -> None:
    s = Settings(config_path=tmp_path / "x.yaml", data_dir=tmp_path)
    s.hotkey = "ctrl+space"
    write_settings(s)
    data = yaml.safe_load((tmp_path / "x.yaml").read_text(encoding="utf-8"))
    assert data["hotkey"] == "ctrl+space"
