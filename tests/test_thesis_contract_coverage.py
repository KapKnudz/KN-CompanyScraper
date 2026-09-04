from kncompanyscraper.analysis.agent.thesis_contract_coverage import (
    build_falsifiable_case_coverage,
)


def stored(company_id: int, *, falsifiable_case=None, thesis="Testable thesis", horizon=36):
    return {
        "analysis_id": company_id + 100,
        "company_id": company_id,
        "content": {
            "ticker": f"T{company_id}",
            "thesis_card_version": "individual-thesis-card-v2",
            "one_sentence_thesis": thesis,
            "case_horizon_months": horizon,
            "falsifiable_case": falsifiable_case,
        },
        "metadata": {},
    }


def test_coverage_measures_complete_and_legacy_cards_without_mutation():
    complete = stored(
        2,
        falsifiable_case={
            "statement": " Testable thesis ",
            "falsification_test": "Revenue misses the stated threshold.",
            "horizon_months": 36,
            "source_ids": ["financial_report:2:2026-Q2"],
        },
    )
    legacy = stored(1, falsifiable_case=None)
    before = complete["content"].copy()

    audit = build_falsifiable_case_coverage({2: complete, 1: legacy})

    assert audit["diagnostic_only"] is True
    assert audit["company_count"] == 2
    assert audit["complete_count"] == 1
    assert audit["coverage_rate"] == 0.5
    assert audit["field_counts"] == {
        "statement": 1,
        "falsification_test": 1,
        "horizon_months": 1,
        "source_ids": 1,
        "statement_reconciled": 1,
        "horizon_reconciled": 1,
    }
    assert audit["rows"][0]["missing_checks"] == [
        "statement",
        "falsification_test",
        "horizon_months",
        "source_ids",
        "statement_reconciled",
        "horizon_reconciled",
    ]
    assert audit["rows"][1]["complete"] is True
    assert complete["content"] == before


def test_coverage_exposes_reconciliation_failures_separately():
    audit = build_falsifiable_case_coverage(
        {
            1: stored(
                1,
                falsifiable_case={
                    "statement": "A different thesis",
                    "falsification_test": "Demand contracts.",
                    "horizon_months": 24,
                    "source_ids": ["research_document:1"],
                },
            )
        }
    )

    row = audit["rows"][0]
    assert row["checks"]["statement"] is True
    assert row["checks"]["horizon_months"] is True
    assert row["missing_checks"] == [
        "statement_reconciled",
        "horizon_reconciled",
    ]


def test_empty_cohort_has_no_misleading_percentage():
    audit = build_falsifiable_case_coverage({})

    assert audit["company_count"] == 0
    assert audit["coverage_rate"] is None
    assert audit["thesis_break_test_coverage"]["coverage_rate"] is None


def test_coverage_measures_all_six_thesis_break_test_types_and_fields():
    complete_tests = [
        {
            "break_type": break_type,
            "condition": "The condition fails.",
            "observable_metric_or_event": "Reported metric",
            "threshold_or_direction": "Falls below the baseline",
            "response": "reassess",
            "source_ids": ["news:21"],
        }
        for break_type in (
            "revenue_or_demand",
            "margin_or_execution",
            "balance_sheet_or_dilution",
            "management_credibility",
            "valuation_overshoot",
            "superior_evidence_or_opportunity",
        )
    ]
    incomplete = [dict(complete_tests[0], break_type="revenue_or_demand")]
    incomplete[0]["source_ids"] = []

    audit = build_falsifiable_case_coverage(
        {
            1: stored(1, falsifiable_case=None),
            2: {
                **stored(2, falsifiable_case=None),
                "content": {
                    **stored(2, falsifiable_case=None)["content"],
                    "thesis_break_tests": complete_tests,
                },
            },
            3: {
                **stored(3, falsifiable_case=None),
                "content": {
                    **stored(3, falsifiable_case=None)["content"],
                    "thesis_break_tests": incomplete,
                },
            },
        }
    )

    break_coverage = audit["thesis_break_test_coverage"]
    assert break_coverage["complete_count"] == 1
    assert break_coverage["coverage_rate"] == 1 / 3
    assert break_coverage["type_counts"] == {
        "revenue_or_demand": 1,
        "margin_or_execution": 1,
        "balance_sheet_or_dilution": 1,
        "management_credibility": 1,
        "valuation_overshoot": 1,
        "superior_evidence_or_opportunity": 1,
    }
    incomplete_row = next(row for row in audit["rows"] if row["company_id"] == 3)
    assert incomplete_row["thesis_break_tests"]["missing_types"] == [
        "revenue_or_demand",
        "margin_or_execution",
        "balance_sheet_or_dilution",
        "management_credibility",
        "valuation_overshoot",
        "superior_evidence_or_opportunity",
    ]
