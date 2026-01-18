from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from app.db import get_cursor


@dataclass
class User:
    id: int
    email: str
    display_name: str | None
    role: str


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def get_identity(request: Request) -> User:
    email = request.headers.get("X-Auth-Email")
    if not email:
        raise HTTPException(status_code=401, detail="Missing identity header")
    email = _normalize_email(email)
    display_name = request.headers.get("X-Auth-Preferred-Username") or request.headers.get(
        "X-Auth-User"
    )
    now = datetime.now(timezone.utc)
    with get_cursor() as cur:
        cur.execute("SELECT id, email, display_name, role FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE users SET last_login = %s, display_name = COALESCE(%s, display_name) WHERE id = %s",
                (now, display_name, row["id"]),
            )
            return User(
                id=row["id"],
                email=row["email"],
                display_name=row["display_name"],
                role=row["role"],
            )
        cur.execute(
            "INSERT INTO users (email, display_name, role, created_at, last_login) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (email, display_name, "viewer", now, now),
        )
        user_id = cur.fetchone()["id"]
        return User(id=user_id, email=email, display_name=display_name, role="viewer")
