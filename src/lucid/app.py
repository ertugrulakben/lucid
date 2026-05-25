"""Main QApplication wiring: tray icon, hotkey, overlay, mode router."""

from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from lucid.agent.state_machine import Mode, ModeRouter
from lucid.capture import ContextSnapshot
from lucid.config.settings import Settings, get_settings
from lucid.hotkey.listener import HotkeyListener
from lucid.i18n import _ as t
from lucid.ui.cursor_halo import CursorHalo
from lucid.ui.overlay import OverlayWindow

log = logging.getLogger("lucid.app")


class AppController(QObject):
    """Wires hotkey → snapshot → overlay → mode router → back to overlay."""

    toggle_overlay = Signal()

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.overlay = OverlayWindow(settings)
        self.router = ModeRouter(settings)
        self._tray: QSystemTrayIcon | None = None
        self._reopen_after_stream = False

        # Reusable cursor flash widget. One instance is enough -- each flash
        # repositions the same window. Constructed lazily in case the user
        # turned the feature off in settings.
        self._halo: CursorHalo | None = None
        if getattr(settings.overlay, "cursor_halo", True):
            self._halo = CursorHalo(
                radius_px=getattr(settings.overlay, "halo_radius_px", 48),
                duration_ms=getattr(settings.overlay, "halo_duration_ms", 450),
            )

        # MCP bridge -- optional. When `settings.mcp.enabled` is True and the
        # `mcp` extra is installed, each configured server is spawned and its
        # tools are registered into the action registry so ExecuteMode can
        # call them just like any built-in action.
        self._mcp_bridge = None
        if getattr(settings.mcp, "enabled", False):
            try:
                from lucid.mcp import MCPBridge

                if MCPBridge is not None:
                    self._mcp_bridge = MCPBridge(settings)
                    self._mcp_bridge.start()
                else:
                    log.warning("MCP enabled but mcp extra not installed; skipping")
            except Exception as exc:
                log.warning("MCP bridge failed to start: %s", exc)

        # Background scheduler — fires saved cron/one-shot tasks while the
        # tray app is up. Optional: if croniter isn't installed we skip
        # silently so headless test environments still boot.
        self._scheduler = None
        try:
            from lucid.scheduler import SchedulerDaemon, ScheduleStore

            store = ScheduleStore(settings.data_dir)
            self._scheduler = SchedulerDaemon(
                store,
                log_dir=settings.data_dir / "schedule_logs",
                on_task_finished=self._notify_scheduled_task,
            )
            self._scheduler.start()
        except Exception as exc:
            log.warning("scheduler daemon disabled: %s", exc)

        self.overlay.submitted.connect(self._on_submitted)
        self.overlay.cancelled.connect(self._on_cancelled)
        self.overlay.new_conversation_requested.connect(self.router.new_conversation)
        self.overlay.stop_requested.connect(self._on_stop)
        self.overlay.run_workflow_requested.connect(self._on_run_workflow)
        self.overlay.run_schedule_requested.connect(self._on_run_schedule)
        self.overlay.open_schedule_file_requested.connect(self._on_open_schedule_file)
        self.overlay.halo_requested.connect(self._on_halo_requested, Qt.ConnectionType.QueuedConnection)
        self.toggle_overlay.connect(self._on_toggle, Qt.ConnectionType.QueuedConnection)

        self.hotkey = HotkeyListener(settings.hotkey)
        self.hotkey.triggered.connect(self.toggle_overlay.emit)
        self.hotkey.start()

        self.router.stream_chunk.connect(self.overlay.append_result)
        self.router.stream_done.connect(self._on_stream_done)
        self.router.error.connect(self.overlay.show_error)

    def set_tray(self, tray: QSystemTrayIcon) -> None:
        self._tray = tray

    @Slot()
    def _on_toggle(self) -> None:
        # If a Teach recording is in progress, the hotkey stops it.
        if self.router.is_teach_recording():
            log.info("Hotkey pressed during Teach recording → stopping")
            self._set_tray_tooltip()
            self.router.stop_teach()
            return

        if self.overlay.isVisible():
            # Don't hide while a task is running — the user needs to watch.
            if self.router.is_busy():
                self.overlay.raise_()
                self.overlay.activateWindow()
                self.overlay.prompt.setFocus()
                return
            self.overlay.hide()
            return

        self._present_overlay()

    def _present_overlay(self) -> None:
        snapshot = ContextSnapshot.capture(self.settings)
        transcript = self.router.conversation.transcript()
        self.overlay.present(snapshot, transcript)

    @Slot(str, str, list)
    def _on_submitted(self, prompt: str, mode_name: str, attachments: list) -> None:
        mode = Mode(mode_name)
        snapshot = self.overlay.current_snapshot
        # Stash reference images so the ModeRouter forwards them into the
        # first user turn of Execute mode. Answer/Teach ignore them today.
        self.router.pending_attachments = list(attachments or [])
        # If a task is running and the user submits again, stop the old run
        # first and start a fresh dispatch with the new prompt.
        if self.router.is_busy():
            log.info("New prompt submitted while busy → cancelling prior run")
            self.router.cancel()
        if mode is Mode.TEACH:
            # Teach needs the user's mouse/keyboard free — get out of the way.
            self.overlay.hide()
            self._reopen_after_stream = True
            self._set_tray_tooltip(recording=True)
        elif mode is Mode.EXECUTE:
            # Keep the overlay visible but dock it to the corner so the user can
            # watch progress. Claude is instructed to ignore the dock.
            self.overlay.setProperty("keep_open", True)
            self.overlay.dock_to_corner()
            self.overlay.set_running(True)
            self._reopen_after_stream = False
            self._set_tray_tooltip(executing=True)
        else:
            self._reopen_after_stream = False
        self.router.dispatch(prompt, mode, snapshot)

    @Slot()
    def _on_stop(self) -> None:
        log.info("User pressed Stop")
        self.router.cancel()
        self.overlay.set_running(False)
        self.overlay.setProperty("keep_open", False)
        self._set_tray_tooltip()
        # Safety net: if the user stopped mid-typing into their own document,
        # we can undo the last edit so Lucid doesn't leave half-written text
        # behind. Opt-in via settings.executor.auto_undo_on_stop.
        if getattr(self.settings.executor, "auto_undo_on_stop", False):
            try:
                import pyautogui

                pyautogui.hotkey("ctrl", "z")
                log.info("auto_undo_on_stop: sent Ctrl+Z to active window")
                self.overlay.append_result("\n[auto-undo] Ctrl+Z sent to the active window.\n")
            except Exception as exc:
                log.warning("auto_undo_on_stop failed: %s", exc)

    @Slot(str)
    def _on_stream_done(self, mode_name: str) -> None:
        self.overlay.mark_done()
        self.overlay.set_running(False)
        self._set_tray_tooltip()
        if mode_name == Mode.EXECUTE.value:
            # Stay docked + open so the user can chain follow-up steps without
            # re-pressing the hotkey. Esc or hotkey will close it.
            self.overlay.setProperty("keep_open", True)
        else:
            self.overlay.setProperty("keep_open", False)
        if self._reopen_after_stream:
            self._reopen_after_stream = False
            self._present_overlay()

    @Slot()
    def _on_cancelled(self) -> None:
        self.router.cancel()

    @Slot(str)
    def _on_run_workflow(self, slug: str) -> None:
        """Overlay toolbar asked us to replay a saved workflow headlessly."""
        import subprocess
        import sys as _sys

        cmd = [_sys.executable, "-m", "lucid", "run", slug, "--timeout", "300"]
        try:
            subprocess.Popen(cmd, creationflags=_detach_flags())
            self.overlay.append_result(f"\n[workflow] running {slug}…\n")
        except OSError as exc:
            self.overlay.show_error(f"workflow launch failed: {exc}")

    @Slot(str)
    def _on_run_schedule(self, slug: str) -> None:
        """Overlay toolbar asked us to fire a scheduled task immediately."""
        if self._scheduler is None:
            self.overlay.show_error("scheduler daemon not running")
            return
        store = self._scheduler.store
        task = store.get(slug)
        if task is None:
            self.overlay.show_error(f"scheduled task not found: {slug}")
            return
        import subprocess

        from lucid.scheduler.daemon import _build_exec_command

        cmd = _build_exec_command(task)
        try:
            subprocess.Popen(cmd, creationflags=_detach_flags())
            self.overlay.append_result(f"\n[schedule] {slug} triggered…\n")
        except OSError as exc:
            self.overlay.show_error(f"schedule launch failed: {exc}")

    @Slot(str, int, int)
    def _on_halo_requested(self, action_name: str, screen_x: int, screen_y: int) -> None:
        """Forward a stream `[halo]` event to the reusable Cursor Halo widget."""
        if self._halo is None:
            return
        try:
            self._halo.flash(action_name, screen_x, screen_y)
        except Exception as exc:
            log.debug("cursor halo flash failed: %s", exc)

    @Slot()
    def _on_open_schedule_file(self) -> None:
        """Open data/scheduled_tasks.json in the OS default editor."""
        import os

        from lucid.scheduler.store import SCHEDULE_FILE

        path = self.settings.data_dir / SCHEDULE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text('{"tasks": []}', encoding="utf-8")
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            else:
                import subprocess

                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            self.overlay.show_error(f"could not open file: {exc}")

    @Slot(object)
    def reload_settings(self, new_settings: Settings) -> None:
        """Settings dialog saved — refresh live overlay + log a restart note.

        Backend/provider swaps can't be hot-swapped cleanly (the router
        holds an active LLM client), so we show a small notice: user
        needs to quit the tray for provider/model changes.
        """
        old_backend = self.settings.backend.mode
        self.settings = new_settings
        # Hot-swappable: overlay appearance
        self.overlay.apply_settings(new_settings)
        # Cursor halo: re-spin the singleton so radius/duration changes apply
        # immediately, and honour the on/off toggle without a restart.
        want_halo = getattr(new_settings.overlay, "cursor_halo", True)
        if want_halo and self._halo is None:
            self._halo = CursorHalo(
                radius_px=getattr(new_settings.overlay, "halo_radius_px", 48),
                duration_ms=getattr(new_settings.overlay, "halo_duration_ms", 450),
            )
        elif want_halo and self._halo is not None:
            self._halo.configure(
                radius_px=getattr(new_settings.overlay, "halo_radius_px", 48),
                duration_ms=getattr(new_settings.overlay, "halo_duration_ms", 450),
            )
        elif not want_halo and self._halo is not None:
            self._halo.hide()
            self._halo.deleteLater()
            self._halo = None
        if new_settings.backend.mode != old_backend and self._tray is not None:
            try:
                from PySide6.QtWidgets import QSystemTrayIcon as _T

                self._tray.showMessage(
                    t("tray-settings-saved-title"),
                    t("tray-settings-saved-body"),
                    _T.MessageIcon.Information,
                    5000,
                )
            except Exception:
                pass

    def _notify_scheduled_task(self, slug: str, exit_code: int, log_path) -> None:
        """Scheduler callback — Windows toast when a task finishes.

        We notify on any non-zero exit (typical: 124 = timeout, 1 = error,
        137 = killed) AND on exit-0 to confirm success for user feedback.
        Signals are Qt-thread-safe via QSystemTrayIcon.showMessage.
        """
        if self._tray is None:
            return
        try:
            from PySide6.QtWidgets import QSystemTrayIcon as _Tray

            if exit_code == 0:
                title = f"✓ Lucid: {slug}"
                body = f"Scheduled task completed (log: {log_path.name})"
                icon = _Tray.MessageIcon.Information
            elif exit_code == 124:
                title = f"⏱ Lucid: {slug} timed out"
                body = f"Resilient budget exhausted (log: {log_path.name})"
                icon = _Tray.MessageIcon.Warning
            else:
                title = f"✗ Lucid: {slug} failed"
                body = f"Exit code {exit_code} (log: {log_path.name})"
                icon = _Tray.MessageIcon.Critical
            self._tray.showMessage(title, body, icon, 5000)
        except Exception as exc:
            log.warning("tray notification failed: %s", exc)

    def _set_tray_tooltip(self, recording: bool = False, executing: bool = False) -> None:
        if self._tray is None:
            return
        if recording:
            self._tray.setToolTip(t("tray-tooltip-recording", hotkey=self.settings.hotkey))
        elif executing:
            self._tray.setToolTip(
                t("tray-tooltip-executing", hotkey=self.settings.safety.kill_switch_hotkey)
            )
        else:
            self._tray.setToolTip(t("tray-tooltip-base", hotkey=self.settings.hotkey))

    def shutdown(self) -> None:
        self.hotkey.stop()
        self.router.cancel()
        if self._scheduler is not None:
            try:
                self._scheduler.stop(timeout=3.0)
            except Exception:
                pass
        if self._halo is not None:
            try:
                self._halo.hide()
                self._halo.deleteLater()
            except Exception:
                pass
            self._halo = None
        # Make sure the Playwright runtime is gone before the QApplication
        # quits -- otherwise the Chromium subprocess can outlive the tray.
        try:
            from lucid.actions.browser.runtime import BrowserRuntime

            BrowserRuntime.reset()
        except Exception:
            pass
        # Tear down the MCP supervisor (its background loop + every spawned
        # server subprocess) the same way.
        if self._mcp_bridge is not None:
            try:
                self._mcp_bridge.stop()
            except Exception as exc:
                log.debug("MCP bridge stop failed: %s", exc)
            self._mcp_bridge = None


