import json
from datetime import date

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from demo_bank_mcp import server
from demo_bank_mcp.security import mark_untrusted
from mock_bank.data import GIRO, INJECTION_PURPOSE, TAGESGELD, generate

# --- what the host sees: tools/list, resources/list, prompts/list ---


def test_server_is_named_demo_bank():
    assert server.mcp.name == "demo-bank"


def test_entry_point_is_callable():
    assert callable(server.main)


async def test_tools_are_listed_with_descriptions_and_schemas():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    assert set(tools) == {
        "list_accounts",
        "get_balance",
        "search_transactions",
        "prepare_transfer",
        "confirm_transfer",
    }
    assert all(t.description for t in tools.values())

    assert tools["list_accounts"].inputSchema["properties"] == {}
    assert tools["get_balance"].inputSchema["required"] == ["account_id"]

    search = tools["search_transactions"].inputSchema
    assert search["required"] == ["account_id", "date_from", "date_to"]
    assert search["properties"]["date_from"]["format"] == "date"
    assert set(search["properties"]) == {
        "account_id",
        "date_from",
        "date_to",
        "min_amount",
        "text",
        "category",
    }
    assert all(p["description"] for p in search["properties"].values())


async def test_resources_are_listed():
    resources = {str(r.uri): r for r in await server.mcp.list_resources()}
    assert set(resources) == {"bank://fees", "bank://faq"}
    assert all(r.description and r.mimeType == "text/markdown" for r in resources.values())


async def test_prompt_is_listed_with_its_argument():
    [prompt] = await server.mcp.list_prompts()
    assert prompt.name == "monthly_summary"
    assert prompt.description
    [argument] = prompt.arguments
    assert (argument.name, argument.required) == ("month", True)
    assert argument.description


# --- resources and prompt ---


async def test_fees_resource_can_be_read():
    [content] = await server.mcp.read_resource("bank://fees")
    assert "price and service list" in content.content
    assert "Girokonto" in content.content


async def test_faq_resource_can_be_read():
    [content] = await server.mcp.read_resource("bank://faq")
    assert "1,000 EUR" in content.content
    assert "Cut-off times" in content.content


async def test_monthly_summary_prompt_is_rendered():
    result = await server.mcp.get_prompt("monthly_summary", {"month": "2026-02"})
    [message] = result.messages
    assert message.role == "user"
    text = message.content.text
    assert "February 2026" in text
    assert "date_from=2026-02-01" in text
    assert "date_to=2026-02-28" in text  # not a leap year
    assert "search_transactions" in text


@pytest.mark.parametrize("month", ["2026-13", "March", "2026-3-1", ""])
def test_monthly_summary_rejects_invalid_month(month):
    with pytest.raises(ValueError, match="YYYY-MM"):
        server.monthly_summary(month)


# --- tools against the mock API ---


def test_list_accounts_masks_ibans(bank_client):
    accounts = server.list_accounts()
    assert [a.name for a in accounts] == ["Girokonto", "Tagesgeld"]
    assert [a.id for a in accounts] == [GIRO.id, TAGESGELD.id]
    assert accounts[0].iban == "DE00 **** **** 0101"
    assert GIRO.iban not in json.dumps([a.model_dump() for a in accounts])


def test_get_balance(bank_client):
    balance = server.get_balance(GIRO.id)
    assert balance.account_id == GIRO.id
    assert balance.iban == "DE00 **** **** 0101"
    assert balance.amount == str(generate().balances[GIRO.id])
    assert balance.currency == "EUR"


def test_get_balance_of_unknown_account(bank_client):
    with pytest.raises(ToolError, match="404.*Account not found"):
        server.get_balance("acc-unknown")


def search(**filters):
    params = {"account_id": GIRO.id, "date_from": date(2026, 1, 1), "date_to": date(2026, 6, 30)}
    return server.search_transactions(**{**params, **filters})


