"""Insert text into the focused control, preferring clipboard paste."""

from __future__ import annotations

from lucid.actions.registry import ActionContext, ActionError, register_action
from lucid.actions.schemas import TypeTextParams


@register_action(
    name="type_text",
    schema=TypeTextParams,
    summary="Insert text at the current focus. Uses clipboard paste by default for speed.",
)
def type_text(ctx: ActionContext, params: TypeTextParams) -> str:
    if params.use_clipboard:
        return _paste(params.text)
    return _typewrite(params.text)


def _paste(text: str) -> str:
    try:
        import pyautogui  # type: ignore
        import pyperclip  # type: ignore
    except ImportError:
        return _typewrite(text)

    try:
        saved = pyperclip.paste()
    except Exception:  # noqa: BLE001 -- empty / locked clipboard
        saved = None

    try:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        return f"pasted {len(text)} chars"
    except Exception as exc:  # noqa: BLE001
        return _typewrite(text) or f"paste failed: {exc}"
    finally:
        if saved is not None:
            try:
                pyperclip.copy(saved)
            except Exception:  # noqa: BLE001
                pass


def _typewrite(text: str) -> str:
    try:
        import pyautogui  # type: ignore
    except ImportError as exc:
        raise ActionError("pyautogui is required for type_text fallback") from exc
    pyautogui.typewrite(text, interval=0.01)
    return f"typed {len(text)} chars"