def _detach_flags() -> int:
    """Windows DETACHED_PROCESS flags so spawned subprocesses outlive the tray."""
    if sys.platform != "win32":
        return 0
    import subprocess

    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )


def _install_tray(app: QApplication, controller: AppController) -> QSystemTrayIcon:
    icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.ico"
    icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip(t("tray-tooltip-base", hotkey=controller.settings.hotkey))

    menu = QMenu()
    act_open = QAction(t("tray-open"), menu)
    act_open.triggered.connect(controller.toggle_overlay.emit)
    menu.addAction(act_open)

    act_new = QAction(t("tray-new-conversation"), menu)
    act_new.triggered.connect(controller.router.new_conversation)
    menu.addAction(act_new)

    # Dynamic submenu — rebuilt on every hover so newly-recorded workflows
    # appear without a tray restart.
    workflows_menu = QMenu(t("tray-saved-workflows"), menu)
    menu.addMenu(workflows_menu)

    def _refresh_workflows() -> None:
        workflows_menu.clear()
        try:
            from lucid.recorder.registry import WorkflowRegistry

            entries = WorkflowRegistry(controller.settings.workflows_dir).list_all()
        except Exception:
            entries = []
        if not entries:
            stub = workflows_menu.addAction(t("tray-no-workflows"))
            stub.setEnabled(False)
            return
        for entry in entries:
            label = entry.name or entry.slug
            action = workflows_menu.addAction(label)
            action.triggered.connect(lambda _=False, s=entry.slug: controller._on_run_workflow(s))

    workflows_menu.aboutToShow.connect(_refresh_workflows)

    schedules_menu = QMenu(t("tray-scheduled-tasks"), menu)
    menu.addMenu(schedules_menu)

    def _refresh_schedules() -> None:
        schedules_menu.clear()
        try:
            from lucid.scheduler import ScheduleStore

            tasks = ScheduleStore(controller.settings.data_dir).list_all()
        except Exception:
            tasks = []
        if not tasks:
            stub = schedules_menu.addAction(t("tray-no-schedules"))
            stub.setEnabled(False)
        else:
            from datetime import datetime

            for task in tasks:
                when = task.cron or task.run_at or "(manual)"
                nxt = (
                    datetime.fromtimestamp(task.next_run_at).strftime("%d %b %H:%M")
                    if task.next_run_at
                    else "-"
                )
                tag = "✓" if task.enabled else "✗"
                action = schedules_menu.addAction(f"{tag} {task.slug}  ·  {when}  ·  {nxt}")
                action.triggered.connect(
                    lambda _=False, s=task.slug: controller._on_run_schedule(s)
                )
        schedules_menu.addSeparator()
        open_file = schedules_menu.addAction(t("menu-open-schedule-file"))
        open_file.triggered.connect(controller._on_open_schedule_file)

    schedules_menu.aboutToShow.connect(_refresh_schedules)

    def _open_settings_dialog() -> None:
        from lucid.ui.settings_dialog import SettingsDialog

        dlg = SettingsDialog(controller.settings)
        dlg.settings_saved.connect(controller.reload_settings)
        dlg.exec()

    act_settings = QAction(t("tray-settings"), menu)
    act_settings.triggered.connect(_open_settings_dialog)
    menu.addAction(act_settings)

    act_settings_file = QAction(t("tray-open-settings-file"), menu)
    act_settings_file.triggered.connect(
        lambda: QMessageBox.information(None, "Lucid", str(controller.settings.config_path))
    )
    menu.addAction(act_settings_file)

    menu.addSeparator()
    act_quit = QAction(t("tray-quit"), menu)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (
            controller.toggle_overlay.emit()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
    )
    tray.show()
    controller.set_tray(tray)
    return tray


def _setup_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(settings.log_dir / "lucid.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_app() -> int:
    settings = get_settings()
    _setup_logging(settings)
    log.info("Lucid starting, hotkey=%s", settings.hotkey)

    app = QApplication(sys.argv)
    app.setApplicationName("Lucid")
    app.setQuitOnLastWindowClosed(False)

    controller = AppController(settings)
    tray = _install_tray(app, controller)
    _ = tray

    signal.signal(signal.SIGINT, lambda *_: app.quit())

    try:
        return app.exec()
    finally:
        controller.shutdown()
