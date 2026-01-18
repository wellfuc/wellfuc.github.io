from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row

from app.config import settings


@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor() -> Generator[psycopg.Cursor, None, None]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
