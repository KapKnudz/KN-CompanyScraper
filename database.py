from contextlib import contextmanager

import psycopg2

from scraper import config


@contextmanager
def get_connection():
    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()