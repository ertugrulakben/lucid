"""GitHub Releases-based update check.

Deliberately small: a single HTTP GET, a version comparison, and a
download URL on hit. Lucid does NOT auto-elevate or replace the running
binary. Anything destructive is left to the user (or to a separate
installer once a signing certificate is available).

API contract:
    check_for_update(current="0.1.0") -> UpdateInfo | None

The default repository is read from ``settings.updater.channel`` and
the well-known repo ``ertugrulakben/lucid``. Override via
``LUCID_UPDATE_REPO`` (e.g. for pre-release forks during QA).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("lucid.updater")

DEFAULT_REPO = "ertugrulakben/lucid"
RELEASE_URL_TEMPLATE = "https://api.github.com/repos/{repo}/releases/latest"
PRERELEASES_URL_TEMPLATE = "https://api.github.com/repos/{repo}/releases?per_page=5"


@dataclass
class UpdateInfo:
    version: str
    download_url: Optional[str]
    notes: str
    channel: str
    asset_size: Optional[int] = None


def check_for_update(
    current: str,
    *,
    settings: object | None = None,
    timeout_seconds: float = 5.0,
) -> Optional[UpdateInfo]:
    """Return :class:`UpdateInfo` when a newer release exists, else ``None``."""
    if not _is_enabled(settings):
        return None
    repo = os.environ.get("LUCID_UPDATE_REPO") or DEFAULT_REPO
    channel = _channel(settings)
    url = (
        PRERELEASES_URL_TEMPLATE.format(repo=repo)
        if channel == "beta"
        else RELEASE_URL_TEMPLATE.format(repo=repo)
    )

    try:
        import httpx  # type: ignore

        response = httpx.get(url, timeout=timeout_seconds, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 -- updater must never block startup
        log.info("update check skipped: %s", exc)
        return None

    candidate = _pick_release(payload, channel)
    if candidate is None:
        return None

    tag = (candidate.get("tag_name") or "").lstrip("v")
    if not tag:
        return None
    if not _is_newer(tag, current):
        return None

    asset = _pick_windows_installer(candidate)
    return UpdateInfo(
        version=tag,
        download_url=asset.get("browser_download_url") if asset else None,
        notes=(candidate.get("body") or "")[:2000],
        channel=channel,
        asset_size=asset.get("size") if asset else None,
    )


def _pick_release(payload: object, channel: str) -> dict | None:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            if channel == "beta" or not entry.get("prerelease"):
                return entry
    return None


def _pick_windows_installer(release: dict) -> dict | None:
    for asset in release.get("assets") or []:
        name = (asset.get("name") or "").lower()
        if name.endswith(".exe"):
            return asset
    return None


def _is_newer(remote: str, current: str) -> bool:
    try:
        from packaging.version import Version  # type: ignore

        return Version(remote) > Version(current)
    except Exception:  # noqa: BLE001 -- packaging may be missing in slim installs
        return _naive_version_compare(remote, current) > 0


def _naive_version_compare(a: str, b: str) -> int:
    def parts(v: str) -> list[int]:
        out: list[int] = []
        for chunk in v.split("."):
            head = "".join(ch for ch in chunk if ch.isdigit())
            out.append(int(head) if head else 0)
        return out

    pa, pb = parts(a), parts(b)
    while len(pa) < len(pb):
        pa.append(0)
    while len(pb) < len(pa):
        pb.append(0)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def _is_enabled(settings: object | None) -> bool:
    if settings is None:
        try:
            from lucid.config.settings import get_settings

            settings = get_settings()
        except Exception:  # noqa: BLE001
            return True
    updater = getattr(settings, "updater", None)
    if updater is None:
        return True
    return bool(getattr(updater, "enabled", True))


def _channel(settings: object | None) -> str:
    if settings is None:
        try:
            from lucid.config.settings import get_settings

            settings = get_settings()
        except Exception:  # noqa: BLE001
            return "stable"
    updater = getattr(settings, "updater", None)
    if updater is None:
        return "stable"
    return str(getattr(updater, "channel", "stable") or "stable")
