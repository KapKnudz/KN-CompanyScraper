from dataclasses import replace

from kncompanyscraper.analysis.valuation.forward_scenario import (
    EndpointResult,
    ForwardScenarioAnalysis,
    ForwardScenarioEngine,
    ForwardScenarioInputs,
    ForwardScenarioRanker,
    RankedForwardCase,
    ScenarioEndpoint,
    SourcedAssumption,
)


def assumption(value: float, *, exception: str | None = None) -> SourcedAssumption:
    return SourcedAssumption(
        value=value,
        source_ids=("report:2026-q2",),
        rationale="Bounded from reported history and the stated operating mechanism.",
        guardrail_exception=exception,
    )


def endpoint(
    kind,
    side,
    *,
    growth,
    margin,
    multiple,
    debt,
    shares,
    distributions=0.0,
):
    return ScenarioEndpoint(
        kind=kind,
        side=side,
        horizon_months=36,
        revenue_cagr=assumption(growth),
        ebit_margin=assumption(margin),
        terminal_ev_ebit=assumption(multiple),
        net_debt=assumption(debt),
        net_debt_change=assumption(debt),
        share_count_growth=assumption(shares / 10 - 1),
        distributions_per_share=assumption(distributions),
    )


def valid_inputs() -> ForwardScenarioInputs:
    base_low = endpoint(
        "base", "low", growth=0.05, margin=0.10, multiple=9, debt=0, shares=10
    )
    base_high = endpoint(
        "base", "high", growth=0.10, margin=0.12, multiple=10, debt=0, shares=10
    )
    return ForwardScenarioInputs(
        current_price=10,
        current_revenue=100,
        current_shares=10,
        current_net_debt=0,
        terminal_multiple_guardrail=(5, 15),
        endpoints=(
            endpoint(
                "bear_multiple_compression",
                "low",
                growth=0.05,
                margin=0.10,
                multiple=6,
                debt=0,
                shares=10,
            ),
            endpoint(
                "bear_multiple_compression",
                "high",
                growth=0.10,
                margin=0.12,
                multiple=7,
                debt=0,
                shares=10,
            ),
            endpoint(
                "bear_fundamental_impairment",
                "low",
                growth=0.00,
                margin=0.07,
                multiple=6,
                debt=5,
                shares=11,
            ),
            endpoint(
                "bear_fundamental_impairment",
                "high",
                growth=0.03,
                margin=0.08,
                multiple=7,
                debt=3,
                shares=10.5,
            ),
            base_low,
            base_high,
            endpoint(
                "bull",
                "low",
                growth=0.12,
                margin=0.13,
                multiple=11,
                debt=-2,
                shares=10,
                distributions=1,
            ),
            endpoint(
                "bull",
                "high",
                growth=0.15,
                margin=0.15,
                multiple=12,
                debt=-5,
                shares=10,
                distributions=1,
            ),
        ),
    )


def test_engine_calculates_reproducible_coherent_bundles():
    engine = ForwardScenarioEngine()

    first = engine.analyze(valid_inputs())
    second = engine.analyze(valid_inputs())

    assert first == second
    assert first.status == "available"
    assert first.methodology_flags == ()
    assert first.result("bear_multiple_compression_low").annualized_return < first.result(
        "base_low"
    ).annualized_return
    assert first.result("bear_fundamental_impairment_low").annualized_return < first.result(
        "base_low"
    ).annualized_return


def test_engine_derives_betsson_style_share_count_from_fractional_growth():
    inputs = valid_inputs()
    endpoints = tuple(
        replace(endpoint, share_count_growth=assumption(-0.0074))
        for endpoint in inputs.endpoints
    )

    result = ForwardScenarioEngine().analyze(
        replace(inputs, current_shares=136.0, endpoints=endpoints)
    )

    assert result.status == "available"
    base = result.result("base_low")
    expected_shares = 136.0 * (1.0 - 0.0074)
    assert base.value_per_share_at_horizon == (
        base.equity_value_at_horizon / expected_shares
    )


def test_engine_exposes_coherence_failures_as_insufficient_evidence():
    inputs = valid_inputs()
    endpoints = list(inputs.endpoints)
    compression = endpoints[0]
    endpoints[0] = replace(
        compression,
        net_debt=assumption(1),
        net_debt_change=assumption(1),
    )

    result = ForwardScenarioEngine().analyze(replace(inputs, endpoints=tuple(endpoints)))

    assert result.status == "insufficient_evidence"
    assert any("must copy base operating" in flag for flag in result.methodology_flags)


def test_engine_requires_sourced_assumptions_and_flags_guardrail_exceptions():
    inputs = valid_inputs()
    endpoints = list(inputs.endpoints)
    bull = endpoints[-1]
    endpoints[-1] = replace(
        bull,
        terminal_ev_ebit=SourcedAssumption(
            value=16,
            source_ids=("peer:premium",),
            rationale="Documented structural premium.",
            guardrail_exception="Sourced peer premium after a business-mix change.",
        ),
    )

    result = ForwardScenarioEngine().analyze(replace(inputs, endpoints=tuple(endpoints)))

    assert result.status == "available"
    assert "guardrail exception" in result.warnings[0]

    endpoints[-1] = replace(
        endpoints[-1],
        revenue_cagr=SourcedAssumption(0.15, (), "Unsupported"),
    )
    invalid = ForwardScenarioEngine().analyze(replace(inputs, endpoints=tuple(endpoints)))
    assert invalid.status == "insufficient_evidence"
    assert any("requires at least one source ID" in flag for flag in invalid.methodology_flags)


def test_engine_keeps_unsupported_company_models_visible():
    result = ForwardScenarioEngine().analyze(replace(valid_inputs(), ranking_model="bank"))

    assert result.status == "method_not_supported"
    assert "dedicated forward valuation method" in result.methodology_flags[0]


def analysis_with_returns(**returns) -> ForwardScenarioAnalysis:
    defaults = {
        "bear_multiple_compression_low": -0.10,
        "bear_multiple_compression_high": -0.05,
        "bear_fundamental_impairment_low": -0.15,
        "bear_fundamental_impairment_high": -0.08,
        "base_low": 0.12,
        "base_high": 0.16,
        "bull_low": 0.22,
        "bull_high": 0.30,
    }
    defaults.update(returns)
    results = tuple(
        EndpointResult(
            key=key,
            horizon_months=36,
            revenue_at_horizon=1,
            ebit_at_horizon=1,
            enterprise_value_at_horizon=1,
            equity_value_at_horizon=1,
            value_per_share_at_horizon=1,
            holding_value_per_share=1,
            annualized_return=value,
        )
        for key, value in defaults.items()
    )
    return ForwardScenarioAnalysis(
        status="available",
        policy_version="test",
        results=results,
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
        bear_fundamental_impairment_low=-0.45,
    )
    lower_base_better_downside = analysis_with_returns(
        base_low=0.12,
        base_high=0.16,
        bear_fundamental_impairment_low=-0.15,
    )

    ranking = ForwardScenarioRanker().rank(
        [
            ranked_case(1, higher_base_worse_downside),
            ranked_case(2, lower_base_better_downside),
        ]
    )

    assert [item.company_id for item in ranking] == [2, 1]
    assert all(item.tier == "A" for item in ranking)


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
