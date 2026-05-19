"""Universal Windows file dialog handler.

Native Open/Save dialogs (class ``#32770`` with a title like "Aç", "Farklı
Kaydet", "Open", "Save As") are where Claude often gets stuck: clicking
through a folder tree with pixel coordinates is fragile. The fastest and
most reliable recipe on Windows 10/11 is:

1. Focus the "File name:" / "Dosya adı:" combobox (Alt+N in English, or
   press Tab until we land on it).
2. Paste the absolute path of the target file (or folder + filename) via
   clipboard — this short-circuits the treeview entirely.
3. Press Enter: Windows navigates + opens/saves in one shot.

This module exposes one function, ``navigate_file_dialog(path)``, that the
Execute action layer can call when Claude emits a ``focus_and_submit_path``
action or when a file-dialog action is detected heuristically.
"""

from __future__ import annotations

import logging
import sys
import time

log = logging.getLogger("lucid.executor.file_dialog")


FILE_DIALOG_TITLES = (
    "aç",
    "open",
    "farklı kaydet",
    "save as",
    "kaydet",
    "save",
    "dosya seç",
    "choose file",
    "upload",
    "select file",
    "yükle",
    "browse for folder",
    "klasör seç",
)


def detect_active_file_dialog() -> int | None:
    """Return the hwnd of the foreground window if it looks like a file dialog."""
    if sys.platform != "win32":
        return None
    try:
        import win32gui  # type: ignore[import-not-found]

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        title = (win32gui.GetWindowText(hwnd) or "").strip().lower()
        if any(t in title for t in FILE_DIALOG_TITLES):
            return int(hwnd)
        try:
            class_name = win32gui.GetClassName(hwnd)
        except Exception:
            class_name = ""
        if class_name == "#32770" and title:
            return int(hwnd)
    except Exception as exc:
        log.debug("detect_active_file_dialog failed: %s", exc)
    return None


def focus_filename_field(hwnd: int) -> bool:
    """Try to put keyboard focus on the File-name / Dosya-adı combobox."""
    if sys.platform != "win32":
        return False
    try:
        import uiautomation as auto  # type: ignore[import-not-found]

        window = auto.ControlFromHandle(hwnd)
        if window is None:
            return False
        # Dosya adı / File name editable combobox — any Edit control near the bottom.
        for role in ("EditControl", "ComboBoxControl"):
            for name_hint in ("Dosya adı", "File name", "Dosya Adı", "File Name"):
                try:
                    target = window.Control(ControlType=role, SubName=name_hint)
                    if target.Exists(0.5):
                        target.SetFocus()
                        return True
                except Exception:
                    continue
        # Last-resort: focus the first editable child.
        for child in window.GetChildren():
            try:
                if (getattr(child, "ControlTypeName", "") or "") == "EditControl":
                    child.SetFocus()
                    return True
            except Exception:
                continue
    except Exception as exc:
        log.debug("focus_filename_field failed: %s", exc)
    return False


def navigate_file_dialog(path: str, submit: bool = True) -> str:
    """Type ``path`` into the focused File-name field and optionally press Enter.

    Returns a short human-readable result for the Execute tool_result.
    Falls back to ``keyboard``-based typing if UIAutomation can't find
    the edit control — modern Windows dialogs always accept a raw path
    in the filename field, even if the user is looking at the sidebar.
    """
    if not path:
        return "error: no path"

    hwnd = detect_active_file_dialog()
    if hwnd is None:
        return "error: no file dialog detected in foreground"

    try:
        import pyautogui
    except ImportError:
        return "error: pyautogui not installed"

    focused = focus_filename_field(hwnd)
    # Some dialogs need a light Alt+N to surface the filename box.
    if not focused:
        try:
            pyautogui.hotkey("alt", "n")
            time.sleep(0.05)
        except Exception:
            pass

    # Clear any placeholder/autocomplete.
    try:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.02)
        pyautogui.press("delete")
        time.sleep(0.02)
    except Exception:
        pass

    # Paste via clipboard (unaffected by keyboard layout).
    try:
        import pyperclip  # type: ignore[import-not-found]

        saved = None
        try:
            saved = pyperclip.paste()
        except Exception:
            saved = None
        pyperclip.copy(path)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        if saved is not None:
            try:
                pyperclip.copy(saved)
            except Exception:
                pass
    except ImportError:
        pyautogui.typewrite(path, interval=0.01)

    if submit:
        time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(0.15)

    return f"file dialog → pasted {path!r} and pressed Enter"


def quick_navigate_to_folder(folder: str) -> str:
    """Navigate an already-open file dialog to ``folder`` without submitting.

    Useful when we want to open the folder first and then let Claude pick a
    specific file via UI or a second paste.
    """
    return navigate_file_dialog(folder, submit=False)
