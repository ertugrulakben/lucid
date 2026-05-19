"""Take a screenshot, ask Claude what is on screen, print the answer.

Run with::

    uv run python examples/01_answer_screenshot.py "what app am I in?"

Requires ``ANTHROPIC_API_KEY`` (or ``LUCID_ANTHROPIC_API_KEY``) in the
environment, OR a configured ``backend.mode`` (``cli`` / ``lm_studio`` /
``kimi``) so that ``create_provider(settings)`` resolves to a working
client.
"""

from __future__ import annotations

import sys

from lucid import i18n
from lucid.capture import ContextSnapshot
from lucid.config.settings import get_settings
from lucid.llm.provider import Message, create_provider


def main(question: str) -> int:
    i18n.init()
    settings = get_settings()
    snapshot = ContextSnapshot.capture(settings)

    provider = create_provider(settings)
    user_msg = Message(
        role="user",
        content=[
            provider.text_block(question),
            provider.image_block(snapshot.image),
        ],
    )
    system = i18n._("prompt-answer-system")

    print("[answer] ", end="", flush=True)
    for event in provider.stream([user_msg], system=system, max_tokens=512):
        if event.kind == "text_delta" and event.text:
            print(event.text, end="", flush=True)
        elif event.kind == "error":
            print(f"\n[error] {event.error}", file=sys.stderr)
            return 1
    print()
    return 0


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Describe what is currently visible on screen."
    sys.exit(main(question))
