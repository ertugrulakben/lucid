"""Entry point: `python -m lucid` or `lucid` console script."""

from __future__ import annotations

import argparse
import sys

from lucid import __version__


def _force_utf8_stdio() -> None:
    """Windows terminals default to cp1254 (Turkish) and crash on ``→``, etc.

    Flip stdout/stderr to UTF-8 replace-mode so Lucid's progress stream
    never dies over a rogue arrow character.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _enable_dpi_awareness() -> None:
    """Opt into per-monitor DPI awareness on Windows.

    Without this, Windows virtualizes coordinates on scaled displays (125%
    is the default on many 4K laptops): ``mss`` screenshots and ``pyautogui``
    clicks end up on different pixel grids, so every click misses the thing
    Claude actually saw. Must run before any GUI toolkit or capture library
    touches the display.
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE_V2
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def _cmd_exec(args: argparse.Namespace) -> int:
    from pathlib import Path

    from lucid.headless import HeadlessOptions, run_headless

    prompt = args.prompt
    if args.template:
        from lucid.templates import TemplateError, expand_template

        variables: dict[str, str] = {}
        for raw in args.var or []:
            if "=" not in raw:
                print(f"error: --var must be KEY=VALUE, got: {raw!r}")
                return 2
            key, _, value = raw.partition("=")
            variables[key.strip()] = value
        try:
            template_prompt = expand_template(args.template, variables)
        except TemplateError as exc:
            print(f"error: {exc}")
            return 2
        prompt = f"{prompt}\n\n{template_prompt}".strip() if prompt else template_prompt

    if not prompt:
        print("error: provide a prompt or --template")
        return 2

    attachments: list[Path] = []
    for raw in args.image or []:
        attachments.append(Path(raw).expanduser())

    # ``--resilient`` = long-task mode: raise the budgets unless the user
    # already set them explicitly, and tell the executor to nudge Claude
    # toward persistence via a prompt prefix.
    timeout = args.timeout
    max_steps = args.max_steps
    if args.resilient:
        if timeout == 180:
            timeout = 600
        if max_steps is None:
            max_steps = 200
        prompt = (
            "[LONG-TASK MODE] This is a multi-part task. Complete every "
            "sub-goal listed below before emitting [done]. Don't stop after "
            "one part — keep going until all parts are finished or blocked.\n\n" + prompt
        )

    options = HeadlessOptions(
        prompt=prompt,
        timeout=timeout,
        max_steps=max_steps,
        backend=args.backend,
        json_output=args.json,
        disable_memory=args.no_memory,
        disable_profile=args.profile_ignore,
        attachments=attachments,
    )
    return run_headless(options)


def _parse_vars(raw_vars: list[str] | None) -> tuple[dict[str, str], str | None]:
    variables: dict[str, str] = {}
    for raw in raw_vars or []:
        if "=" not in raw:
            return {}, f"--var must be KEY=VALUE, got: {raw!r}"
        key, _, value = raw.partition("=")
        variables[key.strip()] = value
    return variables, None


def _parse_relative_delay(spec: str) -> int:
    """'5m', '30m', '2h', '1d' → delay in seconds. Raises ValueError on bad input."""
    import re

    s = (spec or "").strip().lower()
    m = re.fullmatch(r"(\d+)\s*([smhd])", s)
    if not m:
        raise ValueError(f"--in must be like 5m, 30m, 2h, 1d — got {spec!r}")
    n, unit = int(m.group(1)), m.group(2)
    if n <= 0:
        raise ValueError("--in delay must be positive")
    factor = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    total = n * factor
    if total < 30:
        raise ValueError("--in delay too small (min 30 seconds)")
    if total > 30 * 86400:
        raise ValueError("--in delay too large (max 30 days)")
    return total


def _cmd_replay(args: argparse.Namespace) -> int:
    from pathlib import Path

    from lucid.replayer.cli import run_replay

    variables, err = _parse_vars(getattr(args, "var", None))
    if err:
        print(f"error: {err}")
        return 2
    return run_replay(
        workflow_path=Path(args.workflow),
        timeout=args.timeout,
        json_output=args.json,
        variables=variables,
    )


