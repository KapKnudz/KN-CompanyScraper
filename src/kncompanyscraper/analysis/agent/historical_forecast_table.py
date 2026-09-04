"""Build the deterministic historical/forecast table for a thesis card."""

from __future__ import annotations

from math import isfinite

from kncompanyscraper.analysis.policy_versions import FORWARD_SCENARIO_POLICY_VERSION


TABLE_COLUMNS = (
    "revenue",
    "gross_margin",
    "ebit_margin",
    "ebit",
    "net_debt",
    "share_count",
)


def build_historical_forecast_table(candidate, result, analysis) -> dict:
    """Combine sourced history and deterministic scenario endpoints.

    Scenario net-debt and share-count changes are full-horizon assumptions, so
    forecast rows are reported at the selected horizon rather than interpolated
    into invented annual paths. Forecast gross margin remains unavailable
    because the scenario contract does not contain an independently sourced
    gross-margin assumption.
    """
    history = candidate.full_results.get("financial_history")
    annual_reports = _field(history, "annual_reports") or ()
    comparable_reports = [
        report
        for report in annual_reports
        if not _field(report, "broken_fiscal_year")
    ][:3]

    rows = [_historical_row(report) for report in comparable_reports]
    reverse_dcf = candidate.full_results.get("reverse_dcf") or {}
    current = {
        "revenue": _field(reverse_dcf, "current_revenue"),
        "net_debt": _field(reverse_dcf, "current_net_debt"),
        "share_count": _field(reverse_dcf, "current_shares"),
    }
    horizon = result.case_horizon_months
    for bundle in result.scenario_bundles:
        rows.append(_forecast_row(bundle, current, horizon))

    limitations = [
        "Forecast gross margin unavailable: no independently sourced gross-margin assumption.",
    ]
    if not comparable_reports:
        limitations.append("Historical table rows unavailable: no comparable annual reports.")

    return {
        "status": "available" if analysis.status == "available" else "insufficient_evidence",
        "policy_version": FORWARD_SCENARIO_POLICY_VERSION,
        "columns": list(TABLE_COLUMNS),
        "case_horizon_months": horizon,
        "rows": rows,
        "limitations": limitations,
    }


def _historical_row(report) -> dict:
    source_id = _field(report, "source_id")
    revenue = _number(_field(report, "revenue"))
    gross_income = _number(_field(report, "gross_income"))
    ebit = _number(_field(report, "ebit"))
    return {
        "row_type": "historical",
        "case": None,
        "period": _field(report, "year") or _field(report, "period_end"),
        "horizon_months": None,
        "revenue": revenue,
        "gross_margin": _ratio(gross_income, revenue),
        "ebit_margin": _ratio(ebit, revenue),
        "ebit": ebit,
        "net_debt": _number(_field(report, "total_debt")),
        "share_count": _number(_field(report, "shares_outstanding")),
        "gross_margin_status": (
            "available" if _ratio(gross_income, revenue) is not None else "unavailable"
        ),
        "source_ids": [source_id] if source_id else [],
    }


def _forecast_row(bundle, current, horizon) -> dict:
    revenue = _number(current["revenue"])
    net_debt = _number(current["net_debt"])
    shares = _number(current["share_count"])
    revenue = (
        revenue * (1.0 + bundle.revenue_cagr.value) ** (horizon / 12.0)
        if revenue is not None and horizon is not None
        else None
    )
    ebit = (
        revenue * bundle.ebit_margin.value
        if revenue is not None
        else None
    )
    net_debt = (
        net_debt + bundle.net_debt_change.value
        if net_debt is not None
        else None
    )
    shares = (
        shares * (1.0 + bundle.share_count_growth.value)
        if shares is not None
        else None
    )
    source_ids = _unique(
        [
            *bundle.revenue_cagr.source_ids,
            *bundle.ebit_margin.source_ids,
            *bundle.net_debt_change.source_ids,
            *bundle.share_count_growth.source_ids,
            "deterministic:reverse_dcf:current_revenue",
            "deterministic:reverse_dcf:current_net_debt",
            "deterministic:reverse_dcf:current_shares",
        ]
    )
    return {
        "row_type": "forecast",
        "case": bundle.case,
        "period": f"+{horizon}m" if horizon is not None else None,
        "horizon_months": horizon,
        "revenue": revenue,
        "gross_margin": None,
        "ebit_margin": bundle.ebit_margin.value,
        "ebit": ebit,
        "net_debt": net_debt,
        "share_count": shares,
        "gross_margin_status": "unavailable",
        "source_ids": source_ids,
    }


def _field(value, name):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _number(value):
    return value if isinstance(value, (int, float)) and isfinite(value) else None


def _ratio(numerator, denominator):
    numerator = _number(numerator)
    denominator = _number(denominator)
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))
