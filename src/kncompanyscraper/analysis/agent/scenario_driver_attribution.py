"""Deterministic Shapley attribution for forward-scenario holding values."""

from __future__ import annotations

from itertools import combinations
from math import factorial, isclose, isfinite

from kncompanyscraper.analysis.policy_versions import (
    SCENARIO_DRIVER_ATTRIBUTION_POLICY_VERSION,
)


DRIVERS = (
    "revenue_cagr",
    "ebit_margin",
    "net_debt_change",
    "share_count_growth",
    "distributions_per_share",
    "terminal_ev_ebit",
)


def build_scenario_driver_attribution(candidate, result) -> dict:
    """Attribute each scenario endpoint versus a deterministic no-change state."""
    history = candidate.full_results.get("financial_history")
    current_report = _current_report(history)
    current_ebit_margin = _ratio(
        _field(current_report, "ebit") if current_report else None,
        _field(current_report, "revenue") if current_report else None,
    )
    reverse_dcf = candidate.full_results.get("reverse_dcf") or {}
    valuation = candidate.full_results.get("valuation") or {}
    current = {
        "revenue": _number(_field(reverse_dcf, "current_revenue")),
        "shares": _number(_field(reverse_dcf, "current_shares")),
        "net_debt": _number(_field(reverse_dcf, "current_net_debt")),
        "ebit_margin": current_ebit_margin,
        "terminal_ev_ebit": _first_number(
            _field(valuation, "raw_ev_ebit"), _field(valuation, "ev_ebit")
        ),
    }
    missing = [
        name
        for name, value in (
            ("current_revenue", current["revenue"]),
            ("current_shares", current["shares"]),
            ("current_net_debt", current["net_debt"]),
            ("current_ebit_margin", current["ebit_margin"]),
            ("current_ev_ebit", current["terminal_ev_ebit"]),
        )
        if value is None
    ]
    if missing:
        return {
            "status": "unassessable",
            "policy_version": SCENARIO_DRIVER_ATTRIBUTION_POLICY_VERSION,
            "method": "shapley",
            "attribution_unit": "holding_value_per_share",
            "reference": None,
            "endpoints": [],
            "limitations": [
                "Scenario driver attribution unavailable: missing "
                + ", ".join(missing)
                + "."
            ],
        }

    reference_drivers = {
        "revenue_cagr": 0.0,
        "ebit_margin": current["ebit_margin"],
        "net_debt_change": 0.0,
        "share_count_growth": 0.0,
        "distributions_per_share": 0.0,
        "terminal_ev_ebit": current["terminal_ev_ebit"],
    }
    reference_value = _holding_value(
        current,
        reference_drivers,
        result.case_horizon_months,
    )
    endpoints = []
    for bundle in result.scenario_bundles:
        for endpoint_name, multiple in (
            ("low", bundle.terminal_ev_ebit_low),
            ("high", bundle.terminal_ev_ebit_high),
        ):
            target_drivers = {
                "revenue_cagr": bundle.revenue_cagr.value,
                "ebit_margin": bundle.ebit_margin.value,
                "net_debt_change": bundle.net_debt_change.value,
                "share_count_growth": bundle.share_count_growth.value,
                "distributions_per_share": bundle.distributions_per_share.value,
                "terminal_ev_ebit": multiple.value,
            }
            target_value = _holding_value(
                current,
                target_drivers,
                result.case_horizon_months,
            )
            contributions = _shapley_contributions(
                current,
                reference_drivers,
                target_drivers,
                result.case_horizon_months,
            )
            change = target_value - reference_value
            contribution_sum = sum(contributions.values())
            endpoints.append(
                {
                    "case": bundle.case,
                    "endpoint": endpoint_name,
                    "reference_holding_value": reference_value,
                    "target_holding_value": target_value,
                    "holding_value_change": change,
                    "contributions": contributions,
                    "contribution_sum": contribution_sum,
                    "reconciles": isclose(
                        contribution_sum,
                        change,
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    ),
                    "source_ids": list(multiple.source_ids),
                    "driver_source_ids": {
                        "revenue_cagr": list(bundle.revenue_cagr.source_ids),
                        "ebit_margin": list(bundle.ebit_margin.source_ids),
                        "net_debt_change": list(bundle.net_debt_change.source_ids),
                        "share_count_growth": list(bundle.share_count_growth.source_ids),
                        "distributions_per_share": list(
                            bundle.distributions_per_share.source_ids
                        ),
                        "terminal_ev_ebit": list(multiple.source_ids),
                    },
                }
            )

    return {
        "status": "available",
        "policy_version": SCENARIO_DRIVER_ATTRIBUTION_POLICY_VERSION,
        "method": "shapley",
        "attribution_unit": "holding_value_per_share",
        "reference": {
            "state": "no_change",
            "drivers": reference_drivers,
            "holding_value": reference_value,
            "source_ids": _reference_source_ids(current_report, valuation),
        },
        "endpoints": endpoints,
        "limitations": [
            "Attribution is additive for holding value per share; annualized-return attribution is not additive and is not reported."
        ],
    }


