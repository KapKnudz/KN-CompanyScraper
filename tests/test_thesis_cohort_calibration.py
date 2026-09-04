import json
from pathlib import Path

from kncompanyscraper.analysis.agent.thesis_cohort_calibration import (
    build_cohort_calibration_audit,
)


def stored(company_id, verdict, *, confidence="medium", base=(0.05, 0.10), subtype=None):
    return {
        "analysis_id": company_id,
        "company_id": company_id,
        "created_by": "test-model",
        "content": {
            "ticker": f"T{company_id}",
            "verdict": verdict,
            "latent_case_type": subtype,
            "confidence": confidence,
            "reverse_dcf_expectation_assessment": "plausible",
            "missing_information_details": [],
            "activation_trigger": "A defined trigger.",
            "forward_scenario_analysis": {
                "status": "available",
                "bands": [
                    {
                        "case": "base",
                        "low_annualized_return": base[0],
                        "high_annualized_return": base[1],
                    }
                ],
            },
        },
        "metadata": {
            "policy_version": "1.27.0",
            "evidence_as_of": "2026-09-03",
            "deterministic_context_sha256": f"packet-{company_id}",
            "forward_scenario": {"required_return": 0.10},
        },
    }


def test_cohort_audit_distinguishes_latent_labels_and_is_diagnostic_only():
    audit = build_cohort_calibration_audit(
        {
            1: stored(1, "latent_case", base=(0.02, 0.08), subtype="price"),
            2: stored(2, "latent_case", base=(0.11, 0.18), subtype="operating"),
        }
    )

    assert audit["diagnostic_only"] is True
    assert [row["verdict_label"] for row in audit["rows"]] == [
        "price-latent",
        "operating-latent",
    ]
    assert audit["rows"][0]["packet_hash"] == "packet-1"


def test_cohort_audit_marks_same_input_instability_explicitly():
    audit = build_cohort_calibration_audit(
        {1: stored(1, "watch")},
        {
            1: [
                {"packet_hash": "same", "content": {"verdict": "watch"}},
                {"packet_hash": "same", "content": {"verdict": "latent_case"}},
            ]
        },
    )

    assert audit["review_result"] == "unexplained_same_input_instability"
    assert audit["flags"][0]["type"] == "same_input_verdict_instability"


def test_cohort_fixture_preserves_differentiated_spectrum_and_warns_on_no_activation():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "thesis_calibration_spectrum.json").read_text()
    )
    analyses = {item["company_id"]: item for item in fixture}

    audit = build_cohort_calibration_audit(analyses)

    assert [row["verdict_label"] for row in audit["rows"]] == [
        "reject",
        "price-latent",
        "operating-latent",
        "watch",
        "activated_case",
    ]
    assert not any(flag["type"] == "activated_case_absence" for flag in audit["flags"])


def test_cohort_audit_ignores_policy_changes_when_grouping_same_packet():
    history = {
        1: [
            {
                "content": '{"verdict": "watch"}',
                "metadata": {
                    "deterministic_context_sha256": "same",
                    "policy_version": "old",
                },
            },
            {
                "content": '{"verdict": "latent_case"}',
                "metadata": {
                    "deterministic_context_sha256": "same",
                    "policy_version": "new",
                },
            },
        ]
    }

    audit = build_cohort_calibration_audit({1: stored(1, "watch")}, history)

    assert not any(
        flag["type"] == "same_input_verdict_instability" for flag in audit["flags"]
    )


def test_cohort_audit_warns_on_resilience_collapse_and_zero_activation():
    audit = build_cohort_calibration_audit(
        {
            1: stored(1, "reject", base=(-0.10, -0.02)),
            2: stored(2, "watch", base=(0.01, 0.08)),
            3: stored(3, "latent_case", base=(0.11, 0.18), subtype="operating"),
            4: stored(4, "watch", base=(0.20, 0.25)),
            5: stored(5, "reject", base=(0.30, 0.35)),
        }
    )

    flag_types = {flag["type"] for flag in audit["flags"]}
    assert "resilience_collapse" in flag_types
    assert "activated_case_absence" in flag_types
