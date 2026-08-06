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
    )
    HISTORICAL_KPIS = (KpiIds.PE, KpiIds.EV_EBIT, KpiIds.PB)

    def save_snapshot(self, company_id: int, kpi_id: int, value: float | None) -> None:
        query = """
            INSERT INTO kpi_snapshots (company_id, kpi_id, value, fetched_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (company_id, kpi_id)
            DO UPDATE SET value = EXCLUDED.value, fetched_at = NOW()
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (company_id, kpi_id, value))

    def save_history(
        self,
        company_id: int,
        history: KpiHistory,
        period_type: str = "year",
        price_type: str = "mean",
    ) -> None:
        query = """
            INSERT INTO kpi_history (
                company_id, kpi_id, period_type, price_type, year, value, fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (company_id, kpi_id, period_type, price_type, year)
            DO UPDATE SET value = EXCLUDED.value, fetched_at = NOW()
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                for point in history.values:
                    cur.execute(
                        query,
                        (company_id, history.kpi_id, period_type, price_type, point.year, point.value),
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

    def get_historical(self, company_id: int) -> tuple[list[float], list[float], list[float]]:
        return tuple(self._history(company_id, kpi_id) for kpi_id in self.HISTORICAL_KPIS)

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

    def _history(self, company_id: int, kpi_id: int) -> list[float]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT value
                    FROM kpi_history
                    WHERE company_id = %s AND kpi_id = %s
                      AND period_type = 'year' AND price_type = 'mean'
                    ORDER BY year
                    """,
                    (company_id, kpi_id),
                )
                return [float(row[0]) for row in cur.fetchall()]
