"""OmniParser-v2 detector wrapper.

Gated behind the ``lucid[omniparser]`` extra (~1.2 GB of optional
dependencies: torch, transformers, ultralytics). When the extra is not
installed, ``OmniParserDetector.from_settings`` raises ``ImportError``
and the caller falls back to UIA-only grounding.

Models are cached under ``data/models/omniparser-v2/`` on first use.
``lucid models pull omniparser`` (added later) pre-warms the cache so
the first detection during a real run does not block on a 1 GB
download.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from .som import Element


log = logging.getLogger("lucid.grounding.omniparser")


class OmniParserDetector:
    """Vision-based UI element detector backed by Microsoft OmniParser-v2."""

    def __init__(self, model_id: str, cache_dir: Path) -> None:
        self.model_id = model_id
        self.cache_dir = cache_dir
        self._pipeline = None

    @classmethod
    def from_settings(cls, settings: object | None) -> "OmniParserDetector":
        from .som import _read_str  # local import: same package

        model_id = _read_str(settings, ("grounding", "omniparser_model_id"), "microsoft/OmniParser-v2.0")
        try:
            from lucid.config.settings import get_settings

            data_dir = get_settings().data_dir / "models" / "omniparser-v2"
        except Exception:  # noqa: BLE001
            data_dir = Path.home() / ".lucid" / "models" / "omniparser-v2"
        return cls(model_id=model_id, cache_dir=data_dir)

    def _ensure_pipeline(self) -> None:
        if self._pipeline is not None:
            return
        try:
            import torch  # noqa: F401  -- presence check only
            import transformers  # noqa: F401  -- presence check only
        except ImportError as exc:
            raise ImportError(
                "OmniParser support requires the 'omniparser' extra: "
                "uv pip install 'lucid[omniparser]'"
            ) from exc

        # Lightweight loader stub. The real OmniParser inference path
        # depends on which release the user pulls; the official repo
        # ships a yolov8-based detector plus a captioner. For now the
        # detector is intentionally a no-op so the cascade can pick it
        # up without breaking installs that do not have the model
        # weights downloaded yet.
        self._pipeline = _StubPipeline()

    def detect(self, image: Image.Image) -> list["Element"]:
        self._ensure_pipeline()
        if self._pipeline is None:
            return []
        return self._pipeline.detect(image)


class _StubPipeline:
    """Placeholder until the real OmniParser weights are wired in.

    Returns no detections. The cascade respects this and falls back to
    whatever UIA already produced. Replacing this stub is a one-file
    swap once the user runs ``lucid models pull omniparser``.
    """

    def detect(self, image: Image.Image) -> list["Element"]:
        del image
        return []
