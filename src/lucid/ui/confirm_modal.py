"""Modal dialog for destructive action confirmation.

Lives on the Qt main thread. Safety guard callbacks are invoked from the
Execute worker thread, so we route through a queued signal to pop the
modal and block the worker until the user answers.

Three outcomes:
- **Allow**: execute this single action.
- **Deny**: skip this action (Claude sees the refusal in the tool_result).
- **Always in session**: allow subsequent actions of the same kind without
  asking again until Lucid is restarted.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


@dataclass
class ConfirmResult:
    allowed: bool = False
    always: bool = False


@dataclass
class _Pending:
    reason: str
    detail: str
    result: ConfirmResult = field(default_factory=ConfirmResult)
    done: threading.Event = field(default_factory=threading.Event)


class ConfirmBroker(QObject):
    """Thread-safe bridge: worker threads call ``ask`` and block until answered."""

    _show_requested = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session_allow: set[str] = set()
        self._show_requested.connect(self._on_show_requested, Qt.ConnectionType.QueuedConnection)

    def ask(self, kind: str, reason: str, detail: str = "", timeout: float = 20.0) -> ConfirmResult:
        """Blocking call from a worker thread. Returns the user's decision."""
        if kind in self._session_allow:
            return ConfirmResult(allowed=True, always=True)

        pending = _Pending(reason=reason, detail=detail)
        # Cross-thread signal hop — main thread will pop the dialog.
        self._show_requested.emit(pending)
        pending.done.wait(timeout=timeout)
        if not pending.done.is_set():
            # Timed out → treat as denial (safer default).
            return ConfirmResult(allowed=False, always=False)

        if pending.result.always and pending.result.allowed:
            self._session_allow.add(kind)
        return pending.result

    @Slot(object)
    def _on_show_requested(self, pending: _Pending) -> None:
        app = QApplication.instance()
        if app is None:
            pending.done.set()
            return
        dlg = _ConfirmDialog(pending.reason, pending.detail)
        outcome = dlg.exec()
        if outcome == QDialog.DialogCode.Accepted:
            pending.result.allowed = True
            pending.result.always = dlg.remember_choice
        else:
            pending.result.allowed = False
        pending.done.set()


class _ConfirmDialog(QDialog):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__()
        self.setWindowTitle("Lucid — Confirmation Required")
        self.setModal(True)
        self.remember_choice = False

        layout = QVBoxLayout(self)
        header = QLabel("An action with persistent side effects was detected.")
        header.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(header)

        reason_lbl = QLabel(reason)
        reason_lbl.setWordWrap(True)
        layout.addWidget(reason_lbl)

        if detail:
            detail_lbl = QLabel(detail)
            detail_lbl.setWordWrap(True)
            detail_lbl.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(detail_lbl)

        buttons = QHBoxLayout()
        self.btn_deny = QPushButton("Deny")
        self.btn_allow = QPushButton("Allow")
        self.btn_always = QPushButton("Always this session")

        self.btn_deny.clicked.connect(self.reject)
        self.btn_allow.clicked.connect(self._accept_once)
        self.btn_always.clicked.connect(self._accept_always)

        buttons.addWidget(self.btn_deny)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_allow)
        buttons.addWidget(self.btn_always)
        layout.addLayout(buttons)

        self.setMinimumWidth(480)

    def _accept_once(self) -> None:
        self.remember_choice = False
        self.accept()

    def _accept_always(self) -> None:
        self.remember_choice = True
        self.accept()


# Module-level singleton so safety code can fetch/set without wiring through
# every constructor.
_broker: ConfirmBroker | None = None


def get_broker() -> ConfirmBroker | None:
    return _broker


def set_broker(broker: ConfirmBroker | None) -> None:
    global _broker
    _broker = broker
