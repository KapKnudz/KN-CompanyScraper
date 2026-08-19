from __future__ import annotations
from contextlib import contextmanager
from typing import Any, Generator

from psycopg2.extras import RealDictCursor
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
