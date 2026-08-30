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
    cash=30,
    eps=2.5,
    dividend_per_share=1.5,
    investing_cash_flow=-6,
    financing_cash_flow=-3,
    report_date=date(year + 1, 2, 20),
    broken_fiscal_year=False,
    )


def test_save_reports_maps_typed_columns_and_raw_payload():
    cursor = MagicMock()
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        FinancialRepository().save_reports(7, "year", [make_report()])

    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO financials" in sql
    assert "raw_payload" in sql
    assert params[:4] == (7, "year", date(2025, 12, 31), 100)
    assert params[8:16] == (10, 50, 30, 12, 2.5, 1.5, 1_000, 80)


def test_save_report_bundle_persists_all_periods_in_one_transaction():
    cursor = MagicMock()
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        FinancialRepository().save_report_bundle(
            7,
            type(
                "Bundle",
                (),
                {"annual": (make_report(),), "r12": (make_report(),), "quarterly": ()},
            )(),
        )

    assert cursor.execute.call_count == 2


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
            "raw_payload": {
                "year": 2025,
                "cash_Flow_From_Investing_Activities": -6,
            },
            "gross_income": 40,
            "operating_cash_flow": 18,
            "cash": 30,
            "eps": 2.5,
            "dividend_per_share": 1.5,
            "investing_cash_flow": -6,
            "financing_cash_flow": -3,
            "report_date": date(2026, 2, 20),
            "broken_fiscal_year": False,
        }
    ]
    connection = _mock_connection(cursor)

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
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
    assert report.cash == 30
    assert report.eps == 2.5
    assert report.dividend_per_share == 1.5
    assert report.investing_cash_flow == -6
    assert report.financing_cash_flow == -3
    assert report.report_date == date(2026, 2, 20)
    assert report.broken_fiscal_year is False


def test_latest_report_as_of_applies_publication_lag():
    repository = FinancialRepository()
    reports = [make_report(2025), make_report(2024)]

    with patch.object(repository, "_get_reports", return_value=reports):
        before_release = repository.get_latest_report_as_of(
            7,
            "year",
            date(2026, 2, 19),
            availability_lag_days=90,
        )
        after_release = repository.get_latest_report_as_of(
            7,
            "year",
            date(2026, 3, 31),
            availability_lag_days=90,
        )

    assert before_release.year == 2024
    assert after_release.year == 2025


def test_latest_report_as_of_prefers_actual_report_date_over_period_lag():
    repository = FinancialRepository()
    report = make_report(2025)

    with patch.object(repository, "_get_reports", return_value=[report]):
        available = repository.get_latest_report_as_of(
            7,
            "year",
            date(2026, 2, 21),
            availability_lag_days=365,
        )

    assert available == report