def _cmd_run(args: argparse.Namespace) -> int:
    from lucid.replayer.cli import run_replay

    variables, err = _parse_vars(args.var)
    if err:
        print(f"error: {err}")
        return 2
    return run_replay(
        workflow_path=args.target,
        timeout=args.timeout,
        json_output=args.json,
        variables=variables,
    )


def _cmd_workflows(args: argparse.Namespace) -> int:
    from lucid.config.settings import get_settings
    from lucid.recorder.registry import WorkflowRegistry

    settings = get_settings()
    registry = WorkflowRegistry(settings.workflows_dir)
    entries = registry.list_all()
    if not entries:
        print("No recorded workflows yet. Use Teach mode (Ctrl+Alt+J → Ctrl+2) to record one.")
        return 0
    for entry in entries:
        print(f"{entry.slug}  -  {entry.name}")
        if entry.aliases:
            print(f"  aliases: {', '.join(entry.aliases)}")
        if entry.target_app:
            print(f"  target:  {entry.target_app}")
        if entry.variables:
            var_parts = []
            for v in entry.variables:
                bit = v.name
                if v.example:
                    bit += f" (example: {v.example})"
                var_parts.append(bit)
            print(f"  vars:    {', '.join(var_parts)}")
        print(f"  file:    {entry.path}")
    return 0


def _cmd_forget(args: argparse.Namespace) -> int:
    from lucid.config.settings import get_settings
    from lucid.recorder.registry import WorkflowRegistry

    settings = get_settings()
    registry = WorkflowRegistry(settings.workflows_dir)
    entry = registry.get(args.slug) or registry.find(args.slug)
    if entry is None:
        print(f"no workflow matching {args.slug!r}")
        return 2
    removed = registry.remove(entry.slug)
    if args.delete_file:
        path = settings.workflows_dir / entry.path
        try:
            path.unlink()
        except OSError:
            pass
    print(f"forgotten: {entry.slug} ({'removed' if removed else 'not in registry'})")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from lucid.status import print_status

    return print_status(json_output=args.json)


