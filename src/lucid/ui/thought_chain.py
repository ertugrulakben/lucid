"""ThoughtChain: live reasoning view for Execute mode.

The Execute loop emits two flavours of "thought":

    [thought] narration text...
    [thought] 🛠 plan: action_name(...) -- short params

The overlay's :meth:`append_result` parses both, strips the prefix, and routes
the payload to :meth:`ThoughtChainPanel.append_thought`. The panel itself is a
small QTextBrowser styled like a chat log, with a bounded deque so a long
session does not blow the widget's text buffer.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from lucid.i18n import _ as t


class ThoughtChainPanel(QWidget):
    """Compact reasoning timeline. Auto-scrolls to the newest entry."""

    def __init__(self, parent: QWidget | None = None, history: int = 200) -> None:
        super().__init__(parent)
        self.setObjectName("LucidThoughtChain")
        self._history = max(20, int(history))
        self._entries: deque[str] = deque(maxlen=self._history)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self.title = QLabel(t("thought-empty"), self)
        self.title.setObjectName("LucidThoughtTitle")
        header.addWidget(self.title, 1)
        self.clear_btn = QPushButton(t("thought-clear"), self)
        self.clear_btn.setObjectName("LucidToolbarButton")
        self.clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_btn.clicked.connect(self.clear)
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        self.viewer = QTextBrowser(self)
        self.viewer.setObjectName("LucidThoughtViewer")
        self.viewer.setReadOnly(True)
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setMinimumHeight(140)
        self.viewer.setMaximumHeight(260)
        layout.addWidget(self.viewer)

        self.setStyleSheet(
            "QLabel#LucidThoughtTitle { color: #cdd; font-size: 12px; }"
            "QTextBrowser#LucidThoughtViewer { background: rgba(0,0,0,0.55); "
            "color: #dde; font-family: Consolas, 'Cascadia Mono', monospace; "
            "font-size: 11px; border: 1px solid #333; border-radius: 6px; padding: 6px; }"
        )

    # ------------------------- public API -------------------------

    def append_thought(self, text: str) -> None:
        """Add one thought entry (already stripped of its `[thought]` prefix)."""
        text = (text or "").rstrip()
        if not text:
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        entry_html = self._render_entry(stamp, text)
        self._entries.append(entry_html)
        self._rerender()
        self.title.setText(t("thought-active", count=len(self._entries)))

    def clear(self) -> None:
        self._entries.clear()
        self.viewer.clear()
        self.title.setText(t("thought-empty"))

    # ------------------------- internals -------------------------

    def _rerender(self) -> None:
        """Repaint the deque into the viewer and scroll to the bottom."""
        body = "<br>".join(self._entries)
        self.viewer.setHtml(
            "<div style='line-height:1.45'>" + body + "</div>"
        )
        bar = self.viewer.verticalScrollBar()
        bar.setValue(bar.maximum())

    @staticmethod
    def _render_entry(stamp: str, text: str) -> str:
        """Minimal markdown-ish render: highlight plan markers + escape HTML."""
        safe = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        prefix = "<span style='color:#778;'>" + stamp + "</span>  "
        if safe.lstrip().startswith("🛠"):
            return (
                prefix
                + "<span style='color:#56C2FF;'>" + safe + "</span>"
            )
        return prefix + "<span style='color:#dde;'>" + safe + "</span>"
