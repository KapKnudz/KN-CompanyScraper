from __future__ import annotations
from contextlib import contextmanager
from typing import Any, Generator

from psycopg2.extras import RealDictCursor
from psycopg2.extras import Json
from kncompanyscraper.database import get_connection

class BaseRepository:
    def __init__(self, connection=None):
        self._connection = connection

    @contextmanager
    def _get_conn(self) -> Generator[Any, None, None]:
        if self._connection:
            yield self._connection
        else:
            with get_connection() as conn:
                yield conn

    @contextmanager
    def _get_cursor(self, factory=None) -> Generator[Any, None, None]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=factory) as cur:
                yield cur

    @contextmanager
    def _get_dict_cursor(self) -> Generator[RealDictCursor, None, None]:
        with self._get_cursor(factory=RealDictCursor) as cur:
            yield cur

    def _insert_or_get(
        self,
        insert_sql: str,
        insert_params: tuple,
        select_sql: str,
        select_params: tuple,
    ) -> tuple[int, bool]:
        """Run an idempotent insert and return ``(id, inserted)``."""
        with self._get_cursor() as cur:
            cur.execute(insert_sql, insert_params)
            row = cur.fetchone()
            if row:
                return row[0], True
            cur.execute(select_sql, select_params)
            return cur.fetchone()[0], False

    def merge_inputs_summary_once(
        self,
        table: str,
        row_id: int,
        payload: dict,
        guard_key: str,
    ) -> None:
        """Merge provenance into a snapshot once, preserving idempotency."""
        if table not in {"ranking_runs"}:
            raise ValueError("unsupported inputs-summary table")
        with self._get_cursor() as cur:
            cur.execute(
                f"""
                UPDATE {table}
                SET inputs_summary = COALESCE(inputs_summary, '{{}}'::JSONB) || %s
                WHERE id = %s
                  AND snapshot_month IS NOT NULL
                  AND NOT (
                      COALESCE(inputs_summary, '{{}}'::JSONB) ? %s
                  )
                """,
                (Json(payload), row_id, guard_key),
            )
