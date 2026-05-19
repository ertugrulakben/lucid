"""A / B / C mode picker bar beneath the prompt."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from lucid.i18n import _ as t


def _mode_labels() -> dict[str, tuple[str, str]]:
    """Return localised (label, tooltip) pairs at call time so locale
    switches mid-session refresh correctly when the picker is rebuilt."""
    return {
        "answer": (t("mode-answer"), "Ctrl+1  ·  " + t("placeholder-answer").split("…")[0]),
        "teach": (t("mode-teach"), "Ctrl+2  ·  " + t("placeholder-teach").split("…")[0]),
        "execute": (t("mode-execute"), "Ctrl+3  ·  " + t("placeholder-execute").split("…")[0]),
    }


class ModePicker(QWidget):
    """Three buttons: Answer, Teach, Execute. Emits the selected mode."""

    mode_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LucidModeBar")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        self.buttons: dict[str, QPushButton] = {}
        for key, (label, tip) in _mode_labels().items():
            btn = QPushButton(label)
            btn.setObjectName("LucidModeButton")
            btn.setProperty("mode", key)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setFocusPolicy(btn.focusPolicy().NoFocus)
            btn.clicked.connect(lambda _checked=False, k=key: self._on_pick(k))
            self._group.addButton(btn)
            self.buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch(1)
        self.select("answer")

    def select(self, key: str) -> None:
        for k, btn in self.buttons.items():
            btn.setChecked(k == key)
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.mode_changed.emit(key)

    def current(self) -> str:
        for k, btn in self.buttons.items():
            if btn.isChecked():
                return k
        return "answer"

    def _on_pick(self, key: str) -> None:
        self.select(key)
