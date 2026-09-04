from dataclasses import replace

import pytest

from kncompanyscraper.analysis.valuation.forward_scenario import (
    ForwardScenarioAnalysis,
    ForwardScenarioEngine,
    ForwardScenarioInputs,
    ForwardScenarioRanker,
    NetDebtChangeAssumption,
    RankedForwardCase,
    ScenarioBandResult,
    ScenarioBundle,
    SourcedAssumption,
)
from kncompanyscraper.analysis.policy_versions import FORWARD_SCENARIO_POLICY_VERSION


def assumption(value: float) -> SourcedAssumption:
    return SourcedAssumption(
        value=value,
        source_ids=("report:2026-q2",),
        rationale="Bounded from reported history and the stated operating mechanism.",
        mechanism="The stated operating mechanism changes the modeled driver.",
    )


def debt_change_assumption(value: float) -> NetDebtChangeAssumption:
    return NetDebtChangeAssumption(
        value=value,
        source_ids=("report:2026-q2",),
        rationale="Bounded from reported history and the stated operating mechanism.",
        mechanism=(
            "No projected net-debt change."
            if value == 0
            else "Retained cash flow and distributions drive the projected change."
        ),
        provenance_type="not_applicable" if value == 0 else "source_backed",
    )


def bundle(
    case,
    *,
    growth,
    margin,
    low_multiple,
    high_multiple,
    debt_change=0,
    share_growth=0,
    distributions=0.0,
):
    return ScenarioBundle(
        case=case,
        horizon_months=36,
        revenue_cagr=assumption(growth),
        ebit_margin=assumption(margin),
        terminal_ev_ebit_low=assumption(low_multiple),
        terminal_ev_ebit_high=assumption(high_multiple),
        net_debt_change=debt_change_assumption(debt_change),
        share_count_growth=assumption(share_growth),
        distributions_per_share=assumption(distributions),
        mechanism=f"{case} operating state is supported by reported evidence.",
    )


def valid_inputs() -> ForwardScenarioInputs:
    return ForwardScenarioInputs(
        current_price=10,
        current_revenue=100,
        current_shares=10,
        current_net_debt=0,
        historical_terminal_multiple_range=(5, 15),
        bundles=(
            bundle(
                "bear",
                growth=0.02,
                margin=0.08,
                low_multiple=6,
                high_multiple=6.5,
                debt_change=5,
                share_growth=0.05,
            ),
            bundle(
                "base",
                growth=0.05,
                margin=0.10,
                low_multiple=8.5,
                high_multiple=9,
            ),
            bundle(
                "bull",
                growth=0.12,
                margin=0.13,
                low_multiple=10.5,
                high_multiple=12,
                debt_change=-2,
                distributions=1,
            ),
        ),
        base_terminal_multiple_ceiling=10,
        bull_terminal_multiple_ceiling=15,
        demonstrated_revenue_cagr=0.20,
        demonstrated_ebit_margin=0.18,
        price_currency="SEK",
        financial_currency="SEK",
    )


def test_engine_calculates_reproducible_price_and_return_bands():
    first = ForwardScenarioEngine().analyze(valid_inputs())
    second = ForwardScenarioEngine().analyze(valid_inputs())

    assert first == second
    assert first.status == "available"
    assert first.methodology_flags == ()
    assert [band.case for band in first.bands] == ["bear", "base", "bull"]
    assert first.band("bear").high_price <= first.band("base").low_price
    assert first.band("base").high_price <= first.band("bull").low_price


def test_engine_reproduces_hand_calculated_base_price_and_return():
    result = ForwardScenarioEngine().analyze(valid_inputs())
    base = result.band("base")
    revenue = 100 * 1.05**3
    expected_price = revenue * 0.10 * 8.5 / 10
    expected_return = (expected_price / 10) ** (1 / 3) - 1

    assert base.low_price == pytest.approx(expected_price)
    assert base.low_annualized_return == pytest.approx(expected_return)


