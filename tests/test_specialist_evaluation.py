import copy
import json
from hashlib import sha256
from pathlib import Path

import pytest

from kncompanyscraper.analysis.agent.specialist_evaluation import (
    CASES_SCHEMA_VERSION,
    EvaluationFormatError,
    compare_specialist_evaluations,
    format_evaluation_report,
    load_cases,
)


FIXTURES = Path(__file__).parent / "fixtures" / "specialist_evaluation"


def documents():
    return (
        json.loads((FIXTURES / "cases.json").read_text()),
        json.loads((FIXTURES / "artifacts.json").read_text()),
        json.loads((FIXTURES / "packets.json").read_text()),
    )


def run(cases=None, artifacts=None, packets=None):
    fixture_cases, fixture_artifacts, fixture_packets = documents()
    return compare_specialist_evaluations(
        cases or fixture_cases,
        artifacts or fixture_artifacts,
        packets=packets or fixture_packets,
    )


def test_fixture_metrics_cover_claim_management_conflict_and_source_agreement():
    report = run()

    assert report["schema_version"] == "specialist-evaluation-report-v1"
    assert report["metrics"]["parse_semantic_rejection"]["rejected"] == 0
    assert report["metrics"]["source_id_validity"]["validity_rate"] == 1
    assert report["metrics"]["claim_label_agreement"]["agreement_rate"] == 1
    assert report["metrics"]["management_row_classification_agreement"]["agreement_rate"] == 1
    assert report["metrics"]["conflict_precision_recall"]["precision"] == 1
    assert report["metrics"]["conflict_precision_recall"]["recall"] == 1


def test_missing_labels_are_skipped_not_passes():
    cases, artifacts, packets = documents()
    cases["cases"][0]["labels"]["claims"] = [{"status": "not_applicable"}]
    cases["cases"][0]["labels"]["management_rows"] = []
    cases["cases"][0]["labels"]["final_verdict"] = "not_applicable"
    cases["cases"][0]["labels"]["confidence"] = "not_applicable"

    report = run(cases, artifacts, packets)

    claims = report["metrics"]["claim_label_agreement"]
    assert claims["evaluated"] == 0
    assert claims["skipped_not_applicable"] == 1
    assert claims["agreement_rate"] is None
    assert report["metrics"]["final_verdict_agreement"]["agreement_rate"] is None


def test_malformed_fixture_and_artifact_are_distinguished():
    cases, artifacts, packets = documents()
    bad_cases = copy.deepcopy(cases)
    bad_cases["schema_version"] = "specialist-evaluation-cases-v0"
    with pytest.raises(EvaluationFormatError, match="unsupported evaluation cases schema"):
        load_cases(bad_cases)

    bad_artifacts = copy.deepcopy(artifacts)
    bad_artifacts["artifacts"][0]["content"] = "not-json"
    report = run(cases, bad_artifacts, packets)
    assert report["metrics"]["parse_semantic_rejection"] == {
        "rejected": 1,
        "total": 2,
        "rejection_rate": 0.5,
    }
    assert report["cases"][0]["artifact_errors"]


def test_malformed_artifact_records_are_counted_as_rejections():
    cases, artifacts, packets = documents()
    artifacts["artifacts"].append(None)

    report = run(cases, artifacts, packets)
    rejection = report["metrics"]["parse_semantic_rejection"]
    assert rejection["rejected"] == 1
    assert rejection["total"] == 3
    assert report["malformed_artifact_count"] == 1


def test_metadata_packet_mismatch_is_counted_as_rejection():
    cases, artifacts, packets = documents()
    artifacts["artifacts"][0]["metadata"]["packet_hash"] = "f" * 64

    report = run(cases, artifacts, packets)
    rejection = report["metrics"]["parse_semantic_rejection"]
    assert rejection["rejected"] == 1
    assert rejection["total"] == 2
    assert report["cases"][0]["accepted_count"] == 1


def test_human_label_enums_are_validated():
    cases, _, _ = documents()
    mutations = (
        ("claims", "agent_name", "unknown_agent"),
        ("claims", "expected_direction", "unknown_direction"),
        ("management_rows", "expected_result", "unknown_result"),
    )
    for label_group, field, value in mutations:
        invalid = copy.deepcopy(cases)
        invalid["cases"][0]["labels"][label_group][0][field] = value
        with pytest.raises(EvaluationFormatError, match="unknown"):
            load_cases(invalid)

    invalid = copy.deepcopy(cases)
    invalid["cases"][0]["labels"]["final_verdict"] = "unknown_verdict"
    with pytest.raises(EvaluationFormatError, match="final_verdict is unknown"):
        load_cases(invalid)


