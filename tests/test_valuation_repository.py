from datetime import date
from unittest.mock import MagicMock, patch

from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.repositories.valuation_repository import ValuationRepository


def _mock_connection(cursor):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


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
