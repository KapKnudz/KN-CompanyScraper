from dataclasses import asdict

from kncompanyscraper.models.stored_analysis import StoredAnalysisDocument
from tests.test_forward_scenario import analysis_with_returns


def test_thesis_summary_only_projects_persisted_v2_values():
    analysis = analysis_with_returns()
    document = StoredAnalysisDocument(
        {
            "analysis_id": 7,
            "content": {
                "ticker": "TEST",
                "confidence": "medium",
                "verdict": "watch",
                "one_sentence_thesis": "Evidence is incomplete.",
                "reverse_dcf_expectation_assessment": "demanding",
                "reverse_dcf_expectation_rationale": "The curve needs stronger execution.",
                "revenue_resilience": {
                    "assessment": "mixed",
                    "recurring_driver": "Renewals provide persistence.",
                    "variable_driver": "Usage varies by quarter.",
                    "cash_flow_observation": "Cash flow is positive but uneven.",
                    "source_ids": ["report:2026-q2"],
                    "limitations": [],
                },
                "case_horizon_months": 36,
                "thesis_break_conditions": ["Margins deteriorate."],
                "missing_information": ["Next report"],
                "timing_assessment": {"why_now": "The next report tests the case."},
                "scenario_bundles": [
                    {
                        "case": "base",
                        "mechanism": "Stable operating leverage.",
                        "revenue_cagr": {"value": 0.1},
                    }
                ],
            },
            "metadata": {
                "valuation_provenance": {
                    "current_price": 10.0,
                    "expectation_curve": [{"revenue_growth": 0.08}],
                },
                "forward_scenario": {
                    "status": "available",
                    "net_debt_bridges": [
                        {
                            "case": "base",
                            "current_net_debt": 10.0,
                            "net_debt_change": 2.0,
                            "projected_net_debt": 12.0,
                            "current_shares": 20.0,
                            "share_count_growth": 0.05,
                            "projected_shares": 21.0,
                            "distributions_per_share": 0.5,
                        }
                    ],
                    "capital_allocation_limitations": ["Distribution data is missing."],
                },
            },
        }
    )
    document.content["forward_scenario_analysis"] = {
        "status": "available",
        "bands": [asdict(band) for band in analysis.bands],
    }
    document.content["scenario_driver_attribution"] = {
        "status": "available",
        "policy_version": "scenario-driver-attribution-shapley-v1",
    }

    summary = document.thesis_summary

    assert summary["current_price"] == 10.0
    assert summary["horizon_months"] == 36
    assert summary["revenue_resilience"]["assessment"] == "mixed"
    assert summary["scenarios"]["base"]["price_range"] == [1, 1]
    assert summary["scenarios"]["base"]["holding_value_range"] == [1, 1]
    assert summary["scenarios"]["base"]["horizon_months"] == 36
    assert summary["scenarios"]["base"]["annualized_return_range"] == [0.12, 0.16]
    assert summary["scenarios"]["base"]["explanation"] == "Stable operating leverage."
    assert summary["scenario_driver_attribution"]["status"] == "available"
    assert summary["scenarios"]["base"]["capital_allocation"]["projected_shares"] == 21.0
    assert summary["capital_allocation_limitations"] == ["Distribution data is missing."]
    assert summary["reverse_dcf"]["selected_curve_points"] == [
        {"revenue_growth": 0.08}
    ]


def test_thesis_summary_omits_unavailable_bands():
    document = StoredAnalysisDocument(
        {
            "analysis_id": 7,
            "content": {
                "confidence": "medium",
                "verdict": "watch",
                "one_sentence_thesis": "Evidence is incomplete.",
                "reverse_dcf_expectation_assessment": "unassessable",
                "thesis_break_conditions": [],
                "missing_information": [],
                "scenario_bundles": [],
            },
            "metadata": {},
        }
    )
    document.content["forward_scenario_analysis"] = {
        "status": "insufficient_evidence",
        "bands": [
            {
                "case": "bull",
                "low_price": 3,
                "high_price": 4,
                "low_annualized_return": 0.1,
                "high_annualized_return": 0.2,
            }
        ],
    }

    assert document.thesis_summary["scenarios"] == {}


def test_thesis_summary_uses_bear_base_bull_order():
    document = StoredAnalysisDocument(
        {
            "analysis_id": 7,
            "content": {
                "confidence": "medium",
                "verdict": "watch",
                "one_sentence_thesis": "Evidence is incomplete.",
                "reverse_dcf_expectation_assessment": "unassessable",
                "thesis_break_conditions": [],
                "missing_information": [],
                "scenario_bundles": [],
                "forward_scenario_analysis": {
                    "status": "available",
                    "bands": [
                        {
                            "case": "bull",
                            "low_price": 3,
                            "high_price": 4,
                            "low_annualized_return": 0.1,
                            "high_annualized_return": 0.2,
                        },
                        {
                            "case": "bear",
                            "low_price": 1,
                            "high_price": 2,
                            "low_annualized_return": -0.1,
                            "high_annualized_return": 0.0,
                        },
                    ],
                },
            },
            "metadata": {},
        }
    )

    assert list(document.thesis_summary["scenarios"]) == ["bear", "bull"]
