"""Drive Lucid against a local LM Studio server, no API key required.

1. Open LM Studio, load any chat-capable model.
2. Start the local server (``Server`` tab -> ``Start Server`` on port 1234).
3. Run::

    LUCID_LOCALE=en \
        uv run python examples/03_lm_studio_offline.py "what is my desktop wallpaper?"

The example forces ``backend.mode = "lm_studio"`` for this run only by
constructing the provider directly. To make it persistent, edit
``data/settings.yaml`` instead.
"""

from __future__ import annotations

import sys

from lucid import i18n
from lucid.backend.lm_studio_backend import LMStudioProvider
from lucid.capture import ContextSnapshot
from lucid.config.settings import get_settings
from lucid.llm.provider import Message


def main(question: str) -> int:
    i18n.init()
    settings = get_settings()
    snapshot = ContextSnapshot.capture(settings)

    provider = LMStudioProvider(
        base_url=settings.backend.lm_studio_url,
        api_key=settings.backend.lm_studio_api_key,
        model=settings.backend.lm_studio_model,  # "" -> auto-pick first loaded model
    )

    user_msg = Message(
        role="user",
        content=[
            provider.text_block(question),
            provider.image_block(snapshot.image),
        ],
    )

    print("[lm_studio] ", end="", flush=True)
    for event in provider.stream([user_msg], system=i18n._("prompt-answer-system"), max_tokens=512):
        if event.kind == "text_delta" and event.text:
            print(event.text, end="", flush=True)
        elif event.kind == "error":
            print(f"\n[error] {event.error}", file=sys.stderr)
            return 1
    print()
    return 0


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What is currently on screen?"
    sys.exit(main(q))
