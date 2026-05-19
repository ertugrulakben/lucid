"""Frameless translucent Spotlight-style overlay with persistent transcript."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QRectF, Qt, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lucid.capture import ContextSnapshot
from lucid.i18n import _ as t
from lucid.ui.mode_picker import ModePicker
from lucid.ui.prompt_bar import PromptBar
from lucid.ui.theme import QSS_DARK

log = logging.getLogger("lucid.ui.overlay")


class OverlayWindow(QWidget):
    submitted = Signal(str, str, list)  # prompt, mode, attachments (list[PIL.Image])
    cancelled = Signal()
    new_conversation_requested = Signal()
    stop_requested = Signal()
    run_workflow_requested = Signal(str)  # slug
    run_schedule_requested = Signal(str)  # slug (fires scheduled task right now)
    open_schedule_file_requested = Signal()

    def __init__(self, settings) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.settings = settings
        self.current_snapshot: ContextSnapshot | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setObjectName("LucidOverlay")
        self.setStyleSheet(QSS_DARK)
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top toolbar — always-visible entry points for the three discoverability
        # complaints: "where do I attach an image?", "where are my saved
        # workflows?", "where are my scheduled tasks?"
        self.toolbar = QWidget(self)
        self.toolbar.setObjectName("LucidToolbar")
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 0)
        toolbar_layout.setSpacing(6)

        self.attach_button = QPushButton(t("toolbar-attach-image"), self.toolbar)
        self.attach_button.setObjectName("LucidToolbarButton")
        self.attach_button.setFocusPolicy(self.attach_button.focusPolicy().NoFocus)
        self.attach_button.setToolTip(t("toolbar-attach-tooltip"))
        self.attach_button.clicked.connect(self._on_attach_clicked)
        toolbar_layout.addWidget(self.attach_button)

        self.workflows_button = QPushButton(t("toolbar-workflows"), self.toolbar)
        self.workflows_button.setObjectName("LucidToolbarButton")
        self.workflows_button.setFocusPolicy(self.workflows_button.focusPolicy().NoFocus)
        self.workflows_button.setToolTip(t("toolbar-workflows-tooltip"))
        self.workflows_button.clicked.connect(self._show_workflows_menu)
        toolbar_layout.addWidget(self.workflows_button)

        self.schedule_button = QPushButton(t("toolbar-schedule"), self.toolbar)
        self.schedule_button.setObjectName("LucidToolbarButton")
        self.schedule_button.setFocusPolicy(self.schedule_button.focusPolicy().NoFocus)
        self.schedule_button.setToolTip(t("toolbar-schedule-tooltip"))
        self.schedule_button.clicked.connect(self._show_schedule_menu)
        toolbar_layout.addWidget(self.schedule_button)

        toolbar_layout.addStretch(1)

        # Window controls -- minimize, dock, close. Frameless windows lose
        # the OS-provided title bar, so we recreate the essentials so the
        # user can move the overlay out of the way without quitting.
        self.minimize_button = QPushButton(t("window-minimize"), self.toolbar)
        self.minimize_button.setObjectName("LucidWindowControl")
        self.minimize_button.setFocusPolicy(self.minimize_button.focusPolicy().NoFocus)
        self.minimize_button.setToolTip(t("window-minimize-tooltip"))
        self.minimize_button.setFixedWidth(28)
        self.minimize_button.clicked.connect(self._on_minimize)
        toolbar_layout.addWidget(self.minimize_button)

        self.dock_button = QPushButton(t("window-dock"), self.toolbar)
        self.dock_button.setObjectName("LucidWindowControl")
        self.dock_button.setFocusPolicy(self.dock_button.focusPolicy().NoFocus)
        self.dock_button.setToolTip(t("window-dock-tooltip"))
        self.dock_button.setFixedWidth(28)
        self.dock_button.clicked.connect(self._on_dock_cycle)
        toolbar_layout.addWidget(self.dock_button)

        self.close_button = QPushButton(t("window-close"), self.toolbar)
        self.close_button.setObjectName("LucidWindowControl")
        self.close_button.setFocusPolicy(self.close_button.focusPolicy().NoFocus)
        self.close_button.setToolTip(t("window-close-tooltip"))
        self.close_button.setFixedWidth(28)
        self.close_button.clicked.connect(self._on_cancel)
        toolbar_layout.addWidget(self.close_button)

        layout.addWidget(self.toolbar)
        # Drag state -- mousedown on the toolbar starts a window drag.
        self._drag_offset = None

        self.prompt = PromptBar(self)
        self.prompt.submitted.connect(self._on_submit)
        self.prompt.cancelled.connect(self._on_cancel)
        self.prompt.cycle_mode_requested.connect(self._cycle_mode)
        layout.addWidget(self.prompt)

        self.result = QTextEdit(self)
        self.result.setObjectName("LucidResultPane")
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(220)
        self.result.setMaximumHeight(560)
        self.result.hide()
        layout.addWidget(self.result)

        status_row = QWidget(self)
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 8, 0)
        status_layout.setSpacing(8)

        self.status = QLabel(t("status-shortcuts"), status_row)
        self.status.setObjectName("LucidStatus")
        status_layout.addWidget(self.status, 1)

        self.action_log_button = QPushButton(t("toolbar-actions"), status_row)
        self.action_log_button.setObjectName("LucidToolbarButton")
        self.action_log_button.setFocusPolicy(self.action_log_button.focusPolicy().NoFocus)
        self.action_log_button.setToolTip(t("toolbar-actions-tooltip"))
        self.action_log_button.setCheckable(True)
        self.action_log_button.toggled.connect(self._on_toggle_action_log)
        status_layout.addWidget(self.action_log_button)

        self.stop_button = QPushButton(t("toolbar-stop"), status_row)
        self.stop_button.setObjectName("LucidStopButton")
        self.stop_button.setFocusPolicy(self.stop_button.focusPolicy().NoFocus)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.stop_button.hide()
        status_layout.addWidget(self.stop_button)

        layout.addWidget(status_row)

        # Last-10-actions panel. Updated via `append_action_log` each time
        # the Execute loop finishes running a tool call. Hidden by default;
        # toggled via the 📜 Actions button. Useful for video demos and
        # debugging "what did Lucid just try to do?".
        self.action_log = QTextEdit(self)
        self.action_log.setObjectName("LucidActionLog")
        self.action_log.setReadOnly(True)
        self.action_log.setMinimumHeight(120)
        self.action_log.setMaximumHeight(240)
        self.action_log.setStyleSheet(
            "QTextEdit#LucidActionLog { background: rgba(0,0,0,0.55); "
            "color: #ccd; font-family: Consolas, monospace; font-size: 11px; "
            "border: 1px solid #333; border-radius: 6px; padding: 6px; }"
        )
        self.action_log.hide()
        layout.addWidget(self.action_log)
        self._action_log_entries: list[str] = []

        # Horizontal strip showing attached reference images as thumbnails.
        # Appears only when the user pastes one or more images via Ctrl+V.
        self.attachments_bar = QWidget(self)
        self.attachments_bar.setObjectName("LucidAttachmentBar")
        attachments_layout = QHBoxLayout(self.attachments_bar)
        attachments_layout.setContentsMargins(12, 6, 12, 6)
        attachments_layout.setSpacing(8)
        self.attachments_layout = attachments_layout
        self.attachments_hint = QLabel("", self.attachments_bar)
        self.attachments_hint.setStyleSheet("color: #9aa;font-size:11px;")
        attachments_layout.addWidget(self.attachments_hint)
        attachments_layout.addStretch(1)
        self.attachments_bar.hide()
        layout.addWidget(self.attachments_bar)

        self._pending_attachments: list = []

        self.mode_picker = ModePicker(self)
        self.mode_picker.mode_changed.connect(self._on_mode_changed)
        layout.addWidget(self.mode_picker)

        new_chat_sc = QShortcut(QKeySequence("Ctrl+N"), self)
        new_chat_sc.activated.connect(self._on_new_conversation)
        for i, key in enumerate(("answer", "teach", "execute"), start=1):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda k=key: self.mode_picker.select(k))

        # Ctrl+Alt+T — toggle click-through while Execute mode is docked.
        # When engaged, the overlay lets mouse events pass through to the
        # window beneath (close buttons, context menus). Press again to
        # regain focus.
        ct_sc = QShortcut(QKeySequence("Ctrl+Alt+T"), self)
        ct_sc.activated.connect(self._toggle_click_through)

        # Ctrl+M — minimize the overlay to the system tray (hide). The global
        # hotkey reopens it. Lets the user get the overlay out of the way
        # without losing the in-flight conversation transcript.
        min_sc = QShortcut(QKeySequence("Ctrl+M"), self)
        min_sc.activated.connect(self._on_minimize)

        # Ctrl+D — cycle through dock corners (top-right -> top-left ->
        # bottom-right -> bottom-left -> top-right). Persisted to settings
        # so the next session opens in the same corner.
        dock_sc = QShortcut(QKeySequence("Ctrl+D"), self)
        dock_sc.activated.connect(self._on_dock_cycle)

        self._on_mode_changed("answer")
        self._click_through_active = False

    @Slot(str)
    def _on_mode_changed(self, mode: str) -> None:
        keys = {
            "answer": "placeholder-answer",
            "teach": "placeholder-teach",
            "execute": "placeholder-execute",
        }
        self.prompt.setPlaceholderText(t(keys.get(mode, "placeholder-answer")))
        self.prompt.setFocus()

    def _cycle_mode(self) -> None:
        order = ["answer", "teach", "execute"]
        current = self.mode_picker.current()
        idx = (order.index(current) + 1) % len(order)
        self.mode_picker.select(order[idx])

    def present(self, snapshot: ContextSnapshot, transcript: str = "") -> None:
        self.current_snapshot = snapshot
        self.prompt.clear()
        self._clear_attachments()
        self._set_transcript(transcript)
        self._center_on_active_screen()
        self.show()
        self.raise_()
        self.activateWindow()
        self.prompt.setFocus()

    # ---------- toolbar handlers ----------

    @Slot()
    def _on_attach_clicked(self) -> None:
        filters = "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)"
        start = str(getattr(self.settings, "frequent_folders", [""])[0]) if False else ""
        paths, _ = QFileDialog.getOpenFileNames(self, "Select reference image", start, filters)
        if not paths:
            return
        try:
            from PIL import Image
        except ImportError:
            return
        for path in paths:
            try:
                img = Image.open(path).convert("RGB")
            except Exception as exc:
                log.warning("could not open image %s: %s", path, exc)
                continue
            self.attach_image(img)
        self.prompt.setFocus()

    @Slot()
    def _show_workflows_menu(self) -> None:
        menu = QMenu(self)
        try:
            from lucid.recorder.registry import WorkflowRegistry

            registry = WorkflowRegistry(self.settings.workflows_dir)
            entries = registry.list_all()
        except Exception as exc:
            log.warning("workflow menu failed to load: %s", exc)
            entries = []

        if not entries:
            empty = menu.addAction(t("menu-no-workflows"))
            empty.setEnabled(False)
            menu.addSeparator()
            hint = menu.addAction(t("menu-how-to-record"))
            hint.setEnabled(False)
        else:
            for entry in entries:
                label = entry.name or entry.slug
                if entry.target_app:
                    label += f"  ·  {entry.target_app}"
                action = menu.addAction(label)
                action.setToolTip(
                    (entry.slug + "\nAliases: " + ", ".join(entry.aliases[:3]))
                    if entry.aliases
                    else entry.slug
                )
                action.triggered.connect(lambda _=False, s=entry.slug: self._run_workflow(s))

        menu.exec(self.workflows_button.mapToGlobal(self.workflows_button.rect().bottomLeft()))

    @Slot()
    def _show_schedule_menu(self) -> None:
        menu = QMenu(self)
        try:
            from lucid.scheduler import ScheduleStore

            store = ScheduleStore(self.settings.data_dir)
            tasks = store.list_all()
        except Exception as exc:
            log.warning("schedule menu failed to load: %s", exc)
            tasks = []

        if not tasks:
            empty = menu.addAction(t("menu-no-tasks"))
            empty.setEnabled(False)
            menu.addSeparator()
            hint = menu.addAction(t("menu-add-task"))
            hint.setEnabled(False)
        else:
            from datetime import datetime

            for task in tasks:
                when = task.cron or task.run_at or "(manual)"
                nxt = (
                    datetime.fromtimestamp(task.next_run_at).strftime("%d %b %H:%M")
                    if task.next_run_at
                    else "-"
                )
                enabled = "✓" if task.enabled else "✗"
                label = f"{enabled} {task.slug}  ·  {when}  ·  next: {nxt}"
                action = menu.addAction(label)
                action.setToolTip(task.prompt[:200] if task.prompt else task.slug)
                action.triggered.connect(
                    lambda _=False, s=task.slug: self.run_schedule_requested.emit(s)
                )

        menu.addSeparator()
        open_file = menu.addAction(t("menu-open-schedule-file"))
        open_file.triggered.connect(self.open_schedule_file_requested.emit)

        menu.exec(self.schedule_button.mapToGlobal(self.schedule_button.rect().bottomLeft()))

    def _run_workflow(self, slug: str) -> None:
        """Queue a named workflow — switches to Execute mode, prefills slug."""
        self.mode_picker.select("execute")
        self.prompt.setText(slug)
        self.run_workflow_requested.emit(slug)

    # ---------- clipboard / attachment support ----------

    def attach_image(self, pil_image) -> int:
        """Append a clipboard / dropped image and update the thumbnail strip.

        Returns the new total attachment count.
        """
        if pil_image is None:
            return len(self._pending_attachments)
        self._pending_attachments.append(pil_image)
        self._rebuild_attachment_strip()
        return len(self._pending_attachments)

    def _clear_attachments(self) -> None:
        self._pending_attachments = []
        self._rebuild_attachment_strip()

    def _rebuild_attachment_strip(self) -> None:
        # Drop every widget except the hint label + the trailing stretch.
        while self.attachments_layout.count() > 2:
            item = self.attachments_layout.takeAt(1)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        if not self._pending_attachments:
            self.attachments_bar.hide()
            return
        self.attachments_hint.setText(
            f"{len(self._pending_attachments)} reference image(s) attached — Enter to send"
        )
        for idx, pil in enumerate(self._pending_attachments):
            thumb = _pil_to_thumb_label(pil, self.attachments_bar, idx, self)
            self.attachments_layout.insertWidget(self.attachments_layout.count() - 1, thumb)
        self.attachments_bar.show()
        self.adjustSize()

    def remove_attachment(self, index: int) -> None:
        if 0 <= index < len(self._pending_attachments):
            self._pending_attachments.pop(index)
            self._rebuild_attachment_strip()

    def _set_transcript(self, transcript: str) -> None:
        if transcript.strip():
            self.result.setPlainText(transcript.rstrip() + "\n")
            self.result.show()
            cursor = self.result.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.result.setTextCursor(cursor)
            self.result.ensureCursorVisible()
        else:
            self.result.clear()
            self.result.hide()

    def _center_on_active_screen(self) -> None:
        screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.adjustSize()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + int(geo.height() * 0.28)
        self.move(x, y)

    def set_running(self, running: bool) -> None:
        """Toggle the 'Claude is working' UI: stop button + placeholder."""
        self.stop_button.setVisible(running)
        if running:
            self.status.setText(t("status-working"))
        else:
            self.status.setText(t("status-shortcuts"))

    @Slot()
    def _on_minimize(self) -> None:
        """Hide the overlay -- the global hotkey or tray menu reopens it."""
        self.hide()

    @Slot()
    def _on_dock_cycle(self) -> None:
        """Rotate through the four corners and re-dock."""
        order = ["top-right", "top-left", "bottom-right", "bottom-left"]
        current = (
            getattr(self.settings.overlay, "dock_corner", "top-right") or "top-right"
        ).lower()
        try:
            idx = order.index(current)
        except ValueError:
            idx = 0
        nxt = order[(idx + 1) % len(order)]
        try:
            self.settings.overlay.dock_corner = nxt
        except Exception:  # noqa: BLE001 -- settings is read-only in some setups
            pass
        self.dock_to_corner()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Start a window drag when the user grabs the toolbar (or any non-
        widget area at the very top of the overlay).
        """
        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.position().y() <= self.toolbar.geometry().bottom()
        ):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @Slot(bool)
    def _on_toggle_action_log(self, checked: bool) -> None:
        self.action_log.setVisible(checked)
        self.adjustSize()

    def append_action_log(self, line: str) -> None:
        """Push a one-line record (action + short result) into the dock.

        Called by the Execute loop after each tool run. Keeps only the last
        10 lines so the panel stays dense."""
        from datetime import datetime

        stamp = datetime.now().strftime("%H:%M:%S")
        self._action_log_entries.append(f"{stamp}  {line}")
        if len(self._action_log_entries) > 10:
            self._action_log_entries = self._action_log_entries[-10:]
        self.action_log.setPlainText("\n".join(self._action_log_entries))

    def dock_to_corner(self) -> None:
        """Move the overlay to a configurable corner of the active screen.

        ``settings.overlay.dock_corner`` selects the corner so the overlay
        doesn't cover the close button, notification area, or whatever
        the user cares about on their particular layout.
        """
        screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.adjustSize()
        margin = 20
        corner = (getattr(self.settings.overlay, "dock_corner", "top-right") or "top-right").lower()
        if corner == "top-left":
            x, y = geo.x() + margin, geo.y() + margin
        elif corner == "bottom-right":
            x = geo.x() + geo.width() - self.width() - margin
            y = geo.y() + geo.height() - self.height() - margin
        elif corner == "bottom-left":
            x = geo.x() + margin
            y = geo.y() + geo.height() - self.height() - margin
        else:  # top-right (default)
            x = geo.x() + geo.width() - self.width() - margin
            y = geo.y() + margin
        self.move(x, y)
        self.raise_()

    @Slot(str)
    def _on_submit(self, text: str) -> None:
        mode = self.mode_picker.current()
        attachments = list(self._pending_attachments)
        log.info(
            "Submit mode=%s prompt_len=%d attachments=%d",
            mode,
            len(text),
            len(attachments),
        )
        self._append_user_block(text, mode)
        self.status.setText(t("status-working-mode", mode=mode))
        self.submitted.emit(text, mode, attachments)
        self._clear_attachments()

    def _append_user_block(self, text: str, mode: str) -> None:
        self.result.show()
        cursor = self.result.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        prefix = "" if self.result.toPlainText().strip() == "" else "\n\n"
        cursor.insertText(f"{prefix}You: {text}\n\nLucid: ")
        self.result.setTextCursor(cursor)
        self.result.ensureCursorVisible()

    @Slot()
    def _on_cancel(self) -> None:
        self.cancelled.emit()
        self.hide()

    @Slot()
    def _on_new_conversation(self) -> None:
        self.new_conversation_requested.emit()
        self.result.clear()
        self.result.hide()
        self.status.setText(t("status-new"))
        self.prompt.clear()
        self.prompt.setFocus()

    @Slot(str)
    def append_result(self, chunk: str) -> None:
        # Route `[action-log] …` lines to the debug panel only; keep them
        # out of the user-facing conversation pane. Other meta-lines like
        # `[error]`, `[done]`, `[proof]` still render normally so the user
        # sees progress.
        visible_parts: list[str] = []
        for line in chunk.splitlines(keepends=True):
            stripped = line.lstrip()
            if stripped.startswith("[action-log]"):
                payload = stripped[len("[action-log]") :].strip()
                if payload:
                    self.append_action_log(payload)
            else:
                visible_parts.append(line)
        visible = "".join(visible_parts)
        if not visible:
            return
        self.result.show()
        cursor = self.result.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(visible)
        self.result.setTextCursor(cursor)
        self.result.ensureCursorVisible()

    @Slot()
    def mark_done(self) -> None:
        self.status.setText(t("status-done"))
        self.prompt.setFocus()
        self.show()
        self.raise_()
        self.activateWindow()

    @Slot(str)
    def show_error(self, message: str) -> None:
        self.result.show()
        self.append_result(f"\n[error] {message}\n")
        self.status.setText(t("status-error"))

    def paintEvent(self, event) -> None:  # noqa: N802
        """Manually paint the rounded background.

        Qt does not render ``background-color`` on top-level widgets with
        ``WA_TranslucentBackground``, so we draw it ourselves. The alpha
        channel is driven by ``settings.overlay.opacity`` so the user can
        choose how see-through the overlay is — handy in Execute mode
        when something behind the dock (close button, context menu) is
        needed.
        """
        opacity = float(getattr(self.settings.overlay, "opacity", 0.78))
        opacity = max(0.15, min(1.0, opacity))
        alpha = int(round(255 * opacity))
        border_alpha = int(round(255 * min(1.0, opacity + 0.15)))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        painter.fillPath(path, QColor(16, 16, 20, alpha))
        pen = QPen(QColor(120, 120, 140, border_alpha))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)

    def apply_settings(self, settings) -> None:
        """Live-update appearance from (new) settings without a restart."""
        self.settings = settings
        self.update()  # schedule a repaint with the new alpha
        # If the overlay is already docked, move it to the new corner.
        if self.property("keep_open"):
            self.dock_to_corner()

    @Slot()
    def _toggle_click_through(self) -> None:
        """Flip mouse-transparent flag — overlay stays visible but clicks
        pass through to the window underneath. Useful when the dock covers
        a close button or context menu in Execute mode.
        """
        self._click_through_active = not self._click_through_active
        # Qt needs to re-create the native window handle when this attribute
        # changes; we hide + show around setAttribute to force that.
        was_visible = self.isVisible()
        self.hide()
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            self._click_through_active,
        )
        if was_visible:
            self.show()
        log.info("overlay click-through %s", "ON" if self._click_through_active else "OFF")
        self.status.setText(
            t("status-click-through-on")
            if self._click_through_active
            else t("status-click-through-off")
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
            return
        # Ctrl+V → if the OS clipboard holds an image, attach it as a
        # reference (instead of the plain text paste, which would go into
        # the prompt line edit). Text paste still flows through normally
        # because the prompt bar handles it first.
        if event.matches(QKeySequence.StandardKey.Paste) or (
            event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            if self._try_paste_image_from_clipboard():
                return
        super().keyPressEvent(event)

    def _try_paste_image_from_clipboard(self) -> bool:
        """If the clipboard has a raster image, attach it. Returns True on success."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return False
        mime = clipboard.mimeData()
        if mime is None:
            return False
        qimg = None
        if mime.hasImage():
            qimg = clipboard.image()
        if qimg is None or qimg.isNull():
            return False
        try:
            pil = _qimage_to_pil(qimg)
        except Exception as exc:
            log.debug("qimage → PIL failed: %s", exc)
            return False
        count = self.attach_image(pil)
        log.info("clipboard image attached (total=%d)", count)
        return True

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        if (
            event.type() == QEvent.Type.ActivationChange
            and not self.isActiveWindow()
            and not self.property("keep_open")
        ):
            self.hide()
        super().changeEvent(event)


# ---------- module-level helpers ----------


def _qimage_to_pil(qimg):
    """Convert a ``QImage`` into a PIL Image without touching the user's disk."""
    from io import BytesIO

    from PIL import Image as PILImage
    from PySide6.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    qimg.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return PILImage.open(BytesIO(data)).convert("RGB")


def _pil_to_thumb_label(pil_image, parent, index: int, overlay) -> QWidget:
    """Render a ~80px thumbnail; clicking it removes the attachment."""
    from io import BytesIO

    from PySide6.QtCore import QSize
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QPixmap

    thumb_size = 72
    # Downscale on the PIL side to keep Qt fast even for huge pastes.
    preview = pil_image.copy()
    preview.thumbnail((thumb_size * 2, thumb_size * 2))
    buf = BytesIO()
    preview.save(buf, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue())
    button = QPushButton(parent)
    button.setFlat(True)
    button.setIcon(pixmap)
    button.setIconSize(QSize(thumb_size, thumb_size))
    button.setFixedSize(thumb_size + 8, thumb_size + 8)
    button.setFocusPolicy(_Qt.FocusPolicy.NoFocus)
    button.setToolTip(f"Reference image #{index + 1} — click to remove")
    button.clicked.connect(lambda _=False, i=index: overlay.remove_attachment(i))
    return button
