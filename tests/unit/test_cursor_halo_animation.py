"""Unit tests for the Cursor Halo widget.

The fade-out animation is async so the assertion uses Qt's event loop
spinner (qtbot.wait) and checks that the widget hides itself once the
animation finishes. Positioning and colour mapping are checked directly.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from lucid.ui.cursor_halo import ACTION_COLOURS, DEFAULT_COLOUR, CursorHalo


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_flash_centers_on_coordinate(qt_app) -> None:
    halo = CursorHalo(radius_px=40, duration_ms=120)
    halo.flash("left_click", 300, 220)
    rect: QRect = halo.geometry()
    # QRect.center() returns the integer-rounded centre, off by 1 px for
    # even-sided rectangles -- tolerance keeps the assertion stable.
    assert abs(rect.center().x() - 300) <= 1
    assert abs(rect.center().y() - 220) <= 1
    assert halo.isVisible()


def test_flash_hides_after_animation(qtbot, qt_app) -> None:
    halo = CursorHalo(radius_px=24, duration_ms=80)
    qtbot.addWidget(halo)
    halo.flash("right_click", 100, 100)
    qtbot.wait(250)
    assert halo.isVisible() is False


def test_colour_map_known_actions() -> None:
    assert ACTION_COLOURS["left_click"] == "#56C2FF"
    assert ACTION_COLOURS["right_click"] == "#FFB454"
    assert ACTION_COLOURS["type"] == "#F472B6"


def test_unknown_action_falls_back_to_default(qt_app) -> None:
    halo = CursorHalo(radius_px=24, duration_ms=50)
    halo.flash("totally_made_up_action", 50, 50)
    assert halo._colour.name().lower() == DEFAULT_COLOUR.lower()  # noqa: SLF001


def test_configure_resizes(qt_app) -> None:
    halo = CursorHalo(radius_px=24, duration_ms=50)
    original = halo.width()
    halo.configure(radius_px=80, duration_ms=600)
    assert halo.width() > original
    # Duration applies to the underlying animation.
    assert halo._anim.duration() == 600  # noqa: SLF001
