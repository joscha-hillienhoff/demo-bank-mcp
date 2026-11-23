"""FastAPI app of the fictional Demo Bank: PSD2-style REST endpoints.

This is the plain REST API that exists independently of MCP. A later MCP
server wraps it so that AI hosts can discover and call it. All data is
synthetic (see data.py) and kept in memory.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

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

# Limits of the mock bank. The API is the authority: whatever a client or an
# AI assistant asks for, a transfer above these limits is never executed.
MAX_TRANSFER_AMOUNT = Decimal("1000.00")
MAX_TRANSFERS_PER_DAY = 3


def create_app(
    dataset: Dataset | None = None, clock: Callable[[], datetime] | None = None
) -> FastAPI:
    """Build an app with its own data and draft store (a fresh one per call).

    `clock` returns the current time. Tests inject a fake one to test expiry
    and the daily limit without waiting.
    """
    data = dataset or generate()
    now = clock or (lambda: datetime.now(UTC))
    drafts: dict[str, PaymentDraft] = {}
    app = FastAPI(title="Demo Bank mock API", version="1")

    def find_account(account_id: str) -> Account:
        for account in data.accounts:
            if account.id == account_id:
                return account
        raise HTTPException(status_code=404, detail="Account not found")

    def check_daily_limit() -> None:
        """Only confirmed drafts count: a draft alone never moves money."""
        today = now().date()
        executed = sum(
            1 for d in drafts.values() if d.confirmed_at and d.confirmed_at.date() == today
        )
        if executed >= MAX_TRANSFERS_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail=f"Daily limit reached: at most {MAX_TRANSFERS_PER_DAY} transfers per day",
            )

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
        if request.instructed_amount.amount > MAX_TRANSFER_AMOUNT:
            raise HTTPException(
                status_code=422,
                detail=f"Amount exceeds the limit of {MAX_TRANSFER_AMOUNT} EUR per transfer",
            )
        # Fail early; confirm checks again because drafts can be prepared in advance.
        check_daily_limit()
        created = now()
        draft = PaymentDraft(
            id=str(uuid.uuid4()),
            status=DraftStatus.PENDING,
            created_at=created,
            expires_at=created + DRAFT_LIFETIME,
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
        """Execute a pending, unexpired draft. This is the only place money moves."""
        draft = drafts.get(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Payment draft not found")
        if draft.status is DraftStatus.CONFIRMED:
            raise HTTPException(status_code=409, detail="Payment draft is already confirmed")
        if draft.status is DraftStatus.EXPIRED or now() >= draft.expires_at:
            drafts[draft_id] = draft.model_copy(update={"status": DraftStatus.EXPIRED})
            raise HTTPException(
                status_code=410, detail="Payment draft has expired. Prepare a new transfer."
            )
        check_daily_limit()
        confirmed = draft.model_copy(
            update={"status": DraftStatus.CONFIRMED, "confirmed_at": now()}
        )
        drafts[draft_id] = confirmed
        return confirmed

    return app


app = create_app()
