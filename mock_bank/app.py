"""FastAPI app of the fictional Demo Bank: PSD2-style REST endpoints.

This is the plain REST API that exists independently of MCP. A later MCP
server wraps it so that AI hosts can discover and call it. All data is
synthetic (see data.py) and kept in memory.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query

from mock_bank.auth import ACCOUNTS_READ, PAYMENTS_WRITE, require_scope
from mock_bank.data import Dataset, generate
from mock_bank.models import (
    Account,
    AccountList,
    AccountReference,
    Amount,
    Balance,
    BalanceResponse,
    BookedTransactions,
    DraftStatus,
    PaymentDraft,
    PaymentDraftRequest,
    TransactionResponse,
)

DRAFT_LIFETIME = timedelta(minutes=5)


def create_app(dataset: Dataset | None = None) -> FastAPI:
    """Build an app with its own data and draft store (a fresh one per call)."""
    data = dataset or generate()
    drafts: dict[str, PaymentDraft] = {}
    app = FastAPI(title="Demo Bank mock API", version="1")

    def find_account(account_id: str) -> Account:
        for account in data.accounts:
            if account.id == account_id:
                return account
        raise HTTPException(status_code=404, detail="Account not found")

    @app.get(
        "/v1/accounts",
        response_model=AccountList,
        dependencies=[Depends(require_scope(ACCOUNTS_READ))],
    )
    def list_accounts() -> AccountList:
        return AccountList(accounts=data.accounts)

    @app.get(
        "/v1/accounts/{account_id}/balances",
        response_model=BalanceResponse,
        dependencies=[Depends(require_scope(ACCOUNTS_READ))],
    )
    def get_balances(account_id: str) -> BalanceResponse:
        account = find_account(account_id)
        balance = Balance(balance_amount=Amount(amount=data.balances[account.id]))
        return BalanceResponse(account=AccountReference(iban=account.iban), balances=[balance])

    @app.get(
        "/v1/accounts/{account_id}/transactions",
        response_model=TransactionResponse,
        dependencies=[Depends(require_scope(ACCOUNTS_READ))],
    )
    def get_transactions(
        account_id: str,
        date_from: date | None = Query(None, alias="dateFrom"),
        date_to: date | None = Query(None, alias="dateTo"),
    ) -> TransactionResponse:
        """Booked transactions, newest first. Both date bounds are inclusive."""
        account = find_account(account_id)
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=422, detail="dateFrom must not be after dateTo")
        booked = [
            t
            for t in data.transactions[account.id]
            if (date_from is None or t.booking_date >= date_from)
            and (date_to is None or t.booking_date <= date_to)
        ]
        booked.reverse()
        return TransactionResponse(
            account=AccountReference(iban=account.iban),
            transactions=BookedTransactions(booked=booked),
        )

    @app.post(
        "/v1/payments/drafts",
        response_model=PaymentDraft,
        status_code=201,
        dependencies=[Depends(require_scope(PAYMENTS_WRITE))],
    )
    def create_draft(request: PaymentDraftRequest) -> PaymentDraft:
        """Prepare a payment. Nothing is executed until the draft is confirmed."""
        find_account(request.debtor_account_id)
        now = datetime.now(UTC)
        draft = PaymentDraft(
            id=str(uuid.uuid4()),
            status=DraftStatus.PENDING,
            created_at=now,
            expires_at=now + DRAFT_LIFETIME,
            **request.model_dump(),
        )
        drafts[draft.id] = draft
        return draft

    @app.post(
        "/v1/payments/drafts/{draft_id}/confirm",
        response_model=PaymentDraft,
        dependencies=[Depends(require_scope(PAYMENTS_WRITE))],
    )
    def confirm_draft(draft_id: str) -> PaymentDraft:
        draft = drafts.get(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Payment draft not found")
        if draft.status is not DraftStatus.PENDING:
            raise HTTPException(status_code=409, detail="Payment draft is already confirmed")
        confirmed = draft.model_copy(update={"status": DraftStatus.CONFIRMED})
        drafts[draft_id] = confirmed
        return confirmed

    return app


app = create_app()
