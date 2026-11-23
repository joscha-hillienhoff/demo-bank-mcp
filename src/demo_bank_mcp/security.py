"""Security helpers of the MCP server.

Everything a tool returns ends up in the context of a language model, and from
there possibly in logs and chat transcripts. The server therefore hands out as
little sensitive data as possible. This module holds the helpers for that.
"""


def mask_iban(iban: str) -> str:
    """Mask an IBAN, keeping the first four and the last four characters.

    "DE00 DEMO 0000 0001 01" becomes "DE00 **** **** 0101". Values too short to
    be an IBAN are masked completely rather than echoed back.
    """
    compact = iban.replace(" ", "")
    if len(compact) < 12:
        return "****"
    return f"{compact[:4]} **** **** {compact[-4:]}"
