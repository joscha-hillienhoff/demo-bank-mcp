"""Entry point of the Demo Bank MCP server.

MCP concept: a server exposes capabilities to an MCP host over a transport.
There are three kinds, and each has a different "controller":

- tools      (@mcp.tool)     are called by the model, when it decides to.
- resources  (@mcp.resource) are read by the application, as context.
- prompts    (@mcp.prompt)   are picked by the user, as reusable templates.

FastMCP is the high-level API of the official Python SDK. It handles the
JSON-RPC 2.0 protocol, capability negotiation and the transport, so this module
only registers capabilities. The decorated functions stay plain Python
functions, which is why the tests can call them directly.

Important for stdio: the host talks to this process over stdin/stdout, so
nothing in this module may print to stdout. Use stderr for diagnostics.
"""

import calendar
import os
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Annotated

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from demo_bank_mcp.client import (
    DEFAULT_BASE_URL,
    Account,
    Balance,
    BankApiError,
    BankClient,
    Transaction,
)
from demo_bank_mcp.security import mask_iban

# The name is what hosts show to users and send back in the initialize handshake.
mcp = FastMCP("demo-bank")

# Search results are capped so that one tool call cannot flood the model's context.
MAX_TRANSACTIONS = 50

_client: BankClient | None = None


def get_client() -> BankClient:
    """The bank API client, created on first use.

    The server only ever holds the read-only token (scope accounts:read), so
    even a misbehaving model cannot move money through this server.
    """
    global _client
    if _client is None:
        load_dotenv()
        token = os.environ.get("DEMO_BANK_READ_TOKEN")
        if not token:
            raise ToolError("The server is not configured: DEMO_BANK_READ_TOKEN is not set.")
        _client = BankClient.from_token(
            token, os.environ.get("DEMO_BANK_API_URL", DEFAULT_BASE_URL)
        )
    return _client


def _call_bank[T](call: Callable[[], T]) -> T:
    """Run a bank API call and turn API errors into messages the model can act on."""
    try:
        return call()
    except BankApiError as error:
        # A ToolError becomes a tool result with isError=true. The model sees the
        # message and can react (e.g. fix an id), unlike a protocol-level failure.
        raise ToolError(f"Bank API error {error.status_code}: {error.detail}") from error
    except OSError as error:  # httpx connection errors derive from OSError
        raise ToolError("The bank API is not reachable. Is the mock API running?") from error


# --- Tools -------------------------------------------------------------------
#
# @mcp.tool() registers the function as a tool. FastMCP builds what the host
# receives from the function itself:
#   - name:         the function name
#   - description:  the docstring (this is what the model reads to decide when
#                   to call the tool, so it is written for the model)
#   - inputSchema:  a JSON Schema generated from the type hints. Parameter
#                   descriptions come from Annotated[..., Field(description=...)];
#                   a parameter without a default is "required"
#   - outputSchema: a JSON Schema generated from the return annotation


AccountId = Annotated[str, Field(description='Account id from list_accounts, e.g. "acc-giro".')]


@mcp.tool()
def list_accounts() -> list[Account]:
    """List the customer's bank accounts.

    Call this first: the other tools need an account id from this list.
    IBANs are masked.
    """
    accounts = _call_bank(get_client().list_accounts)
    return [a.model_copy(update={"iban": mask_iban(a.iban)}) for a in accounts]


@mcp.tool()
def get_balance(account_id: AccountId) -> Balance:
    """Get the current booked balance of one account."""
    balance = _call_bank(lambda: get_client().get_balance(account_id))
    return balance.model_copy(update={"iban": mask_iban(balance.iban)})


class TransactionSearch(BaseModel):
    """Matching transactions, newest first, capped at MAX_TRANSACTIONS."""

    total_matches: int
    returned: int
    transactions: list[Transaction]


