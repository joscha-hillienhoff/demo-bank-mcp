# 5. Hosts and transports

The previous guides looked at the server. This one looks at who starts it and how the two talk.

## What a host is

An MCP **host** is the application the user works in, such as Claude Desktop, Claude Code or the
MCP Inspector. Inside the host, an MCP **client** keeps one connection to one server. A host with
three configured servers runs three clients. The host also contains the model: it puts the tool
descriptions into the model's context, forwards the model's tool calls to the right client, shows
results and asks the user for permission where it chooses to.

## How a host launches a stdio server

A stdio server is a program that the host starts itself. The host needs three things from its
configuration: a name, a command and its arguments, and optionally environment variables. For
Claude Desktop that is `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "demo-bank": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/demo-bank-mcp", "run", "demo-bank-mcp"],
      "env": { "DEMO_BANK_API_URL": "http://localhost:8000" }
    }
  }
}
```

For Claude Code the same information is given on the command line (`claude mcp add demo-bank --
uv --directory ... run demo-bank-mcp`). Some details matter in practice:

- **The host starts the process directly**, with its own working directory and often a shorter
  `PATH` than your terminal has. That is why the config uses `--directory` to point `uv` at the
  project, and why a desktop app may need the absolute path of `uv`.
- **`demo-bank-mcp` is a script entry point** declared in `pyproject.toml`; it calls `main()` in
  [`server.py`](../../src/demo_bank_mcp/server.py), which calls `mcp.run(transport="stdio")`.
- **The tokens come from `.env`** in the project directory, loaded by the server itself.
  Variables in the `env` block of the config are set before and take precedence.
- **The mock API is not started by the host.** The MCP server is only a client of it; start it
  separately.

## What happens on startup

1. The host starts the process with the configured command. The server begins to read stdin.
2. The host sends `initialize` (protocol version, its capabilities); the server answers with its
   version, name `demo-bank` and capabilities (tools, resources, prompts).
3. The host sends the notification `notifications/initialized`.
4. The host calls `tools/list` (and `resources/list`, `prompts/list`) and keeps the answers. From
   here on the model can be told about the tools.
5. Tool calls arrive as `tools/call` while the user chats. When the host quits, it closes stdin
   and the server ends.

The handshake is shown with real messages in [guide 1](01-api-and-mcp.md). If a server does not
show up in a host, the usual causes are a wrong path, `uv` not found, or something written to
stdout that is not protocol (nothing in this server prints to stdout; diagnostics go to stderr,
which hosts write to their own log files).

## stdio versus Streamable HTTP

MCP defines two standard transports; the messages are the same JSON-RPC in both.

**stdio** (used here) runs the server as a child process of the host on the same machine. It
needs no network, no port and no extra authentication: whoever can start the process is the user.
That is why it suits local tools and this project. One process serves one host.

**Streamable HTTP** runs the server as a web service that clients reach with HTTP requests
(optionally with server-to-client streaming). It suits remote and shared servers: many clients,
deployed somewhere, behind a URL. The price is everything a network service needs: transport
security, real authentication (the MCP specification builds on OAuth for this) and deployment.
FastMCP can serve both: the same tools would run with `mcp.run(transport="streamable-http")`. This
project stays with stdio, because real OAuth and deployment are out of scope.

Previous: [security patterns](04-security-patterns.md). Back to the [index](README.md).