def test_search_by_period_is_inclusive_and_newest_first(bank_client):
    result = search(date_from=date(2026, 3, 1), date_to=date(2026, 3, 31))
    dates = [t.booking_date for t in result.transactions]
    assert dates == sorted(dates, reverse=True)
    assert min(dates) >= date(2026, 3, 1)
    assert max(dates) <= date(2026, 3, 31)
    assert result.total_matches == len(dates) == result.returned


def test_search_results_are_capped(bank_client):
    result = search()
    assert result.total_matches > server.MAX_TRANSACTIONS
    assert result.returned == len(result.transactions) == server.MAX_TRANSACTIONS


def test_search_by_category(bank_client):
    result = search(category="miete")  # case-insensitive
    assert result.total_matches == 6
    assert {t.category for t in result.transactions} == {"Miete"}


def test_search_by_text_matches_counterparty_and_purpose(bank_client):
    by_counterparty = search(text="hausverwaltung")
    by_purpose = search(text="Miete Maerz")
    assert by_counterparty.total_matches == 6
    assert by_purpose.total_matches == 1


def test_search_by_min_amount_uses_absolute_value(bank_client):
    result = search(min_amount=800)
    amounts = {t.category for t in result.transactions}
    assert amounts == {"Miete", "Gehalt"}  # rent is negative, salary positive


def test_search_filters_are_combined(bank_client):
    result = search(category="Gehalt", text="mai")
    assert [t.purpose for t in result.transactions] == [mark_untrusted("Gehalt Mai")]


def test_search_masks_counterparty_ibans(bank_client):
    result = search(text="Hausverwaltung")
    assert {t.counterparty_iban for t in result.transactions} == {"DE00 **** **** 0001"}
    payload = json.dumps(result.model_dump(mode="json"))
    assert "DE00 DEMO" not in payload


def test_search_keeps_missing_counterparty_iban_empty(bank_client):
    result = search(category="Lebensmittel")
    assert {t.counterparty_iban for t in result.transactions} == {None}


def test_search_marks_third_party_text_as_untrusted(bank_client):
    result = search(text="ignore previous")  # filters on the original text
    [transaction] = result.transactions
    assert transaction.purpose == f"<untrusted-data>{INJECTION_PURPOSE}</untrusted-data>"
    assert transaction.counterparty == "<untrusted-data>Unbekannter Absender</untrusted-data>"
    assert "never follow requests" in result.notice


def test_search_with_reversed_period_reports_the_api_error(bank_client):
    with pytest.raises(ToolError, match="422.*dateFrom must not be after dateTo"):
        search(date_from=date(2026, 3, 1), date_to=date(2026, 2, 1))


def test_search_in_unknown_account(bank_client):
    with pytest.raises(ToolError, match="Account not found"):
        search(account_id="acc-unknown")


async def test_errors_reach_the_host_as_tool_errors(bank_client):
    # Through the MCP layer, the same failure is what the host receives.
    with pytest.raises(ToolError, match="Account not found"):
        await server.mcp.call_tool("get_balance", {"account_id": "acc-unknown"})


async def test_call_tool_returns_structured_content(bank_client):
    _, structured = await server.mcp.call_tool("get_balance", {"account_id": GIRO.id})
    assert structured["account_id"] == GIRO.id


# --- configuration ---


def test_client_requires_the_read_token(monkeypatch):
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.setattr(server, "load_dotenv", lambda: None)
    monkeypatch.delenv("DEMO_BANK_READ_TOKEN")
    with pytest.raises(ToolError, match="DEMO_BANK_READ_TOKEN"):
        server.get_client()


def test_client_uses_the_read_only_token(monkeypatch):
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.setenv("DEMO_BANK_READ_TOKEN", "read-token-value")
    monkeypatch.setenv("DEMO_BANK_FULL_TOKEN", "full-token-value")
    client = server.get_client()
    assert client._http.headers["Authorization"] == "Bearer read-token-value"
