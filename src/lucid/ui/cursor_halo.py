"""Cursor Halo: brief radial flash at the point Lucid just acted on.

A tiny click-through frameless window is reused for every flash. When
:meth:`CursorHalo.flash` is called, the widget jumps to ``(x, y)`` in
absolute screen coordinates, paints two concentric rings whose colour
encodes the action category, and runs a 450 ms opacity+scale animation to
fade out. The widget then hides itself until the next flash.

Multi-monitor: callers must pass *absolute* screen pixels. ExecuteMode
already translates coordinate-bearing actions to absolute coordinates via
:func:`lucid.agent.execute_mode._translate_coords`, so no extra math is
needed here.

The widget never accepts mouse events (``WA_TransparentForMouseEvents``)
so clicks pass through to whatever Lucid is automating.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    Slot,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

ACTION_COLOURS: dict[str, str] = {
    "left_click": "#56C2FF",
    "click_element": "#56C2FF",
    "click": "#56C2FF",
    "scroll_into_view": "#56C2FF",
    "right_click": "#FFB454",
    "double_click": "#A78BFA",
    "triple_click": "#A78BFA",
    "drag": "#34D399",
    "left_click_drag": "#34D399",
    "type": "#F472B6",
    "type_text": "#F472B6",
    "key": "#F472B6",
    "hotkey": "#F472B6",
}
DEFAULT_COLOUR = "#9aa0ff"


class CursorHalo(QWidget):
    """Reusable transparent flash widget. Construct once per AppController."""

    def __init__(self, radius_px: int = 48, duration_ms: int = 450) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self._radius = max(12, int(radius_px))
        self._duration = max(100, int(duration_ms))
        self._colour = QColor(DEFAULT_COLOUR)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        # Side length: ring needs room for outer stroke + glow padding.
        self.setFixedSize(self._radius * 2 + 16, self._radius * 2 + 16)
        self.hide()

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(self._duration)
        self._anim.setStartValue(0.95)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_finished)

    # ------------------------- configuration -------------------------

    def configure(self, *, radius_px: int | None = None, duration_ms: int | None = None) -> None:
        if radius_px is not None:
            self._radius = max(12, int(radius_px))
            self.setFixedSize(self._radius * 2 + 16, self._radius * 2 + 16)
        if duration_ms is not None:
            self._duration = max(100, int(duration_ms))
            self._anim.setDuration(self._duration)

    # ------------------------- flash -------------------------

    @Slot(str, int, int)
    def flash(self, action_name: str, screen_x: int, screen_y: int) -> None:
        """Show a halo at the given absolute screen coordinate."""
        colour_hex = ACTION_COLOURS.get(action_name.lower(), DEFAULT_COLOUR)
        self._colour = QColor(colour_hex)
        side = self.width()
        top_left = QPoint(int(screen_x) - side // 2, int(screen_y) - side // 2)
        self.setGeometry(QRect(top_left, self.size()))
        self.update()
        if self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        self._effect.setOpacity(0.95)
        self.show()
        self.raise_()
        self._anim.start()

    def _on_finished(self) -> None:
        self._effect.setOpacity(0.0)
        self.hide()

    # ------------------------- painting -------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        # Outer thin ring for visibility, inner thicker ring for the action colour.
        outer = QColor(self._colour)
        outer.setAlpha(180)
        pen_outer = QPen(outer)
        pen_outer.setWidth(2)
        painter.setPen(pen_outer)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(cx - self._radius), int(cy - self._radius), self._radius * 2, self._radius * 2)

        inner = QColor(self._colour)
        inner.setAlpha(220)
        pen_inner = QPen(inner)
        pen_inner.setWidth(4)
        painter.setPen(pen_inner)
        r2 = max(6, self._radius - 14)
        painter.drawEllipse(int(cx - r2), int(cy - r2), r2 * 2, r2 * 2)

        dot = QColor(self._colour)
        dot.setAlpha(255)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot)
        painter.drawEllipse(int(cx - 3), int(cy - 3), 6, 6)
