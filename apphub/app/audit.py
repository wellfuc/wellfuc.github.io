from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.auth import User
from app.db import get_cursor


def log_action(
    *,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: int | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    ip: str | None,
) -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log
                (actor_email, action, entity_type, entity_id, before_json, after_json, ip, created_at)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                actor.email,
                action,
                entity_type,
                entity_id,
                json.dumps(before) if before is not None else None,
                json.dumps(after) if after is not None else None,
                ip,
                datetime.now(timezone.utc),
            ),
        )