def test_conflict_false_positive_and_false_negative_counts_are_explicit():
    cases, artifacts, packets = documents()
    labels = cases["cases"][0]["labels"]["conflicts"]
    labels["expected_triggered"] = []
    labels["expected_not_triggered"] = ["insider_vs_credibility_record"]
    report = run(cases, artifacts, packets)
    metrics = report["metrics"]["conflict_precision_recall"]
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 0

    labels["expected_triggered"] = ["margin_vs_sell_condition"]
    labels["expected_not_triggered"] = []
    report = run(cases, artifacts, packets)
    metrics = report["metrics"]["conflict_precision_recall"]
    assert metrics["false_positive"] == 0
    assert metrics["false_negative"] == 1


def test_overlapping_conflict_labels_are_rejected():
    cases, _, _ = documents()
    cases["cases"][0]["labels"]["conflicts"]["expected_not_triggered"].append(
        "insider_vs_credibility_record"
    )

    with pytest.raises(EvaluationFormatError, match="both triggered and not_triggered"):
        load_cases(cases)


def test_invalid_source_ids_are_counted_and_source_label_disagrees():
    cases, artifacts, packets = documents()
    artifacts["artifacts"][0]["content"] = artifacts["artifacts"][0]["content"].replace(
        "report:one", "report:not-in-packet"
    )
    cases["cases"][0]["labels"]["source_validity"] = "all_valid"
    report = run(cases, artifacts, packets)

    source = report["metrics"]["source_id_validity"]
    assert source["invalid"] == 4
    assert source["label_incorrect"] == 1
    assert source["label_agreement_rate"] == 0


def test_missing_source_ids_are_unavailable_not_all_valid():
    cases, artifacts, packets = documents()
    payload = json.loads(artifacts["artifacts"][0]["content"])
    payload["claims"][0]["source_ids"] = []
    payload["management_credibility"]["ledger"][0]["claim_source_ids"] = []
    payload["management_credibility"]["ledger"][0]["outcome_source_ids"] = []
    payload["management_credibility"]["ledger"][0]["source_ids"] = []
    artifacts["artifacts"][0]["content"] = json.dumps(payload)

    report = run(cases, artifacts, packets)
    source = report["metrics"]["source_id_validity"]
    assert source["valid"] == 0
    assert source["evaluated"] == 0
    assert source["unavailable"] == 1
    assert source["label_incorrect"] == 0


def test_rejected_and_mismatched_artifacts_are_not_scored():
    cases, artifacts, packets = documents()
    payload = json.loads(artifacts["artifacts"][0]["content"])
    payload["run_id"] = "wrong-run"
    artifacts["artifacts"][0]["content"] = json.dumps(payload)
    report = run(cases, artifacts, packets)
    assert report["metrics"]["parse_semantic_rejection"]["rejected"] == 1
    assert report["cases"][0]["accepted_count"] == 1

    artifacts["artifacts"][0]["content"] = documents()[1]["artifacts"][0]["content"]
    artifacts["artifacts"][0]["metadata"]["validation_status"] = "rejected"
    report = run(cases, artifacts, packets)
    assert report["metrics"]["parse_semantic_rejection"]["rejected"] == 1
    assert report["cases"][0]["accepted_count"] == 1


