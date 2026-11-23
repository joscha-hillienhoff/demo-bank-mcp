import pytest

from mock_bank.data import GIRO

READ_ROUTES = [
    ("get", "/v1/accounts"),
    ("get", f"/v1/accounts/{GIRO.id}/balances"),
    ("get", f"/v1/accounts/{GIRO.id}/transactions"),
]
PAYMENT_ROUTES = [
    ("post", "/v1/payments/drafts"),
    ("post", "/v1/payments/drafts/some-id/confirm"),
]
ALL_ROUTES = READ_ROUTES + PAYMENT_ROUTES


@pytest.mark.parametrize(("method", "path"), ALL_ROUTES)
def test_no_token_returns_401(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(("method", "path"), ALL_ROUTES)
def test_unknown_token_returns_401(client, method, path):
    response = getattr(client, method)(path, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), ALL_ROUTES)
def test_non_bearer_scheme_returns_401(client, method, path):
    response = getattr(client, method)(path, headers={"Authorization": "Basic abc"})
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), PAYMENT_ROUTES)
def test_read_token_gets_403_on_payment_routes(client, read_headers, method, path):
    response = getattr(client, method)(path, headers=read_headers)
    assert response.status_code == 403
    assert "payments:write" in response.json()["detail"]


@pytest.mark.parametrize(("method", "path"), READ_ROUTES)
def test_read_token_can_read(client, read_headers, method, path):
    assert getattr(client, method)(path, headers=read_headers).status_code == 200


@pytest.mark.parametrize(("method", "path"), READ_ROUTES)
def test_full_token_can_read(client, full_headers, method, path):
    assert getattr(client, method)(path, headers=full_headers).status_code == 200


def test_unset_tokens_accept_nothing(client, monkeypatch):
    monkeypatch.delenv("DEMO_BANK_READ_TOKEN")
    monkeypatch.delenv("DEMO_BANK_FULL_TOKEN")
    # Guards against an empty configured value matching an empty bearer token.
    response = client.get("/v1/accounts", headers={"Authorization": "Bearer "})
    assert response.status_code == 401
    response = client.get("/v1/accounts", headers={"Authorization": "Bearer None"})
    assert response.status_code == 401
