"""Typed HTTP client for the Demo Bank API.

The MCP server never touches bank data directly: it calls the REST API like any
other API consumer, with a bearer token. This module is the only place that
knows URLs and JSON shapes of that API. The server above it only deals with
the small typed results defined here, which keep just the fields an assistant
needs (the raw API responses are more verbose).
"""

from datetime import date, datetime
from urllib.parse import quote

import httpx
from pydantic import BaseModel

DEFAULT_BASE_URL = "http://localhost:8000"


class BankApiError(Exception):
    """The bank API answered with an error status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class Account(BaseModel):
    id: str
    iban: str
    name: str
    product: str
    currency: str


class Balance(BaseModel):
    account_id: str
    iban: str
    balance_type: str
    amount: str  # decimal string such as "-850.00", as in the API
    currency: str


class Transaction(BaseModel):
    id: str
    booking_date: date
    amount: str  # decimal string such as "-850.00", as in the API
    currency: str
    counterparty: str
    counterparty_iban: str | None
    purpose: str
    category: str


class PaymentDraft(BaseModel):
    """A prepared payment. `status` is "pending" until it is confirmed."""

    id: str
    status: str
    expires_at: datetime
    debtor_account_id: str
    creditor_name: str
    creditor_iban: str
    amount: str  # decimal string such as "25.00", as in the API
    currency: str
    purpose: str


class BankClient:
    """Calls against the bank API. What a call may do depends on the token's scopes."""

    def __init__(self, http: httpx.Client) -> None:
        # The caller configures base URL and Authorization header on `http`.
        # Tests pass a FastAPI TestClient here, which is an httpx.Client.
        self._http = http

    @classmethod
    def from_token(cls, token: str, base_url: str = DEFAULT_BASE_URL) -> "BankClient":
        headers = {"Authorization": f"Bearer {token}"}
        return cls(httpx.Client(base_url=base_url, headers=headers, timeout=10.0))

    def list_accounts(self) -> list[Account]:
        body = self._get("/v1/accounts")
        return [
            Account(
                id=a["id"],
                iban=a["iban"],
                name=a["name"],
                product=a["product"],
                currency=a["currency"],
            )
            for a in body["accounts"]
        ]

    def get_balance(self, account_id: str) -> Balance:
        body = self._get(f"/v1/accounts/{account_id}/balances")
        # The API returns a list of balances; this mock only ever has one.
        balance = body["balances"][0]
        return Balance(
            account_id=account_id,
            iban=body["account"]["iban"],
            balance_type=balance["balanceType"],
            amount=balance["balanceAmount"]["amount"],
            currency=balance["balanceAmount"]["currency"],
        )

    def get_transactions(
        self, account_id: str, date_from: date, date_to: date
    ) -> list[Transaction]:
        """Booked transactions of the period, newest first (bounds inclusive)."""
        params = {"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()}
        body = self._get(f"/v1/accounts/{account_id}/transactions", params=params)
        return [
            Transaction(
                id=t["transactionId"],
                booking_date=t["bookingDate"],
                amount=t["transactionAmount"]["amount"],
                currency=t["transactionAmount"]["currency"],
                counterparty=t["counterpartyName"],
                counterparty_iban=t.get("counterpartyIban"),
                purpose=t["remittanceInformationUnstructured"],
                category=t["category"],
            )
            for t in body["transactions"]["booked"]
        ]

    def create_draft(
        self, account_id: str, creditor_name: str, creditor_iban: str, amount: str, purpose: str
    ) -> PaymentDraft:
        """Prepare a payment (scope payments:write). Nothing is executed yet."""
        body = {
            "debtorAccountId": account_id,
            "creditorName": creditor_name,
            "creditorIban": creditor_iban,
            "instructedAmount": {"currency": "EUR", "amount": amount},
            "remittanceInformationUnstructured": purpose,
        }
        return _to_draft(self._post("/v1/payments/drafts", json=body))

    def confirm_draft(self, draft_id: str) -> PaymentDraft:
        """Execute a pending, unexpired draft (scope payments:write)."""
        # quote(): the draft id comes from the model, so it must not alter the path.
        return _to_draft(self._post(f"/v1/payments/drafts/{quote(draft_id, safe='')}/confirm"))

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
        return self._checked(self._http.get(path, params=params))

    def _post(self, path: str, json: dict | None = None) -> dict:
        return self._checked(self._http.post(path, json=json))

    @staticmethod
    def _checked(response: httpx.Response) -> dict:
        if response.is_error:
            raise BankApiError(response.status_code, _error_detail(response))
        return response.json()


def _to_draft(body: dict) -> PaymentDraft:
    return PaymentDraft(
        id=body["id"],
        status=body["status"],
        expires_at=body["expiresAt"],
        debtor_account_id=body["debtorAccountId"],
        creditor_name=body["creditorName"],
        creditor_iban=body["creditorIban"],
        amount=body["instructedAmount"]["amount"],
        currency=body["instructedAmount"]["currency"],
        purpose=body["remittanceInformationUnstructured"],
    )


def _error_detail(response: httpx.Response) -> str:
    try:
        detail = response.json()["detail"]
    except (ValueError, KeyError, TypeError):
        return response.reason_phrase
    # FastAPI returns a list of objects for request validation errors.
    return detail if isinstance(detail, str) else "Invalid request"
