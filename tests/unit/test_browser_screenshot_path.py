"""browser_screenshot never writes outside the screenshots folder (G-Güvenlik-53).

The page, and a prompt injection in it, can steer the model's ``path``; whatever it
says, the file lands in settings.screenshot_dir under a name retention recognises.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("playwright")

from lucid.actions import registry
from lucid.actions.browser import ops
from lucid.config.settings import Settings
from lucid.privacy import LUCID_NAMES

STAMP = "20260101-000000"


@pytest.mark.parametrize(
    "requested",
    [
        "C:\\Users\\someone\\Documents\\report.docx",
        "C:report.png",  # drive-relative
        "/etc/passwd",
        "\\\\server\\share\\shot.png",  # UNC
        "..\\shot.png",
        "../shot.png",
        "..",
        ".",
        "sub/shot.png",
        "sub\\shot.png",
        "shot.png:hidden",  # alternate data stream
    ],
)
def test_unsafe_paths_are_refused(tmp_path: Path, requested: str) -> None:
    with pytest.raises(registry.ActionError, match="plain file name"):
        ops._screenshot_target(tmp_path, requested, STAMP)


@pytest.mark.parametrize(
    "requested, expected",
    [
        (None, "browser-20260101-000000.png"),
        ("   ", "browser-20260101-000000.png"),
        ("checkout.png", "browser-20260101-000000-checkout.png"),
        ("Sepet Özeti.JPG", "browser-20260101-000000-sepet_zeti.png"),
        ("~", "browser-20260101-000000.png"),
    ],
)
def test_plain_names_land_in_the_folder_under_lucids_pattern(
    tmp_path: Path, requested: str | None, expected: str
) -> None:
    target = ops._screenshot_target(tmp_path, requested, STAMP)
    assert target == tmp_path / expected
    assert LUCID_NAMES["screenshots"].fullmatch(target.name)


def _link_dir(link: Path, target: Path) -> None:
    """A junction on Windows (no privilege needed), a symlink elsewhere; skips when not allowed."""
    try:
        if sys.platform == "win32":
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)
    except (OSError, ImportError, AttributeError) as exc:
        pytest.skip(f"cannot create a directory link here: {exc}")


def test_an_existing_file_is_never_overwritten(tmp_path: Path) -> None:
    earlier = tmp_path / "browser-20260101-000000-checkout.png"
    earlier.write_bytes(b"earlier")
    target = ops._screenshot_target(tmp_path, "checkout.png", STAMP)
    assert target.name == "browser-20260101-000000-checkout-2.png"
    assert LUCID_NAMES["screenshots"].fullmatch(target.name)
    assert earlier.read_bytes() == b"earlier"


def test_a_dangling_link_at_the_name_is_skipped(tmp_path: Path) -> None:
    # exists() is False for a link whose target is gone, lexists() is True. Writing
    # to a dangling file symlink would create its target outside the folder.
    gone = tmp_path / "gone"
    gone.mkdir()
    shots = tmp_path / "screenshots"
    shots.mkdir()
    _link_dir(shots / "browser-20260101-000000-checkout.png", gone)
    gone.rmdir()
    target = ops._screenshot_target(shots, "checkout.png", STAMP)
    assert target.name == "browser-20260101-000000-checkout-2.png"


def test_the_action_writes_inside_screenshots_and_refuses_before_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    written: list[str] = []

    def screenshot(path: str, full_page: bool) -> None:
        written.append(path)
        Path(path).write_bytes(b"png")

    page = SimpleNamespace(screenshot=screenshot)
    monkeypatch.setattr(ops, "_runtime", lambda ctx: SimpleNamespace(page=lambda: page))
    monkeypatch.setattr(ops, "_stamp", lambda: STAMP)
    monkeypatch.chdir(tmp_path)  # a bare name taken as a path would land here, not in the repo
    ctx = registry.ActionContext(settings=settings)
    out = ops.browser_screenshot(ctx, ops.BrowserScreenshotParams(path="checkout.png"))
    assert not (tmp_path / "checkout.png").exists()
    assert Path(written[0]).parent == settings.screenshot_dir
    assert "browser-20260101-000000-checkout.png" in out
    outside = tmp_path / "outside.png"
    with pytest.raises(registry.ActionError):
        ops.browser_screenshot(ctx, ops.BrowserScreenshotParams(path=str(outside)))
    assert len(written) == 1  # the refused call never reached the page
    assert not outside.exists()
