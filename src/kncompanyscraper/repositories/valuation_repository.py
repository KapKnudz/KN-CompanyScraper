from datetime import date

from psycopg2.extras import RealDictCursor

from kncompanyscraper.borsdata.kpi_history import KpiHistory
from kncompanyscraper.borsdata.valuation_snapshot import ValuationSnapshot
from kncompanyscraper.borsdata.kpi_ids import KpiIds
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.database import get_connection


class ValuationRepository:

    CURRENT_KPIS = (
        KpiIds.MARKET_CAP,
        KpiIds.ENTERPRISE_VALUE,
        KpiIds.PE,
        KpiIds.EV_EBIT,
        KpiIds.EV_EBITDA,
        KpiIds.PB,
        KpiIds.PS,
        KpiIds.PFCF,
        KpiIds.PEG,
        KpiIds.DIVIDEND_YIELD,
        *KpiIds.GENERAL_FUNDAMENTAL_KPIS,
    )
    HISTORICAL_KPIS = (KpiIds.PE, KpiIds.EV_EBIT, KpiIds.PB)

    def save_snapshot(self, company_id: int, kpi_id: int, value: float | None) -> None:
        current_query = """
            INSERT INTO kpi_snapshots (company_id, kpi_id, value, fetched_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (company_id, kpi_id)
            DO UPDATE SET value = EXCLUDED.value, fetched_at = NOW()
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(current_query, (company_id, kpi_id, value))
                cur.execute(
                    """
                    INSERT INTO kpi_snapshot_history (
                        company_id, kpi_id, observation_date, value, fetched_at
                    )
                    VALUES (%s, %s, CURRENT_DATE, %s, NOW())
                    ON CONFLICT (company_id, kpi_id, observation_date)
                    DO UPDATE SET value = EXCLUDED.value, fetched_at = NOW()
                    """,
                    (company_id, kpi_id, value),
                )

    def save_history(
        self,
        company_id: int,
        history: KpiHistory,
        period_type: str = "year",
        price_type: str = "mean",
    ) -> None:
        query = """
            INSERT INTO kpi_history (
                company_id, kpi_id, period_type, price_type, year,
                report_period, value, fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (company_id, kpi_id, period_type, price_type, year)
            DO UPDATE SET
                report_period = EXCLUDED.report_period,
                value = EXCLUDED.value,
                fetched_at = NOW()
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                for point in history.values:
                    cur.execute(
                        query,
                        (
                            company_id,
                            history.kpi_id,
                            period_type,
                            price_type,
                            point.year,
                            point.period,
                            point.value,
                        ),
                    )

    def save_stock_prices(
        self,
        company_id: int,
        prices: list[StockPrice],
        currency: str | None = None,
    ) -> None:
        query = """
            INSERT INTO stock_prices (company_id, price_date, close, currency, fetched_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (company_id, price_date)
            DO UPDATE SET
                close = EXCLUDED.close,
                currency = EXCLUDED.currency,
                fetched_at = NOW()
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                for price in prices:
                    cur.execute(
                        query,
                        (company_id, price.date, price.close, price.currency or currency),
                    )

    def get_latest_stock_price(self, company_id: int) -> StockPrice | None:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT price_date, close, currency
                    FROM stock_prices
                    WHERE company_id = %s
                    ORDER BY price_date DESC
                    LIMIT 1
                    """,
                    (company_id,),
                )
                row = cur.fetchone()

        if row is None:
            return None
        return StockPrice(
            date=row["price_date"],
            close=float(row["close"]),
            currency=row["currency"],
        )

    def get_stock_price_on_date(
        self,
        company_id: int,
        target_date: date,
        max_age_days: int | None = None,
    ) -> StockPrice | None:
        """Return the closest stock price on or before *target_date*."""
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT price_date, close, currency
                    FROM stock_prices
                    WHERE company_id = %s AND price_date <= %s
                    ORDER BY price_date DESC
                    LIMIT 1
                    """,
                    (company_id, target_date),
                )
                row = cur.fetchone()
        if row is None:
            return None
        if max_age_days is not None and (target_date - row["price_date"]).days > max_age_days:
            return None
        return StockPrice(
            date=row["price_date"],
            close=float(row["close"]),
            currency=row["currency"],
        )

    def get_snapshot_history_as_of(
        self,
        company_id: int,
        kpi_ids: tuple[int, ...],
        target_date: date,
    ) -> dict[int, float | None]:
        """Return the most recent snapshot value per KPI on or before *target_date*."""
        if not kpi_ids:
            return {}
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (kpi_id) kpi_id, value
                    FROM kpi_snapshot_history
                    WHERE company_id = %s AND kpi_id = ANY(%s)
                      AND observation_date <= %s
                    ORDER BY kpi_id, observation_date DESC
                    """,
                    (company_id, list(kpi_ids), target_date),
                )
                return {
                    row["kpi_id"]: float(row["value"]) if row["value"] is not None else None
                    for row in cur.fetchall()
                }

    def get_month_end_price_dates(
        self,
        company_id: int,
        min_date: date | None = None,
        max_date: date | None = None,
    ) -> list[date]:
        """Distinct month-end price dates for *company_id*, oldest → newest."""
        query = """
            SELECT MAX(price_date) AS price_date
            FROM stock_prices
            WHERE company_id = %s
        """
        params: list = [company_id]
        if min_date is not None:
            query += " AND price_date >= %s"
            params.append(min_date)
        if max_date is not None:
            query += " AND price_date <= %s"
            params.append(max_date)
        query += " GROUP BY date_trunc('month', price_date) ORDER BY price_date"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return [row[0] for row in cur.fetchall()]

    def get_backtest_month_end_dates(
        self,
        min_date: date,
        max_date: date,
    ) -> list[date]:
        """Return one final stored trading date for each calendar month."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT MAX(price_date) AS price_date
                    FROM stock_prices
                    WHERE price_date BETWEEN %s AND %s
                    GROUP BY date_trunc('month', price_date)
                    ORDER BY price_date
                    """,
                    (min_date, max_date),
                )
                return [row[0] for row in cur.fetchall()]

    def get_current(self, company_id: int) -> ValuationSnapshot:
        values = self._snapshot_values(company_id)
        return ValuationSnapshot(
            market_cap=values.get(KpiIds.MARKET_CAP),
            enterprise_value=values.get(KpiIds.ENTERPRISE_VALUE),
            pe=values.get(KpiIds.PE),
            ev_ebit=values.get(KpiIds.EV_EBIT),
            ev_ebitda=values.get(KpiIds.EV_EBITDA),
            pb=values.get(KpiIds.PB),
            ps=values.get(KpiIds.PS),
            pfcf=values.get(KpiIds.PFCF),
            peg=values.get(KpiIds.PEG),
            dividend_yield=values.get(KpiIds.DIVIDEND_YIELD),
        )

    def get_sector_current(self, company_id: int, branch_id: int | None) -> dict[int, float | None]:
        if branch_id == 75:
            allowed = set(KpiIds.PROPERTY_KPIS)
        elif branch_id in (68, 69, 70):
            allowed = set(KpiIds.BANK_KPIS)
        else:
            return {}
        return {
            kpi_id: value
            for kpi_id, value in self._snapshot_values(company_id).items()
            if kpi_id in allowed
        }

    def get_snapshot_history(
        self,
        company_id: int,
        kpi_ids: tuple[int, ...],
    ) -> dict[int, list[tuple[date, float]]]:
        """Return dated observations for *kpi_ids*, ordered oldest → newest.

        Each value is a ``(observation_date, value)`` pair.  KPIs with no
        history are omitted from the returned dict.
        """
        if not kpi_ids:
            return {}
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT kpi_id, observation_date, value
                    FROM kpi_snapshot_history
                    WHERE company_id = %s AND kpi_id = ANY(%s)
                    ORDER BY kpi_id, observation_date
                    """,
                    (company_id, list(kpi_ids)),
                )
                rows = cur.fetchall()

        result: dict[int, list[tuple[date, float]]] = {}
        for row in rows:
            kpi_id = row["kpi_id"]
            obs_date = row["observation_date"]
            value = float(row["value"]) if row["value"] is not None else None
            if value is not None:
                result.setdefault(kpi_id, []).append((obs_date, value))
        return result

    def get_general_fundamentals(self, company_id: int) -> dict[int, float | None]:
        allowed = set(KpiIds.GENERAL_FUNDAMENTAL_KPIS)
        return {
            kpi_id: value
            for kpi_id, value in self._snapshot_values(company_id).items()
            if kpi_id in allowed
        }

    def get_historical(self, company_id: int) -> tuple[list[float], list[float], list[float]]:
        return tuple(self._history(company_id, kpi_id) for kpi_id in self.HISTORICAL_KPIS)

    def get_historical_as_of(
        self,
        company_id: int,
        as_of: date,
    ) -> tuple[list[float], list[float], list[float]]:
        """Return annual KPI histories completed before the observation year."""
        return tuple(
            self._history(company_id, kpi_id, before_year=as_of.year)
            for kpi_id in self.HISTORICAL_KPIS
        )

    def _snapshot_values(self, company_id: int) -> dict[int, float | None]:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT kpi_id, value FROM kpi_snapshots WHERE company_id = %s",
                    (company_id,),
                )
                return {
                    row["kpi_id"]: float(row["value"]) if row["value"] is not None else None
                    for row in cur.fetchall()
                }

    def _history(
        self,
        company_id: int,
        kpi_id: int,
        before_year: int | None = None,
    ) -> list[float]:
        query = """
            SELECT value
            FROM kpi_history
            WHERE company_id = %s AND kpi_id = %s
              AND period_type = 'year' AND price_type = 'mean'
        """
        params: list = [company_id, kpi_id]
        if before_year is not None:
            query += " AND year < %s"
            params.append(before_year)
        query += " ORDER BY year"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return [float(row[0]) for row in cur.fetchall()]
