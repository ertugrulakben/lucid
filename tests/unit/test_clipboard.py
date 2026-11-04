"""Pasted text is kept out of the Windows clipboard history (lucid.clipboard).

Every test fakes the clipboard and the keyboard; the real ones are never touched.
"""

from __future__ import annotations

import struct
import sys
from types import SimpleNamespace

import pytest

from lucid import clipboard
from lucid.actions.builtin import type_text as type_text_action
from lucid.executor import actions as actions_module

TYPED = "hunter2-Parola!"


class FakeWin32Clipboard:
    CF_UNICODETEXT = 13

    def __init__(self, fail_open: bool = False, fail_set: bool = False) -> None:
        self.calls: list = []
        self.formats: dict[str, int] = {}
        self.fail_open, self.fail_set = fail_open, fail_set

    def OpenClipboard(self) -> None:
        if self.fail_open:
            raise RuntimeError("busy")
        self.calls.append("open")

    def EmptyClipboard(self) -> None:
        self.calls.append("empty")

    def RegisterClipboardFormat(self, name: str) -> int:
        return self.formats.setdefault(name, 49000 + len(self.formats))

    def SetClipboardData(self, fmt: int, data: object) -> None:
        if self.fail_set:
            raise RuntimeError("set failed")
        self.calls.append(("set", fmt, data))

    def CloseClipboard(self) -> None:
        self.calls.append("close")


def _fake_win32(monkeypatch: pytest.MonkeyPatch, **kw: bool) -> FakeWin32Clipboard:
    fake = FakeWin32Clipboard(**kw)
    monkeypatch.setitem(sys.modules, "win32clipboard", fake)
    monkeypatch.setattr(clipboard.sys, "platform", "win32")
    return fake


def test_copy_private_opts_out_of_history_and_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_win32(monkeypatch)
    assert clipboard.copy_private(TYPED) is True
    sets = [c for c in fake.calls if isinstance(c, tuple)]
    assert sets[0] == ("set", FakeWin32Clipboard.CF_UNICODETEXT, TYPED)
    assert {c[1] for c in sets[1:]} == {fake.formats[n] for n in clipboard.PRIVATE_FORMATS}
    assert all(c[2] == struct.pack("<I", 0) for c in sets[1:])
    assert fake.calls[0] == "open"
    assert fake.calls[-1] == "close"


def test_copy_private_busy_clipboard(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_win32(monkeypatch, fail_open=True)
    assert clipboard.copy_private(TYPED) is False
    assert "close" not in fake.calls


def test_copy_private_failure_still_closes_clipboard(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_win32(monkeypatch, fail_set=True)
    assert clipboard.copy_private(TYPED) is False
    assert fake.calls[-1] == "close"


def test_copy_private_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    assert clipboard.copy_private(TYPED) is False


@pytest.mark.parametrize(
    "private_ok, expected_copies", [(True, ["önceki"]), (False, [TYPED, "önceki"])]
)
def test_type_text_action_pastes_privately(
    monkeypatch: pytest.MonkeyPatch, private_ok: bool, expected_copies: list[str]
) -> None:
    copies: list[str] = []
    keys: list[tuple] = []
    monkeypatch.setitem(
        sys.modules, "pyperclip", SimpleNamespace(paste=lambda: "önceki", copy=copies.append)
    )
    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(hotkey=lambda *k: keys.append(k)))
    monkeypatch.setattr(type_text_action, "copy_private", lambda text: private_ok)
    assert type_text_action._paste(TYPED) == f"pasted {len(TYPED)} chars"
    assert copies == expected_copies  # the previous clipboard is restored last
    assert keys == [("ctrl", "v")]


def test_executor_type_pastes_privately(monkeypatch: pytest.MonkeyPatch) -> None:
    copies: list[str] = []
    private: list[str] = []
    keys: list[tuple] = []
    monkeypatch.setitem(
        sys.modules, "pyperclip", SimpleNamespace(paste=lambda: "önceki", copy=copies.append)
    )
    monkeypatch.setattr(
        actions_module, "pyautogui", SimpleNamespace(hotkey=lambda *k: keys.append(k))
    )
    monkeypatch.setattr(actions_module, "copy_private", lambda text: private.append(text) or True)
    monkeypatch.setattr(actions_module.time, "sleep", lambda _s: None)
    out = actions_module.Actions._type(SimpleNamespace(), {"text": TYPED})
    assert out == f"pasted {len(TYPED)} chars"
    assert private == [TYPED]
    assert copies == ["önceki"]
    assert keys == [("ctrl", "v")]
