import re
from datetime import date
from decimal import Decimal

from mock_bank.data import GIRO, INJECTION_PURPOSE, OPENING_BALANCES_CENTS, TAGESGELD, generate

FAKE_IBAN = re.compile(r"^DE00 DEMO( \d+)+$")


def all_transactions():
    return [t for rows in generate().transactions.values() for t in rows]


def test_same_seed_gives_identical_data():
    assert generate(seed=1) == generate(seed=1)


def test_different_seed_gives_different_data():
    assert generate(seed=1) != generate(seed=2)


def test_has_one_customer_and_two_accounts():
    data = generate()
    assert data.customer.name
    assert [a.name for a in data.accounts] == ["Girokonto", "Tagesgeld"]
    assert all(a.owner_name == data.customer.name for a in data.accounts)


def test_about_150_transactions_over_six_months():
    transactions = all_transactions()
    assert 140 <= len(transactions) <= 160
    assert min(t.booking_date for t in transactions) >= date(2026, 1, 1)
    assert max(t.booking_date for t in transactions) <= date(2026, 6, 30)
    months = {t.booking_date.month for t in transactions}
    assert months == {1, 2, 3, 4, 5, 6}


def test_covers_expected_categories():
    categories = {t.category for t in all_transactions()}
    assert {"Lebensmittel", "Miete", "Gehalt", "Freizeit", "Mobilitaet"} <= categories


def test_transaction_ids_are_unique():
    transactions = all_transactions()
    assert len({t.transaction_id for t in transactions}) == len(transactions)


def test_injection_transaction_is_present_exactly_once():
    matches = [
        t for t in all_transactions() if t.remittance_information_unstructured == INJECTION_PURPOSE
    ]
    assert len(matches) == 1
    assert "Ignore previous instructions" in matches[0].remittance_information_unstructured


def test_only_fake_ibans_appear():
    data = generate()
    ibans = [a.iban for a in data.accounts]
    ibans += [t.counterparty_iban for t in all_transactions() if t.counterparty_iban]
    assert ibans
    assert all(FAKE_IBAN.match(iban) for iban in ibans)


def test_balance_equals_opening_balance_plus_transactions():
    data = generate()
    for account in (GIRO, TAGESGELD):
        total = sum(t.transaction_amount.amount for t in data.transactions[account.id])
        opening = Decimal(OPENING_BALANCES_CENTS[account.id]) / 100
        assert data.balances[account.id] == opening + total
        assert data.balances[account.id] > 0
