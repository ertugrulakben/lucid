"""Draw numbered bounding boxes over a screenshot.

Output style: thin coloured rectangle around each element, with a
filled label tab in the top-left corner showing the integer ID. The
default colour mirrors ``settings.grounding.label_color`` (green).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from .som import Element


def draw_numbered_boxes(
    image: "Image.Image",
    elements: list["Element"],
    *,
    color: str = "#00C853",
    font_size: int = 14,
) -> "Image.Image":
    """Return a copy of ``image`` with one labelled box per element."""
    canvas = image.convert("RGBA").copy()
    draw = ImageDraw.Draw(canvas, "RGBA")

    font = _load_font(font_size)
    rgb = _hex_to_rgb(color)
    box_rgba = (*rgb, 255)
    label_rgba = (*rgb, 220)

    for el in elements:
        left, top, right, bottom = el.bbox
        draw.rectangle([(left, top), (right, bottom)], outline=box_rgba, width=2)

        text = str(el.id)
        try:
            tw = int(draw.textlength(text, font=font))
        except AttributeError:
            tw = 8 * len(text)
        th = font_size + 2
        pad = 2
        tab = [(left, max(0, top - th - 2 * pad)), (left + tw + 2 * pad, top)]
        draw.rectangle(tab, fill=label_rgba)
        draw.text(
            (left + pad, max(0, top - th - pad)),
            text,
            font=font,
            fill=(255, 255, 255, 255),
        )

    return canvas.convert("RGB")


def _load_font(size: int) -> "ImageFont.FreeTypeFont | ImageFont.ImageFont":
    for candidate in ("seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    s = value.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return (0, 200, 83)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return (0, 200, 83)
