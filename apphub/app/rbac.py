from __future__ import annotations

from fastapi import HTTPException

from app.auth import User

ROLE_ORDER = {"viewer": 1, "editor": 2, "admin": 3}


def require_role(user: User, minimum: str) -> None:
    if ROLE_ORDER.get(user.role, 0) < ROLE_ORDER.get(minimum, 0):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
