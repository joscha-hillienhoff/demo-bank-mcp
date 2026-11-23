"""The write flow end to end: MCP tool -> bank client -> mock API."""

from datetime import date

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from demo_bank_mcp import server
from demo_bank_mcp.client import BankClient
from mock_bank.data import GIRO, generate

RECIPIENT = "DE00 DEMO 3000 0000 01"


def prepare(amount="25.00", **overrides):
    arguments = {
        "from_account_id": GIRO.id,
        "recipient_name": "Beispiel Empfaenger",
        "iban": RECIPIENT,
        "amount": amount,
        "purpose": "Test payment",
        **overrides,
    }
    return server.prepare_transfer(**arguments)


def balance(bank_client):
    return bank_client.get_balance(GIRO.id).amount


# --- the valid path ---


def test_prepare_then_confirm(bank_client, write_client):
    draft = prepare()
    assert draft.draft_id
    receipt = server.confirm_transfer(draft.draft_id)
    assert receipt.draft_id == draft.draft_id
    assert receipt.status == "confirmed"


def test_prepare_returns_a_summary_for_the_user_and_does_not_execute(bank_client, write_client):
    draft = prepare()
    assert draft.summary == (
        "25.00 EUR from Girokonto (DE00 **** **** 0101) to Beispiel Empfaenger "
        f'({RECIPIENT}), purpose: "Test payment"'
    )
    assert "explicitly agreed" in draft.next_step
    # Nothing happened to the account.
    assert balance(bank_client) == str(generate().balances[GIRO.id])


# --- what must not be possible ---


def test_confirm_without_a_draft_is_refused(write_client):
    with pytest.raises(ToolError, match="404.*Payment draft not found"):
        server.confirm_transfer("made-up-draft-id")


def test_draft_id_cannot_change_the_request_path(write_client):
    with pytest.raises(ToolError, match="404"):
        server.confirm_transfer("../../accounts")


def test_confirm_after_expiry_is_refused(bank_client, write_client, clock):
    draft = prepare()
    clock.advance(minutes=5)
    with pytest.raises(ToolError, match="410.*expired"):
        server.confirm_transfer(draft.draft_id)


def test_confirming_twice_is_refused(bank_client, write_client):
    draft = prepare()
    server.confirm_transfer(draft.draft_id)
    with pytest.raises(ToolError, match="409.*already confirmed"):
        server.confirm_transfer(draft.draft_id)


def test_amount_above_the_limit_is_reported_to_the_model(bank_client, write_client):
    with pytest.raises(ToolError, match="422.*1000.00 EUR per transfer"):
        prepare("1000.01")


def test_fourth_transfer_of_the_day_is_reported_to_the_model(bank_client, write_client):
    for _ in range(3):
        server.confirm_transfer(prepare().draft_id)
    with pytest.raises(ToolError, match="429.*3 transfers per day"):
        prepare()


def test_read_only_token_cannot_prepare_or_confirm(
    bank_app, bank_client, write_client, monkeypatch
):
    # Give the write tools the read token: the API must refuse, not the tool.
    monkeypatch.setattr(server, "_write_client", bank_client)
    with pytest.raises(ToolError, match="403.*payments:write"):
        prepare()
    with pytest.raises(ToolError, match="403.*payments:write"):
        server.confirm_transfer("any-draft-id")


# --- least privilege ---


def test_write_client_uses_the_full_token_and_read_client_the_read_token(monkeypatch):
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.setattr(server, "_write_client", None)
    monkeypatch.setenv("DEMO_BANK_READ_TOKEN", "read-token-value")
    monkeypatch.setenv("DEMO_BANK_FULL_TOKEN", "full-token-value")
    assert server.get_client()._http.headers["Authorization"] == "Bearer read-token-value"
    assert server.get_write_client()._http.headers["Authorization"] == "Bearer full-token-value"


def test_write_client_requires_the_full_token(monkeypatch):
    monkeypatch.setattr(server, "_write_client", None)
    monkeypatch.setattr(server, "load_dotenv", lambda: None)
    monkeypatch.delenv("DEMO_BANK_FULL_TOKEN")
    with pytest.raises(ToolError, match="DEMO_BANK_FULL_TOKEN"):
        server.get_write_client()


def test_read_tools_never_touch_the_write_client(bank_client, monkeypatch):
    def fail() -> BankClient:
        raise AssertionError("a read tool asked for the write client")

    monkeypatch.setattr(server, "get_write_client", fail)
    server.list_accounts()
    server.get_balance(GIRO.id)
    server.search_transactions(GIRO.id, date(2026, 1, 1), date(2026, 6, 30))


# --- what the host sees ---


async def test_tool_annotations_tell_the_host_which_tools_can_change_things():
    tools = {t.name: t.annotations for t in await server.mcp.list_tools()}
    for name in ("list_accounts", "get_balance", "search_transactions"):
        assert tools[name].readOnlyHint is True
    assert tools["prepare_transfer"].readOnlyHint is False
    assert tools["prepare_transfer"].destructiveHint is False
    assert tools["confirm_transfer"].readOnlyHint is False
    assert tools["confirm_transfer"].destructiveHint is True


async def test_descriptions_tell_the_model_to_ask_the_user():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    assert "does NOT move any money" in tools["prepare_transfer"].description
    assert "explicit confirmation" in tools["prepare_transfer"].description
    assert "explicitly agreed" in tools["confirm_transfer"].description
    assert tools["confirm_transfer"].inputSchema["required"] == ["draft_id"]
    assert set(tools["prepare_transfer"].inputSchema["required"]) == {
        "from_account_id",
        "recipient_name",
        "iban",
        "amount",
        "purpose",
    }


async def test_prepare_through_the_mcp_layer(bank_client, write_client):
    _, structured = await server.mcp.call_tool(
        "prepare_transfer",
        {
            "from_account_id": GIRO.id,
            "recipient_name": "Beispiel Empfaenger",
            "iban": RECIPIENT,
            "amount": 25.5,
            "purpose": "Test payment",
        },
    )
    assert structured["summary"].startswith("25.50 EUR from Girokonto")
    assert structured["draft_id"]