def test_engine_derives_diluted_shares_from_fractional_growth():
    inputs = valid_inputs()
    bundles = tuple(
        replace(
            item,
            share_count_growth=assumption(-0.0074),
        )
        for item in inputs.bundles
    )

    result = ForwardScenarioEngine().analyze(
        replace(inputs, current_shares=136.0, bundles=bundles)
    )

    assert result.status == "available"
    base = result.band("base")
    expected_shares = 136.0 * (1.0 - 0.0074)
    expected_price = 100 * 1.05**3 * 0.10 * 8.5 / expected_shares
    assert base.low_price == pytest.approx(expected_price)


def test_engine_flags_zero_share_and_distribution_values_based_on_missing_data():
    inputs = valid_inputs()
    missing_zero = SourcedAssumption(
        value=0.0,
        source_ids=("report:2026-q2",),
        rationale="Ownership and distribution data are missing.",
        mechanism=None,
    )
    bundles = tuple(
        replace(
            item,
            share_count_growth=missing_zero,
            distributions_per_share=missing_zero,
        )
        for item in inputs.bundles
    )

    result = ForwardScenarioEngine().analyze(replace(inputs, bundles=bundles))

    assert result.status == "available"
    assert len(result.warnings) == 6
    assert all("analyst sensitivity" in warning for warning in result.warnings)


def test_engine_rejects_missing_duplicate_and_unordered_cases():
    inputs = valid_inputs()
    missing = ForwardScenarioEngine().analyze(
        replace(inputs, bundles=inputs.bundles[:2])
    )
    duplicate = ForwardScenarioEngine().analyze(
        replace(inputs, bundles=inputs.bundles + (inputs.bundles[0],))
    )
    unordered = ForwardScenarioEngine().analyze(
        replace(
            inputs,
            bundles=(
                replace(inputs.bundles[0], terminal_ev_ebit_low=assumption(7)),
                inputs.bundles[1],
                inputs.bundles[2],
            ),
        )
    )

    assert missing.status == "insufficient_evidence"
    assert any("missing scenario bundles" in flag for flag in missing.methodology_flags)
    assert duplicate.status == "insufficient_evidence"
    assert any("exactly one bundle" in flag for flag in duplicate.methodology_flags)
    assert unordered.status == "insufficient_evidence"
    assert any("terminal multiple range" in flag for flag in unordered.methodology_flags)


def test_engine_rejects_incoherent_case_drivers():
    inputs = valid_inputs()
    result = ForwardScenarioEngine().analyze(
        replace(
            inputs,
            bundles=(
                replace(inputs.bundles[0], revenue_cagr=assumption(0.06)),
                inputs.bundles[1],
                replace(inputs.bundles[2], ebit_margin=assumption(0.09)),
            ),
        )
    )

    assert result.status == "insufficient_evidence"
    assert any("cannot improve" in flag or "cannot worsen" in flag for flag in result.methodology_flags)


def test_engine_requires_sourced_assumptions_and_mechanisms():
    inputs = valid_inputs()
    broken = replace(
        inputs.bundles[0],
        mechanism="",
        net_debt_change=NetDebtChangeAssumption(
            value=1,
            source_ids=(),
            rationale="",
            mechanism="",
            provenance_type="not_applicable",
        ),
    )
    result = ForwardScenarioEngine().analyze(
        replace(inputs, bundles=(broken, *inputs.bundles[1:]))
    )

    assert result.status == "insufficient_evidence"
    assert any("requires at least one source ID" in flag for flag in result.methodology_flags)
    assert any("requires a rationale" in flag for flag in result.methodology_flags)


def test_engine_requires_an_explicit_mechanism_for_zero_debt_change():
    inputs = valid_inputs()
    broken = replace(
        inputs.bundles[1],
        net_debt_change=NetDebtChangeAssumption(
            value=0,
            source_ids=("report:2026-q2",),
            rationale="No change is supported by the balance-sheet evidence.",
            mechanism="",
            provenance_type="not_applicable",
        ),
    )

    result = ForwardScenarioEngine().analyze(
        replace(inputs, bundles=(inputs.bundles[0], broken, inputs.bundles[2]))
    )

    assert result.status == "insufficient_evidence"
    assert "base.net_debt_change requires a mechanism" in result.methodology_flags


