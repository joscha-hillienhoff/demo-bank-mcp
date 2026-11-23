"""Entry point of the Demo Bank MCP server.

MCP concept: a server exposes capabilities (tools, resources, prompts) to an
MCP host over a transport. FastMCP is the high-level API of the official Python
SDK; it handles the JSON-RPC 2.0 protocol, capability negotiation and the
transport, so this module only has to register capabilities.

No capabilities are registered yet. The server starts, completes the MCP
handshake and advertises an empty capability set.
"""

from mcp.server.fastmcp import FastMCP

# The name is what hosts show to users and send back in the initialize handshake.
mcp = FastMCP("demo-bank")


def main() -> None:
    """Run the server over stdio, the transport used by local MCP hosts."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
