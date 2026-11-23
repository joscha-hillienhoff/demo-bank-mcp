import pytest

from demo_bank_mcp.security import mask_iban


@pytest.mark.parametrize(
    ("iban", "masked"),
    [
        ("DE00 DEMO 0000 0001 01", "DE00 **** **** 0101"),
        ("DE00DEMO0000000101", "DE00 **** **** 0101"),
        ("DE00 DEMO 9999", "DE00 **** **** 9999"),
        ("DE00", "****"),
        ("", "****"),
    ],
)
def test_mask_iban(iban, masked):
    assert mask_iban(iban) == masked
