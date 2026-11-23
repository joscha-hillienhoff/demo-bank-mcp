import pytest
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


@pytest.fixture
def client() -> TestClient:
    """A client on a fresh app, so payment drafts never leak between tests."""
    return TestClient(create_app())


@pytest.fixture
def read_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {READ_TOKEN}"}


@pytest.fixture
def full_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {FULL_TOKEN}"}


@pytest.fixture
def bank_client(monkeypatch: pytest.MonkeyPatch, read_headers: dict[str, str]) -> BankClient:
    """The MCP server's bank client, wired to an in-process mock API (no network)."""
    http = TestClient(create_app(), headers=read_headers)
    client = BankClient(http)
    monkeypatch.setattr(server, "_client", client)
    return client
