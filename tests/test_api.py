from datetime import datetime

import pytest

from mock_bank.data import GIRO, INJECTION_PURPOSE, TAGESGELD, generate

DRAFT_BODY = {
    "debtorAccountId": GIRO.id,
    "creditorName": "Beispiel Empfaenger",
    "creditorIban": "DE00 DEMO 3000 0000 01",
    "instructedAmount": {"currency": "EUR", "amount": "25.00"},
    "remittanceInformationUnstructured": "Test payment",
}


def transactions(client, headers, account_id=GIRO.id, **params):
    response = client.get(f"/v1/accounts/{account_id}/transactions", params=params, headers=headers)
    assert response.status_code == 200
    return response.json()["transactions"]["booked"]


# --- accounts and balances ---


def test_list_accounts(client, read_headers):
    response = client.get("/v1/accounts", headers=read_headers)
    assert response.status_code == 200
    accounts = response.json()["accounts"]
    assert [a["name"] for a in accounts] == ["Girokonto", "Tagesgeld"]
    assert accounts[0]["ownerName"] == generate().customer.name
    assert accounts[0]["iban"] == GIRO.iban


def test_balances_are_returned_as_decimal_strings(client, read_headers):
    response = client.get(f"/v1/accounts/{TAGESGELD.id}/balances", headers=read_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["account"]["iban"] == TAGESGELD.iban
    [balance] = body["balances"]
    assert balance["balanceType"] == "closingBooked"
    assert balance["balanceAmount"]["currency"] == "EUR"
    assert balance["balanceAmount"]["amount"] == str(generate().balances[TAGESGELD.id])


def test_unknown_account_returns_404(client, read_headers):
    assert client.get("/v1/accounts/nope/balances", headers=read_headers).status_code == 404
    assert client.get("/v1/accounts/nope/transactions", headers=read_headers).status_code == 404


# --- transactions and date filtering ---


def test_transactions_without_filter_return_everything_newest_first(client, read_headers):
    booked = transactions(client, read_headers)
    assert len(booked) == len(generate().transactions[GIRO.id])
    dates = [t["bookingDate"] for t in booked]
    assert dates == sorted(dates, reverse=True)


def test_transaction_fields(client, read_headers):
    booked = transactions(client, read_headers)
    injected = next(
        t for t in booked if t["remittanceInformationUnstructured"] == INJECTION_PURPOSE
    )
    assert injected["transactionAmount"] == {"currency": "EUR", "amount": "1.00"}
    assert injected["category"] == "Sonstiges"
    assert injected["counterpartyName"]


def test_date_from_and_date_to_are_inclusive(client, read_headers):
    booked = transactions(client, read_headers, dateFrom="2026-03-01", dateTo="2026-03-31")
    assert booked
    assert all("2026-03-01" <= t["bookingDate"] <= "2026-03-31" for t in booked)
    # The monthly rent is booked on the first day, so the lower bound must be inclusive.
    assert any(t["category"] == "Miete" and t["bookingDate"] == "2026-03-01" for t in booked)


def test_single_day_filter(client, read_headers):
    booked = transactions(client, read_headers, dateFrom="2026-05-14", dateTo="2026-05-14")
    assert {t["bookingDate"] for t in booked} == {"2026-05-14"}
    assert any(t["remittanceInformationUnstructured"] == INJECTION_PURPOSE for t in booked)


def test_open_ended_date_filters(client, read_headers):
    everything = transactions(client, read_headers)
    from_only = transactions(client, read_headers, dateFrom="2026-06-01")
    to_only = transactions(client, read_headers, dateTo="2026-01-31")
    assert 0 < len(from_only) < len(everything)
    assert 0 < len(to_only) < len(everything)
    assert all(t["bookingDate"] >= "2026-06-01" for t in from_only)
    assert all(t["bookingDate"] <= "2026-01-31" for t in to_only)


def test_filter_outside_data_range_is_empty(client, read_headers):
    assert transactions(client, read_headers, dateFrom="2030-01-01") == []


def test_reversed_date_range_is_rejected(client, read_headers):
    response = client.get(
        f"/v1/accounts/{GIRO.id}/transactions",
        params={"dateFrom": "2026-03-31", "dateTo": "2026-03-01"},
        headers=read_headers,
    )
    assert response.status_code == 422


def test_invalid_date_is_rejected(client, read_headers):
    response = client.get(
        f"/v1/accounts/{GIRO.id}/transactions",
        params={"dateFrom": "not-a-date"},
        headers=read_headers,
    )
    assert response.status_code == 422


# --- payment drafts ---


def test_create_draft_returns_pending_draft_with_expiry(client, full_headers):
    response = client.post("/v1/payments/drafts", json=DRAFT_BODY, headers=full_headers)
    assert response.status_code == 201
    draft = response.json()
    assert draft["id"]
    assert draft["status"] == "pending"
    assert draft["debtorAccountId"] == GIRO.id
    assert draft["instructedAmount"] == {"currency": "EUR", "amount": "25.00"}
    created = datetime.fromisoformat(draft["createdAt"])
    expires = datetime.fromisoformat(draft["expiresAt"])
    assert (expires - created).total_seconds() == 5 * 60


def test_creating_a_draft_does_not_move_money(client, full_headers):
    before = client.get(f"/v1/accounts/{GIRO.id}/balances", headers=full_headers).json()
    client.post("/v1/payments/drafts", json=DRAFT_BODY, headers=full_headers)
    after = client.get(f"/v1/accounts/{GIRO.id}/balances", headers=full_headers).json()
    assert before == after


def test_create_draft_for_unknown_account_returns_404(client, full_headers):
    body = {**DRAFT_BODY, "debtorAccountId": "nope"}
    response = client.post("/v1/payments/drafts", json=body, headers=full_headers)
    assert response.status_code == 404


@pytest.mark.parametrize("amount", ["0.00", "-5.00"])
def test_create_draft_rejects_non_positive_amount(client, full_headers, amount):
    body = {**DRAFT_BODY, "instructedAmount": {"currency": "EUR", "amount": amount}}
    response = client.post("/v1/payments/drafts", json=body, headers=full_headers)
    assert response.status_code == 422


def test_create_draft_rejects_missing_fields(client, full_headers):
    response = client.post("/v1/payments/drafts", json={}, headers=full_headers)
    assert response.status_code == 422


def test_confirm_draft(client, full_headers):
    draft = client.post("/v1/payments/drafts", json=DRAFT_BODY, headers=full_headers).json()
    response = client.post(f"/v1/payments/drafts/{draft['id']}/confirm", headers=full_headers)
    assert response.status_code == 200
    confirmed = response.json()
    assert confirmed["id"] == draft["id"]
    assert confirmed["status"] == "confirmed"


def test_confirming_twice_returns_409(client, full_headers):
    draft = client.post("/v1/payments/drafts", json=DRAFT_BODY, headers=full_headers).json()
    url = f"/v1/payments/drafts/{draft['id']}/confirm"
    assert client.post(url, headers=full_headers).status_code == 200
    assert client.post(url, headers=full_headers).status_code == 409


def test_confirm_unknown_draft_returns_404(client, full_headers):
    response = client.post("/v1/payments/drafts/does-not-exist/confirm", headers=full_headers)
    assert response.status_code == 404


def test_drafts_are_not_shared_between_apps(client, full_headers):
    from fastapi.testclient import TestClient

    from mock_bank.app import create_app

    draft = client.post("/v1/payments/drafts", json=DRAFT_BODY, headers=full_headers).json()
    other = TestClient(create_app())
    response = other.post(f"/v1/payments/drafts/{draft['id']}/confirm", headers=full_headers)
    assert response.status_code == 404
