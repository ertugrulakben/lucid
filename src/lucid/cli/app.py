"""Top-level Typer application.

Bootstrap order is intentional: UTF-8 stdout, then DPI awareness, then
i18n, THEN we let Typer build the parser. Reordering any of these has
historically caused live bugs (mojibake on Windows terminals, off-by-DPI
clicks, English-only help on TR systems).
"""

from __future__ import annotations

import sys

import typer

from lucid import __version__, i18n


def _force_utf8_stdio() -> None:
    """Windows terminals default to cp1254 and crash on arrow characters."""
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

    Without this, scaled displays virtualize coordinates and screenshots
    end up on a different pixel grid than where pyautogui clicks. Must
    run before any GUI toolkit or capture library touches the display.
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def build_app() -> typer.Typer:
    app = typer.Typer(
        name="lucid",
        no_args_is_help=False,
        add_completion=False,
        rich_markup_mode="rich",
        context_settings={"help_option_names": ["-h", "--help"]},
        help=i18n._("cli-app-help"),
    )

    from . import commands  # -- registered for side effects

    commands.register(app)

    @app.callback(invoke_without_command=True)
    def _root(
        ctx: typer.Context,
        version: bool = typer.Option(
            False,
            "--version",
            "-V",
            help="Show version and exit.",
            is_eager=True,
        ),
    ) -> None:
        if version:
            typer.echo(i18n._("cli-version", version=__version__))
            raise typer.Exit(0)
        if ctx.invoked_subcommand is None:
            from lucid.app import run_app

            raise typer.Exit(run_app())

    return app


def main(argv: list[str] | None = None) -> int:
    """Entry point for both ``python -m lucid`` and the ``lucid`` console script."""
    _force_utf8_stdio()
    _enable_dpi_awareness()
    i18n.init()

    app = build_app()
    # Click's standalone_mode=True ensures every typer.Exit / UsageError
    # converts into a SystemExit with the right code; we just translate
    # SystemExit -> int return for legacy tests that expect a returncode.
    try:
        app(args=argv, standalone_mode=True)
        return 0
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 2
    except KeyboardInterrupt:
        return 130


__all__ = ["build_app", "main"]
