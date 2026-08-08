from unittest.mock import MagicMock

from kncompanyscraper.analysis.financial.financial_result import FinancialResult
from kncompanyscraper.analysis.fundamental_kpi_skill import FundamentalKpiSkill
from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
from kncompanyscraper.analysis.sector_kpi_skill import SectorKpiSkill
from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult
from kncompanyscraper.borsdata.kpi_ids import KpiIds
from kncompanyscraper.models.company import Company


def _company(branch_id):
    return Company(1, "Sector Co", "SECTOR", None, 42, None, branch_id=branch_id)


def _financial():
    return FinancialResult(
        operating_margin=0.20,
        net_margin=0.15,
        fcf_margin=-0.50,
        revenue_growth=0.12,
        ebit_growth=0.50,
        net_income_growth=0.10,
        roe=0.15,
        roa=0.02,
        debt_to_equity=4.0,
        revenue_growth_years=3,
        net_income_growth_years=3,
    )


def _valuation():
    return ValuationResult(
        pe=10.0,
        ev_ebit=20.0,
        ev_ebitda=None,
        pb=1.2,
        ps=None,
        pfcf=-12.0,
        peg=None,
        earnings_yield=0.10,
        free_cash_flow_yield=-0.08,
        pe_vs_5y_avg=0.8,
        ev_ebit_vs_5y_avg=1.0,
        pb_vs_5y_avg=0.8,
        pe_percentile=20.0,
        ev_ebit_percentile=80.0,
        dividend_yield=5.0,
    )


def test_property_model_uses_property_metrics_instead_of_fcf_and_net_debt():
    company = _company(75)
    score = RankingEngine().rank(
        [company],
        {
            1: {
                "financial": _financial(),
                "valuation": _valuation(),
                "sector_kpis": {
                    KpiIds.PROPERTY_OCCUPANCY: 96.0,
                    KpiIds.PROPERTY_INTEREST_COVERAGE: 3.2,
                    KpiIds.PROPERTY_LTV: 38.0,
                    KpiIds.PROPERTY_NAV_DISCOUNT: 20.0,
                    KpiIds.PROPERTY_PRICE_TO_INCOME: 11.0,
                },
            }
        },
    ).scores[0]

    assert score.ranking_model == "property"
    assert score.quality_score > 70
    assert score.balance_sheet_score > 70
    assert not any("FCF" in item for item in score.negatives)
    assert not any("D/E" in item for item in score.negatives)


def test_property_model_emits_sector_risk_flags():
    company = _company(75)
    score = RankingEngine().rank(
        [company],
        {
            1: {
                "financial": _financial(),
                "valuation": _valuation(),
                "sector_kpis": {
                    KpiIds.PROPERTY_OCCUPANCY: 88.0,
                    KpiIds.PROPERTY_INTEREST_COVERAGE: 1.2,
                    KpiIds.PROPERTY_LTV: 60.0,
                    KpiIds.PROPERTY_NAV_DISCOUNT: 10.0,
                    KpiIds.PROPERTY_PRICE_TO_INCOME: 23.0,
                },
            }
        },
    ).scores[0]

    assert {"low_occupancy", "weak_interest_coverage", "high_ltv", "nav_premium"} <= set(
        score.flags
    )


def test_bank_model_uses_capital_and_liquidity_instead_of_debt_equity():
    company = _company(68)
    score = RankingEngine().rank(
        [company],
        {
            1: {
                "financial": _financial(),
                "valuation": _valuation(),
                "sector_kpis": {
                    KpiIds.BANK_COST_INCOME: 36.0,
                    KpiIds.BANK_CREDIT_LOSSES: 0.10,
                    KpiIds.BANK_CET1: 19.0,
                    KpiIds.BANK_CAPITAL_ADEQUACY: 23.0,
                    KpiIds.BANK_LCR: 190.0,
                },
            }
        },
    ).scores[0]

    assert score.ranking_model == "bank"
    assert score.quality_score > 70
    assert score.balance_sheet_score > 80
    assert not any("D/E" in item for item in score.negatives)


