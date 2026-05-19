"""Background scheduler — fires ``lucid exec`` subprocesses on their due time.

Owned by the Qt tray app. Runs a daemon thread that wakes every 20–30 s,
asks :class:`ScheduleStore` for tasks whose ``next_run_at`` has elapsed,
spawns ``python -m lucid exec ...`` for each, and stamps the store with
the result. Because each fire is its own subprocess, a long-running task
never blocks subsequent timers.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

from lucid.config.settings import get_settings
from lucid.scheduler.store import ScheduledTask, ScheduleStore, compute_next_run

log = logging.getLogger("lucid.scheduler")


def _settings_int(path: tuple[str, ...], fallback: int) -> int:
    """Read a nested setting and degrade gracefully when settings can't be loaded."""
    try:
        node: object = get_settings()
        for attr in path:
            node = getattr(node, attr)
        if isinstance(node, int):
            return node
    except Exception:  # -- settings IO errors are non-fatal here
        pass
    return fallback


# Backstop constants kept for older callers; live values come from Settings.
POLL_INTERVAL_SECONDS = 20
RESILIENT_MIN_TIMEOUT = 600
RESILIENT_MIN_MAX_STEPS = 200
KERNEL_KILL_BUFFER_SECONDS = 30


def _effective_timeout(task: ScheduledTask) -> int:
    """The real per-task wall-clock limit Lucid will honour inside the run.

    When ``resilient`` is set the user wants long tasks to work; enforce a
    floor so cron `timeout_seconds=300` doesn't silently shackle a flagged-
    as-resilient task back to 5 minutes (the symptom we saw in production
    logs: exit=124 on btc_sinyal at 302s with resilient=true).
    """
    base = int(task.timeout_seconds or 0) or 180
    if task.resilient:
        floor = _settings_int(("executor", "resilient_min_timeout"), RESILIENT_MIN_TIMEOUT)
        return max(base, floor)
    return base


def _effective_max_steps(task: ScheduledTask) -> int | None:
    raw = int(task.max_steps or 0)
    if task.resilient:
        floor = _settings_int(("executor", "resilient_min_max_steps"), RESILIENT_MIN_MAX_STEPS)
        if raw and raw < floor:
            return floor
        if not raw:
            return floor
    return raw or None


def _build_exec_command(task: ScheduledTask) -> list[str]:
    """Translate a ScheduledTask into the equivalent ``lucid exec`` argv."""
    cmd = [sys.executable, "-m", "lucid", "exec", task.prompt]
    if task.template:
        cmd.extend(["--template", task.template])
    for key, value in (task.variables or {}).items():
        cmd.extend(["--var", f"{key}={value}"])
    for attachment in task.attachments or []:
        cmd.extend(["--image", str(attachment)])
    effective_timeout = _effective_timeout(task)
    cmd.extend(["--timeout", str(effective_timeout)])
    effective_steps = _effective_max_steps(task)
    if effective_steps:
        cmd.extend(["--max-steps", str(effective_steps)])
    if task.resilient:
        cmd.append("--resilient")
    return cmd


def run_once_now(task: ScheduledTask, log_dir: Path | None = None) -> int:
    """Fire a task immediately (ignoring its schedule). Used by ``lucid schedule run``.

    Blocks until the subprocess finishes and returns its exit code. Stdout
    and stderr are merged into a per-task log file when ``log_dir`` is
    given; otherwise they inherit the current terminal.
    """
    cmd = _build_exec_command(task)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stdout = None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{stamp}-{task.slug}.log"
        stdout = log_path.open("w", encoding="utf-8")
        log.info("scheduled run → %s (log: %s)", task.slug, log_path)
    else:
        log.info("scheduled run → %s (inline stdout)", task.slug)
    try:
        proc = subprocess.run(
            cmd,
            stdout=stdout,
            stderr=subprocess.STDOUT if stdout is not None else None,
            text=True,
        )
        return proc.returncode
    finally:
        if stdout is not None:
            stdout.close()


