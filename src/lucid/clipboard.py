"""Put text on the clipboard without leaving it in the Windows clipboard history.

Lucid types by pasting: it puts the text on the clipboard and sends Ctrl+V,
which is immune to keyboard layouts. Since Windows 10 1809 every clipboard
change can land in the clipboard history (Win+V) and, with cloud clipboard
on, on the user's other devices. Lucid pastes passwords too, so its copies
carry the registered formats Windows documents for opting out ("Cloud
Clipboard and Clipboard History Formats",
https://learn.microsoft.com/windows/win32/dataxchg/clipboard-formats):

- ``ExcludeClipboardContentFromMonitorProcessing`` with any data,
- ``CanIncludeInClipboardHistory`` with a DWORD zero,
- ``CanUploadToCloudClipboard`` with a DWORD zero.
"""

from __future__ import annotations

import logging
import struct
import sys

log = logging.getLogger("lucid.clipboard")

_DWORD_ZERO = struct.pack("<I", 0)
PRIVATE_FORMATS = (
    "ExcludeClipboardContentFromMonitorProcessing",
    "CanIncludeInClipboardHistory",
    "CanUploadToCloudClipboard",
)


def copy_private(text: str) -> bool:
    """Put ``text`` on the clipboard, kept out of history and cloud sync.

    Returns False when this is not Windows, pywin32 is missing or the
    clipboard is busy; the caller then falls back to a plain copy.
    """
    if sys.platform != "win32":
        return False
    try:
        import win32clipboard
    except ImportError:
        return False
    try:
        win32clipboard.OpenClipboard()
    except Exception as exc:  # another process holds the clipboard
        log.debug("clipboard busy: %s", exc)
        return False
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        for name in PRIVATE_FORMATS:
            fmt = win32clipboard.RegisterClipboardFormat(name)
            win32clipboard.SetClipboardData(fmt, _DWORD_ZERO)
        return True
    except Exception as exc:
        log.debug("private clipboard copy failed: %s", exc)
        return False
    finally:
        win32clipboard.CloseClipboard()
