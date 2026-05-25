"""Step Gallery: visual run history for Execute mode.

The panel slots into the overlay below the result pane. Each cell is a
before-thumbnail with the action name + one-line outcome underneath; clicking
a cell opens a detail dialog with the before/after pair side by side and the
raw tool params.

The panel is purely a viewer. The Execute loop writes records via
:class:`lucid.journal.StepJournal`; the overlay calls :meth:`add_record` for
each new step it sees in the stream, and the gallery reads previous sessions
on demand via :meth:`load_session`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from lucid.i18n import _ as t
from lucid.journal.models import StepRecord
from lucid.journal.store import read_session

log = logging.getLogger("lucid.ui.step_gallery")

_THUMB_WIDTH = 200
_CELL_PADDING = 6


class StepGalleryPanel(QWidget):
    """Scrolling grid of step cards for the active or a loaded session."""

    cell_activated = Signal(int)  # step id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LucidStepGallery")
        self._session_dir: Path | None = None
        self._records: list[StepRecord] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 8)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.title_label = QLabel(t("step-gallery-empty"), self)
        self.title_label.setObjectName("LucidStepGalleryTitle")
        header.addWidget(self.title_label, 1)
        outer.addLayout(header)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("LucidStepGalleryScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(180)
        self.scroll.setMaximumHeight(360)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._grid_host = QWidget(self.scroll)
        self._grid_host.setObjectName("LucidStepGridHost")
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(8)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self._grid_host)
        outer.addWidget(self.scroll)

        self.setStyleSheet(
            "QLabel#LucidStepGalleryTitle { color: #cdd; font-size: 12px; }"
            "QScrollArea#LucidStepGalleryScroll { border: 1px solid #333; "
            "border-radius: 6px; background: rgba(0,0,0,0.4); }"
            "QWidget#LucidStepGridHost { background: transparent; }"
            "QPushButton[LucidStepCell=\"true\"] { background: rgba(28,28,36,0.85); "
            "border: 1px solid #2c2c38; border-radius: 6px; padding: 4px; color: #dde; }"
            "QPushButton[LucidStepCell=\"true\"]:hover { border: 1px solid #56C2FF; }"
        )

    # ------------------------- public API -------------------------

    def clear(self) -> None:
        """Drop every cell. Used when a new Execute run starts."""
        self._records.clear()
        self._session_dir = None
        self._rebuild()
        self.title_label.setText(t("step-gallery-empty"))

    def bind_session(self, session_dir: Path) -> None:
        """Point the gallery at an active session folder so new records can land here."""
        self._session_dir = session_dir
        if not self._records:
            self.title_label.setText(t("step-gallery-active", name=session_dir.name))

    def add_record(self, record: StepRecord, session_dir: Path | None = None) -> None:
        """Append one freshly-recorded step to the grid."""
        if session_dir is not None:
            self._session_dir = session_dir
        self._records.append(record)
        self.title_label.setText(
            t("step-gallery-active", name=(self._session_dir.name if self._session_dir else "session"))
        )
        self._add_cell(record)

    def load_session(self, session_dir: Path) -> None:
        """Replace the visible grid with a previously saved session."""
        self._records = read_session(session_dir)
        self._session_dir = session_dir
        self.title_label.setText(
            t("step-gallery-loaded", name=session_dir.name, count=len(self._records))
            if self._records
            else t("step-gallery-empty")
        )
        self._rebuild()

    # ------------------------- internals -------------------------

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        for record in self._records:
            self._add_cell(record)

    def _add_cell(self, record: StepRecord) -> None:
        cell = _StepCell(record, self._session_dir, parent=self._grid_host)
        cell.activated.connect(lambda rec=record: self._open_detail(rec))
        cell.setProperty("LucidStepCell", True)
        cell.style().unpolish(cell)
        cell.style().polish(cell)
        count = self._grid.count()
        row, col = divmod(count, 3)
        self._grid.addWidget(cell, row, col)

    def _open_detail(self, record: StepRecord) -> None:
        dialog = StepDetailDialog(record, self._session_dir, parent=self.window())
        dialog.exec()
        self.cell_activated.emit(record.id)


class _StepCell(QPushButton):
    """One step thumbnail tile."""

    activated = Signal()

    def __init__(self, record: StepRecord, session_dir: Path | None, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFlat(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(QSize(_THUMB_WIDTH + _CELL_PADDING * 2, 170))
        self.setMaximumWidth(_THUMB_WIDTH + _CELL_PADDING * 2 + 4)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.clicked.connect(self.activated.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_CELL_PADDING, _CELL_PADDING, _CELL_PADDING, _CELL_PADDING)
        layout.setSpacing(4)

        thumb_label = QLabel(self)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setMinimumHeight(110)
        thumb_label.setStyleSheet("background: rgba(0,0,0,0.5); border-radius: 4px;")
        pix = _load_thumb(record.after_thumb or record.before_thumb, session_dir)
        if pix is not None:
            thumb_label.setPixmap(
                pix.scaled(
                    _THUMB_WIDTH,
                    110,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            thumb_label.setText("(no thumbnail)")
            thumb_label.setStyleSheet(
                "background: rgba(0,0,0,0.5); border-radius: 4px; color: #777;"
            )
        layout.addWidget(thumb_label)

        head = QLabel(f"#{record.id}  {record.action_name}", self)
        head.setStyleSheet("color: #ddf; font-weight: 600; font-size: 11px;")
        head.setWordWrap(True)
        layout.addWidget(head)

        short = record.short_params()
        if short:
            sub = QLabel(short, self)
            sub.setStyleSheet("color: #9ac; font-size: 10px;")
            sub.setWordWrap(True)
            layout.addWidget(sub)

        outcome = record.outcome_one_line()
        if outcome:
            tail = QLabel(outcome, self)
            tail.setStyleSheet("color: #bbb; font-size: 10px;")
            tail.setWordWrap(True)
            layout.addWidget(tail)


class StepDetailDialog(QDialog):
    """Modal: before/after side-by-side plus raw tool params + outcome."""

    def __init__(
        self,
        record: StepRecord,
        session_dir: Path | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Lucid Step #{record.id} — {record.action_name}")
        self.resize(960, 640)

        outer = QVBoxLayout(self)

        images_row = QHBoxLayout()
        images_row.setSpacing(12)
        images_row.addWidget(self._image_panel(t("step-detail-before"), record.before_thumb, session_dir))
        images_row.addWidget(self._image_panel(t("step-detail-after"), record.after_thumb, session_dir))
        outer.addLayout(images_row, 3)

        meta = QTextBrowser(self)
        meta.setObjectName("LucidStepDetailMeta")
        meta.setStyleSheet(
            "QTextBrowser#LucidStepDetailMeta { background: #111118; color: #cdd; "
            "font-family: Consolas, monospace; font-size: 11px; border: 1px solid #222; }"
        )
        meta.setPlainText(
            f"Action:   {record.action_name}\n"
            f"Step id:  {record.id}\n"
            f"Time:     {record.ts}\n"
            f"Coord:    {record.coord}\n"
            f"Monitor:  {record.monitor_index}\n"
            f"\nParams:\n{json.dumps(record.params, indent=2, ensure_ascii=False)}\n"
            f"\nOutcome:\n{record.outcome.strip()}"
        )
        outer.addWidget(meta, 2)

        close = QPushButton(t("button-close"), self)
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        outer.addLayout(bottom)

    def _image_panel(self, caption: str, name: str | None, session_dir: Path | None) -> QWidget:
        wrapper = QWidget(self)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        cap = QLabel(caption, wrapper)
        cap.setStyleSheet("color: #aab; font-weight: 600;")
        layout.addWidget(cap)

        image_label = QLabel(wrapper)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setStyleSheet("background: #0a0a10; border: 1px solid #222; border-radius: 6px;")
        image_label.setMinimumHeight(360)
        pix = _load_thumb(name, session_dir)
        if pix is not None:
            image_label.setPixmap(
                pix.scaled(
                    440,
                    340,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            image_label.setText("(missing)")
            image_label.setStyleSheet(
                "background: #0a0a10; border: 1px solid #222; border-radius: 6px; color: #555;"
            )
        layout.addWidget(image_label, 1)
        return wrapper


def _load_thumb(name: str | None, session_dir: Path | None) -> QPixmap | None:
    if not name or session_dir is None:
        return None
    target = session_dir / name
    if not target.exists():
        return None
    pix = QPixmap(str(target))
    if pix.isNull():
        return None
    return pix
