# 1. The API and the MCP server

## Two programs, on purpose

```
MCP host  --MCP over stdio-->  demo_bank_mcp  --HTTP + bearer token-->  mock_bank
(Claude Desktop,               (src/demo_bank_mcp)                      (mock_bank/app.py,
 Claude Code, Inspector)                                                 synthetic data)
```

`mock_bank` is an ordinary REST API. It knows nothing about AI, and any client could use it
(try `curl`, or the interactive docs at <http://localhost:8000/docs>).

`demo_bank_mcp` is a second, separate program. It does not replace the API and it holds no bank
data. It calls the API through a typed client ([`client.py`](../../src/demo_bank_mcp/client.py))
and re-publishes selected parts of it in a form an AI host can discover and use:

| | REST API | MCP server |
| --- | --- | --- |
| Consumer | A programmer who read the docs | A language model, at run time |
| Discovery | OpenAPI document, read by a human | `tools/list`, `resources/list`, `prompts/list`, answered by the server itself |
| Contract | Endpoints and JSON shapes | Names, natural-language descriptions and JSON Schemas |
| Auth | Bearer token with scopes | Same: the server holds one token and decides what it exposes |

The point of the split: the API stays the source of truth and keeps its own security (scopes,
status codes). The MCP layer adds what a model needs on top: descriptions it can read, compact
results, masked data and clear error messages.

The MCP server only holds the read-only token (`accounts:read`, see [`.env.example`](../../.env.example)).
Even if a model misbehaved, this server could not call a payment endpoint, because the API would
answer 403.

## The transport: JSON-RPC over stdio

An MCP host starts the server as a child process and talks to it through stdin and stdout.
Every message is one line of JSON-RPC 2.0: a request with an `id` gets a response with the same
`id`; a notification has no `id` and gets no response.

The session starts with a handshake:

1. The client sends `initialize` with its protocol version and capabilities.
2. The server answers with its own protocol version, its name and the capabilities it offers.
3. The client sends the notification `notifications/initialized`. Now normal requests may follow.

You can run this by hand. Start the mock API (`uv run uvicorn mock_bank.app:app --port 8000`),
copy `.env.example` to `.env`, then:

```sh
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | (cat; sleep 2) | uv run demo-bank-mcp 2>/dev/null
```

The first response (shortened) shows the capability negotiation. The server declares that it
offers tools, resources and prompts, and none of them notifies the client about changes:

```json
{"jsonrpc": "2.0", "id": 1, "result": {
  "protocolVersion": "2025-06-18",
  "capabilities": {
    "prompts":   {"listChanged": false},
    "resources": {"subscribe": false, "listChanged": false},
    "tools":     {"listChanged": false}
  },
  "serverInfo": {"name": "demo-bank", "version": "1.30.0"}
}}
```

`serverInfo.name` is the string passed to `FastMCP("demo-bank")` in
[`server.py`](../../src/demo_bank_mcp/server.py); the version is the one of the SDK.

Two practical consequences of stdio:

- **stdout belongs to the protocol.** A stray `print()` in server code corrupts the message stream.
  Logs go to stderr (which is why the command above discards it).
- **The host owns the process.** It starts the server when needed and ends it by closing stdin.

You can also explore everything interactively with the MCP Inspector:
`uv run mcp dev src/demo_bank_mcp/server.py`.

Next: [tools, resources and prompts](02-tools-resources-prompts.md).
