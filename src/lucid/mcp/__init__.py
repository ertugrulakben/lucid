"""Model Context Protocol bridge.

Lucid talks to MCP servers over stdio and re-publishes every advertised tool
as a regular Lucid action with the prefix ``mcp_<server>_<tool>``. ExecuteMode
treats them like built-in or browser actions; the model can call them via the
same ``computer`` tool channel through the dispatch indirection in
:mod:`lucid.executor.actions`.

Public entry points:
    MCPBridge      -- lifecycle holder, started from AppController
    load_servers   -- parse data/mcp_servers.yaml
"""

from __future__ import annotations

import logging

log = logging.getLogger("lucid.mcp")

try:  # pragma: no cover -- guarded so vanilla installs keep working
    from .bridge import MCPBridge
    from .config import MCPServerConfig, load_servers

    AVAILABLE = True
except Exception as exc:  # noqa: BLE001 -- missing extra means MCP off
    log.debug("MCP bridge unavailable: %s", exc)
    MCPBridge = None  # type: ignore[assignment]
    MCPServerConfig = None  # type: ignore[assignment]
    load_servers = None  # type: ignore[assignment]
    AVAILABLE = False


__all__ = ["AVAILABLE", "MCPBridge", "MCPServerConfig", "load_servers"]
