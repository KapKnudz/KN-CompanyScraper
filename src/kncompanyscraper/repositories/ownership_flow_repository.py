from datetime import date

from psycopg2.extras import Json, RealDictCursor

from kncompanyscraper.models.ownership_flow import (
    StoredBuybackEvent,
    StoredShortInterestSnapshot,
)
from kncompanyscraper.repositories.base_repository import BaseRepository


class OwnershipFlowRepository(BaseRepository):
    SOURCE = "borsdata"

    def save_buybacks(self, company_id: int, events: tuple) -> int:
        inserted = 0
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for event in events:
                    cur.execute(
                        """
                        INSERT INTO company_buyback_events (
                            company_id, event_date, change_shares, change_pct_raw,
                            reported_price, currency, treasury_shares,
                            treasury_shares_pct_raw, source, raw_payload
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (company_id, event_date, source) DO UPDATE SET
                            change_shares = EXCLUDED.change_shares,
                            change_pct_raw = EXCLUDED.change_pct_raw,
                            reported_price = EXCLUDED.reported_price,
                            currency = EXCLUDED.currency,
                            treasury_shares = EXCLUDED.treasury_shares,
                            treasury_shares_pct_raw = EXCLUDED.treasury_shares_pct_raw,
                            fetched_at = NOW(), raw_payload = EXCLUDED.raw_payload
                        """,
                        (
                            company_id, event.event_date, event.change_shares,
                            event.change_pct_raw, event.reported_price, event.currency,
                            event.treasury_shares, event.treasury_shares_pct_raw,
                            self.SOURCE, Json(event.raw_payload),
                        ),
                    )
                    inserted += cur.rowcount
        return inserted

    def save_short_snapshot(self, company_id: int, observation_date: date, snapshot) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO company_short_snapshots (
                        company_id, observation_date, short_pct_raw,
                        reported_holder_count, average_short_pct_raw,
                        short_value_millions_raw, average_short_value_millions_raw,
                        last_transaction_date, days_to_cover_sum,
                        days_to_cover_average, trend_1w, trend_1m, trend_3m,
                        trend_6m, source, raw_payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (company_id, observation_date, source) DO UPDATE SET
                        short_pct_raw = EXCLUDED.short_pct_raw,
                        reported_holder_count = EXCLUDED.reported_holder_count,
                        average_short_pct_raw = EXCLUDED.average_short_pct_raw,
                        short_value_millions_raw = EXCLUDED.short_value_millions_raw,
                        average_short_value_millions_raw = EXCLUDED.average_short_value_millions_raw,
                        last_transaction_date = EXCLUDED.last_transaction_date,
                        days_to_cover_sum = EXCLUDED.days_to_cover_sum,
                        days_to_cover_average = EXCLUDED.days_to_cover_average,
                        trend_1w = EXCLUDED.trend_1w, trend_1m = EXCLUDED.trend_1m,
                        trend_3m = EXCLUDED.trend_3m, trend_6m = EXCLUDED.trend_6m,
                        fetched_at = NOW(), raw_payload = EXCLUDED.raw_payload
                    """,
                    (
                        company_id, observation_date, snapshot.short_pct_raw,
                        snapshot.reported_holder_count, snapshot.average_short_pct_raw,
                        snapshot.short_value_millions_raw,
                        snapshot.average_short_value_millions_raw,
                        snapshot.last_transaction_date, snapshot.days_to_cover_sum,
                        snapshot.days_to_cover_average, snapshot.trend_1w,
                        snapshot.trend_1m, snapshot.trend_3m, snapshot.trend_6m,
                        self.SOURCE, Json(snapshot.raw_payload),
                    ),
                )

    def list_buybacks_as_of(
        self, company_id: int, as_of: date
    ) -> tuple[StoredBuybackEvent, ...]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT company_id, event_date, change_shares, change_pct_raw,
                           reported_price, currency, treasury_shares,
                           treasury_shares_pct_raw, source, raw_payload
                    FROM company_buyback_events
                    WHERE company_id = %s AND event_date <= %s
                    ORDER BY event_date DESC, source
                    """,
                    (company_id, as_of),
                )
                return tuple(
                    StoredBuybackEvent(
                        **_float_fields(
                            dict(row),
                            "change_pct_raw",
                            "reported_price",
                            "treasury_shares_pct_raw",
                        )
                    )
                    for row in cur.fetchall()
                )

    def get_latest_short_as_of(
        self, company_id: int, as_of: date
    ) -> StoredShortInterestSnapshot | None:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT company_id, observation_date, short_pct_raw,
                           reported_holder_count, average_short_pct_raw,
                           short_value_millions_raw,
                           average_short_value_millions_raw,
                           last_transaction_date, days_to_cover_sum,
                           days_to_cover_average, trend_1w, trend_1m, trend_3m,
                           trend_6m, source, raw_payload
                    FROM company_short_snapshots
                    WHERE company_id = %s AND observation_date <= %s
                    ORDER BY observation_date DESC, source
                    LIMIT 1
                    """,
                    (company_id, as_of),
                )
                row = cur.fetchone()
                return (
                    StoredShortInterestSnapshot(
                        **_float_fields(
                            dict(row),
                            "short_pct_raw",
                            "reported_holder_count",
                            "average_short_pct_raw",
                            "short_value_millions_raw",
                            "average_short_value_millions_raw",
                            "days_to_cover_sum",
                            "days_to_cover_average",
                            "trend_1w",
                            "trend_1m",
                            "trend_3m",
                            "trend_6m",
                        )
                    )
                    if row
                    else None
                )

    def get_latest_sync_coverage(self, company_id: int) -> dict:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT status, result
                    FROM jobs
                    WHERE company_id = %s AND job_type = 'borsdata_holdings_sync'
                    ORDER BY started_at DESC, id DESC
                    LIMIT 1
                    """,
                    (company_id,),
                )
                row = cur.fetchone()
        if not row:
            return {}
        return {
            "job_status": row["status"],
            **((row["result"] or {}).get("coverage") or {}),
        }

    def get_operational_coverage(self, company_ids: list[int]) -> list[dict]:
        if not company_ids:
            return []
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT c.id AS company_id, c.name, c.ticker,
                           prices.oldest AS price_oldest,
                           prices.newest AS price_newest,
                           prices.collected_at AS price_collected_at,
                           liquidity_job.status AS liquidity_job_status,
                           liquidity_job.error AS liquidity_error,
                           buybacks.oldest AS buyback_oldest,
                           buybacks.newest AS buyback_newest,
                           buybacks.collected_at AS buyback_collected_at,
                           shorts.oldest AS short_oldest,
                           shorts.newest AS short_newest,
                           shorts.collected_at AS short_collected_at,
                           holdings_job.completed_at AS holdings_completed_at,
                           holdings_job.status AS holdings_job_status,
                           holdings_job.result->'coverage' AS holdings_coverage,
                           holdings_job.error AS holdings_error
                    FROM companies c
                    LEFT JOIN LATERAL (
                        SELECT MIN(price_date) AS oldest,
                               MAX(price_date) AS newest,
                               MAX(fetched_at) AS collected_at
                        FROM stock_prices
                        WHERE company_id = c.id AND volume IS NOT NULL
                    ) prices ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT MIN(event_date) AS oldest,
                               MAX(event_date) AS newest,
                               MAX(fetched_at) AS collected_at
                        FROM company_buyback_events
                        WHERE company_id = c.id
                    ) buybacks ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT MIN(observation_date) AS oldest,
                               MAX(observation_date) AS newest,
                               MAX(fetched_at) AS collected_at
                        FROM company_short_snapshots
                        WHERE company_id = c.id
                    ) shorts ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT status, error
                        FROM jobs
                        WHERE company_id = c.id
                          AND job_type IN (
                              'borsdata_sync', 'borsdata_liquidity_backfill'
                          )
                        ORDER BY started_at DESC, id DESC
                        LIMIT 1
                    ) liquidity_job ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT status, completed_at, result, error
                        FROM jobs
                        WHERE company_id = c.id
                          AND job_type = 'borsdata_holdings_sync'
                        ORDER BY started_at DESC, id DESC
                        LIMIT 1
                    ) holdings_job ON TRUE
                    WHERE c.id = ANY(%s)
                    ORDER BY c.name, c.id
                    """,
                    (company_ids,),
                )
                return [dict(row) for row in cur.fetchall()]


def _float_fields(row: dict, *fields: str) -> dict:
    for field in fields:
        if row.get(field) is not None:
            row[field] = float(row[field])
    return row
