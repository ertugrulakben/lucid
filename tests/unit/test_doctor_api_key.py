"""`lucid doctor` API-key check and model probe must match what the client reads.

The client resolves the key through ``secrets.get_secret``: OS keyring first,
then ``LUCID_ANTHROPIC_API_KEY``. A plain ``ANTHROPIC_API_KEY`` is ignored.
"""

from __future__ import annotations

import pytest

from lucid.cli import doctor


@pytest.fixture
def api_mode_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default settings use backend.mode == "api"; start with no key anywhere.
    monkeypatch.delenv("LUCID_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("keyring.get_password", lambda service, name: None)


def test_key_in_keyring_passes(api_mode_no_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keyring.get_password", lambda service, name: "dummy-key")
    status, _ = doctor._check_api_key()
    assert status == doctor.OK


def test_lucid_env_fallback_passes(api_mode_no_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUCID_ANTHROPIC_API_KEY", "dummy-key")
    status, _ = doctor._check_api_key()
    assert status == doctor.OK


def test_plain_anthropic_env_is_not_enough(
    api_mode_no_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    status, _ = doctor._check_api_key()
    assert status == doctor.FAIL


def test_model_probe_uses_the_same_key_source(
    api_mode_no_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    class FakeAnthropic:
        def __init__(self, api_key: str | None = None, **_: object) -> None:
            seen["key"] = api_key
            self.messages = self

        def create(self, **_: object) -> None:
            return None

    monkeypatch.setattr("anthropic.Anthropic", FakeAnthropic)
    monkeypatch.setattr("keyring.get_password", lambda service, name: "dummy-key")
    status, _ = doctor._check_model()
    assert status == doctor.OK
    assert seen["key"] == "dummy-key"


def test_model_probe_skips_on_plain_anthropic_env(
    api_mode_no_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[object] = []
    monkeypatch.setattr("anthropic.Anthropic", lambda **kwargs: created.append(kwargs))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    status, _ = doctor._check_model()
    assert status == doctor.WARN
    assert created == []
