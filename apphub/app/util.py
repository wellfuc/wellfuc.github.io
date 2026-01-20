from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from fastapi import Request


_slug_re = re.compile(r"[^a-z0-9-]")


def slugify(value: str) -> str:
    value = value.strip().lower().replace(" ", "-")
    value = _slug_re.sub("", value)
    return value


def parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [tag.strip() for tag in raw.split(",") if tag.strip()]


def format_dt(dt: datetime | None) -> str:
    if not dt:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M")


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def ensure_filter_in(values: Iterable[str]) -> str:
    cleaned = [v for v in values if v]
    return ",".join(cleaned)
