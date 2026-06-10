"""Generic stdio MCP client support for discovery's external research tools.

Each configured server is a shell-style command string (e.g.
``"npx -y exa-mcp-server"``). Servers are best-effort: one that fails to
spawn, initialize, or list tools is skipped with a stderr warning so
discovery always proceeds with whatever tools remain.
"""

from __future__ import annotations

import asyncio
import shlex
import sys
from contextlib import AsyncExitStack

import dspy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# A hung server command (e.g. npx waiting on the network) must not stall the
# run: bound each server's spawn/initialize/list_tools phase.
SERVER_STARTUP_TIMEOUT_SECONDS = 20.0


async def open_mcp_tools(server_commands: list[str], stack: AsyncExitStack) -> list[dspy.Tool]:
    """Start each stdio MCP server on ``stack`` and return its tools as dspy Tools.

    Sessions stay open until ``stack`` closes; tool calls go through the live
    session. Failing servers are skipped with one stderr warning each.
    """
    tools: list[dspy.Tool] = []
    for command in server_commands:
        try:
            # asyncio.timeout (not wait_for) keeps the coroutine in the
            # current task: contexts entered on `stack` must be exited by the
            # same task or anyio cancel scopes raise at cleanup.
            async with asyncio.timeout(SERVER_STARTUP_TIMEOUT_SECONDS):
                tools.extend(await _open_server_tools(command, stack))
        except Exception as exc:  # never block discovery on a failing server
            print(
                "bd-1: mcp server failed, continuing without it: "
                f"{command}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
    return tools


async def _open_server_tools(command: str, stack: AsyncExitStack) -> list[dspy.Tool]:
    argv = shlex.split(command)
    if not argv:
        raise ValueError("empty MCP server command")
    parameters = StdioServerParameters(command=argv[0], args=argv[1:])
    read_stream, write_stream = await stack.enter_async_context(stdio_client(parameters))
    session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
    await session.initialize()
    listed = await session.list_tools()
    return [dspy.Tool.from_mcp_tool(session, tool) for tool in listed.tools]
