from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote, unquote

from fastapi import HTTPException, Request

from .config import settings


COOKIE_NAME = "restaurantos_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7


def _signature(value: str) -> str:
    return hmac.new(
        settings.admin_token.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_session_cookie() -> str:
    expires = int(time.time()) + SESSION_TTL_SECONDS
    value = str(expires)
    return quote(f"{value}.{_signature(value)}")


def validate_session_cookie(raw_value: str | None) -> bool:
    if not raw_value:
        return False

    try:
        decoded = unquote(raw_value)
        expires_raw, signature = decoded.rsplit(".", 1)
        expires = int(expires_raw)
    except (ValueError, TypeError):
        return False

    if expires < int(time.time()):
        return False

    return hmac.compare_digest(
        signature,
        _signature(expires_raw),
    )


def require_browser_session(request: Request) -> None:
    if not validate_session_cookie(
        request.cookies.get(COOKIE_NAME)
    ):
        raise HTTPException(
            status_code=401,
            detail="Требуется вход",
        )
