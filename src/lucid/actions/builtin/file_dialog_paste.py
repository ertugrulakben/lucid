"""Paste a file path into the foreground File-Open / Save dialog."""

from __future__ import annotations

import time

from lucid.actions.registry import ActionContext, ActionError, register_action
from lucid.actions.schemas import FileDialogPasteParams


@register_action(
    name="file_dialog_paste",
    schema=FileDialogPasteParams,
    summary="Focus the File-name field of the foreground dialog, paste a path, optionally submit.",
)
def file_dialog_paste(ctx: ActionContext, params: FileDialogPasteParams) -> str:
    try:
        import pyautogui  # type: ignore
        import pyperclip  # type: ignore
    except ImportError as exc:
        raise ActionError("pyautogui and pyperclip are required for file_dialog_paste") from exc

    saved = None
    try:
        saved = pyperclip.paste()
    except Exception:  # noqa: BLE001
        pass

    try:
        # Common-dialog convention: Alt+N targets the File name field.
        pyautogui.hotkey("alt", "n")
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "a")
        pyperclip.copy(params.path)
        pyautogui.hotkey("ctrl", "v")
        if params.submit:
            time.sleep(0.05)
            pyautogui.press("enter")
        return f"file_dialog_paste: {params.path}"
    except Exception as exc:  # noqa: BLE001
        raise ActionError(f"file_dialog_paste failed: {exc}") from exc
    finally:
        if saved is not None:
            try:
                pyperclip.copy(saved)
            except Exception:  # noqa: BLE001
                pass
