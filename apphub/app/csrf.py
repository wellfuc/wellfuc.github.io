from __future__ import annotations

import secrets
from fastapi import HTTPException, Request
from fastapi.responses import Response

CSRF_COOKIE = "apphub_csrf"
CSRF_HEADER = "X-CSRF-Token"


def csrf_token(request: Request) -> str:
    token = request.cookies.get(CSRF_COOKIE)
    if not token:
        token = secrets.token_urlsafe(32)
    return token


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        secure=True,
        samesite="lax",
        path="/",
    )


async def validate_csrf(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get(CSRF_HEADER)
    form_token = None
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/x-www-form-urlencoded") or content_type.startswith(
        "multipart/form-data"
    ):
        form = await request.form()
        form_token = form.get("csrf_token")
    if not cookie_token or not (header_token or form_token):
        raise HTTPException(status_code=403, detail="Missing CSRF token")
    provided = header_token or form_token
    if not secrets.compare_digest(cookie_token, provided):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
