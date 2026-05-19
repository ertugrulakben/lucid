"""Typer-based CLI for Lucid.

Split out of ``lucid.__main__`` so the entry point itself stays tiny and
each subcommand can live in its own module without ballooning into one
570-line file.
"""

from __future__ import annotations

from .app import build_app, main

__all__ = ["build_app", "main"]
