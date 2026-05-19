"""Fail when source code contains user-facing strings that bypass i18n.

Run as a pre-commit hook and in CI. The check is deliberately narrow:
it only looks at modules that produce text for the user (UI, agent
prose, CLI). Library modules (capture, executor internals, networking)
are exempt because their strings are either log lines or developer-
facing identifiers.

A line fails when:
    - it lives in a watched module,
    - it contains non-ASCII characters or a multi-word run of letters
      that looks like a sentence,
    - the substring is not inside a comment, docstring, ``_("...")``
      call, log call, or one of the explicit allow-list patterns below.

Exit code:
    0  no offenders
    1  offenders found (printed with ``path:line:column message``)
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "lucid"

WATCHED_DIRS = (
    SRC_ROOT / "ui",
    SRC_ROOT / "agent",
)
WATCHED_FILES = (
    SRC_ROOT / "__main__.py",
)

I18N_CALL_PATTERN = re.compile(r"\b_\s*\(")
LOG_CALL_PATTERN = re.compile(r"\b(logger|log|logging)\.[a-z_]+\s*\(")
PRINT_PATTERN = re.compile(r"\bprint\s*\(")

NON_ASCII_PATTERN = re.compile(r"[^\x00-\x7f]")
SENTENCE_PATTERN = re.compile(
    r"['\"]("
    r"[A-Z][A-Za-z]+(?:\s+[A-Za-z][A-Za-z']*){2,}"
    r")['\"]"
)

ALLOW_SUBSTRINGS = (
    "TODO",
    "FIXME",
    "noqa",
    "type: ignore",
    "PYTHONPATH",
    "ANTHROPIC_API_KEY",
)


def iter_target_files() -> Iterable[Path]:
    seen: set[Path] = set()
    for d in WATCHED_DIRS:
        if not d.exists():
            continue
        for path in d.rglob("*.py"):
            if path not in seen:
                seen.add(path)
                yield path
    for path in WATCHED_FILES:
        if path.exists() and path not in seen:
            seen.add(path)
            yield path


def line_is_string_literal_assignment_to_protected(_line: str) -> bool:
    return False


def line_is_exempt(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if stripped.startswith(('"""', "'''")):
        return True
    if I18N_CALL_PATTERN.search(line):
        return True
    if LOG_CALL_PATTERN.search(line):
        return True
    if any(token in line for token in ALLOW_SUBSTRINGS):
        return True
    return False


def docstring_line_ranges(source: str) -> set[int]:
    """1-indexed line numbers occupied by module/class/function docstrings."""
    occupied: set[int] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return occupied
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            start = first.lineno
            end = getattr(first, "end_lineno", start) or start
            for ln in range(start, end + 1):
                occupied.add(ln)
    return occupied


def offenders_in_file(path: Path) -> list[tuple[int, int, str]]:
    text = path.read_text(encoding="utf-8")
    docstring_lines = docstring_line_ranges(text)
    out: list[tuple[int, int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if lineno in docstring_lines:
            continue
        if line_is_exempt(line):
            continue
        match = NON_ASCII_PATTERN.search(line)
        if match:
            out.append((lineno, match.start() + 1, "non-ASCII text outside i18n / comment"))
            continue
        sentence_match = SENTENCE_PATTERN.search(line)
        if sentence_match:
            out.append(
                (
                    lineno,
                    sentence_match.start() + 1,
                    "multi-word sentence-cased literal outside i18n",
                )
            )
    return out


def main(argv: list[str]) -> int:
    targets = list(iter_target_files())
    failures = 0
    for path in targets:
        for lineno, col, message in offenders_in_file(path):
            rel = path.relative_to(REPO_ROOT)
            print(f"{rel}:{lineno}:{col}  {message}")
            failures += 1
    if failures:
        print(f"\n{failures} hardcoded-text offender(s). Wrap them in _(\"...\") or move to .ftl.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
