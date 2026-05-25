"""Async MCP stdio client wrapped in a sync facade.

Lucid's executor runs actions on a synchronous worker thread, but the official
MCP SDK is asyncio-first. ``MCPSupervisor`` owns a private background thread
that hosts one asyncio event loop; every server gets a ``ClientSession`` that
stays open inside that loop. Sync callers hand the supervisor a coroutine
through :meth:`submit` and block on the resulting concurrent future.

Failure modes are isolated: one server crashing on initialise does not take
the others down, and a tool call that times out closes its own future without
disturbing the loop.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import threading
from typing import Any

from mcp import ClientSession, StdioServerParameters  # type: ignore[import-not-found]
from mcp.client.stdio import stdio_client  # type: ignore[import-not-found]

from .config import MCPServerConfig

log = logging.getLogger("lucid.mcp.client")


class _ServerHandle:
    """Live session + its surrounding async context managers."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.session: ClientSession | None = None
        self.tools: list[Any] = []
        self._exit_stack: contextlib.AsyncExitStack | None = None

    async def open(self, config: MCPServerConfig, init_timeout: float) -> None:
        params = StdioServerParameters(
            command=config.command,
            args=list(config.args),
            env={**config.env} if config.env else None,
            cwd=config.cwd,
        )
        stack = contextlib.AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=init_timeout)
            tools_response = await asyncio.wait_for(session.list_tools(), timeout=init_timeout)
            self.session = session
            self.tools = list(tools_response.tools or [])
            self._exit_stack = stack
        except Exception:
            await stack.aclose()
            raise

    async def close(self) -> None:
        if self._exit_stack is not None:
            with contextlib.suppress(Exception):
                await self._exit_stack.aclose()
        self._exit_stack = None
        self.session = None
        self.tools = []


class MCPSupervisor:
    """Owns the background asyncio loop and the per-server handles."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._servers: dict[str, _ServerHandle] = {}
        self._lock = threading.Lock()
        self._started = False

    # ------------------------- lifecycle -------------------------

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        def _run() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            try:
                self._loop.run_forever()
            finally:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                self._loop.run_until_complete(asyncio.sleep(0))
                self._loop.close()

        self._thread = threading.Thread(target=_run, daemon=True, name="lucid-mcp-loop")
        self._thread.start()
        self._ready.wait(timeout=5.0)

    def stop(self, timeout: float = 5.0) -> None:
        if not self._started or self._loop is None:
            return
        # Close every server cleanly before tearing the loop down.
        for name in list(self._servers):
            try:
                self.submit(self._servers[name].close(), timeout=timeout).result(timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                log.debug("close of MCP server %s failed: %s", name, exc)
        self._servers.clear()
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._loop = None
        self._thread = None
        self._started = False

    # ------------------------- submit -------------------------

    def submit(self, coro: Any, timeout: float | None = None) -> concurrent.futures.Future:
        """Schedule ``coro`` on the supervisor loop and return a sync future."""
        if self._loop is None:
            raise RuntimeError("MCP supervisor not running")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        if timeout is not None:
            # We attach a fallback so blocked callers can wait_for with a
            # bounded budget without blowing up the supervisor loop.
            future_timeout_marker = timeout
            future._lucid_timeout = future_timeout_marker  # type: ignore[attr-defined]
        return future

    # ------------------------- server ops -------------------------

    def open_server(self, config: MCPServerConfig, init_timeout: float) -> _ServerHandle:
        handle = _ServerHandle(config.name)
        future = self.submit(handle.open(config, init_timeout), timeout=init_timeout + 2)
        future.result(timeout=init_timeout + 5)
        with self._lock:
            self._servers[config.name] = handle
        return handle

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None,
        timeout: float,
    ) -> Any:
        handle = self._servers.get(server_name)
        if handle is None or handle.session is None:
            raise RuntimeError(f"MCP server {server_name!r} is not connected")

        async def _call() -> Any:
            return await asyncio.wait_for(
                handle.session.call_tool(tool_name, arguments or {}),
                timeout=timeout,
            )

        future = self.submit(_call(), timeout=timeout + 2)
        return future.result(timeout=timeout + 5)

    def list_tools(self, server_name: str) -> list[Any]:
        handle = self._servers.get(server_name)
        if handle is None:
            return []
        return list(handle.tools)
