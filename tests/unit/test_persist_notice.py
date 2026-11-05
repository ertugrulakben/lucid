"""Start-up notice while screenshot.persist is on; the settings file is never rewritten."""

from __future__ import annotations

import logging
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


def _tray(supports_messages: bool = True) -> tuple[SimpleNamespace, list[tuple]]:
    shown: list[tuple] = []
    tray = SimpleNamespace(
        showMessage=lambda *args: shown.append(args), supportsMessages=lambda: supports_messages
    )
    return tray, shown


def _persisting(data_dir: Path, hours: int) -> Settings:
    settings = Settings(data_dir=data_dir)
    settings.screenshot.persist = True
    settings.screenshot.retention_hours = hours
    return settings


@pytest.fixture(autouse=True)
def _english_and_no_settings_writes(monkeypatch: pytest.MonkeyPatch):
    def refuse(_settings: Settings) -> None:
        raise AssertionError("the notice must not rewrite settings.yaml")

    monkeypatch.setattr(settings_module, "write_settings", refuse)
    i18n.init("en")
    yield
    i18n.init("en")


def test_notice_when_persist_is_on(tmp_path: Path) -> None:
    tray, shown = _tray()
    assert app_module._notify_persist(tray, _persisting(tmp_path, 12)) is True  # type: ignore[arg-type]
    title, body, _icon, timeout = shown[0]
    assert "screenshots are kept" in title
    assert "12 hours" in _plain(body)
    assert timeout == 10000


@pytest.mark.parametrize(
    "hours, expected", [(0, "until you delete it"), (-5, "until you delete it"), (1, "1 hour.")]
)
def test_notice_wording_for_zero_and_one_hour(tmp_path: Path, hours: int, expected: str) -> None:
    tray, shown = _tray()
    app_module._notify_persist(tray, _persisting(tmp_path, hours))  # type: ignore[arg-type]
    assert expected in _plain(shown[0][1])


def test_no_notice_when_persist_is_off(tmp_path: Path) -> None:
    tray, shown = _tray()
    assert app_module._notify_persist(tray, Settings(data_dir=tmp_path)) is False  # type: ignore[arg-type]
    assert shown == []


def test_without_tray_messages_the_warning_still_reaches_the_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    tray, shown = _tray(supports_messages=False)
    with caplog.at_level(logging.WARNING, logger="lucid.app"):
        shown_now = app_module._notify_persist(tray, _persisting(tmp_path, 24))  # type: ignore[arg-type]
    assert shown_now is False
    assert shown == []
    assert "screenshot.persist is on" in caplog.text


def test_notice_is_in_turkish_too() -> None:
    i18n.init("tr")
    title = i18n._("tray-persist-on-title")
    assert "ekran görüntüleri" in title
    assert "24 saat" in _plain(i18n._("tray-persist-on-body", hours=24))
    assert "silene kadar saklanıyor" in _plain(i18n._("tray-persist-on-body", hours=0))
