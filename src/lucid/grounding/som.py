"""Set-of-Mark element detection orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image

from .overlay_render import draw_numbered_boxes

log = logging.getLogger("lucid.grounding")


@dataclass
class Element:
    """A single labelled element within a screen region.

    ``bbox`` is in screen pixels: ``(left, top, right, bottom)``. ``id``
    is the integer drawn on the overlay; the model refers to it. ``role``
    and ``label`` are descriptive but not load-bearing.
    """
    id: int
    bbox: tuple[int, int, int, int]
    role: str = ""
    label: str = ""
    source: str = "uia"  # "uia" | "omniparser"
    extras: dict = field(default_factory=dict)

    @property
    def centre(self) -> tuple[int, int]:
        left, top, right, bottom = self.bbox
        return ((left + right) // 2, (top + bottom) // 2)


def detect_elements(
    image: Image.Image,
    *,
    settings: object | None = None,
    foreground_window=None,
) -> list[Element]:
    """Return a list of :class:`Element` for the given screenshot.

    Honours ``settings.grounding.mode``:

    - ``"off"``        -> empty list (caller falls back to raw screenshot)
    - ``"uia"``        -> UIA tree only
    - ``"uia+omniparser"`` -> UIA, then OmniParser if UIA produced too few
    """
    mode = _read_mode(settings)
    if mode == "off":
        return []

    threshold = _read_int(settings, ("grounding", "min_uia_elements"), 3)

    elements: list[Element] = []
    if mode in ("uia", "uia+omniparser"):
        elements = _uia_detect(foreground_window)
        log.debug("UIA returned %d elements", len(elements))

    if mode == "uia+omniparser" and len(elements) < threshold:
        log.debug("UIA below threshold (%d < %d); invoking OmniParser", len(elements), threshold)
        try:
            from .omniparser import OmniParserDetector

            extra = OmniParserDetector.from_settings(settings).detect(image)
            elements = _merge(elements, extra)
        except (ImportError, RuntimeError) as exc:
            log.info("OmniParser unavailable: %s", exc)

    return _renumber(elements)


def overlay_image(image: Image.Image, elements: list[Element], *, settings: object | None = None) -> Image.Image:
    """Return a copy of ``image`` with numbered boxes drawn over each element."""
    color = _read_str(settings, ("grounding", "label_color"), "#00C853")
    size = _read_int(settings, ("grounding", "label_size"), 14)
    return draw_numbered_boxes(image, elements, color=color, font_size=size)


# --------------------------------------------------------------------------- #
# UIA detector
# --------------------------------------------------------------------------- #

def _uia_detect(foreground_window) -> list[Element]:
    """Walk the foreground window's UIA tree and emit one Element per
    keyboard-focusable control with a non-empty bounding rectangle.
    """
    try:
        import uiautomation as auto  # type: ignore
    except ImportError:
        return []

    root = foreground_window or auto.GetForegroundControl()
    if root is None:
        return []

    found: list[Element] = []
    stack = [root]
    seen = 0
    while stack and seen < 200:
        node = stack.pop()
        seen += 1
        try:
            rect = node.BoundingRectangle
            if rect is None:
                continue
            w, h = rect.width(), rect.height()
            if w < 6 or h < 6:
                continue
            if not getattr(node, "IsKeyboardFocusable", False) and not _looks_clickable(node):
                pass  # still record; many buttons report Focusable=False on Windows
            label = (node.Name or "")[:80]
            role = getattr(node, "ControlTypeName", "") or ""
            found.append(
                Element(
                    id=0,
                    bbox=(rect.left, rect.top, rect.right, rect.bottom),
                    role=role,
                    label=label,
                    source="uia",
                )
            )
        except Exception:  # noqa: BLE001 -- some UIA nodes raise on attribute access
            pass
        try:
            children = node.GetChildren()
        except Exception:  # noqa: BLE001
            children = []
        for child in children:
            stack.append(child)
    return found


def _looks_clickable(node) -> bool:
    role = (getattr(node, "ControlTypeName", "") or "").lower()
    return any(token in role for token in ("button", "menuitem", "hyperlink", "tab", "checkbox"))


def _merge(uia: list[Element], extra: list[Element]) -> list[Element]:
    """Drop OmniParser detections that overlap with an existing UIA box."""
    out = list(uia)
    for cand in extra:
        if any(_iou(cand.bbox, e.bbox) > 0.4 for e in uia):
            continue
        out.append(cand)
    return out


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    a_area = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    b_area = max(0, bx2 - bx1) * max(0, by2 - by1)
    return inter / float(a_area + b_area - inter or 1)


def _renumber(elements: list[Element]) -> list[Element]:
    return [Element(
        id=i + 1,
        bbox=e.bbox,
        role=e.role,
        label=e.label,
        source=e.source,
        extras=e.extras,
    ) for i, e in enumerate(elements)]


# --------------------------------------------------------------------------- #
# settings access (defensive -- never explodes when settings unavailable)
# --------------------------------------------------------------------------- #

def _read_mode(settings: object | None) -> str:
    return _read_str(settings, ("grounding", "mode"), "uia")


def _read_str(settings: object | None, path: tuple[str, ...], default: str) -> str:
    value = _read_attr(settings, path)
    return str(value) if value else default


def _read_int(settings: object | None, path: tuple[str, ...], default: int) -> int:
    value = _read_attr(settings, path)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_attr(settings: object | None, path: tuple[str, ...]) -> Optional[object]:
    if settings is None:
        try:
            from lucid.config.settings import get_settings

            settings = get_settings()
        except Exception:  # noqa: BLE001
            return None
    node: object = settings
    for attr in path:
        node = getattr(node, attr, None)
        if node is None:
            return None
    return node
