from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.models.company import Company


def test_company_exposes_separate_listing_and_financial_currencies():
    company = Company(
        1,
        "Test AB",
        "TEST",
        None,
        42,
        None,
        currency="SEK",
        stock_price_currency="NOK",
        report_currency="EUR",
    )

    assert company.listing_currency == "NOK"
    assert company.financial_currency == "EUR"


def test_company_currency_legacy_fallback_is_listing_currency():
    company = Company(1, "Test AB", "TEST", None, 42, None, currency="SEK")

    assert company.listing_currency == "SEK"
    assert company.financial_currency == "SEK"


def test_report_uses_ebit_as_canonical_operating_profit():
    report = Report(
        revenue=100,
        operating_profit=70,
        ebit=50,
        ebitda=None,
        net_income=None,
        free_cash_flow=None,
        equity=None,
        total_assets=None,
        total_debt=None,
        shares_outstanding=None,
    )

    assert report.ebit == 50
    assert report.operating_profit == 50
