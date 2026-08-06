from datetime import date

from kncompanyscraper.analysis.valuation.valuation_skill import ValuationSkill
from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.borsdata.stock_price import StockPrice
from kncompanyscraper.borsdata.valuation_snapshot import ValuationSnapshot
from kncompanyscraper.models.company import Company


class FakeValuationRepository:
    def get_current(self, company_id):
        return ValuationSnapshot(
            market_cap=None,
            enterprise_value=None,
            pe=None,
            ev_ebit=None,
            ev_ebitda=None,
            pb=None,
            ps=None,
            pfcf=None,
            peg=None,
            dividend_yield=None,
        )

    def get_historical(self, company_id):
        return [], [], []

    def get_latest_stock_price(self, company_id):
        return StockPrice(date(2026, 8, 1), 10.0, "SEK")


class FakeFinancialRepository:
    def get_latest_report(self, company_id):
        return Report(
            revenue=1_000.0,
            operating_profit=100.0,
            ebit=100.0,
            ebitda=None,
            net_income=80.0,
            free_cash_flow=60.0,
            equity=500.0,
            total_assets=800.0,
            total_debt=200.0,
            shares_outstanding=100.0,
            year=2025,
            currency="SEK",
        )


def test_valuation_skill_uses_stored_price_and_report_for_raw_valuation():
    company = Company(1, "Test", "TEST", None, 42, None, currency="SEK")

    result = ValuationSkill(FakeValuationRepository(), FakeFinancialRepository()).run(company)

    assert result.raw_market_cap == 1_000.0
    assert result.raw_enterprise_value == 1_200.0
    assert result.raw_earnings_yield == 0.08
    assert result.raw_fcf_yield == 0.06
