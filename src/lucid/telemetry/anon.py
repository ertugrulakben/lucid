"""Anonymous, opt-in usage telemetry.

Disabled by default. When enabled, emits hashed events only: the event name and
a constant installation UUID. No screenshots, no prompts, no API keys, ever.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

import httpx

from lucid.config.settings import Settings

log = logging.getLogger("lucid.telemetry")


class Telemetry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._install_id: str | None = None

    @property
    def install_id(self) -> str:
        if self._install_id is not None:
            return self._install_id
        path = self.settings.data_dir / "install_id"
        if path.exists():
            self._install_id = path.read_text(encoding="utf-8").strip()
        else:
            self._install_id = str(uuid.uuid4())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self._install_id, encoding="utf-8")
        return self._install_id

    def event(self, name: str, **props: Any) -> None:
        if not self.settings.telemetry.enabled or not self.settings.telemetry.endpoint:
            return
        payload = {
            "event": name,
            "install_id": self.install_id,
            "props": {k: v for k, v in props.items() if _is_safe(v)},
        }
        threading.Thread(target=self._send, args=(payload,), daemon=True).start()

    def _send(self, payload: dict) -> None:
        try:
            httpx.post(self.settings.telemetry.endpoint, json=payload, timeout=5.0)
        except Exception as exc:
            log.debug("telemetry send failed: %s", exc)


def _is_safe(value: Any) -> bool:
    if isinstance(value, (int, float, bool)):
        return True
    if isinstance(value, str):
        return len(value) < 80 and "key" not in value.lower() and "token" not in value.lower()
    return False
