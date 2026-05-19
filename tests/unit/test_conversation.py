from __future__ import annotations

from PIL import Image

from lucid.agent.conversation import Conversation


class _P:
    def image_block(self, img):
        return {"type": "image"}

    def text_block(self, text):
        return {"type": "text", "text": text}


def test_append_and_transcript() -> None:
    conv = Conversation()
    conv.append_user("hello")
    conv.append_assistant("hi")
    t = conv.transcript()
    assert "You: hello" in t
    assert "Lucid: hi" in t


def test_clear() -> None:
    conv = Conversation()
    conv.append_user("x")
    conv.clear()
    assert conv.is_empty()


def test_only_latest_user_has_image() -> None:
    conv = Conversation()
    img = Image.new("RGB", (4, 4))
    conv.append_user("first", image=img)
    conv.append_assistant("ok")
    conv.append_user("second", image=img)
    msgs = conv.to_messages(_P())
    assert msgs[0].role == "user"
    assert all(b["type"] == "text" for b in msgs[0].content)
    assert any(b["type"] == "image" for b in msgs[-1].content)


def test_trim_respects_max_turns() -> None:
    conv = Conversation(max_turns=3)
    for i in range(5):
        conv.append_user(f"u{i}")
    assert len(conv.turns) == 3
    assert conv.turns[0].text == "u2"
