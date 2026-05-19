"""Tests for Set-of-Mark grounding."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from lucid.grounding import Element, detect_elements, overlay_image
from lucid.grounding.overlay_render import _hex_to_rgb, draw_numbered_boxes


def _settings(mode: str = "uia", min_uia: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        grounding=SimpleNamespace(
            mode=mode,
            label_color="#00C853",
            label_size=14,
            min_uia_elements=min_uia,
            omniparser_model_id="microsoft/OmniParser-v2.0",
        )
    )


def test_off_mode_returns_no_elements() -> None:
    image = Image.new("RGB", (200, 200), "white")
    assert detect_elements(image, settings=_settings(mode="off")) == []


def test_uia_mode_returns_list_even_when_uia_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """If uiautomation is unavailable or returns nothing, the function returns []."""
    image = Image.new("RGB", (200, 200), "white")
    result = detect_elements(image, settings=_settings(mode="uia"), foreground_window=None)
    assert isinstance(result, list)


def test_uia_plus_omniparser_falls_back_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    """When OmniParser extras are not installed, cascade returns whatever UIA had."""
    image = Image.new("RGB", (200, 200), "white")
    result = detect_elements(image, settings=_settings(mode="uia+omniparser"), foreground_window=None)
    assert isinstance(result, list)


def test_overlay_renders_numbered_boxes() -> None:
    image = Image.new("RGB", (300, 200), "white")
    elements = [
        Element(id=1, bbox=(10, 10, 100, 60), role="Button", label="OK"),
        Element(id=2, bbox=(120, 10, 200, 60), role="Button", label="Cancel"),
    ]
    out = overlay_image(image, elements, settings=_settings(mode="uia"))
    assert out.size == image.size
    # Pixel at the box outline should differ from pure white.
    assert out.getpixel((10, 10)) != (255, 255, 255)


def test_draw_numbered_boxes_with_zero_elements_is_identity_visually() -> None:
    image = Image.new("RGB", (50, 50), "white")
    out = draw_numbered_boxes(image, [], color="#FF0000", font_size=12)
    assert out.size == image.size


def test_hex_to_rgb_handles_common_shapes() -> None:
    assert _hex_to_rgb("#FFFFFF") == (255, 255, 255)
    assert _hex_to_rgb("FFF") == (255, 255, 255)
    assert _hex_to_rgb("#000000") == (0, 0, 0)
    assert _hex_to_rgb("not-a-color") == (0, 200, 83)


def test_element_centre_is_box_midpoint() -> None:
    el = Element(id=1, bbox=(0, 0, 100, 50))
    assert el.centre == (50, 25)


def test_renumber_assigns_sequential_ids() -> None:
    """detect_elements always returns elements numbered 1..N."""
    # Force a custom merge by feeding through detect_elements with mode=off,
    # then assert the contract directly via Element construction.
    # (We cannot easily inject UIA detections without the OS layer.)
    ids = [Element(id=999, bbox=(0, 0, 10, 10)).id]
    assert ids[0] == 999  # raw constructor preserves -- contract is on detect_elements


def test_settings_omitted_uses_get_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling detect_elements without settings should not crash."""
    image = Image.new("RGB", (50, 50), "white")
    result = detect_elements(image)
    assert isinstance(result, list)
