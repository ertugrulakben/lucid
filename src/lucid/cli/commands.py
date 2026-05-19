"""Subcommand registrations for the Lucid CLI.

Most subcommands delegate to small handlers that already exist in
``lucid.__main__`` (kept for backward compatibility) or in dedicated
modules under ``lucid.cli.cmd_*``. Keeping the Typer wiring in one
file makes the CLI shape easy to read in a single screen.
"""

from __future__ import annotations

from pathlib import Path

import typer

from lucid import i18n


def register(app: typer.Typer) -> None:
    _register_setup(app)
    _register_exec(app)
    _register_run(app)
    _register_replay(app)
    _register_workflows(app)
    _register_forget(app)
    _register_templates(app)
    _register_status(app)
    _register_profile(app)
    _register_schedule(app)
    _register_doctor(app)
    _register_actions(app)
    _register_update(app)


# --------------------------------------------------------------------------- #
# setup
# --------------------------------------------------------------------------- #


def _register_setup(app: typer.Typer) -> None:
    @app.command("setup", help="Configure API keys and preferences.")
    def setup() -> None:
        from lucid.config.secrets import run_setup_wizard

        raise typer.Exit(run_setup_wizard())


# --------------------------------------------------------------------------- #
# exec
# --------------------------------------------------------------------------- #


def _register_exec(app: typer.Typer) -> None:
    @app.command("exec", help=i18n._("cli-cmd-exec"))
    def exec_cmd(
        prompt: str = typer.Argument("", help="Natural-language task description (quoted)."),
        template: str | None = typer.Option(None, "--template", help="Name of a shipped template."),
        var: list[str] | None = typer.Option(
            None, "--var", help="Template variable KEY=VALUE (repeatable)."
        ),
        image: list[str] | None = typer.Option(
            None, "--image", "-i", help="Reference image path (repeatable)."
        ),
        timeout: int = typer.Option(180, "--timeout", help="Wall-clock timeout in seconds."),
        max_steps: int | None = typer.Option(
            None, "--max-steps", help="Override executor.max_steps."
        ),
        backend: str | None = typer.Option(
            None, "--backend", help="Override backend.mode (api or cli)."
        ),
        json_output: bool = typer.Option(False, "--json", help="Emit JSON-lines to stdout."),
        no_memory: bool = typer.Option(
            False, "--no-memory", help="Disable memory read/write for this run."
        ),
        profile_ignore: bool = typer.Option(
            False, "--profile-ignore", help="Ignore the user profile for this run."
        ),
        resilient: bool = typer.Option(
            False, "--resilient", help="Long-task mode: raise budgets and persist."
        ),
    ) -> None:
        from lucid.headless import HeadlessOptions, run_headless
        from lucid.templates import TemplateError, expand_template

        full_prompt = prompt
        if template:
            variables: dict[str, str] = {}
            for raw in var or []:
                if "=" not in raw:
                    typer.echo(
                        f"{i18n._('cli-error-prefix')} --var must be KEY=VALUE, got: {raw!r}"
                    )
                    raise typer.Exit(2)
                key, _, value = raw.partition("=")
                variables[key.strip()] = value
            try:
                template_prompt = expand_template(template, variables)
            except TemplateError as exc:
                typer.echo(f"{i18n._('cli-error-prefix')} {exc}")
                raise typer.Exit(2)
            full_prompt = (
                f"{full_prompt}\n\n{template_prompt}".strip() if full_prompt else template_prompt
            )

        if not full_prompt:
            typer.echo(f"{i18n._('cli-error-prefix')} provide a prompt or --template")
            raise typer.Exit(2)

        attachments: list[Path] = [Path(p).expanduser() for p in image or []]

        effective_timeout = timeout
        effective_max_steps = max_steps
        if resilient:
            from lucid.config.settings import get_settings

            try:
                cfg = get_settings().executor
                floor_t = int(cfg.resilient_min_timeout)
                floor_s = int(cfg.resilient_min_max_steps)
            except Exception:
                floor_t, floor_s = 600, 200
            if effective_timeout == 180:
                effective_timeout = floor_t
            if effective_max_steps is None:
                effective_max_steps = floor_s
            from lucid.i18n import _ as t

            full_prompt = t("prompt-execute-resilient-suffix") + "\n\n" + full_prompt

        options = HeadlessOptions(
            prompt=full_prompt,
            timeout=effective_timeout,
            max_steps=effective_max_steps,
            backend=backend,
            json_output=json_output,
            disable_memory=no_memory,
            disable_profile=profile_ignore,
            attachments=attachments,
        )
        raise typer.Exit(run_headless(options))


