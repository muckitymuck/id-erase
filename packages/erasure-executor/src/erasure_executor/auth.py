from __future__ import annotations

import hmac

from fastapi import HTTPException, status


def require_bearer(authorization: str | None, expected_token: str) -> None:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization must be Bearer")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, expected_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
