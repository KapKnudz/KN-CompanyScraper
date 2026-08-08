from datetime import date
from unittest.mock import MagicMock, patch

from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.repositories.financial_repository import FinancialRepository


def _mock_connection(cursor):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


def make_report(year=2025):
    return Report(
        revenue=100,
        operating_profit=20,
        ebit=20,
        ebitda=25,
        net_income=15,
        free_cash_flow=12,
        equity=50,
        total_assets=80,
        total_debt=10,
        shares_outstanding=1_000,
        year=year,
        period=1,
        period_end=date(year, 12, 31),
        currency="SEK",
        raw_payload={"year": year},
        gross_income=40,
        operating_cash_flow=18,
    )


def test_save_reports_maps_typed_columns_and_raw_payload():
    cursor = MagicMock()
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.financial_repository.get_connection",
        return_value=connection,
    ):
        FinancialRepository().save_reports(7, "year", [make_report()])

    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO financials" in sql
    assert "raw_payload" in sql
    assert params[:4] == (7, "year", date(2025, 12, 31), 100)
    assert params[8:13] == (10, 50, 12, 1_000, 80)


def test_latest_report_is_loaded_by_local_company_id():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "revenue": 100,
            "operating_profit": 20,
            "ebit": 20,
            "ebitda": None,
            "net_income": 15,
            "free_cash_flow": 12,
            "equity": 50,
            "total_assets": 80,
            "debt": 10,
            "shares_outstanding": 1_000,
            "report_year": 2025,
            "report_period": 1,
            "period_end": date(2025, 12, 31),
            "currency": "SEK",
            "raw_payload": {"year": 2025},
            "gross_income": 40,
            "operating_cash_flow": 18,
        }
    ]
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.financial_repository.get_connection",
        return_value=connection,
    ):
        report = FinancialRepository().get_latest_report(7)

    _, params = cursor.execute.call_args[0]
    assert params == (7, "year", 1)
    assert report.year == 2025
    assert report.total_debt == 10
    assert report.ebitda is None
    assert report.gross_income == 40
    assert report.operating_cash_flow == 18
