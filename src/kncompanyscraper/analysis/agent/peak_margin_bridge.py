"""Build the deterministic gross-to-EBIT and peak-margin bridge."""

from __future__ import annotations

from math import isfinite

from kncompanyscraper.analysis.policy_versions import FORWARD_SCENARIO_POLICY_VERSION


def build_peak_margin_bridge(candidate, result) -> dict:
    """Compare the current reported margin with the defensible observed peak.

    Forecast gross margin is intentionally not estimated. Scenario EBIT margins
    are included as supplied assumptions, while their gross-to-EBIT spread stays
    unavailable unless a separately sourced forecast gross margin is added to the
    contract.
    """
    history = candidate.full_results.get("financial_history")
    annual_reports = [
        report
        for report in (_field(history, "annual_reports") or ())
        if not _field(report, "broken_fiscal_year")
    ]
    current_report = _current_report(history, annual_reports)
    observed_reports = [*annual_reports]
    latest_r12 = _field(history, "latest_r12")
    if latest_r12 is not None and not _field(latest_r12, "broken_fiscal_year"):
        observed_reports.append(latest_r12)
    observed_reports = [report for report in observed_reports if _margin(report) is not None]
    peak_report = max(observed_reports, key=lambda report: _margin(report), default=None)

    current = _observation(current_report) if current_report is not None else None
    peak = _observation(peak_report) if peak_report is not None else None
    current_ebit_margin = _field(current, "ebit_margin") if current else None
    peak_ebit_margin = _field(peak, "ebit_margin") if peak else None
    bridge = {
        "margin_runway": (
            peak_ebit_margin - current_ebit_margin
            if current_ebit_margin is not None and peak_ebit_margin is not None
            else None
        ),
        "gross_margin_change": _difference(
            _field(peak, "gross_margin") if peak else None,
            _field(current, "gross_margin") if current else None,
        ),
        "gross_to_ebit_spread_change": _difference(
            _field(peak, "gross_to_ebit_spread") if peak else None,
            _field(current, "gross_to_ebit_spread") if current else None,
        ),
    }
    forecast = [
        {
            "case": bundle.case,
            "ebit_margin": bundle.ebit_margin.value,
            "gross_margin": None,
            "gross_to_ebit_spread": None,
            "gross_margin_status": "unavailable",
            "source_ids": list(bundle.ebit_margin.source_ids),
        }
        for bundle in result.scenario_bundles
    ]
    limitations = []
    if current is None:
        limitations.append("Current EBIT margin unavailable: no complete current report.")
    if peak is None:
        limitations.append("Peak EBIT margin unavailable: no complete observed report.")
    limitations.append(
        "Forecast gross margin unavailable: no independently sourced gross-margin assumption."
    )
    return {
        "status": "available" if current is not None and peak is not None else "unassessable",
        "policy_version": FORWARD_SCENARIO_POLICY_VERSION,
        "formulas": {
            "gross_to_ebit_spread": "gross_margin - ebit_margin",
            "margin_runway": "peak_ebit_margin - current_ebit_margin",
        },
        "current": current,
        "peak": peak,
        "bridge": bridge,
        "forecast": forecast,
        "qualitative_operating_changes": list(
            result.margin_expansion_case.required_operating_changes
        ),
        "qualitative_operating_change_source_ids": list(
            result.margin_expansion_case.source_ids
        ),
        "limitations": limitations,
    }


def _current_report(history, annual_reports):
    latest_r12 = _field(history, "latest_r12")
    if (
        latest_r12 is not None
        and not _field(latest_r12, "broken_fiscal_year")
        and _margin(latest_r12) is not None
    ):
        return latest_r12
    return next((report for report in annual_reports if _margin(report) is not None), None)


def _observation(report):
    revenue = _number(_field(report, "revenue"))
    gross_margin = _ratio(_field(report, "gross_income"), revenue)
    ebit_margin = _ratio(_field(report, "ebit"), revenue)
    source_id = _field(report, "source_id")
    return {
        "period": _field(report, "year") or _field(report, "period_end"),
        "revenue": revenue,
        "gross_margin": gross_margin,
        "ebit_margin": ebit_margin,
        "ebit": _number(_field(report, "ebit")),
        "gross_to_ebit_spread": (
            gross_margin - ebit_margin
            if gross_margin is not None and ebit_margin is not None
            else None
        ),
        "source_ids": [source_id] if source_id else [],
    }


def _margin(report):
    return _ratio(_field(report, "ebit"), _field(report, "revenue"))


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


def _difference(first, second):
    if first is None or second is None:
        return None
    return first - second
