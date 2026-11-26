# demo-bank-mcp

A learning project: an MCP server that lets AI assistants read the accounts of a fictional bank and prepare transfers through a draft-and-confirm flow, with prompt-injection safeguards.

All data is synthetic and the bank ("Demo Bank") does not exist. Nothing here connects to a real bank.

## Why MCP

A bank already has a REST API. That API is written for programmers who read its documentation
before they write code. An AI assistant has no such step: it must find out at run time what exists,
what the parts mean and how to call them. The Model Context Protocol (MCP) standardises that:
a server describes its tools, resources and prompts in a machine-readable way, and any MCP host
(Claude Desktop, Claude Code, the MCP Inspector, ...) can use them without custom integration code.

MCP does not replace the REST API. In this project the two are deliberately separate programs:
the API keeps the data and its own security, and the MCP server re-publishes selected parts of it
in a form a model can use. See [docs/mcp-vs-api.md](docs/mcp-vs-api.md) for the comparison with
REST and with agent-to-agent protocols.

## Architecture

```mermaid
flowchart LR
    Host["MCP host<br/>(Claude Desktop, Claude Code,<br/>MCP Inspector)"]
    Server["demo_bank_mcp<br/>tools, resources, prompts"]
    API["mock_bank<br/>FastAPI, PSD2-style REST,<br/>synthetic data"]

    Host -- "MCP over stdio<br/>(JSON-RPC 2.0)" --> Server
    Server -- "HTTP + bearer token<br/>(scopes)" --> API
```

The host starts the MCP server as a child process and talks to it over stdin and stdout. The
server calls the mock bank's REST API with httpx and a mock bearer token. The account endpoints
are modelled on the public NextGenPSD2 (Berlin Group) standard, simplified.

## What the server offers

| Kind | Name | Purpose |
| --- | --- | --- |
| Tool | `list_accounts` | The customer's accounts, IBANs masked |
| Tool | `get_balance` | Booked balance of one account |
| Tool | `search_transactions` | Transactions of a period, filtered by amount, text or category; third-party text is marked untrusted |
| Tool | `prepare_transfer` | Creates a transfer **draft**; moves no money |
| Tool | `confirm_transfer` | Executes an unexpired draft after the user has agreed |
| Resource | `bank://fees` | Price list of accounts, cards and transfers |
| Resource | `bank://faq` | Transfer limits and cut-off times |
| Prompt | `monthly_summary(month)` | Template that asks the model to summarise one month |

Who controls what: the model calls tools, the application reads resources, the user picks prompts.

## Security patterns

- **Confirmation step:** money moves only after `prepare_transfer` (draft) and an explicit
  `confirm_transfer`.
- **Server-side limits:** the API enforces 1,000 EUR per transfer, 3 transfers per day and a
  5 minute draft lifetime, whatever the model or host does.
- **Least privilege:** read tools use a token with `accounts:read`; only the transfer tools use
  `payments:write`.
- **Audit log:** every tool call is appended to `logs/audit.jsonl`, with IBANs masked.
- **Data minimisation:** masked IBANs, no owner name, at most 50 transactions per search.
- **Injection guard:** free text from third parties is wrapped in `<untrusted-data>` tags. The
  seeded data contains a transaction that tries to hijack an assistant.

The reference, including what these patterns cannot guarantee, is
[docs/security-patterns.md](docs/security-patterns.md).

## Run

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
cp .env.example .env   # mock bearer tokens, not real credentials
uv run uvicorn mock_bank.app:app --port 8000
```

The interactive API docs are at <http://localhost:8000/docs>. Send a token with each request, e.g.:

```sh
curl -H "Authorization: Bearer mock-read-token-change-me" http://localhost:8000/v1/accounts
```

With the mock API running, start the MCP server (stdio) or explore it in the MCP Inspector:

```sh
uv run demo-bank-mcp
uv run mcp dev src/demo_bank_mcp/server.py
```

`mcp dev` starts the MCP Inspector through `npx`, so it needs Node.js.

The server reads its mock tokens and the API URL from `.env`. The mock API keeps its drafts and
the daily transfer count in memory, so restarting it resets both.

### Use it from a host

Start the mock API first (above); the MCP server only forwards calls to it.

**Claude Desktop.** Add the server to `claude_desktop_config.json` (on macOS under
`~/Library/Application Support/Claude/`), then restart Claude Desktop. Replace the path
placeholder with the absolute path of this project. If Claude Desktop cannot find `uv`, use the
absolute path from `which uv` as the command.

```json
{
  "mcpServers": {
    "demo-bank": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/demo-bank-mcp", "run", "demo-bank-mcp"],
      "env": {
        "DEMO_BANK_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

The tokens (`DEMO_BANK_READ_TOKEN`, `DEMO_BANK_FULL_TOKEN`) are read from the project's `.env`, so
they do not need to be repeated here. Variables in `env` take precedence over `.env`.

**Claude Code.**

```sh
claude mcp add demo-bank -- uv --directory /absolute/path/to/demo-bank-mcp run demo-bank-mcp
```

How a host starts a server and what happens on startup is explained in
[docs/learn/05-hosts-and-transports.md](docs/learn/05-hosts-and-transports.md). A four-step manual
demo for a host is in [docs/demo-script.md](docs/demo-script.md).

## Learn

The guides in [`docs/learn/`](docs/learn/README.md) explain the concepts using this project's own
code. Read them in order:

1. [The API and the MCP server](docs/learn/01-api-and-mcp.md): why they are separate, and the stdio JSON-RPC handshake.
2. [Tools, resources and prompts](docs/learn/02-tools-resources-prompts.md): who controls each, how a tool call flows, and how docstrings and type hints become the schema.
3. [The write flow and confirmation](docs/learn/03-write-flow-and-confirmation.md): why transfers take two steps, how drafts and expiry work, tool annotations and elicitation.
4. [Security patterns and prompt injection](docs/learn/04-security-patterns.md): a walk-through of the injected transaction in the seeded data.
5. [Hosts and transports](docs/learn/05-hosts-and-transports.md): how a host launches a stdio server, the config file, startup, and stdio versus Streamable HTTP.

[docs/learn/README.md](docs/learn/README.md) ends with a list of questions to explore across the whole
project.

## Test and lint

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Limitations

This is a teaching project, not a banking product.

- **Mock bank only.** One customer, two accounts, data from January to June 2026, kept in memory.
  An executed transfer is confirmed but does not appear in the balance or the transactions.
- **No real authentication.** The bearer tokens are static mock values from `.env`; there is no
  OAuth, no user management and no multi-user support.
- **Local use only.** The server runs over stdio on one machine. There is no deployment, no
  remote transport and no UI.
- **The safeguards are layers, not guarantees.** Whether a model respects the untrusted-data
  marking and whether a host really asks the user before a tool call are outside this server's
  control; the API-side limits are what holds. Details in
  [docs/security-patterns.md](docs/security-patterns.md).
- **Simplified standards.** The endpoints follow NextGenPSD2 in spirit but are not compliant with
  it.

## License

[MIT](LICENSE)
