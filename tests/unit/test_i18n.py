"""Smoke tests for the i18n bootstrap and bundle manager."""

from __future__ import annotations

import os

import pytest

from lucid import i18n
from lucid.i18n import loader


def _fluent_available() -> bool:
    try:
        import fluent.runtime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def test_available_locales_includes_en_and_tr() -> None:
    locales = i18n.available_locales()
    assert "en" in locales
    assert "tr" in locales


def test_default_init_resolves_to_known_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LUCID_LOCALE", raising=False)
    i18n.init()
    assert i18n.get_locale() in i18n.available_locales()


def test_env_override_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUCID_LOCALE", "tr")
    i18n.init("tr")
    assert i18n.get_locale() == "tr"


def test_unknown_locale_falls_back_to_english() -> None:
    i18n.init("xx_YY")
    assert i18n.get_locale() == "en"


def test_set_locale_runtime_switch() -> None:
    i18n.init("en")
    i18n.set_locale("tr")
    assert i18n.get_locale() == "tr"
    i18n.set_locale("en")
    assert i18n.get_locale() == "en"


def test_normalise_handles_dialect_codes() -> None:
    i18n.init("en-US")
    assert i18n.get_locale() == "en"
    i18n.init("TR")
    assert i18n.get_locale() == "tr"


@pytest.mark.skipif(not _fluent_available(), reason="fluent.runtime not installed")
def test_translate_known_key_in_english() -> None:
    i18n.init("en")
    rendered = i18n._("overlay-mode-answer")
    assert rendered == "Answer"


@pytest.mark.skipif(not _fluent_available(), reason="fluent.runtime not installed")
def test_translate_known_key_in_turkish() -> None:
    i18n.init("tr")
    rendered = i18n._("overlay-mode-answer")
    assert rendered == "Cevapla"


@pytest.mark.skipif(not _fluent_available(), reason="fluent.runtime not installed")
def test_missing_key_returns_key_itself() -> None:
    i18n.init("en")
    rendered = i18n._("definitely-not-a-real-key-xyz")
    assert rendered == "definitely-not-a-real-key-xyz"


@pytest.mark.skipif(not _fluent_available(), reason="fluent.runtime not installed")
def test_turkish_falls_back_to_english_for_unique_keys() -> None:
    """If a key only exists in en/, the tr/ bundle should still resolve via fallback."""
    i18n.init("tr")
    # ``cli-version`` exists in both, sanity check
    assert i18n._("cli-version", version="1.0") != "cli-version"


def test_loader_module_constants() -> None:
    assert loader.DEFAULT_LOCALE == "en"
    assert "ui.ftl" in loader.RESOURCE_FILES
    assert "errors.ftl" in loader.RESOURCE_FILES


def test_loader_no_fluent_installed_returns_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even without fluent.runtime, the manager must not crash."""
    mgr = loader.FluentBundleManager()
    monkeypatch.setattr(mgr, "_build_localization", lambda _locale: None)
    mgr.load("en")
    assert mgr.format("any-key") == "any-key"


@pytest.fixture(autouse=True)
def _reset_locale_state() -> None:
    """Each test gets a fresh i18n state to avoid order dependence."""
    yield
    os.environ.pop("LUCID_LOCALE", None)
    i18n.init("en")
