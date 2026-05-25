"""High-level bridge: spawn configured servers and publish each tool as a Lucid action.

Lifecycle:
    bridge = MCPBridge(settings)
    bridge.start()        # AppController.__init__
    ...
    bridge.stop()         # AppController.shutdown

Once started, the registry exposes every advertised tool as
``mcp_<server>_<tool>``. The action handler serialises the MCP response into
a short string for ExecuteMode's tool_result channel; structured content
items (text, json, image) are flattened into a single readable block.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from lucid.actions.registry import ActionContext, ActionError, register_action

from .client import MCPSupervisor
from .config import load_servers

log = logging.getLogger("lucid.mcp.bridge")

_NAME_SAFE = re.compile(r"[^A-Za-z0-9_]+")


class MCPActionParams(BaseModel):
    """Catch-all params model for dynamic MCP actions.

    The MCP tool can advertise any input schema; rather than building a
    Pydantic model per tool at runtime we accept an opaque dict and forward
    it to the server. The action handler validates required keys against the
    MCP-published schema if one is available.
    """

    model_config = ConfigDict(extra="allow")

    arguments: dict[str, Any] = {}


class MCPBridge:
    """Reads ``mcp_servers.yaml``, runs each enabled server, registers actions."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._supervisor: MCPSupervisor | None = None
        self._registered_names: list[str] = []
        self._started = False

    @property
    def registered_action_names(self) -> list[str]:
        return list(self._registered_names)

    def start(self) -> list[str]:
        """Spin everything up. Returns the list of registered action names."""
        cfg = getattr(self.settings, "mcp", None)
        if cfg is None or not getattr(cfg, "enabled", False):
            log.debug("MCP disabled in settings; bridge inert")
            return []
        servers_path = getattr(cfg, "servers_file", None)
        if servers_path is None:
            log.warning("MCP enabled but no servers_file configured; nothing to wire")
            return []
        servers = [s for s in load_servers(servers_path) if s.enabled]
        if not servers:
            log.info("MCP enabled but no servers listed; nothing to do")
            return []

        self._supervisor = MCPSupervisor()
        self._supervisor.start()
        init_timeout = float(getattr(cfg, "initialize_timeout_seconds", 15))
        for srv in servers:
            try:
                handle = self._supervisor.open_server(srv, init_timeout=init_timeout)
            except Exception as exc:  # noqa: BLE001 -- one bad server can't kill the bridge
                log.warning("MCP server %s failed to start: %s", srv.name, exc)
                continue
            for tool in handle.tools:
                tool_name = getattr(tool, "name", None)
                if not tool_name:
                    continue
                action_name = self._safe_action_name(srv.name, tool_name)
                summary = (getattr(tool, "description", "") or "").strip()
                self._register_one(srv.name, tool_name, action_name, summary)
        self._started = True
        log.info("MCP bridge ready: %d action(s) registered", len(self._registered_names))
        return list(self._registered_names)

    def stop(self) -> None:
        if self._supervisor is not None:
            try:
                self._supervisor.stop()
            except Exception as exc:  # noqa: BLE001
                log.debug("MCP supervisor stop error: %s", exc)
        self._supervisor = None
        self._registered_names.clear()
        self._started = False

    # ------------------------- internals -------------------------

    @staticmethod
    def _safe_action_name(server: str, tool: str) -> str:
        return f"mcp_{_NAME_SAFE.sub('_', server)}_{_NAME_SAFE.sub('_', tool)}"

    def _register_one(
        self, server_name: str, tool_name: str, action_name: str, summary: str
    ) -> None:
        supervisor = self._supervisor
        if supervisor is None:
            return
        timeout = float(getattr(self.settings.mcp, "call_timeout_seconds", 30))

        def _handler(ctx: ActionContext, params: MCPActionParams) -> str:
            args: dict[str, Any] = dict(params.arguments or {})
            # Anything extra at top level (the model passed flat kwargs) ends
            # up in MCPActionParams via model_config extra="allow"; merge it
            # so the operator does not have to wrap every call in ``arguments``.
            extras = {
                k: v
                for k, v in (getattr(params, "__pydantic_extra__", {}) or {}).items()
                if k != "arguments"
            }
            args = {**extras, **args}
            try:
                result = supervisor.call_tool(server_name, tool_name, args, timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                raise ActionError(f"mcp call failed: {exc}") from exc
            return _flatten_mcp_result(result)

        # Brand the source as 'mcp' so an entry-point plugin with the same
        # name can still override it; built-ins are rank 0, MCP slots above
        # them via the existing registry rule.
        register_action(
            name=action_name,
            schema=MCPActionParams,
            summary=summary or f"MCP tool {server_name}/{tool_name}",
            source="entry_point",
        )(_handler)
        self._registered_names.append(action_name)


def _flatten_mcp_result(result: Any) -> str:
    """Turn an MCP ``CallToolResult`` into a single string for the tool_result block."""
    if result is None:
        return "(empty result)"
    contents = getattr(result, "content", None) or []
    parts: list[str] = []
    for item in contents:
        kind = getattr(item, "type", "")
        if kind == "text":
            parts.append(getattr(item, "text", "") or "")
        elif kind == "image":
            mime = getattr(item, "mimeType", "image/*")
            parts.append(f"[image: {mime}]")
        elif kind == "resource":
            uri = getattr(getattr(item, "resource", None), "uri", "")
            parts.append(f"[resource: {uri}]")
        else:
            parts.append(str(item))
    if getattr(result, "isError", False):
        return "[error] " + (" ".join(p for p in parts if p) or "MCP server reported an error")
    return "\n".join(p for p in parts if p) or "(no content)"