def test_bank_model_emits_capital_liquidity_and_credit_flags():
    company = _company(69)
    score = RankingEngine().rank(
        [company],
        {
            1: {
                "financial": _financial(),
                "valuation": _valuation(),
                "sector_kpis": {
                    KpiIds.BANK_COST_INCOME: 65.0,
                    KpiIds.BANK_CREDIT_LOSSES: 0.90,
                    KpiIds.BANK_CET1: 11.0,
                    KpiIds.BANK_CAPITAL_ADEQUACY: 16.0,
                    KpiIds.BANK_LCR: 90.0,
                },
            }
        },
    ).scores[0]

    assert {
        "poor_cost_efficiency",
        "high_credit_losses",
        "weak_capital",
        "weak_liquidity",
    } <= set(score.flags)


def test_missing_sector_balance_data_does_not_claim_balance_sheet_risk():
    company = _company(70)
    score = RankingEngine().rank(
        [company],
        {1: {"financial": _financial(), "valuation": _valuation(), "sector_kpis": {}}},
    ).scores[0]

    assert score.ranking_model == "bank"
    assert "balance_sheet_risk" not in score.flags
    assert "low_data_quality" in score.flags
    assert score.rank_eligible is False
    assert "incomplete_data" in score.flags


def test_sector_kpi_skill_reads_current_values_for_company_branch():
    repository = MagicMock()
    repository.get_sector_current.return_value = {KpiIds.PROPERTY_LTV: 45.0}
    company = _company(75)

    result = SectorKpiSkill(repository).run(company)

    assert result == {KpiIds.PROPERTY_LTV: 45.0}
    repository.get_sector_current.assert_called_once_with(1, 75)


def test_fundamental_kpi_skill_reads_current_values():
    repository = MagicMock()
    repository.get_general_fundamentals.return_value = {
        KpiIds.ROIC: 15.0,
        KpiIds.NET_DEBT_EBITDA: 1.2,
    }
    company = _company(None)

    result = FundamentalKpiSkill(repository).run(company)

    assert result[KpiIds.ROIC] == 15.0
    repository.get_general_fundamentals.assert_called_once_with(1)


def test_ineligible_sector_company_sorts_after_eligible_company():
    property_company = _company(75)
    general_company = Company(2, "Weak General", "WEAK", None, 43, None)
    ranking = RankingEngine().rank(
        [property_company, general_company],
        {
            1: {
                "financial": _financial(),
                "valuation": _valuation(),
                "sector_kpis": {KpiIds.PROPERTY_OCCUPANCY: 99.0},
            },
            2: {"financial": _financial(), "valuation": _valuation()},
        },
    )

    assert ranking.scores[0].company_id == 2
    assert ranking.scores[0].rank_eligible
    assert not ranking.scores[1].rank_eligible


def test_property_total_gives_balance_sheet_more_weight_than_growth():
    company = _company(75)
    score = RankingEngine().rank(
        [company],
        {
            1: {
                "financial": _financial(),
                "valuation": _valuation(),
                "sector_kpis": {
                    KpiIds.PROPERTY_OCCUPANCY: 95.0,
                    KpiIds.PROPERTY_INTEREST_COVERAGE: 1.0,
                    KpiIds.PROPERTY_LTV: 65.0,
                    KpiIds.PROPERTY_NAV_DISCOUNT: -30.0,
                    KpiIds.PROPERTY_PRICE_TO_INCOME: 8.0,
                },
            }
        },
    ).scores[0]

    expected = (
        score.quality_score * 0.25
        + score.growth_score * 0.15
        + score.valuation_score * 0.30
        + score.balance_sheet_score * 0.30
    )
    assert score.total_score == round(expected, 1)
