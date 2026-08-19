from datetime import date

from psycopg2.extras import execute_values

from kncompanyscraper.database import get_connection


class BenchmarkRepository:
    def get_latest_date(self, series_code: str) -> date | None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT MAX(price_date)
                    FROM benchmark_prices
                    WHERE series_code = %s
                    """,
                    (series_code,),
                )
                row = cur.fetchone()
        return row[0] if row else None

    def save_values(
        self,
        series_code: str,
        values: list[tuple[date, float]],
        *,
        return_basis: str,
        source: str,
    ) -> int:
        if return_basis not in {"price_return", "gross_total_return", "net_total_return"}:
            raise ValueError("unsupported benchmark return basis")
        if not values:
            return 0
        with get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO benchmark_prices (
                        series_code, price_date, close, return_basis, source
                    ) VALUES %s
                    ON CONFLICT (series_code, price_date) DO UPDATE SET
                        close = EXCLUDED.close,
                        return_basis = EXCLUDED.return_basis,
                        source = EXCLUDED.source,
                        fetched_at = NOW()
                    """,
                    [
                        (series_code, price_date, close, return_basis, source)
                        for price_date, close in values
                    ],
                )
        return len(values)

    def get_return_basis(self, series_code: str) -> str | None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT return_basis
                    FROM benchmark_prices
                    WHERE series_code = %s
                    ORDER BY price_date DESC
                    LIMIT 1
                    """,
                    (series_code,),
                )
                row = cur.fetchone()
        return row[0] if row else None

    def get_value_on_or_after(
        self,
        series_code: str,
        target_date: date,
        max_age_days: int | None = None,
    ) -> tuple[date, float] | None:
        return self._get_value(series_code, target_date, True, max_age_days)

    def get_value_on_or_before(
        self,
        series_code: str,
        target_date: date,
        max_age_days: int | None = None,
    ) -> tuple[date, float] | None:
        return self._get_value(series_code, target_date, False, max_age_days)

    @staticmethod
    def _get_value(series_code, target_date, after, max_age_days):
        comparator = ">=" if after else "<="
        ordering = "ASC" if after else "DESC"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT price_date, close
                    FROM benchmark_prices
                    WHERE series_code = %s AND price_date {comparator} %s
                    ORDER BY price_date {ordering}
                    LIMIT 1
                    """,
                    (series_code, target_date),
                )
                row = cur.fetchone()
        if row is None:
            return None
        distance = (
            (row[0] - target_date).days if after else (target_date - row[0]).days
        )
        if max_age_days is not None and distance > max_age_days:
            return None
        return row[0], float(row[1])
