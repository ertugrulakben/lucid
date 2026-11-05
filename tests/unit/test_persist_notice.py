"""Start-up notice while screenshot.persist is on; the settings file is never rewritten."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("fluent.runtime")

from lucid import app as app_module  # noqa: E402
from lucid import i18n  # noqa: E402
from lucid.config import settings as settings_module  # noqa: E402
from lucid.config.settings import Settings  # noqa: E402


def _plain(text: str) -> str:
    """Drop the Unicode isolation marks Fluent may put around placeables."""
    return text.replace("⁨", "").replace("⁩", "")


def _tray() -> tuple[SimpleNamespace, list[tuple]]:
    shown: list[tuple] = []
    return SimpleNamespace(showMessage=lambda *args: shown.append(args)), shown


@pytest.fixture(autouse=True)
def _no_settings_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_settings: Settings) -> None:
        raise AssertionError("the notice must not rewrite settings.yaml")

    monkeypatch.setattr(settings_module, "write_settings", refuse)


def test_notice_when_persist_is_on(tmp_path: Path) -> None:
    i18n.init("en")
    tray, shown = _tray()
    settings = Settings(data_dir=tmp_path)
    settings.screenshot.persist = True
    settings.screenshot.retention_hours = 12
    assert app_module._notify_persist(tray, settings) is True  # type: ignore[arg-type]
    title, body, _icon, timeout = shown[0]
    assert "screenshots are kept" in title
    assert "12 hours" in _plain(body)
    assert timeout == 10000


def test_no_notice_when_persist_is_off(tmp_path: Path) -> None:
    tray, shown = _tray()
    assert app_module._notify_persist(tray, Settings(data_dir=tmp_path)) is False  # type: ignore[arg-type]
    assert shown == []


@pytest.mark.parametrize("locale", ["en", "tr"])
def test_notice_is_translated(locale: str) -> None:
    i18n.init(locale)
    try:
        assert i18n._("tray-persist-on-title") != "tray-persist-on-title"
        assert "24" in _plain(i18n._("tray-persist-on-body", hours=24))
    finally:
        i18n.init("en")
