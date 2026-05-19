"""Built-in actions live one-per-file under this package and register
themselves via the ``@register_action`` decorator on import.
"""

from __future__ import annotations

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