def _cmd_schedule(args: argparse.Namespace) -> int:
    import json
    from datetime import datetime, timedelta

    from lucid.config.settings import get_settings
    from lucid.recorder.workflow import slugify
    from lucid.scheduler import (
        ScheduledTask,
        ScheduleStore,
        compute_next_run,
        normalise_every,
        run_once_now,
    )

    settings = get_settings()
    store = ScheduleStore(settings.data_dir)
    action = args.schedule_cmd

    if action == "list":
        tasks = store.list_all()
        if not tasks:
            print(
                'No scheduled tasks. Add one with: lucid schedule add --cron "0 9 * * *" --prompt "..."'
            )
            return 0
        payload = []
        for task in tasks:
            nxt = (
                datetime.fromtimestamp(task.next_run_at).strftime("%Y-%m-%d %H:%M")
                if task.next_run_at
                else "-"
            )
            last = (
                datetime.fromtimestamp(task.last_run_at).strftime("%Y-%m-%d %H:%M")
                if task.last_run_at
                else "never"
            )
            if args.json:
                payload.append(task.to_dict())
            else:
                flag = "on " if task.enabled else "off"
                schedule = task.cron or task.run_at or "(manual)"
                print(
                    f"{task.slug:24} [{flag}]  {schedule:24}  next: {nxt}  last: {last}  runs: {task.run_count}"
                )
                if task.prompt:
                    preview = task.prompt if len(task.prompt) < 80 else task.prompt[:77] + "..."
                    print(f"    → {preview}")
        if args.json:
            print(json.dumps({"tasks": payload}, ensure_ascii=False, indent=2))
        return 0

    if action == "add":
        slug = (args.slug or slugify(args.prompt or args.template or "")).strip().lower()
        if not slug:
            print("error: --slug (or a prompt to derive one) is required")
            return 2
        if not (args.prompt or args.template):
            print("error: either --prompt or --template must be supplied")
            return 2

        cron = args.cron
        if args.every:
            if cron:
                print("error: use either --cron or --every, not both")
                return 2
            try:
                cron = normalise_every(args.every)
            except ValueError as exc:
                print(f"error: {exc}")
                return 2

        run_at = args.at
        if run_at:
            try:
                datetime.fromisoformat(run_at)
            except ValueError:
                print(f"error: --at must be ISO 8601 (e.g. 2026-04-20T09:00), got: {run_at!r}")
                return 2
            if cron:
                print("error: use either --cron/--every or --at, not both")
                return 2

        if getattr(args, "in_delay", None):
            if cron or run_at:
                print("error: --in cannot be combined with --cron/--every/--at")
                return 2
            try:
                delta_seconds = _parse_relative_delay(args.in_delay)
            except ValueError as exc:
                print(f"error: {exc}")
                return 2
            target = datetime.now() + timedelta(seconds=delta_seconds)
            run_at = target.isoformat(timespec="minutes")

        if not cron and not run_at:
            print("error: schedule needs --cron, --every, --at, or --in")
            return 2

        variables, err = _parse_vars(args.var)
        if err:
            print(f"error: {err}")
            return 2

        task = ScheduledTask(
            slug=slug,
            prompt=args.prompt or "",
            cron=cron,
            run_at=run_at,
            template=args.template,
            variables=variables,
            attachments=list(args.image or []),
            enabled=not args.disabled,
            timeout_seconds=int(args.timeout),
            max_steps=args.max_steps,
            resilient=bool(args.resilient),
            description=args.description or "",
        )
        task.next_run_at = compute_next_run(task)
        store.upsert(task)
        when = (
            datetime.fromtimestamp(task.next_run_at).strftime("%Y-%m-%d %H:%M")
            if task.next_run_at
            else "never (check expression)"
        )
        print(f"scheduled: {task.slug}")
        print(f"  schedule: {task.cron or task.run_at}")
        print(f"  next run: {when}")
        return 0

    if action == "remove":
        if store.remove(args.slug):
            print(f"removed: {args.slug}")
            return 0
        print(f"no scheduled task matching {args.slug!r}")
        return 2

    if action in ("enable", "disable"):
        wanted = action == "enable"
        if store.set_enabled(args.slug, wanted):
            state = "enabled" if wanted else "disabled"
            print(f"{state}: {args.slug}")
            if wanted:
                store.refresh_next_run(args.slug)
            return 0
        print(f"no scheduled task matching {args.slug!r}")
        return 2

    if action == "run":
        task = store.get(args.slug)
        if task is None:
            print(f"no scheduled task matching {args.slug!r}")
            return 2
        log_dir = settings.data_dir / "schedule_logs"
        print(f"firing now: {task.slug}")
        code = run_once_now(task, log_dir=log_dir if args.log else None)
        store.mark_fired(task.slug, exit_code=code)
        print(f"  exit: {code}")
        return code

    return 2


def _cmd_templates(args: argparse.Namespace) -> int:
    from lucid.templates import list_templates

    specs = list_templates()
    if not specs:
        print("No templates installed.")
        return 0
    for spec in specs:
        print(f"{spec.name}")
        if spec.description:
            print(f"  {spec.description}")
        if spec.required_vars:
            print(f"  required: {', '.join(spec.required_vars)}")
        if spec.defaults:
            defaults = ", ".join(f"{k}={v!r}" for k, v in spec.defaults.items())
            print(f"  defaults: {defaults}")
    return 0


def _cmd_profile(args: argparse.Namespace) -> int:
    from lucid.config.profile import ensure_profile_file
    from lucid.config.settings import get_settings

    settings = get_settings()
    if args.profile_cmd == "path":
        print(settings.profile_path)
        return 0
    if args.profile_cmd == "init":
        path = ensure_profile_file(settings)
        print(f"profile.yaml ready at {path}")
        return 0
    if args.profile_cmd == "show":
        from lucid.config.profile import get_profile

        profile = get_profile(settings)
        print(profile.to_prompt_block() or "(empty profile)")
        return 0
    return 2