def _shapley_contributions(current, reference, target, horizon):
    count = len(DRIVERS)
    contributions = {driver: 0.0 for driver in DRIVERS}
    denominator = factorial(count)
    for driver in DRIVERS:
        others = [item for item in DRIVERS if item != driver]
        for size in range(count):
            weight = factorial(size) * factorial(count - size - 1) / denominator
            for subset in combinations(others, size):
                before = dict(reference)
                before.update({item: target[item] for item in subset})
                after = dict(before)
                after[driver] = target[driver]
                contributions[driver] += weight * (
                    _holding_value(current, after, horizon)
                    - _holding_value(current, before, horizon)
                )
    return contributions


def _holding_value(current, drivers, horizon):
    years = horizon / 12.0
    revenue = current["revenue"] * (1.0 + drivers["revenue_cagr"]) ** years
    ebit = revenue * drivers["ebit_margin"]
    equity_value = ebit * drivers["terminal_ev_ebit"] - (
        current["net_debt"] + drivers["net_debt_change"]
    )
    price = equity_value / (
        current["shares"] * (1.0 + drivers["share_count_growth"])
    )
    return price + drivers["distributions_per_share"]


def _current_report(history):
    latest_r12 = _field(history, "latest_r12")
    if (
        latest_r12 is not None
        and not _field(latest_r12, "broken_fiscal_year")
        and _ratio(_field(latest_r12, "ebit"), _field(latest_r12, "revenue"))
        is not None
    ):
        return latest_r12
    return next(
        (
            report
            for report in (_field(history, "annual_reports") or ())
            if not _field(report, "broken_fiscal_year")
            and _ratio(_field(report, "ebit"), _field(report, "revenue")) is not None
        ),
        None,
    )


def _reference_source_ids(current_report, valuation):
    source_ids = []
    if current_report is not None and _field(current_report, "source_id"):
        source_ids.append(_field(current_report, "source_id"))
    multiple_name = (
        "raw_ev_ebit"
        if _field(valuation, "raw_ev_ebit") is not None
        else "ev_ebit"
    )
    source_ids.append(f"deterministic:valuation:{multiple_name}")
    source_ids.extend(
        [
            "deterministic:reverse_dcf:current_revenue",
            "deterministic:reverse_dcf:current_net_debt",
            "deterministic:reverse_dcf:current_shares",
        ]
    )
    return list(dict.fromkeys(source_ids))


def _field(value, name):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _number(value):
    return value if isinstance(value, (int, float)) and isfinite(value) else None


def _first_number(*values):
    return next((value for value in values if _number(value) is not None), None)


def _ratio(numerator, denominator):
    numerator = _number(numerator)
    denominator = _number(denominator)
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator
