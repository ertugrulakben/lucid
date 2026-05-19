# Contributing to Lucid

Thanks for your interest. This document covers the dev setup, code style, and pull request workflow.

## Dev Setup

```powershell
git clone https://github.com/lucid-app/lucid
cd lucid
uv sync --all-extras
uv run lucid
```

Lucid targets Python 3.10+. All development happens against Windows 10/11. Linux and macOS support is tracked in the backlog.

## Code Style

- `ruff check .` — lint
- `ruff format .` — format
- `black src tests` — additional formatting parity
- `mypy src` — type check (non-strict for now)

CI runs all four on every pull request. Please run them locally before pushing.

## Commits

Use Conventional Commits prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`. Keep commits small and focused. Refactors do not belong in the same commit as features.

## Pull Requests

1. Fork the repo, create a branch `feat/short-name` off `main`.
2. Write tests for new behavior. Unit tests live in `tests/unit/`, integration in `tests/integration/`.
3. Update `CHANGELOG.md` under `[Unreleased]`.
4. Run the full test suite and linters.
5. Open a PR with a clear description, linked issue, and screenshots for UI changes.

## Design Principles

- **Privacy first.** Screenshots never leave the user's machine unless they explicitly send a prompt. Telemetry is opt-in and strictly anonymous.
- **Safety first.** Any destructive action must be confirmable. A kill switch must always work.
- **Thin abstractions.** Prefer small, readable modules over clever frameworks.
- **No vendor lock-in.** The LLM layer is pluggable. Anthropic is the default, not a dependency of the core loop.

## Reporting Bugs

Open an issue on GitHub with:
- Lucid version (`lucid --version`)
- Windows version
- Python version
- Steps to reproduce
- Expected vs actual behavior
- Log file from `%APPDATA%\Lucid\logs\lucid.log`

## Security

Do not open public issues for security problems. Email `security@lucid.app` (placeholder — set real address before launch).
