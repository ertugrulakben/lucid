"""OCR fallback for UIs where the accessibility tree is empty.

Canvas-drawn UIs (Paint, many games, some Electron apps, PDF viewers) leave
UI Automation with nothing to query. When ``click_element`` misses and
coordinate guessing is unreliable, we fall back to OCR: run the screenshot
through EasyOCR, find the text region whose content matches the requested
label, and click the centre of that region.

EasyOCR is heavy (~30 MB model download on first use, ~300 MB of torch
deps). We keep it as an **optional extra** installed via
``pip install lucid[ocr]``. If missing, ``find_text_region`` returns
``None`` immediately so callers can fall back to a different strategy.

Design notes:
- One cached reader per process; first call initialises with the
  user-selected language list and is slow (~2 s), subsequent calls are fast.
- Callers provide the current screenshot (the same one Claude saw) so our
  coordinate space matches ``ContextSnapshot.image_to_screen`` translations.
- Ranking prefers the shortest text whose lowercased content contains the
  needle; ties broken by vertical position (topmost first) to match typical
  reading order.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

log = logging.getLogger("lucid.executor.ocr")

_reader_lock = threading.Lock()
_reader: Any | None = None
_reader_langs: tuple[str, ...] = ()


@dataclass
class TextRegion:
    """A single OCR hit: bounding box centre in image coordinates + text + confidence."""

    cx: int
    cy: int
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2)


def is_available() -> bool:
    """True when the optional ``easyocr`` dependency is importable."""
    try:
        import easyocr  # noqa: F401  (import check only)
    except ImportError:
        return False
    return True


def _get_reader(languages: list[str]):
    """Lazy-init a shared reader; swap if the language list changes."""
    global _reader, _reader_langs
    if not is_available():
        return None
    key = tuple(languages or ["en"])
    with _reader_lock:
        if _reader is None or _reader_langs != key:
            import easyocr  # type: ignore[import-not-found]

            log.info("initialising EasyOCR reader (%s)", ",".join(key))
            _reader = easyocr.Reader(list(key), gpu=False, verbose=False)
            _reader_langs = key
    return _reader


def ocr_image(image: PILImage, languages: list[str] | None = None) -> list[TextRegion]:
    """Run OCR over a PIL image and return text regions in image coordinates."""
    reader = _get_reader(languages or ["en", "tr"])
    if reader is None:
        return []
    import numpy as np  # type: ignore[import-not-found]

    arr = np.array(image.convert("RGB"))
    try:
        raw = reader.readtext(arr)
    except Exception as exc:
        log.debug("easyocr failed: %s", exc)
        return []

    regions: list[TextRegion] = []
    for entry in raw:
        # entry = (bbox:list[[x,y],4], text, confidence)
        try:
            bbox, text, conf = entry
            xs = [int(p[0]) for p in bbox]
            ys = [int(p[1]) for p in bbox]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            regions.append(
                TextRegion(
                    cx=cx,
                    cy=cy,
                    text=str(text),
                    confidence=float(conf),
                    bbox=(x1, y1, x2, y2),
                )
            )
        except Exception:
            continue
    return regions


def find_text_region(
    image: PILImage,
    needle: str,
    languages: list[str] | None = None,
    min_confidence: float = 0.35,
) -> TextRegion | None:
    """Return the best text region containing ``needle`` (case-insensitive)."""
    needle = (needle or "").strip().lower()
    if not needle:
        return None
    regions = ocr_image(image, languages=languages)
    if not regions:
        return None
    matches = [r for r in regions if r.confidence >= min_confidence and needle in r.text.lower()]
    if not matches:
        return None
    # Prefer the shortest text (more specific match), then topmost in reading order.
    matches.sort(key=lambda r: (len(r.text), r.cy, r.cx))
    return matches[0]
