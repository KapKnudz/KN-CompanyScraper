# tests/test_financial_skill.py
"""
Test that FinancialSkill correctly wires FinancialRepository -> FinancialMapper
-> FinancialCalculator using mock data shaped like the Borsdata API.

Run with: python -m pytest tests/test_financial_skill.py -v
"""

import copy

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

    def __init__(self, reports, r12_reports=None, quarter_reports=None):
        self.reports = reports
        self.reports_by_type = {
            "year": reports,
            "r12": r12_reports or [],
            "quarter": quarter_reports or [],
        }
        self.requested_company_ids = []

    def get_latest_report(self, company_id, period_type="year"):
        self.requested_company_ids.append((company_id, period_type))
        reports = self.reports_by_type[period_type]
        return reports[-1] if reports else None

    def get_historical_reports(self, company_id, period_type="year"):
        self.requested_company_ids.append((company_id, period_type))
        return self.reports_by_type[period_type][:-1]


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
        assert result.revenue_growth == pytest.approx((550_000_000 / 450_000_000) ** (1 / 3) - 1)
        assert result.roe == pytest.approx(55_000_000 / 180_000_000, rel=1e-6)
        assert repository.requested_company_ids == [
            (company.id, "year"),
            (company.id, "r12"),
            (company.id, "year"),
            (company.id, "quarter"),
        ]

    def test_r12_is_used_for_current_margins_while_growth_remains_annual(self):
        reports = reports_from_mock()
        r12 = copy.deepcopy(reports[-1])
        r12.revenue = 600_000_000
        repository = FakeFinancialRepository(reports, r12_reports=[r12])

        result = FinancialSkill(repository).run(make_company())

        assert result.operating_margin == pytest.approx(70_000_000 / 600_000_000)
        assert result.revenue_growth == pytest.approx(
            (550_000_000 / 450_000_000) ** (1 / 3) - 1
        )

    def test_run_returns_none_when_no_reports(self):
        repository = FakeFinancialRepository([])
        skill = FinancialSkill(repository)
        company = make_company()

        result = skill.run(company)

        assert result is None

    def test_name_is_financial(self):
        skill = FinancialSkill(FakeFinancialRepository([]))
        assert skill.name == "financial"
