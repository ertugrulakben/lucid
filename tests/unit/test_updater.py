"""Tests for the GitHub-Releases auto-updater."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from lucid.updater.check import (
    _is_newer,
    _naive_version_compare,
    _pick_release,
    _pick_windows_installer,
    check_for_update,
)


class _FakeResponse:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")

    def json(self) -> Any:
        return self._payload


def _settings(enabled: bool = True, channel: str = "stable") -> SimpleNamespace:
    return SimpleNamespace(updater=SimpleNamespace(enabled=enabled, channel=channel))


def test_naive_version_compare() -> None:
    assert _naive_version_compare("1.0.0", "0.9.9") == 1
    assert _naive_version_compare("0.1.0", "0.1.0") == 0
    assert _naive_version_compare("0.1.0", "0.1.1") == -1
    assert _naive_version_compare("1.10.0", "1.9.0") == 1  # numeric, not lexical


def test_is_newer_strips_v_prefix() -> None:
    assert _is_newer("1.0.0", "0.1.0") is True
    assert _is_newer("0.1.0", "1.0.0") is False
    assert _is_newer("0.1.0", "0.1.0") is False


def test_pick_windows_installer_returns_first_exe() -> None:
    release = {
        "assets": [
            {"name": "Lucid-Setup-1.0.0.zip", "browser_download_url": "url-zip"},
            {"name": "Lucid-Setup-1.0.0.exe", "browser_download_url": "url-exe", "size": 12345},
        ]
    }
    asset = _pick_windows_installer(release)
    assert asset["name"] == "Lucid-Setup-1.0.0.exe"
    assert asset["size"] == 12345


def test_pick_windows_installer_handles_no_assets() -> None:
    assert _pick_windows_installer({}) is None
    assert _pick_windows_installer({"assets": []}) is None


def test_pick_release_dict_returned_as_is() -> None:
    payload = {"tag_name": "v1.0.0"}
    assert _pick_release(payload, "stable") is payload


def test_pick_release_list_skips_prerelease_in_stable() -> None:
    payload = [
        {"tag_name": "v1.0.0-rc1", "prerelease": True},
        {"tag_name": "v0.9.0", "prerelease": False},
    ]
    chosen = _pick_release(payload, "stable")
    assert chosen["tag_name"] == "v0.9.0"


def test_pick_release_list_accepts_prerelease_in_beta() -> None:
    payload = [
        {"tag_name": "v1.0.0-rc1", "prerelease": True},
        {"tag_name": "v0.9.0", "prerelease": False},
    ]
    chosen = _pick_release(payload, "beta")
    assert chosen["tag_name"] == "v1.0.0-rc1"


def test_check_for_update_returns_info_when_remote_is_newer(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "tag_name": "v1.0.0",
        "body": "Big release notes here.",
        "prerelease": False,
        "assets": [
            {"name": "Lucid-Setup-1.0.0.exe", "browser_download_url": "https://x/y.exe", "size": 99},
        ],
    }
    _install_fake_httpx(monkeypatch, payload)

    info = check_for_update("0.1.0", settings=_settings())
    assert info is not None
    assert info.version == "1.0.0"
    assert info.download_url == "https://x/y.exe"
    assert info.asset_size == 99


def test_check_for_update_returns_none_when_already_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"tag_name": "v0.1.0", "body": "", "prerelease": False, "assets": []}
    _install_fake_httpx(monkeypatch, payload)
    assert check_for_update("0.1.0", settings=_settings()) is None


def test_check_for_update_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_httpx(monkeypatch, {"tag_name": "v9.9.9"})
    assert check_for_update("0.1.0", settings=_settings(enabled=False)) is None


def test_check_for_update_swallows_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("network down")

    monkeypatch.setattr("httpx.get", _boom)
    assert check_for_update("0.1.0", settings=_settings()) is None


def _install_fake_httpx(monkeypatch: pytest.MonkeyPatch, payload: Any) -> None:
    def _fake_get(_url: str, **_kw: Any) -> _FakeResponse:
        return _FakeResponse(payload)

    monkeypatch.setattr("httpx.get", _fake_get)
