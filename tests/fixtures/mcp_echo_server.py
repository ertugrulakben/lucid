"""Minimal MCP server for tests -- exposes a single `echo` tool.

Started as a stdio subprocess by ``test_mcp_bridge_register.py`` to verify the
real client/bridge path. Production code never imports this module.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

app = FastMCP("lucid-test-echo")


@app.tool()
def echo(text: str) -> str:
    """Return the text wrapped in an echo: prefix."""
    return f"echo: {text}"


@app.tool()
def add(a: int, b: int) -> int:
    """Return a + b -- second tool used to verify multi-tool registration."""
    return int(a) + int(b)


if __name__ == "__main__":
    app.run()