def test_engine_requires_not_applicable_provenance_for_zero_debt_change():
    inputs = valid_inputs()
    broken = replace(
        inputs.bundles[1],
        net_debt_change=NetDebtChangeAssumption(
            value=0,
            source_ids=("report:2026-q2",),
            rationale="No projected net-debt change.",
            mechanism="No projected net-debt change.",
            provenance_type="source_backed",
        ),
    )

    result = ForwardScenarioEngine().analyze(
        replace(inputs, bundles=(inputs.bundles[0], broken, inputs.bundles[2]))
    )

    assert result.status == "insufficient_evidence"
    assert "base.zero net_debt_change must use not_applicable provenance" in (
        result.methodology_flags
    )


def test_engine_rejects_cross_case_overlap_and_wide_base_band():
    def band(case, low_price=10, high_price=12, low_return=0, high_return=0.1):
        return ScenarioBandResult(
            case,
            36,
            low_price,
            high_price,
            low_price,
            high_price,
            low_return,
            high_return,
        )

    overlap_flags = ForwardScenarioEngine._validate_outputs(
        (
            band("bear", high_price=15),
            band("base", low_price=10),
            band("bull", low_price=20),
        )
    )
    wide_flags = ForwardScenarioEngine._validate_outputs(
        (
            band("bear"),
            band("base", low_return=-0.1, high_return=0.1),
            band("bull", low_price=20),
        )
    )

    assert any("bear_high" in flag for flag in overlap_flags)
    assert any("15 percentage points" in flag for flag in wide_flags)


def test_engine_applies_plausibility_tolerance_and_bull_lever_limit():
    inputs = replace(
        valid_inputs(),
        demonstrated_revenue_cagr=0.115,
        demonstrated_ebit_margin=0.125,
        bull_terminal_multiple_ceiling=10.0,
        historical_terminal_multiple_range=(5, 20),
    )
    within_tolerance = replace(
        inputs,
        bundles=(
            inputs.bundles[0],
            inputs.bundles[1],
            replace(
                inputs.bundles[2],
                revenue_cagr=assumption(0.121),
                ebit_margin=assumption(0.131),
                terminal_ev_ebit_high=assumption(10.4),
            ),
        ),
    )
    result = ForwardScenarioEngine().analyze(within_tolerance)
    assert result.status == "insufficient_evidence"
    assert any("combines 3" in flag for flag in result.methodology_flags)


def test_engine_uses_absolute_tolerance_for_authored_growth_and_margin():
    base_inputs = valid_inputs()
    inputs = replace(
        base_inputs,
        demonstrated_revenue_cagr=0.14595,
        demonstrated_ebit_margin=0.175,
        bundles=(
            base_inputs.bundles[0],
            replace(
                base_inputs.bundles[1],
                revenue_cagr=assumption(0.15),
                ebit_margin=assumption(0.18),
            ),
            replace(
                base_inputs.bundles[2],
                revenue_cagr=assumption(0.15),
                ebit_margin=assumption(0.18),
            ),
        ),
    )

    assert ForwardScenarioEngine().analyze(inputs).status == "available"


def test_engine_keeps_unsupported_company_models_visible():
    result = ForwardScenarioEngine().analyze(
        replace(valid_inputs(), ranking_model="bank")
    )

    assert result.status == "method_not_supported"
    assert "dedicated forward valuation method" in result.methodology_flags[0]