def test_packet_identity_mismatch_makes_source_evidence_unavailable():
    cases, artifacts, packets = documents()
    wrong_packet = {
        "company_id": 2,
        "ticker": "OTHER",
        "full_results": {"financial_history": {"revenue": 10}},
        "research_evidence": {"documents": [{"source_id": "report:one"}]},
    }
    wrong_hash = sha256(
        json.dumps(wrong_packet, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    cases["cases"][0]["packet_hash"] = wrong_hash
    for artifact in artifacts["artifacts"]:
        artifact["metadata"]["packet_hash"] = wrong_hash
        payload = json.loads(artifact["content"])
        payload["packet_hash"] = wrong_hash
        artifact["content"] = json.dumps(payload)
    packets["1"] = wrong_packet

    report = run(cases, artifacts, packets)
    assert report["cases"][0]["packet_status"] == "unavailable"
    assert report["metrics"]["source_id_validity"]["unavailable"] >= 1


def test_duplicate_agent_artifacts_are_rejected():
    cases, artifacts, packets = documents()
    artifacts["artifacts"].append(copy.deepcopy(artifacts["artifacts"][0]))
    report = run(cases, artifacts, packets)
    assert report["metrics"]["parse_semantic_rejection"]["rejected"] == 1
    assert report["cases"][0]["accepted_count"] == 2


def test_activation_false_positive_and_metadata_availability_are_reported():
    cases, artifacts, packets = documents()
    artifacts["artifacts"][0]["metadata"]["final_verdict"] = "activated_case"
    artifacts["artifacts"][0]["metadata"]["result_scope"] = "case"
    cases["cases"][0]["labels"]["activation"] = False
    report = run(cases, artifacts, packets)

    activation = report["metrics"]["activation_false_positive_rate"]
    assert activation["false_positives"] == 1
    assert activation["eligible"] == 1
    assert activation["rate"] == 1
    outcomes = report["metrics"]["activation_outcomes"]
    assert outcomes["false_positive"] == 1
    assert outcomes["evaluated"] == 1
    assert report["metadata_fields"]["latency_ms"]["unavailable"] == 2


def test_activation_false_negative_is_reported():
    cases, artifacts, packets = documents()
    artifacts["artifacts"][0]["metadata"]["final_verdict"] = "latent_case"
    artifacts["artifacts"][0]["metadata"]["result_scope"] = "case"
    cases["cases"][0]["labels"]["activation"] = True

    report = run(cases, artifacts, packets)
    outcomes = report["metrics"]["activation_outcomes"]
    assert outcomes["false_negative"] == 1
    assert outcomes["evaluated"] == 1
    assert outcomes["unavailable"] == 0


def test_case_level_records_do_not_contaminate_specialist_metrics():
    cases, artifacts, packets = documents()
    artifacts["artifacts"][0]["metadata"]["final_verdict"] = "activated_case"
    artifacts["artifacts"][0]["metadata"]["result_scope"] = "case"

    report = run(cases, artifacts, packets)
    case_report = report["cases"][0]
    assert case_report["accepted_count"] == 1
    assert case_report["rejected_count"] == 0
    assert case_report["case_level_result"]["available"] is True
    assert len(case_report["metadata"]) == 1
    assert report["metrics"]["confidence_calibration"]["evaluated"] == 1
    assert report["metrics"]["source_id_validity"]["unavailable"] == 1


def test_investable_is_not_an_activation_verdict_alias():
    cases, artifacts, packets = documents()
    artifacts["artifacts"][0]["metadata"]["final_verdict"] = "investable"
    artifacts["artifacts"][0]["metadata"]["result_scope"] = "case"
    cases["cases"][0]["labels"]["activation"] = False

    report = run(cases, artifacts, packets)
    outcomes = report["metrics"]["activation_outcomes"]
    assert outcomes["true_negative"] == 1
    assert outcomes["false_positive"] == 0


def test_confidence_is_calibrated_per_labeled_agent_and_metadata_is_preserved():
    cases, artifacts, packets = documents()
    insider = json.loads(artifacts["artifacts"][1]["content"])
    insider["confidence"] = "high"
    artifacts["artifacts"][1]["content"] = json.dumps(insider)
    cases["cases"][0]["labels"]["confidence"] = {
        "management_credibility": "low",
        "insider_ownership": "high",
    }

    report = run(cases, artifacts, packets)
    confidence = report["metrics"]["confidence_calibration"]
    assert confidence["evaluated"] == 2
    assert confidence["correct"] == 2
    assert confidence["by_agent"]["management_credibility"]["evaluated"] == 1
    assert confidence["by_agent"]["insider_ownership"]["correct"] == 1
    assert report["cases"][0]["metadata"][0]["run_id"] == "synthetic-run"
    assert report["cases"][0]["metadata"][0]["agent_name"] == "management_credibility"
    assert report["metadata_fields"]["run_id"]["available"] == 2


def test_output_order_is_deterministic_and_human_summary_is_concise():
    cases, artifacts, packets = documents()
    cases["cases"].append({**cases["cases"][0], "case_id": "aaa-first"})
    artifacts["artifacts"] = list(reversed(artifacts["artifacts"]))
    report = run(cases, artifacts, packets)

    assert [case["case_id"] for case in report["cases"]] == [
        "aaa-first",
        "synthetic-management-insider",
    ]
    summary = format_evaluation_report(report)
    assert "parse/semantic rejection:" in summary
    assert "Metadata unavailable fields" in summary


def test_case_schema_version_is_exactly_versioned():
    cases, _, _ = documents()
    assert cases["schema_version"] == CASES_SCHEMA_VERSION
    with pytest.raises(EvaluationFormatError, match="packet_hash"):
        load_cases({
            "schema_version": CASES_SCHEMA_VERSION,
            "cases": [{"case_id": "bad", "company_id": 1, "ticker": "X", "labels": {}}],
        })
