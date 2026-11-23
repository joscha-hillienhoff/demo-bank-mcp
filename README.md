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

## Test and lint

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
