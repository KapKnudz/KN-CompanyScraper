from dataclasses import replace

import pytest

from kncompanyscraper.analysis.valuation.reverse_dcf import (
    DcfAssumptions,
    ReverseDcfEngine,
    ReverseDcfInputs,
    UnsupportedValuationModel,
)


@pytest.fixture
def inputs() -> ReverseDcfInputs:
    return ReverseDcfInputs(
        current_price=10.0,
        shares_outstanding=100.0,
        current_revenue=1_000.0,
        net_debt=200.0,
        assumptions=DcfAssumptions(
            projection_years=5,
            revenue_growth=0.05,
            ebit_margin=0.15,
            tax_rate=0.20,
            discount_rate=0.10,
            terminal_growth=0.025,
            net_reinvestment_rate=0.02,
        ),
    )


def test_values_fcff_and_equity_per_share_deterministically(inputs):
    result = ReverseDcfEngine().value(inputs)

    assert result.projected_cash_flows[0].revenue == pytest.approx(1_050.0)
    assert result.projected_cash_flows[0].fcff == pytest.approx(105.0)
    assert result.enterprise_value == pytest.approx(1_518.8550133)
    assert result.equity_value == pytest.approx(1_318.8550133)
    assert result.value_per_share == pytest.approx(13.1885501)


def test_terminal_reinvestment_is_recomputed_from_terminal_growth_and_roic(inputs):
    assumptions = replace(inputs.assumptions, reinvestment_return=0.20)
    result = ReverseDcfEngine().value(replace(inputs, assumptions=assumptions))

    final_revenue = result.projected_cash_flows[-1].revenue
    terminal_revenue = final_revenue * (1.0 + assumptions.terminal_growth)
    terminal_nopat = (
        terminal_revenue
        * assumptions.ebit_margin
        * (1.0 - assumptions.tax_rate)
    )
    terminal_fcff = terminal_nopat * (
        1.0 - assumptions.terminal_growth / assumptions.reinvestment_return
    )

    assert result.terminal_value == pytest.approx(
        terminal_fcff / (assumptions.discount_rate - assumptions.terminal_growth)
    )


def test_explicit_reinvestment_responds_to_solved_growth_when_roic_is_available(inputs):
    assumptions = replace(inputs.assumptions, reinvestment_return=0.20)
    result = ReverseDcfEngine().value(replace(inputs, assumptions=assumptions))

    first = result.projected_cash_flows[0]
    assert first.nopat == pytest.approx(126.0)
    assert first.fcff == pytest.approx(126.0 * (1.0 - 0.05 / 0.20))


def test_growth_and_margin_follow_explicit_linear_fade_paths(inputs):
    assumptions = replace(
        inputs.assumptions,
        revenue_growth=0.10,
        revenue_growth_fade_to=0.02,
        ebit_margin_start=0.10,
        ebit_margin=0.20,
        reinvestment_return=0.25,
    )

    result = ReverseDcfEngine().value(replace(inputs, assumptions=assumptions))

    assert [point.revenue_growth for point in result.projected_cash_flows] == pytest.approx(
        [0.10, 0.08, 0.06, 0.04, 0.02]
    )
    assert [point.ebit_margin for point in result.projected_cash_flows] == pytest.approx(
        [0.10, 0.125, 0.15, 0.175, 0.20]
    )
    assert result.projected_cash_flows[0].fcff == pytest.approx(
        result.projected_cash_flows[0].nopat * (1.0 - 0.10 / 0.25)
    )
    assert result.projected_cash_flows[-1].fcff == pytest.approx(
        result.projected_cash_flows[-1].nopat * (1.0 - 0.02 / 0.25)
    )


@pytest.mark.parametrize(
    ("assumption", "known_value", "bounds"),
    [
        ("revenue_growth", 0.08, (-0.20, 0.30)),
        ("ebit_margin", 0.18, (0.01, 0.40)),
        ("terminal_growth", 0.035, (-0.02, 0.07)),
    ],
)
def test_solves_assumption_implied_by_current_price(
    inputs,
    assumption,
    known_value,
    bounds,
):
    engine = ReverseDcfEngine()
    known_assumptions = replace(inputs.assumptions, **{assumption: known_value})
    target_price = engine.value(replace(inputs, assumptions=known_assumptions)).value_per_share
    reverse_inputs = replace(inputs, current_price=target_price)

    result = engine.solve(reverse_inputs, assumption, *bounds)

    assert result.implied_assumption == pytest.approx(known_value, abs=1e-8)
    assert (result.lower_bound, result.upper_bound) == bounds
    assert result.modeled_price == pytest.approx(target_price, abs=1e-6)
    assert result.price_difference == pytest.approx(0.0, abs=1e-6)


def test_rejects_price_that_cannot_be_reached_within_bounds(inputs):
    unreachable = replace(inputs, current_price=1_000.0)

    with pytest.raises(ValueError, match="not bracketed"):
        ReverseDcfEngine().solve(unreachable, "ebit_margin", 0.01, 0.30)


@pytest.mark.parametrize("branch_id", [68, 69, 70, 75])
def test_rejects_sectors_that_require_a_different_valuation_model(inputs, branch_id):
    sector_inputs = replace(inputs, branch_id=branch_id)

    with pytest.raises(UnsupportedValuationModel):
        ReverseDcfEngine().value(sector_inputs)


def test_rejects_invalid_discount_and_terminal_growth_relationship(inputs):
    invalid = replace(
        inputs,
        assumptions=replace(
            inputs.assumptions,
            discount_rate=0.02,
            terminal_growth=0.02,
        ),
    )

    with pytest.raises(ValueError, match="discount_rate must exceed terminal_growth"):
        ReverseDcfEngine().value(invalid)
