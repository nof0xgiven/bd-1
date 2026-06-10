import asyncio
import shlex
import sys
from contextlib import AsyncExitStack
from pathlib import Path

import dspy

from bd1.mcp_tools import open_mcp_tools

FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "echo_mcp_server.py"


def fixture_server_command() -> str:
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(FIXTURE_SERVER))}"


def _open(commands: list[str]) -> list[dspy.Tool]:
    async def run() -> list[dspy.Tool]:
        async with AsyncExitStack() as stack:
            return await open_mcp_tools(commands, stack)

    return asyncio.run(run())


def test_open_mcp_tools_converts_real_server_tools_to_dspy_tools():
    async def run():
        async with AsyncExitStack() as stack:
            tools = await open_mcp_tools([fixture_server_command()], stack)
            assert [tool.name for tool in tools] == ["echo"]
            tool = tools[0]
            assert isinstance(tool, dspy.Tool)
            assert "Echo the given text back." in tool.desc
            return await tool.acall(text="hello")

    assert asyncio.run(run()) == "echo: hello"


def test_open_mcp_tools_skips_unspawnable_server_with_warning(capsys):
    tools = _open(["definitely-not-a-real-binary-xyz"])

    assert tools == []
    stderr = capsys.readouterr().err
    assert "bd-1: mcp server failed, continuing without it" in stderr
    assert "definitely-not-a-real-binary-xyz" in stderr


def test_open_mcp_tools_keeps_healthy_servers_when_one_fails(capsys):
    tools = _open(["definitely-not-a-real-binary-xyz", fixture_server_command()])

    assert [tool.name for tool in tools] == ["echo"]
    assert "definitely-not-a-real-binary-xyz" in capsys.readouterr().err


def test_open_mcp_tools_with_no_servers_returns_empty_without_warnings(capsys):
    assert _open([]) == []
    assert capsys.readouterr().err == ""
