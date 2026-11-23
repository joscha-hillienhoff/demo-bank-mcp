"""Bearer-token authentication with scopes for the mock bank API.

Tokens are mock values read from the environment (see .env.example). There is
no OAuth flow: a token is simply looked up and mapped to a set of scopes.
Unset or empty variables define no token, so nothing is accepted by default.
"""

import os
from collections.abc import Callable

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ACCOUNTS_READ = "accounts:read"
PAYMENTS_WRITE = "payments:write"

_bearer = HTTPBearer(auto_error=False)


def token_scopes() -> dict[str, set[str]]:
    """Map each configured mock token to its scopes."""
    load_dotenv()  # Does not override variables that are already set.
    configured = {
        os.environ.get("DEMO_BANK_READ_TOKEN"): {ACCOUNTS_READ},
        os.environ.get("DEMO_BANK_FULL_TOKEN"): {ACCOUNTS_READ, PAYMENTS_WRITE},
    }
    return {token: scopes for token, scopes in configured.items() if token}


def require_scope(scope: str) -> Callable[..., None]:
    """Build a dependency: 401 without a valid token, 403 if the scope is missing."""

    def check(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="Missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        scopes = token_scopes().get(credentials.credentials)
        if scopes is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if scope not in scopes:
            raise HTTPException(status_code=403, detail=f"Missing scope: {scope}")

    return check
