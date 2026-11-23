from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from demo_bank_mcp import server
from demo_bank_mcp.client import BankClient
from mock_bank.app import create_app

READ_TOKEN = "test-read-token"
FULL_TOKEN = "test-full-token"


@pytest.fixture(autouse=True)
def mock_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_BANK_READ_TOKEN", READ_TOKEN)
    monkeypatch.setenv("DEMO_BANK_FULL_TOKEN", FULL_TOKEN)


class FakeClock:
    """A clock the test controls, injected into the mock bank to test expiry."""

    def __init__(self) -> None:
        self.now = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def bank_app(clock: FakeClock) -> FastAPI:
    """A fresh mock bank, so payment drafts never leak between tests."""
    return create_app(clock=clock)


@pytest.fixture(autouse=True)
def audit_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep audit lines of tests out of the project's logs directory."""
    path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("DEMO_BANK_AUDIT_LOG", str(path))
    return path


@pytest.fixture
def client(bank_app: FastAPI) -> TestClient:
    return TestClient(bank_app)


@pytest.fixture
def read_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {READ_TOKEN}"}


@pytest.fixture
def full_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {FULL_TOKEN}"}


@pytest.fixture
def bank_client(
    monkeypatch: pytest.MonkeyPatch, bank_app: FastAPI, read_headers: dict[str, str]
) -> BankClient:
    """The MCP server's read client, wired to an in-process mock API (no network)."""
    client = BankClient(TestClient(bank_app, headers=read_headers))
    monkeypatch.setattr(server, "_client", client)
    return client


@pytest.fixture
def write_client(
    monkeypatch: pytest.MonkeyPatch, bank_app: FastAPI, full_headers: dict[str, str]
) -> BankClient:
    """The MCP server's write client, on the same mock API as `bank_client`."""
    client = BankClient(TestClient(bank_app, headers=full_headers))
    monkeypatch.setattr(server, "_write_client", client)
    return client
