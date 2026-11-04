"""Tests for the pre-commit hook that keeps local data and secrets out of git."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _blocked(path: str) -> bool:
    """Match the way pre-commit does: search `files`, then drop `exclude` hits."""
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hook = next(
        h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "forbidden-paths"
    )
    return bool(re.search(hook["files"], path)) and not re.search(hook["exclude"], path)


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".ENV",
        ".env.local",
        "config/.env",
        "data/settings.yaml",
        "Data/memory.json",
        "private/notes.md",
        "PRIVATE/notes.md",
        "profile.yaml",
        "Profile.YML",
        "mcp_servers.yaml",
        "MCP_SERVERS.yaml",
        "server.key",
        "cert.PEM",
        "id.p12",
        "id.PFX",
        "memory.db",
        "MEMORY.DB",
        "memory.db-wal",
        "memory.DB-SHM",
        "cache.sqlite3",
        "data/profile.example.yaml",
        "private/.env.example",
    ],
)
def test_guard_blocks_local_data_and_secret_files(path: str) -> None:
    assert _blocked(path)


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        "docs/.env.example",
        "profile.example.yaml",
        "mcp_servers.example.yaml",
        "metadata/notes.md",
        "docs/database.md",
        "src/lucid/config/secrets.py",
        "src/lucid/memory/store.py",
    ],
)
def test_guard_lets_templates_and_source_through(path: str) -> None:
    assert not _blocked(path)
