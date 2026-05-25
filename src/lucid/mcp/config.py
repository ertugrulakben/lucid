"""YAML loader for ``data/mcp_servers.yaml``.

The file shape is intentionally tiny so a non-developer can hand-edit it:

    servers:
      - name: filesystem
        command: npx
        args: ["-y", "@modelcontextprotocol/server-filesystem", "C:/data"]
        env: { OPTIONAL_KEY: "${OPTIONAL_KEY}" }
        enabled: true

``${ENV_VAR}`` patterns in the ``env`` map are expanded at load time from the
process environment. Missing variables expand to an empty string so a server
config never silently leaks the literal placeholder back to the subprocess.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

log = logging.getLogger("lucid.mcp.config")

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class MCPServerConfig(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    command: str = Field(..., min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    cwd: str | None = None


def load_servers(path: Path) -> list[MCPServerConfig]:
    """Read the YAML file and return validated, env-expanded server configs."""
    path = Path(path)
    if not path.exists():
        log.info("MCP servers file not found (%s); nothing to wire", path)
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        log.warning("MCP servers file %s is malformed: %s", path, exc)
        return []
    entries = raw.get("servers") or []
    out: list[MCPServerConfig] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            cfg = MCPServerConfig.model_validate(entry)
        except Exception as exc:  # noqa: BLE001 -- bad row should not kill the rest
            log.warning("MCP server config skipped: %s", exc)
            continue
        if cfg.name in seen:
            log.warning("duplicate MCP server name %r ignored", cfg.name)
            continue
        seen.add(cfg.name)
        cfg.env = {key: _expand_env(value) for key, value in cfg.env.items()}
        out.append(cfg)
    return out


def _expand_env(value: Any) -> str:
    """Substitute ``${VAR}`` references in a string against the live environment."""
    if not isinstance(value, str):
        return str(value)

    def _sub(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), "")

    return _ENV_PATTERN.sub(_sub, value)