# --------------------------------------------------------------------------- #
# run / replay / workflows / forget
# --------------------------------------------------------------------------- #


def _register_run(app: typer.Typer) -> None:
    @app.command("run", help=i18n._("cli-cmd-run"))
    def run_cmd(
        target: str = typer.Argument(
            "", help="Workflow slug, alias, phrase, or path. Empty = launch overlay."
        ),
        var: list[str] | None = typer.Option(
            None, "--var", help="Variable KEY=VALUE (repeatable)."
        ),
        timeout: int = typer.Option(180, "--timeout"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        if not target:
            from lucid.app import run_app

            raise typer.Exit(run_app())

        from lucid.replayer.cli import run_replay

        variables, err = _parse_vars(var)
        if err:
            typer.echo(f"{i18n._('cli-error-prefix')} {err}")
            raise typer.Exit(2)
        raise typer.Exit(
            run_replay(
                workflow_path=target,
                timeout=timeout,
                json_output=json_output,
                variables=variables,
            )
        )


def _register_replay(app: typer.Typer) -> None:
    @app.command("replay", help="Replay a Teach-mode workflow JSON by path.")
    def replay_cmd(
        workflow: str = typer.Argument(..., help="Path to the workflow .json file."),
        timeout: int = typer.Option(180, "--timeout"),
        json_output: bool = typer.Option(False, "--json"),
        var: list[str] | None = typer.Option(None, "--var"),
    ) -> None:
        from lucid.replayer.cli import run_replay

        variables, err = _parse_vars(var)
        if err:
            typer.echo(f"{i18n._('cli-error-prefix')} {err}")
            raise typer.Exit(2)
        raise typer.Exit(
            run_replay(
                workflow_path=Path(workflow),
                timeout=timeout,
                json_output=json_output,
                variables=variables,
            )
        )


def _register_workflows(app: typer.Typer) -> None:
    @app.command("workflows", help="List recorded named workflows in this install.")
    def workflows_cmd() -> None:
        from lucid.config.settings import get_settings
        from lucid.recorder.registry import WorkflowRegistry

        settings = get_settings()
        registry = WorkflowRegistry(settings.workflows_dir)
        entries = registry.list_all()
        if not entries:
            typer.echo("No recorded workflows yet.")
            raise typer.Exit(0)
        for entry in entries:
            typer.echo(f"{entry.slug}  -  {entry.name}")
            if entry.aliases:
                typer.echo(f"  aliases: {', '.join(entry.aliases)}")
            if entry.target_app:
                typer.echo(f"  target:  {entry.target_app}")
            if entry.variables:
                bits = []
                for v in entry.variables:
                    bit = v.name
                    if v.example:
                        bit += f" (example: {v.example})"
                    bits.append(bit)
                typer.echo(f"  vars:    {', '.join(bits)}")
            typer.echo(f"  file:    {entry.path}")


def _register_forget(app: typer.Typer) -> None:
    @app.command("forget", help="Remove a workflow from the registry (keeps the JSON).")
    def forget_cmd(
        slug: str = typer.Argument(..., help="Slug, alias, or natural-language phrase."),
        delete_file: bool = typer.Option(
            False, "--delete-file", help="Also delete the JSON file on disk."
        ),
    ) -> None:
        from lucid.config.settings import get_settings
        from lucid.recorder.registry import WorkflowRegistry

        settings = get_settings()
        registry = WorkflowRegistry(settings.workflows_dir)
        entry = registry.get(slug) or registry.find(slug)
        if entry is None:
            typer.echo(f"no workflow matching {slug!r}")
            raise typer.Exit(2)
        removed = registry.remove(entry.slug)
        if delete_file:
            path = settings.workflows_dir / entry.path
            try:
                path.unlink()
            except OSError:
                pass
        typer.echo(f"forgotten: {entry.slug} ({'removed' if removed else 'not in registry'})")


def _register_templates(app: typer.Typer) -> None:
    @app.command("templates", help="List ship-in Execute templates.")
    def templates_cmd() -> None:
        from lucid.templates import list_templates

        specs = list_templates()
        if not specs:
            typer.echo("No templates installed.")
            raise typer.Exit(0)
        for spec in specs:
            typer.echo(spec.name)
            if spec.description:
                typer.echo(f"  {spec.description}")
            if spec.required_vars:
                typer.echo(f"  required: {', '.join(spec.required_vars)}")
            if spec.defaults:
                defaults = ", ".join(f"{k}={v!r}" for k, v in spec.defaults.items())
                typer.echo(f"  defaults: {defaults}")


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #


def _register_status(app: typer.Typer) -> None:
    @app.command("status", help="Print current Lucid state, memory stats, and paths.")
    def status_cmd(
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        from lucid.status import print_status

        raise typer.Exit(print_status(json_output=json_output))


# --------------------------------------------------------------------------- #
# profile
# --------------------------------------------------------------------------- #


def _register_profile(app: typer.Typer) -> None:
    profile_app = typer.Typer(help="Inspect or scaffold the user profile.")
    app.add_typer(profile_app, name="profile")

    @profile_app.command("path")
    def profile_path() -> None:
        from lucid.config.settings import get_settings

        typer.echo(str(get_settings().profile_path))

    @profile_app.command("init")
    def profile_init() -> None:
        from lucid.config.profile import ensure_profile_file
        from lucid.config.settings import get_settings

        path = ensure_profile_file(get_settings())
        typer.echo(f"profile.yaml ready at {path}")

    @profile_app.command("show")
    def profile_show() -> None:
        from lucid.config.profile import get_profile
        from lucid.config.settings import get_settings

        prof = get_profile(get_settings())
        typer.echo(prof.to_prompt_block() or "(empty profile)")


# --------------------------------------------------------------------------- #
# schedule (delegates to legacy handler -- it's already self-contained)
# --------------------------------------------------------------------------- #


def _register_schedule(app: typer.Typer) -> None:
    sched_app = typer.Typer(help=i18n._("cli-cmd-schedule"))
    app.add_typer(sched_app, name="schedule")

    @sched_app.command("list")
    def sched_list(json_output: bool = typer.Option(False, "--json")) -> None:
        from argparse import Namespace

        from lucid.__main__ import _cmd_schedule

        ns = Namespace(schedule_cmd="list", json=json_output)
        raise typer.Exit(_cmd_schedule(ns))

    @sched_app.command("add")
    def sched_add(
        slug: str | None = typer.Option(None, "--slug"),
        prompt: str | None = typer.Option(None, "--prompt"),
        template: str | None = typer.Option(None, "--template"),
        var: list[str] | None = typer.Option(None, "--var"),
        image: list[str] | None = typer.Option(None, "--image"),
        cron: str | None = typer.Option(None, "--cron"),
        every: str | None = typer.Option(None, "--every"),
        at: str | None = typer.Option(None, "--at"),
        in_delay: str | None = typer.Option(None, "--in"),
        timeout: int = typer.Option(300, "--timeout"),
        max_steps: int | None = typer.Option(None, "--max-steps"),
        resilient: bool = typer.Option(False, "--resilient"),
        disabled: bool = typer.Option(False, "--disabled"),
        description: str = typer.Option("", "--description"),
    ) -> None:
        from argparse import Namespace

        from lucid.__main__ import _cmd_schedule

        ns = Namespace(
            schedule_cmd="add",
            slug=slug,
            prompt=prompt,
            template=template,
            var=var,
            image=image,
            cron=cron,
            every=every,
            at=at,
            in_delay=in_delay,
            timeout=timeout,
            max_steps=max_steps,
            resilient=resilient,
            disabled=disabled,
            description=description,
        )
        raise typer.Exit(_cmd_schedule(ns))

    for name in ("remove", "enable", "disable"):
        _bind_simple_schedule(sched_app, name)

    @sched_app.command("run")
    def sched_run(
        slug: str = typer.Argument(...),
        log: bool = typer.Option(False, "--log"),
    ) -> None:
        from argparse import Namespace

        from lucid.__main__ import _cmd_schedule

        ns = Namespace(schedule_cmd="run", slug=slug, log=log)
        raise typer.Exit(_cmd_schedule(ns))


def _bind_simple_schedule(sched_app: typer.Typer, name: str) -> None:
    @sched_app.command(name)
    def _handler(slug: str = typer.Argument(...)) -> None:
        from argparse import Namespace

        from lucid.__main__ import _cmd_schedule

        ns = Namespace(schedule_cmd=name, slug=slug)
        raise typer.Exit(_cmd_schedule(ns))


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #


def _register_doctor(app: typer.Typer) -> None:
    @app.command("doctor", help=i18n._("cli-cmd-doctor"))
    def doctor_cmd(
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable output."),
    ) -> None:
        from lucid.cli.doctor import run_doctor

        raise typer.Exit(run_doctor(json_output=json_output))


# --------------------------------------------------------------------------- #
# actions
# --------------------------------------------------------------------------- #


def _register_actions(app: typer.Typer) -> None:
    actions_app = typer.Typer(help="List or inspect registered actions and plugins.")
    app.add_typer(actions_app, name="actions")

    @actions_app.command("list")
    def actions_list(
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        import json as json_mod

        from lucid.actions import available, get

        names = available()
        rows = [
            {
                "name": n,
                "summary": get(n).summary,
                "source": get(n).source,
                "schema": get(n).schema.__name__ if get(n).schema else None,
            }
            for n in names
        ]
        if json_output:
            typer.echo(json_mod.dumps({"actions": rows}, indent=2))
            return
        for row in rows:
            line = f"{row['name']:24}  [{row['source']}]"
            if row["schema"]:
                line += f"  schema={row['schema']}"
            if row["summary"]:
                line += f"\n    {row['summary']}"
            typer.echo(line)


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #


def _register_update(app: typer.Typer) -> None:
    update_app = typer.Typer(help="Check for new Lucid releases on GitHub.")
    app.add_typer(update_app, name="update")

    @update_app.command("check")
    def update_check(
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        import json as json_mod

        from lucid import __version__
        from lucid.updater import check_for_update

        info = check_for_update(__version__)
        if info is None:
            payload = {"current": __version__, "newer_available": False}
            if json_output:
                typer.echo(json_mod.dumps(payload))
            else:
                typer.echo(f"You are on the latest version: {__version__}")
            return

        payload = {
            "current": __version__,
            "newer_available": True,
            "version": info.version,
            "channel": info.channel,
            "download_url": info.download_url,
            "asset_size": info.asset_size,
        }
        if json_output:
            typer.echo(json_mod.dumps(payload))
            return
        typer.echo(f"Update available: {info.version} (current: {__version__})")
        if info.download_url:
            typer.echo(f"  Download: {info.download_url}")
        if info.notes:
            typer.echo("  Release notes:")
            for line in info.notes.splitlines()[:6]:
                typer.echo(f"    {line}")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _parse_vars(raw_vars: list[str] | None) -> tuple[dict[str, str], str | None]:
    variables: dict[str, str] = {}
    for raw in raw_vars or []:
        if "=" not in raw:
            return {}, f"--var must be KEY=VALUE, got: {raw!r}"
        key, _, value = raw.partition("=")
        variables[key.strip()] = value
    return variables, None
