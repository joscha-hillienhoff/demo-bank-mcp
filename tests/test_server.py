from demo_bank_mcp import server


def test_server_is_named_demo_bank():
    assert server.mcp.name == "demo-bank"


async def test_server_has_no_tools_yet():
    assert await server.mcp.list_tools() == []


def test_entry_point_is_callable():
    assert callable(server.main)
