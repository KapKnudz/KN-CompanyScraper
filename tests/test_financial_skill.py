# tests/test_financial_skill.py
"""
Test that FinancialSkill correctly wires FinancialRepository -> FinancialMapper
-> FinancialCalculator using mock data shaped like the Borsdata API.

Run with: python -m pytest tests/test_financial_skill.py -v
"""

import pytest

from kncompanyscraper.analysis.financial.financial_skill import FinancialSkill
from kncompanyscraper.models.company import Company
from .test_analysis import reports_from_mock


class FakeFinancialRepository:
    """
    Stands in for FinancialRepository so the test doesn't depend on
    BorsdataClient (which is still stubbed). Returns the same mock reports
    tests/test_analysis.py already uses.
    """

    def __init__(self, reports):
        self.reports = reports

    def get_latest_report(self, instrument_id):
        return self.reports[-1] if self.reports else None

    def get_historical_reports(self, instrument_id):
        return self.reports[:-1]


def make_company(borsdata_id=3):
    return Company(
        id=1,
        name="Test Company",
        ticker="TEST",
        mfn_slug=None,
        borsdata_id=borsdata_id,
        last_updated=None,
    )


class TestFinancialSkill:

    def test_run_returns_financial_result_with_correct_values(self):
        reports = reports_from_mock()
        repository = FakeFinancialRepository(reports)
        skill = FinancialSkill(repository)
        company = make_company()

        result = skill.run(company)

        assert result.operating_margin == pytest.approx(70_000_000 / 550_000_000, rel=1e-6)
        assert result.net_margin == pytest.approx(55_000_000 / 550_000_000, rel=1e-6)
        assert result.revenue_growth == pytest.approx(30_000_000 / 520_000_000, rel=1e-6)
        assert result.roe == pytest.approx(55_000_000 / 180_000_000, rel=1e-6)

    def test_run_returns_none_when_no_reports(self):
        repository = FakeFinancialRepository([])
        skill = FinancialSkill(repository)
        company = make_company()

        result = skill.run(company)

        assert result is None

    def test_name_is_financial(self):
        skill = FinancialSkill(FakeFinancialRepository([]))
        assert skill.name == "financial"