"""Pydantic models of the mock bank API.

The shapes are loosely modelled on the public NextGenPSD2 (Berlin Group)
account information and payment initiation endpoints, simplified for learning:
camelCase JSON, amounts as decimal strings, and a booked/pending split reduced
to booked transactions only.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base class: snake_case in Python, camelCase on the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Amount(ApiModel):
    currency: str = "EUR"
    amount: Decimal = Field(decimal_places=2)


class Customer(ApiModel):
    id: str
    name: str


class Account(ApiModel):
    id: str
    iban: str
    name: str
    product: str
    currency: str = "EUR"
    owner_name: str


class Balance(ApiModel):
    balance_type: str = "closingBooked"
    balance_amount: Amount


class Transaction(ApiModel):
    transaction_id: str
    booking_date: date
    transaction_amount: Amount
    counterparty_name: str
    counterparty_iban: str | None = None
    remittance_information_unstructured: str
    category: str


class AccountReference(ApiModel):
    iban: str


class AccountList(ApiModel):
    accounts: list[Account]


class BalanceResponse(ApiModel):
    account: AccountReference
    balances: list[Balance]


class BookedTransactions(ApiModel):
    booked: list[Transaction]


class TransactionResponse(ApiModel):
    account: AccountReference
    transactions: BookedTransactions


class DraftStatus(StrEnum):
    """Lifecycle of a payment draft. Later stages add expiry handling."""

    PENDING = "pending"
    CONFIRMED = "confirmed"


class PaymentDraftRequest(ApiModel):
    debtor_account_id: str
    creditor_name: str = Field(min_length=1)
    creditor_iban: str = Field(min_length=1)
    instructed_amount: Amount
    remittance_information_unstructured: str = ""

    @field_validator("instructed_amount")
    @classmethod
    def amount_must_be_positive(cls, value: Amount) -> Amount:
        if value.amount <= 0:
            raise ValueError("amount must be greater than zero")
        return value


class PaymentDraft(ApiModel):
    """A payment that was prepared but not executed until it is confirmed."""

    id: str
    status: DraftStatus
    created_at: datetime
    expires_at: datetime
    debtor_account_id: str
    creditor_name: str
    creditor_iban: str
    instructed_amount: Amount
    remittance_information_unstructured: str
