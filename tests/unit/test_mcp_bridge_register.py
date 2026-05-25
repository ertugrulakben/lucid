"""End-to-end tests for the MCP bridge against a real stdio server.

The fixture ``mcp_echo_server.py`` is a tiny FastMCP server that publishes
``echo`` and ``add`` tools. The tests spawn it via the bridge, verify that
the registry picks up both tools, and round-trip a real call through the
async loop down to the subprocess and back.

Skipped automatically when the optional ``mcp`` extra is not installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from lucid.actions import registry
from lucid.config.settings import Settings
from lucid.mcp.bridge import MCPActionParams, MCPBridge
from lucid.mcp.config import MCPServerConfig, load_servers


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mcp_echo_server.py"


@pytest.fixture
def echo_yaml(tmp_path: Path) -> Path:
    target = tmp_path / "mcp_servers.yaml"
    target.write_text(
        "servers:\n"
        f"  - name: echo\n"
        f"    command: {sys.executable!r}\n"
        f"    args: [{str(FIXTURE)!r}]\n"
        f"    enabled: true\n",
        encoding="utf-8",
    )
    return target


def test_load_servers_round_trip(echo_yaml: Path) -> None:
    servers = load_servers(echo_yaml)
    assert len(servers) == 1
    assert servers[0].name == "echo"
    assert servers[0].args[0].endswith("mcp_echo_server.py")


def test_load_servers_expands_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUCID_TEST_TOKEN", "expanded-value")
    path = tmp_path / "mcp_servers.yaml"
    path.write_text(
        "servers:\n  - name: x\n    command: echo\n    env: {KEY: '${LUCID_TEST_TOKEN}'}\n",
        encoding="utf-8",
    )
    servers = load_servers(path)
    assert servers[0].env["KEY"] == "expanded-value"


def test_safe_action_name_normalises_punctuation() -> None:
    assert MCPBridge._safe_action_name("file system", "read-file") == "mcp_file_system_read_file"


def test_disabled_settings_does_not_start(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()  # mcp.enabled defaults to False
    bridge = MCPBridge(settings)
    names = bridge.start()
    assert names == []
    bridge.stop()


def test_bridge_starts_server_and_calls_tool(echo_yaml: Path) -> None:
    settings = Settings()
    settings.mcp.enabled = True
    settings.mcp.servers_file = echo_yaml
    settings.mcp.initialize_timeout_seconds = 15
    settings.mcp.call_timeout_seconds = 10
    bridge = MCPBridge(settings)
    try:
        names = bridge.start()
        assert "mcp_echo_echo" in names
        assert "mcp_echo_add" in names

        ctx = registry.ActionContext(settings=settings)
        result = registry.run(
            "mcp_echo_echo", ctx, MCPActionParams(arguments={"text": "merhaba"})
        )
        assert "merhaba" in result
        assert "echo:" in result

        add_result = registry.run(
            "mcp_echo_add", ctx, MCPActionParams(arguments={"a": 2, "b": 5})
        )
        assert "7" in add_result
    finally:
        bridge.stop()


def test_load_servers_skips_malformed_rows(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.yaml"
    path.write_text(
        "servers:\n"
        "  - name: ok\n"
        "    command: echo\n"
        "  - 'not a dict'\n"
        "  - name: dup\n"
        "    command: echo\n"
        "  - name: dup\n"
        "    command: echo\n",
        encoding="utf-8",
    )
    servers = load_servers(path)
    assert [s.name for s in servers] == ["ok", "dup"]