def test_engine_allows_bear_multiple_below_history_and_warns_when_history_is_missing():
    inputs = valid_inputs()
    inputs = replace(
        inputs,
        historical_terminal_multiple_range=(None, None),
        current_terminal_multiple=12.0,
        base_terminal_multiple_ceiling=None,
        bull_terminal_multiple_ceiling=None,
        bundles=(
            replace(
                inputs.bundles[0],
                terminal_ev_ebit_low=assumption(3.0),
                terminal_ev_ebit_high=assumption(4.0),
            ),
            inputs.bundles[1],
            inputs.bundles[2],
        ),
    )

    result = ForwardScenarioEngine().analyze(inputs)

    assert result.status == "available"
    assert any("historical terminal multiple range is unavailable" in warning for warning in result.warnings)


def analysis_with_returns(**returns) -> ForwardScenarioAnalysis:
    defaults = {
        "bear_low": -0.10,
        "bear_high": -0.05,
        "base_low": 0.12,
        "base_high": 0.16,
        "bull_low": 0.22,
        "bull_high": 0.30,
    }
    defaults.update(returns)
    bands = tuple(
        ScenarioBandResult(
            case=case,
            horizon_months=36,
            low_price=1,
            high_price=1,
            low_holding_value=1,
            high_holding_value=1,
            low_annualized_return=defaults[f"{case}_low"],
            high_annualized_return=defaults[f"{case}_high"],
        )
        for case in ("bear", "base", "bull")
    )
    return ForwardScenarioAnalysis(
        status="available",
        policy_version=FORWARD_SCENARIO_POLICY_VERSION,
        bands=bands,
    )


def ranked_case(company_id, analysis, confidence="high", **kwargs):
    return RankedForwardCase(
        company_id=company_id,
        ticker=f"C{company_id}",
        analysis=analysis,
        required_return=0.10,
        evidence_confidence=confidence,
        **kwargs,
    )


def test_ranker_is_hurdle_first_then_downside_first():
    higher_base_worse_downside = analysis_with_returns(
        base_low=0.16,
        base_high=0.20,
        bear_low=-0.45,
    )
    lower_base_better_downside = analysis_with_returns(
        base_low=0.12,
        base_high=0.16,
        bear_low=-0.15,
    )

    ranking = ForwardScenarioRanker().rank(
        [
            ranked_case(1, higher_base_worse_downside),
            ranked_case(2, lower_base_better_downside),
        ]
    )

    assert [item.company_id for item in ranking] == [2, 1]
    assert all(item.tier == "A" for item in ranking)
    assert ranking[0].bear_lower_bound == -0.15


def test_ranker_uses_bull_lower_bound_only_as_final_tie_break():
    lower_bull = analysis_with_returns(bull_low=0.22, bull_high=0.80)
    higher_bull = analysis_with_returns(bull_low=0.28, bull_high=0.31)

    ranking = ForwardScenarioRanker().rank(
        [ranked_case(1, lower_bull), ranked_case(2, higher_bull)]
    )

    assert [item.company_id for item in ranking] == [2, 1]


def test_ranker_permits_ties_and_keeps_insufficient_evidence_visible():
    near_equal_one = analysis_with_returns(base_low=0.101, base_high=0.141)
    near_equal_two = analysis_with_returns(base_low=0.109, base_high=0.149)
    insufficient = ForwardScenarioAnalysis(
        status="insufficient_evidence",
        policy_version="test",
        methodology_flags=("missing terminal multiple evidence",),
    )

    ranking = ForwardScenarioRanker().rank(
        [
            ranked_case(1, near_equal_one),
            ranked_case(2, near_equal_two),
            ranked_case(3, insufficient),
        ]
    )

    assert ranking[0].rank == ranking[1].rank
    assert ranking[0].tied and ranking[1].tied
    assert ranking[2].tier == "IE"
    assert "missing terminal multiple evidence" in ranking[2].flags


def test_ranker_blocks_unresolved_high_severity_challenge():
    ranking = ForwardScenarioRanker().rank(
        [
            ranked_case(
                1,
                analysis_with_returns(),
                unresolved_high_severity_challenge=True,
            )
        ]
    )

    assert ranking[0].tier == "RESEARCH"
    assert not ranking[0].actionable
