# demo-bank-mcp

MCP server that connects AI assistants to a fictional bank's PSD2-style API, with a draft-and-confirm write flow and prompt-injection safeguards.

All data is synthetic and the bank ("Demo Bank") does not exist.

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

Run the MCP server (stdio) against the running mock API, or explore it in the MCP Inspector:

```sh
uv run demo-bank-mcp
uv run mcp dev src/demo_bank_mcp/server.py
```

The server offers the tools `list_accounts`, `get_balance` and `search_transactions`, the
resources `bank://fees` and `bank://faq`, and the prompt `monthly_summary`. It reads its
mock token and the API URL from `.env`.

## Learn

Short guides that explain the concepts using this project's own code:

1. [The API and the MCP server](docs/learn/01-api-and-mcp.md): why they are separate, and the stdio JSON-RPC handshake.
2. [Tools, resources and prompts](docs/learn/02-tools-resources-prompts.md): who controls each, how a tool call flows, and how docstrings and type hints become the schema.

## Test and lint

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
