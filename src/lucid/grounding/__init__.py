"""Set-of-Mark grounding -- numbered overlay of clickable elements.

The model sees a screenshot with each interactive element labelled by a
number. Instead of returning pixel coordinates (which often miss after a
window resize or DPI change), the model returns ``click(id=N)``. The
runtime then translates that ID back to a bounding box and dispatches
the actual click. This is the same approach used by Anthropic's
computer-use research and several recent open-source agents.

Detection cascade (cheap to expensive):

    1. ``UIATreeDetector`` -- walks the Windows accessibility tree for
       the foreground window. Free, ~50 ms, perfectly accurate when the
       app exposes UIA (most native apps, Office, Edge, modern Win32).

    2. ``OmniParserDetector`` -- runs the OmniParser-v2 vision model on
       the screenshot. Slower (~2 fps CPU, 15 fps GPU), used only when
       UIA returns fewer than ``settings.grounding.min_uia_elements``
       (typical for games, Electron with shadow DOM, custom GL canvases).
       Available only with the ``lucid[omniparser]`` extra installed.

Use :func:`detect_elements` for a one-shot call that respects the
configured ``grounding.mode`` setting.
"""

from __future__ import annotations

from .som import (
    Element,
    detect_elements,
    overlay_image,
)

__all__ = [
    "Element",
    "detect_elements",
    "overlay_image",
]