@mcp.tool()
def search_transactions(
    account_id: AccountId,
    date_from: Annotated[date, Field(description="First booking date to include (YYYY-MM-DD).")],
    date_to: Annotated[date, Field(description="Last booking date to include (YYYY-MM-DD).")],
    min_amount: Annotated[
        float | None,
        Field(description="Only transactions whose absolute amount is at least this, in EUR."),
    ] = None,
    text: Annotated[
        str | None,
        Field(description="Only transactions whose counterparty or purpose contains this text."),
    ] = None,
    category: Annotated[
        str | None, Field(description='Only this category, e.g. "Lebensmittel" or "Miete".')
    ] = None,
) -> TransactionSearch:
    """Search booked transactions of one account within a period.

    Amounts are negative for money going out and positive for money coming in.
    Text and category matching ignore case. All filters are combined with AND.
    """
    transactions = _call_bank(lambda: get_client().get_transactions(account_id, date_from, date_to))

    matches = [
        t
        for t in transactions
        if (min_amount is None or abs(Decimal(t.amount)) >= Decimal(str(min_amount)))
        and (text is None or _contains(t, text))
        and (category is None or t.category.casefold() == category.casefold())
    ]
    shown = [
        t.model_copy(
            update={
                "counterparty_iban": mask_iban(t.counterparty_iban) if t.counterparty_iban else None
            }
        )
        for t in matches[:MAX_TRANSACTIONS]
    ]
    return TransactionSearch(total_matches=len(matches), returned=len(shown), transactions=shown)


def _contains(transaction: Transaction, text: str) -> bool:
    needle = text.casefold()
    return needle in transaction.counterparty.casefold() or needle in transaction.purpose.casefold()


# --- Resources ---------------------------------------------------------------
#
# A resource is read-only content addressed by a URI. The host lists them with
# resources/list and fetches one with resources/read. Unlike a tool, the model
# does not call it: the application decides when to load it into the context.

FEES = """\
# Demo Bank price and service list

All prices are fictional.

| Service | Price |
| --- | --- |
| Girokonto (current account) | 4.90 EUR per month |
| Tagesgeld (savings account) | 0.00 EUR per month |
| Card payment in euro | free |
| Cash withdrawal at Demo Bank ATMs | free |
| Cash withdrawal at other ATMs | 3.00 EUR |
| SEPA transfer | free |
| Instant transfer | 0.50 EUR |
| Paper statement | 1.50 EUR per statement |
| Replacement card | 10.00 EUR |

The Tagesgeld account earns 2.0 % interest per year, credited monthly.
"""

FAQ = """\
# Demo Bank FAQ

## Transfer limits
- A single transfer is limited to 1,000 EUR.
- At most 3 transfers per day can be made.
- A prepared transfer expires after 5 minutes if it is not confirmed.

## Cut-off times (Berlin time, business days)
- SEPA transfers submitted before 15:00 are executed the same day.
- Transfers submitted later are executed on the next business day.
- Instant transfers are executed within seconds, around the clock.

## Account information
- Balances show the booked balance. Card payments can take up to two days to be booked.
- Transactions are available for the last 6 months.
"""


@mcp.resource(
    "bank://fees",
    title="Demo Bank price and service list",
    description="Prices of accounts, cards, cash withdrawals and transfers.",
    mime_type="text/markdown",
)
def fees() -> str:
    return FEES


@mcp.resource(
    "bank://faq",
    title="Demo Bank FAQ",
    description="Transfer limits and cut-off times.",
    mime_type="text/markdown",
)
def faq() -> str:
    return FAQ


# --- Prompts -----------------------------------------------------------------
#
# A prompt is a reusable template that the user picks explicitly (hosts show it
# like a slash command). The host asks for it with prompts/get, passing the
# arguments, and receives ready-made messages to send to the model.


@mcp.prompt()
def monthly_summary(
    month: Annotated[str, Field(description='The month as YYYY-MM, e.g. "2026-03".')],
) -> str:
    """Summarise income and spending of one month across all accounts."""
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise ValueError(f"month must be formatted as YYYY-MM, got {month!r}") from None
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])

    return (
        f"Write a summary of my finances for {first:%B %Y} "
        f"({first.isoformat()} to {last.isoformat()}).\n\n"
        "1. Call list_accounts to find my accounts.\n"
        f"2. For each account, call search_transactions with date_from={first.isoformat()} "
        f"and date_to={last.isoformat()}.\n"
        "3. Report total income, total spending and the balance change per account.\n"
        "4. Break spending down by category, largest category first.\n"
        "5. Point out unusual transactions."
    )


def main() -> None:
    """Run the server over stdio, the transport used by local MCP hosts."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