class SchedulerDaemon:
    """Long-lived thread that ticks the store and dispatches due tasks."""

    def __init__(
        self,
        store: ScheduleStore,
        log_dir: Path,
        poll_seconds: int | None = None,
        on_task_finished: callable | None = None,  # type: ignore[valid-type]
    ) -> None:
        self.store = store
        self.log_dir = Path(log_dir)
        if poll_seconds is None:
            poll_seconds = _settings_int(
                ("scheduler", "poll_interval_seconds"), POLL_INTERVAL_SECONDS
            )
        self.poll_seconds = max(5, int(poll_seconds))
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._active: dict[str, subprocess.Popen] = {}
        # Called after a scheduled task exits with (slug, exit_code, log_path).
        # The tray app plugs this in to raise a Windows toast when exit != 0.
        self._on_task_finished = on_task_finished

    # ---------- lifecycle ----------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="lucid-scheduler")
        self._thread.start()
        log.info("scheduler daemon started (poll %ds)", self.poll_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        # Don't forcibly kill running subprocesses — they represent real
        # work the user chose to schedule; best-effort reap only.
        self._reap_finished()

    # ---------- main loop ----------

    def _run(self) -> None:
        self._prime_next_runs()
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                log.exception("scheduler tick crashed: %s", exc)
            self._stop.wait(self.poll_seconds)

    def _prime_next_runs(self) -> None:
        """Fill ``next_run_at`` for any freshly-loaded tasks that lack it."""
        for task in self.store.list_all():
            if task.next_run_at is None and task.enabled:
                try:
                    self.store.refresh_next_run(task.slug)
                except Exception as exc:
                    log.debug("prime next_run_at failed for %s: %s", task.slug, exc)

    def _tick(self) -> None:
        self._reap_finished()
        now = time.time()
        for task in self.store.list_all():
            if not task.enabled:
                continue
            if task.slug in self._active:
                continue  # previous firing still running
            due = task.next_run_at
            if due is None:
                due = compute_next_run(task, reference=now)
                if due is None:
                    continue
                self.store.refresh_next_run(task.slug)
            if due <= now:
                self._dispatch(task)

    def _dispatch(self, task: ScheduledTask) -> None:
        cmd = _build_exec_command(task)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / f"{stamp}-{task.slug}.log"
        try:
            handle = log_path.open("w", encoding="utf-8")
            proc = subprocess.Popen(
                cmd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=_DETACH_FLAGS,
            )
        except OSError as exc:
            log.error("failed to launch scheduled task %s: %s", task.slug, exc)
            self.store.mark_fired(task.slug, exit_code=-1)
            return
        self._active[task.slug] = proc
        # Monitor subprocess in its own thread so we can stamp the store
        # when it exits without blocking the scheduler tick cadence.
        threading.Thread(
            target=self._await_exit,
            args=(task.slug, proc, handle, log_path, _effective_timeout(task)),
            daemon=True,
            name=f"lucid-scheduler-{task.slug}",
        ).start()
        log.info("scheduled task fired: %s (pid=%s, log=%s)", task.slug, proc.pid, log_path)

    def _await_exit(
        self,
        slug: str,
        proc: subprocess.Popen,
        handle,
        log_path: Path,
        effective_timeout: int,
    ) -> None:
        """Wait for the subprocess, but enforce a hard wall-clock ceiling.

        Lucid's in-process ``--timeout`` should fire first and let the task
        exit cleanly. If it doesn't (hung thread, deadlock, Windows input
        event pump blocked), we escalate to terminate → kill after a short
        buffer. This is what actually ensures exit=124 surfaces instead of
        a phantom "still running" row in the scheduled-tasks list.
        """
        hard_limit = effective_timeout + KERNEL_KILL_BUFFER_SECONDS
        exit_code = -1
        try:
            exit_code = proc.wait(timeout=hard_limit)
        except subprocess.TimeoutExpired:
            log.warning(
                "scheduled task %s exceeded hard limit (%ds); terminating", slug, hard_limit
            )
            try:
                proc.terminate()
                exit_code = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log.warning("scheduled task %s did not terminate; killing", slug)
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    exit_code = proc.wait(timeout=5)
                except Exception:
                    exit_code = 137  # SIGKILL equivalent
        except Exception:
            exit_code = -1
        finally:
            try:
                handle.close()
            except Exception:
                pass
            self._active.pop(slug, None)
        self.store.mark_fired(slug, exit_code=exit_code)
        log.info("scheduled task %s finished (exit=%s, log=%s)", slug, exit_code, log_path)
        if self._on_task_finished is not None:
            try:
                self._on_task_finished(slug, exit_code, log_path)
            except Exception as exc:
                log.warning("on_task_finished hook raised: %s", exc)

    def _reap_finished(self) -> None:
        for slug, proc in list(self._active.items()):
            if proc.poll() is not None:
                self._active.pop(slug, None)


# CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS so the subprocess survives
# even if the tray app is Ctrl+C'd (Windows). On other OSes this is a no-op.
if sys.platform == "win32":
    _DETACH_FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )
else:
    _DETACH_FLAGS = 0