def main() -> int:
    """Entry point. Delegates to the Typer CLI when typer is installed."""
    try:
        from lucid.cli import main as typer_main
    except ImportError:
        typer_main = None
    if typer_main is not None:
        return typer_main()
    return _legacy_main()


def _legacy_main() -> int:
    """Argparse fallback used only when typer cannot be imported."""
    _force_utf8_stdio()
    _enable_dpi_awareness()
    parser = argparse.ArgumentParser(prog="lucid", description="Desktop AI assistant")
    parser.add_argument("--version", action="version", version=f"lucid {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Configure API keys and preferences")

    exec_p = sub.add_parser("exec", help="Run an Execute-mode task headless and print progress")
    exec_p.add_argument(
        "prompt", nargs="?", default="", help="Natural-language task description (quoted)"
    )
    exec_p.add_argument("--template", help="Name of a shipped template (see `lucid templates`)")
    exec_p.add_argument("--var", action="append", help="Template variable KEY=VALUE (repeatable)")
    exec_p.add_argument(
        "--image",
        "-i",
        action="append",
        help="Path to a reference image to attach as visual context (repeatable).",
    )
    exec_p.add_argument(
        "--timeout", type=int, default=180, help="Wall-clock timeout in seconds (default 180)"
    )
    exec_p.add_argument("--max-steps", type=int, default=None, help="Override executor.max_steps")
    exec_p.add_argument(
        "--backend", choices=["api", "cli"], default=None, help="Override backend.mode"
    )
    exec_p.add_argument(
        "--json", action="store_true", help="Emit JSON-lines to stdout instead of plain text"
    )
    exec_p.add_argument(
        "--no-memory", action="store_true", help="Disable memory read/write for this run"
    )
    exec_p.add_argument(
        "--profile-ignore", action="store_true", help="Ignore user profile context for this run"
    )
    exec_p.add_argument(
        "--resilient",
        action="store_true",
        help="Long-task mode: pushes max-steps to 200 and timeout to 600 unless overridden, and tells Claude to persist until every sub-goal is finished.",
    )
    exec_p.set_defaults(func=_cmd_exec)

    tpl_p = sub.add_parser("templates", help="List ship-in Execute templates")
    tpl_p.set_defaults(func=_cmd_templates)

    replay_p = sub.add_parser("replay", help="Replay a Teach-mode workflow JSON by path")
    replay_p.add_argument("workflow", help="Path to the workflow .json file")
    replay_p.add_argument("--timeout", type=int, default=180)
    replay_p.add_argument("--json", action="store_true")
    replay_p.add_argument("--var", action="append", help="Variable KEY=VALUE (repeatable)")
    replay_p.set_defaults(func=_cmd_replay)

    run_p = sub.add_parser(
        "run",
        help="Run a saved workflow by slug/alias (or, with no args, launch the tray GUI)",
    )
    run_p.add_argument(
        "target",
        nargs="?",
        default="",
        help="Workflow slug, alias, natural-language phrase, or path. Empty = launch tray app.",
    )
    run_p.add_argument("--var", action="append", help="Variable KEY=VALUE (repeatable)")
    run_p.add_argument("--timeout", type=int, default=180)
    run_p.add_argument("--json", action="store_true")
    run_p.set_defaults(func=_cmd_run)

    wf_p = sub.add_parser("workflows", help="List recorded named workflows in this install")
    wf_p.set_defaults(func=_cmd_workflows)

    forget_p = sub.add_parser("forget", help="Remove a workflow from the registry (keeps the JSON)")
    forget_p.add_argument("slug", help="Slug, alias, or natural-language phrase")
    forget_p.add_argument(
        "--delete-file", action="store_true", help="Also delete the JSON file on disk"
    )
    forget_p.set_defaults(func=_cmd_forget)

    # lucid schedule ... — cron / one-shot / every timer catalogue
    sched_p = sub.add_parser(
        "schedule", help="Schedule Execute prompts on cron / one-shot / every-N timers"
    )
    sched_sub = sched_p.add_subparsers(dest="schedule_cmd", required=True)

    sched_list = sched_sub.add_parser("list", help="List scheduled tasks")
    sched_list.add_argument("--json", action="store_true")
    sched_list.set_defaults(func=_cmd_schedule)

    sched_add = sched_sub.add_parser("add", help="Add or overwrite a scheduled task")
    sched_add.add_argument("--slug", help="Human identifier (defaults to a slug of the prompt)")
    sched_add.add_argument("--prompt", help="Task description to hand to `lucid exec`")
    sched_add.add_argument(
        "--template", help="Use a ship-in template instead of / alongside the prompt"
    )
    sched_add.add_argument(
        "--var", action="append", help="Template variable KEY=VALUE (repeatable)"
    )
    sched_add.add_argument(
        "--image", action="append", help="Attach reference image(s) (repeatable)"
    )
    sched_add.add_argument("--cron", help='Standard 5-field cron (e.g. "0 9 * * 1-5")')
    sched_add.add_argument("--every", help="Interval shorthand: 30m, 1h, 2d")
    sched_add.add_argument("--at", help="One-shot ISO datetime (e.g. 2026-04-20T09:00)")
    sched_add.add_argument(
        "--in",
        dest="in_delay",
        help="One-shot relative delay: 5m, 30m, 2h, 1d (fires once then disables)",
    )
    sched_add.add_argument(
        "--timeout", type=int, default=300, help="Per-run timeout seconds (default 300)"
    )
    sched_add.add_argument(
        "--max-steps", type=int, default=None, help="Override executor.max_steps for this task"
    )
    sched_add.add_argument(
        "--resilient",
        action="store_true",
        help="Give the task long-task budgets (max-steps 200, timeout 600)",
    )
    sched_add.add_argument(
        "--disabled", action="store_true", help="Create the task but don't fire it yet"
    )
    sched_add.add_argument(
        "--description", default="", help="Free-text note shown by `schedule list`"
    )
    sched_add.set_defaults(func=_cmd_schedule)

    for cmd, help_text in (
        ("remove", "Delete a scheduled task"),
        ("enable", "Re-enable a disabled scheduled task"),
        ("disable", "Pause a scheduled task without deleting it"),
    ):
        sp = sched_sub.add_parser(cmd, help=help_text)
        sp.add_argument("slug", help="Scheduled task slug")
        sp.set_defaults(func=_cmd_schedule)

    sched_run = sched_sub.add_parser(
        "run", help="Fire a scheduled task right now (useful for testing)"
    )
    sched_run.add_argument("slug")
    sched_run.add_argument(
        "--log",
        action="store_true",
        help="Write stdout to data/schedule_logs/<stamp>.log instead of the terminal",
    )
    sched_run.set_defaults(func=_cmd_schedule)

    status_p = sub.add_parser("status", help="Print current Lucid state, memory stats, and paths")
    status_p.add_argument("--json", action="store_true")
    status_p.set_defaults(func=_cmd_status)

    profile_p = sub.add_parser("profile", help="Inspect or scaffold the user profile")
    profile_p.add_argument(
        "profile_cmd",
        choices=["init", "path", "show"],
        default="show",
        nargs="?",
        help="init: create data/profile.yaml from example; path: print it; show: print loaded profile",
    )
    profile_p.set_defaults(func=_cmd_profile)

    args = parser.parse_args()

    # ``run`` is overloaded: with no argument it launches the tray GUI
    # (back-compat with ``lucid run``), with an argument it replays a
    # saved workflow. argparse validates below.
    if args.command == "run" and not getattr(args, "target", None):
        from lucid.app import run_app

        return run_app()

    if args.command == "setup":
        from lucid.config.secrets import run_setup_wizard

        return run_setup_wizard()

    func = getattr(args, "func", None)
    if func is not None:
        return func(args)

    from lucid.app import run_app

    return run_app()


if __name__ == "__main__":
    sys.exit(main())
