"""Minimal stdio MCP server used by tests; no network access."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("echo-fixture")


@server.tool()
def echo(text: str) -> str:
    """Echo the given text back."""
    return f"echo: {text}"


if __name__ == "__main__":
    server.run()
