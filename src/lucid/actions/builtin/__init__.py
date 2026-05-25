"""Built-in actions live one-per-file under this package and register
themselves via the ``@register_action`` decorator on import.
"""

from __future__ import annotations

import importlib as _importlib
import logging

# Import order does not matter; each module is self-contained and only
# touches the registry. Listing modules here is what triggers their
# decorator side effects.
from . import (  # noqa: F401
    click_element,
    file_dialog_paste,
    focus_window,
    type_text,
    wait,
)

_log = logging.getLogger("lucid.actions.builtin")

# Optional Playwright-backed `browser_*` action group. Importing the
# sub-package triggers its own @register_action calls when Playwright is
# installed; otherwise the import is a silent no-op. We route through
# importlib (rather than `from lucid.actions import browser`) so test reset
# helpers that clear sys.modules can re-trigger the registration cleanly.
try:
    _importlib.import_module("lucid.actions.browser")
except Exception as _exc:  # pragma: no cover -- only fires when extras absent
    _log.debug("browser action group not loaded: %s", _exc)
