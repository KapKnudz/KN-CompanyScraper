from datetime import date
from unittest.mock import MagicMock, patch

from kncompanyscraper.borsdata.kpi_history import KpiHistory, KpiHistoryPoint
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.repositories.valuation_repository import ValuationRepository


def _mock_connection(cursor):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


def test_save_snapshot_preserves_daily_observation():
    cursor = MagicMock()
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.valuation_repository.get_connection",
        return_value=connection,
    ):
        ValuationRepository().save_snapshot(7, 279, 54.6)

    assert cursor.execute.call_count == 2
    history_sql, history_params = cursor.execute.call_args_list[1].args
    assert "INSERT INTO kpi_snapshot_history" in history_sql
    assert history_params == (7, 279, 54.6)


def test_save_stock_prices_upserts_company_date_and_currency():
    cursor = MagicMock()
    connection = _mock_connection(cursor)
    price = StockPrice(date(2026, 8, 1), 125.5)

    with patch(
        "kncompanyscraper.repositories.valuation_repository.get_connection",
        return_value=connection,
    ):
        ValuationRepository().save_stock_prices(7, [price], "SEK")

    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO stock_prices" in sql
    assert params == (7, date(2026, 8, 1), 125.5, "SEK")


def test_get_latest_stock_price_maps_database_row():
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "price_date": date(2026, 8, 1),
        "close": 125.5,
        "currency": "SEK",
    }
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.valuation_repository.get_connection",
        return_value=connection,
    ):
        result = ValuationRepository().get_latest_stock_price(7)

    assert result == StockPrice(date(2026, 8, 1), 125.5, "SEK")


def test_save_history_persists_report_period():
    cursor = MagicMock()
    connection = _mock_connection(cursor)
    history = KpiHistory(2, [KpiHistoryPoint(2026, 18.5, period=2)])

    with patch(
        "kncompanyscraper.repositories.valuation_repository.get_connection",
        return_value=connection,
    ):
        ValuationRepository().save_history(7, history)

    sql, params = cursor.execute.call_args[0]
    assert "report_period" in sql
    assert params == (7, 2, "year", "mean", 2026, 2, 18.5)


def test_stock_price_on_date_rejects_stale_price():
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "price_date": date(2026, 7, 1),
        "close": 125.5,
        "currency": "SEK",
    }
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.valuation_repository.get_connection",
        return_value=connection,
    ):
        result = ValuationRepository().get_stock_price_on_date(
            7,
            date(2026, 8, 1),
            max_age_days=7,
        )

    assert result is None


def test_month_end_dates_select_one_final_trading_day_per_month():
    cursor = MagicMock()
    cursor.fetchall.return_value = [(date(2026, 6, 30),), (date(2026, 7, 31),)]
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.valuation_repository.get_connection",
        return_value=connection,
    ):
        result = ValuationRepository().get_backtest_month_end_dates(
            date(2026, 6, 1),
            date(2026, 7, 31),
        )

    sql, params = cursor.execute.call_args.args
    assert "MAX(price_date)" in sql
    assert "GROUP BY date_trunc('month', price_date)" in sql
    assert params == (date(2026, 6, 1), date(2026, 7, 31))
    assert result == [date(2026, 6, 30), date(2026, 7, 31)]


def test_historical_kpis_are_restricted_to_prior_years():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.valuation_repository.get_connection",
        return_value=connection,
    ):
        ValuationRepository().get_historical_as_of(7, date(2025, 8, 1))

    assert cursor.execute.call_count == 3
    for execute_call in cursor.execute.call_args_list:
        sql, params = execute_call.args
        assert "year < %s" in sql
        assert params[-1] == 2025
