import pytest
from fastapi.testclient import TestClient

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
