"""Read-only coverage measurement for persisted thesis-card contracts."""

from kncompanyscraper.models.stored_analysis import as_stored_analysis
from kncompanyscraper.analysis.agent.output_schema import THESIS_BREAK_TYPES


MEASUREMENT_VERSION = "thesis-contract-coverage-v2"
CHECKS = (
    "statement",
    "falsification_test",
    "horizon_months",
    "source_ids",
    "statement_reconciled",
    "horizon_reconciled",
)


def build_falsifiable_case_coverage(analyses_by_company: dict[int, dict]) -> dict:
    """Measure falsifiable-case completeness without changing stored analyses."""
    rows = [
        _coverage_row(company_id, analysis)
        for company_id, analysis in analyses_by_company.items()
    ]
    rows.sort(key=lambda row: row["company_id"])
    field_counts = {
        check: sum(row["checks"][check] for row in rows) for check in CHECKS
    }
    complete_count = sum(row["complete"] for row in rows)
    company_count = len(rows)
    return {
        "measurement_version": MEASUREMENT_VERSION,
        "diagnostic_only": True,
        "company_count": company_count,
        "complete_count": complete_count,
        "coverage_rate": complete_count / company_count if company_count else None,
        "field_counts": field_counts,
        "thesis_break_test_coverage": _break_test_coverage(rows),
        "rows": rows,
    }


def _coverage_row(company_id: int, analysis: dict) -> dict:
    content = as_stored_analysis(analysis)._projected_content()
    falsifiable = content.get("falsifiable_case") or {}
    if not isinstance(falsifiable, dict):
        falsifiable = {}

    statement = falsifiable.get("statement")
    falsification_test = falsifiable.get("falsification_test")
    horizon = falsifiable.get("horizon_months")
    source_ids = falsifiable.get("source_ids")
    thesis = content.get("one_sentence_thesis")
    case_horizon = content.get("case_horizon_months")

    checks = {
        "statement": _has_text(statement),
        "falsification_test": _has_text(falsification_test),
        "horizon_months": _positive_integer(horizon),
        "source_ids": (
            isinstance(source_ids, list)
            and bool(source_ids)
            and all(_has_text(source_id) for source_id in source_ids)
        ),
        "statement_reconciled": (
            _has_text(statement)
            and _has_text(thesis)
            and statement.strip() == thesis.strip()
        ),
        "horizon_reconciled": (
            _positive_integer(horizon)
            and _positive_integer(case_horizon)
            and horizon == case_horizon
        ),
    }
    missing_checks = [check for check in CHECKS if not checks[check]]
    break_coverage = _break_test_row(content.get("thesis_break_tests"))
    return {
        "analysis_id": analysis.get("analysis_id"),
        "company_id": company_id,
        "ticker": content.get("ticker"),
        "thesis_card_version": content.get("thesis_card_version"),
        "checks": checks,
        "complete": not missing_checks,
        "missing_checks": missing_checks,
        "thesis_break_tests": break_coverage,
    }


def _break_test_coverage(rows: list[dict]) -> dict:
    complete_count = sum(
        all(row["thesis_break_tests"]["checks"].values()) for row in rows
    )
    type_counts = {
        break_type: sum(
            row["thesis_break_tests"]["checks"][break_type]
            for row in rows
        )
        for break_type in THESIS_BREAK_TYPES
    }
    company_count = len(rows)
    return {
        "required_types": list(THESIS_BREAK_TYPES),
        "complete_count": complete_count,
        "coverage_rate": (
            complete_count / company_count if company_count else None
        ),
        "type_counts": type_counts,
    }


def _break_test_row(value) -> dict:
    tests = value if isinstance(value, list) else []
    by_type = {}
    duplicate_types = []
    for test in tests:
        if not isinstance(test, dict):
            continue
        break_type = test.get("break_type")
        if break_type in by_type:
            duplicate_types.append(break_type)
            continue
        by_type[break_type] = test

    checks = {
        break_type: _complete_break_test(by_type.get(break_type))
        for break_type in THESIS_BREAK_TYPES
    }
    missing_types = [break_type for break_type, present in checks.items() if not present]
    unsupported_types = sorted(
        break_type
        for break_type in by_type
        if break_type not in THESIS_BREAK_TYPES
    )
    return {
        "checks": checks,
        "missing_types": missing_types,
        "duplicate_types": sorted(set(duplicate_types)),
        "unsupported_types": unsupported_types,
        "complete": not missing_types
        and not duplicate_types
        and not unsupported_types,
    }


def _complete_break_test(test) -> bool:
    if not isinstance(test, dict):
        return False
    required_fields = (
        "condition",
        "observable_metric_or_event",
        "threshold_or_direction",
        "response",
        "source_ids",
    )
    return all(
        _has_text(test.get(field))
        if field != "source_ids"
        else (
            isinstance(test.get(field), list)
            and bool(test[field])
            and all(_has_text(source_id) for source_id in test[field])
        )
        for field in required_fields
    )


def _has_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
