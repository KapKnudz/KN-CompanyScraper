"""Reviewable specialist evaluation cases and deterministic comparison metrics.

This module is intentionally read-only: it evaluates stored artifacts against
human-authored labels and never participates in production verdict selection.
"""

from __future__ import annotations

import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from kncompanyscraper.analysis.agent.agent_packet import (
    build_evidence_catalog,
    resolve_source_id,
    SourcePathError,
)
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_specialist_output,
)
from kncompanyscraper.analysis.agent.specialist_conflicts import (
    evaluate_specialist_conflicts,
)

CASES_SCHEMA_VERSION = "specialist-evaluation-cases-v1"
REPORT_SCHEMA_VERSION = "specialist-evaluation-report-v1"
CONFLICT_RULES = (
    "margin_vs_sell_condition",
    "insider_vs_credibility_record",
    "circle_of_competence_vs_valuation",
    "multiple_expansion_vs_activation",
)
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_METADATA_FIELDS = (
    "model",
    "tier",
    "prompt_hash",
    "packet_hash",
    "latency_ms",
    "tokens",
    "cost",
    "attempts",
    "repairs",
)


class EvaluationFormatError(ValueError):
    """Raised when a labeled case file is not the versioned case format."""


def _na(value: Any) -> bool:
    return value is None or value == "not_applicable" or (
        isinstance(value, Mapping) and value.get("status") == "not_applicable"
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluationFormatError(message)


def _load_json(value: str | Path | Mapping | Sequence) -> Any:
    if isinstance(value, (str, Path)):
        try:
            return json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvaluationFormatError(f"cannot read evaluation JSON: {value}") from exc
    return value


def _validate_labels(labels: Any, case_id: str) -> None:
    _require(isinstance(labels, Mapping), f"case {case_id}: labels must be an object")
    claims = labels.get("claims", [])
    _require(isinstance(claims, list), f"case {case_id}: labels.claims must be a list")
    for index, label in enumerate(claims):
        _require(isinstance(label, Mapping), f"case {case_id}: claim label {index} must be an object")
        if not _na(label):
            _require(isinstance(label.get("agent_name"), str), f"case {case_id}: claim label needs agent_name")
            _require(isinstance(label.get("claim_id"), str), f"case {case_id}: claim label needs claim_id")
            _require(
                label.get("expected_direction") is not None or label.get("expected_value") is not None,
                f"case {case_id}: claim label needs expected_direction or expected_value",
            )
    rows = labels.get("management_rows", [])
    _require(isinstance(rows, list), f"case {case_id}: labels.management_rows must be a list")
    for index, label in enumerate(rows):
        _require(isinstance(label, Mapping), f"case {case_id}: management row label {index} must be an object")
        if not _na(label):
            _require(isinstance(label.get("claim_id"), str), f"case {case_id}: management row needs claim_id")
            _require(isinstance(label.get("expected_result"), str), f"case {case_id}: management row needs expected_result")
    conflicts = labels.get("conflicts", {})
    _require(isinstance(conflicts, Mapping), f"case {case_id}: labels.conflicts must be an object")
    for key in ("expected_triggered", "expected_not_triggered"):
        values = conflicts.get(key, [])
        _require(isinstance(values, list), f"case {case_id}: conflicts.{key} must be a list")
        _require(
            all(isinstance(value, str) and value in CONFLICT_RULES for value in values),
            f"case {case_id}: conflicts.{key} contains an unknown rule",
        )
    source = labels.get("source_validity", "not_applicable")
    _require(
        _na(source) or source in {"all_valid", "invalid_present", "unavailable"},
        f"case {case_id}: source_validity must be all_valid, invalid_present, or not_applicable",
    )
    activation = labels.get("activation", "not_applicable")
    _require(
        _na(activation) or isinstance(activation, bool),
        f"case {case_id}: activation must be boolean or not_applicable",
    )
    confidence = labels.get("confidence", "not_applicable")
    _require(
        _na(confidence) or confidence in _CONFIDENCE_RANK,
        f"case {case_id}: confidence must be low, medium, high, or not_applicable",
    )


def validate_cases_document(document: Mapping) -> list[dict]:
    """Validate and return cases in deterministic case-id order."""
    _require(isinstance(document, Mapping), "evaluation cases must be an object")
    _require(document.get("schema_version") == CASES_SCHEMA_VERSION, "unsupported evaluation cases schema version")
    cases = document.get("cases")
    _require(isinstance(cases, list), "evaluation cases must contain a cases list")
    seen: set[str] = set()
    result = []
    for case in cases:
        _require(isinstance(case, Mapping), "each evaluation case must be an object")
        case_id = case.get("case_id")
        _require(isinstance(case_id, str) and case_id, "each evaluation case needs case_id")
        _require(case_id not in seen, f"duplicate evaluation case_id: {case_id}")
        seen.add(case_id)
        _require(isinstance(case.get("company_id"), int), f"case {case_id}: company_id must be an integer")
        _require(isinstance(case.get("ticker"), str) and case["ticker"], f"case {case_id}: ticker is required")
        packet_hash = case.get("packet_hash")
        _require(
            isinstance(packet_hash, str) and len(packet_hash) == 64 and all(c in "0123456789abcdef" for c in packet_hash),
            f"case {case_id}: packet_hash must be a lowercase SHA-256 hex digest",
        )
        _validate_labels(case.get("labels", {}), case_id)
        result.append(dict(case))
    return sorted(result, key=lambda item: item["case_id"])


def load_cases(value: str | Path | Mapping) -> list[dict]:
    return validate_cases_document(_load_json(value))


def _artifact_records(value: Any) -> list[dict]:
    document = _load_json(value)
    if isinstance(document, Mapping):
        records = document.get("artifacts")
    else:
        records = document
    if not isinstance(records, list):
        raise EvaluationFormatError("specialist artifacts must be a list or an object with artifacts")
    return [dict(record) if isinstance(record, Mapping) else {"_malformed": record} for record in records]


def _packet_map(value: Any) -> dict[str, Mapping]:
    if value is None:
        return {}
    document = _load_json(value)
    if isinstance(document, Mapping) and "packets" in document:
        document = document["packets"]
    if isinstance(document, Mapping):
        return {str(key): packet for key, packet in document.items() if isinstance(packet, Mapping)}
    if isinstance(document, list):
        return {
            str(packet.get("company_id")): packet
            for packet in document
            if isinstance(packet, Mapping) and packet.get("company_id") is not None
        }
    raise EvaluationFormatError("packets must be an object map, packet list, or object with packets")


def _packet_for_case(case: Mapping, packets: Mapping[str, Mapping]) -> Mapping | None:
    ref = case.get("packet_ref")
    packet = packets.get(str(ref)) if ref is not None else None
    if packet is None:
        packet = packets.get(str(case["company_id"]))
    if packet is None and isinstance(case.get("packet"), Mapping):
        packet = case["packet"]
    if packet is None:
        return None
    serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if sha256(serialized.encode("utf-8")).hexdigest() != case["packet_hash"]:
        return {"_packet_hash_mismatch": True}
    return packet


def _metadata(record: Mapping) -> dict:
    metadata = dict(record.get("metadata") or {}) if isinstance(record.get("metadata"), Mapping) else {}
    if record.get("created_by") is not None:
        metadata.setdefault("model", record["created_by"])
    metadata.setdefault("packet_hash", metadata.get("packet_hash"))
    metadata.setdefault("tier", metadata.get("model_tier"))
    metadata.setdefault("attempts", metadata.get("analysis_attempt"))
    metadata.setdefault("repairs", metadata.get("repair_count"))
    metadata.setdefault("prompt_hash", metadata.get("prompt_sha256"))
    usage = metadata.get("usage") if isinstance(metadata.get("usage"), Mapping) else {}
    metadata.setdefault("tokens", usage.get("total_tokens"))
    return metadata


def _record_matches(case: Mapping, record: Mapping) -> bool:
    if record.get("_malformed") is not None:
        return False
    metadata = _metadata(record)
    company_id = record.get("company_id", metadata.get("company_id"))
    if company_id is not None and company_id != case["company_id"]:
        return False
    if metadata.get("case_id", record.get("case_id")) not in (None, case["case_id"]):
        return False
    if metadata.get("packet_hash") not in (None, case["packet_hash"]):
        return False
    if case.get("run_id") is not None and metadata.get("run_id") != case["run_id"]:
        return False
    return True


def _output_claims(output) -> list:
    claims = list(output.claims)
    domain = getattr(output, output.agent_name.value, None)
    if domain is not None:
        claims.extend(getattr(domain, "claims", []))
        claims.extend(getattr(domain, "event_claims", []))
    return claims


def _actual_final_verdict(records: Sequence[Mapping], parsed: Sequence[Any]) -> str | None:
    for record in reversed(records):
        metadata = _metadata(record)
        value = record.get("final_verdict", metadata.get("final_verdict"))
        if value is not None:
            return value
    return None


def _metric(correct: int, incorrect: int, skipped: int = 0, unavailable: int = 0) -> dict:
    evaluated = correct + incorrect
    return {
        "correct": correct,
        "incorrect": incorrect,
        "evaluated": evaluated,
        "skipped_not_applicable": skipped,
        "unavailable": unavailable,
        "agreement_rate": correct / evaluated if evaluated else None,
    }


def _source_status(outputs: Sequence[Any], packet: Mapping | None) -> tuple[int, int, int]:
    source_ids = []
    for output in outputs:
        for claim in _output_claims(output):
            source_ids.extend(claim.source_ids)
        if output.management_credibility is not None:
            for row in output.management_credibility.ledger:
                source_ids.extend(row.source_ids)
                source_ids.extend(row.claim_source_ids)
                source_ids.extend(row.outcome_source_ids)
        if output.margin is not None:
            source_ids.extend(output.margin.supporting_source_ids)
            source_ids.extend(output.margin.contrary_source_ids)
        if output.sell_conditions is not None:
            for test in output.sell_conditions.tests:
                source_ids.extend(test.get("source_ids", []))
            for blocker in output.sell_conditions.activation_blockers:
                source_ids.extend(blocker.get("source_ids", []))
    if packet is None or packet.get("_packet_hash_mismatch"):
        return 0, 0, max(1, len(source_ids))
    catalog = packet.get("evidence_catalog") or build_evidence_catalog(packet.get("full_results", {}), packet.get("research_evidence", {}))
    valid = invalid = 0
    for source_id in source_ids:
        try:
            resolved = resolve_source_id(source_id, packet.get("full_results", {}), packet.get("research_evidence", {}), catalog=catalog)
            if resolved in set(catalog.get("canonical_source_ids", [])):
                valid += 1
            else:
                invalid += 1
        except (SourcePathError, TypeError, AttributeError):
            invalid += 1
    return valid, invalid, 0


def compare_specialist_evaluations(
    cases: str | Path | Mapping | Sequence,
    artifacts: str | Path | Mapping | Sequence,
    *,
    packets: str | Path | Mapping | Sequence | None = None,
) -> dict:
    """Compare stored specialist artifacts to explicit labels.

    Invalid model artifacts are reported as rejections; malformed labeled case
    files raise ``EvaluationFormatError`` because silently changing labels would
    invalidate the evaluation.
    """
    case_list = load_cases(cases) if not isinstance(cases, list) else validate_cases_document({"schema_version": CASES_SCHEMA_VERSION, "cases": cases})
    records = _artifact_records(artifacts)
    packet_map = _packet_map(packets)
    totals = {
        "parse_semantic_rejection": {"rejected": 0, "total": 0, "rejection_rate": None},
        "source_id_validity": {"valid": 0, "invalid": 0, "evaluated": 0, "unavailable": 0, "validity_rate": None, "label_correct": 0, "label_incorrect": 0, "label_skipped_not_applicable": 0, "label_agreement_rate": None},
        "claim_label_agreement": _metric(0, 0),
        "management_row_classification_agreement": _metric(0, 0),
        "conflict_precision_recall": {"true_positive": 0, "false_positive": 0, "false_negative": 0, "precision": None, "recall": None, "skipped_not_applicable": 0},
        "final_verdict_agreement": _metric(0, 0),
        "activation_false_positive_rate": {"false_positives": 0, "eligible": 0, "rate": None, "unavailable": 0},
        "confidence_calibration": {"correct": 0, "evaluated": 0, "mean_absolute_error": None, "unavailable": 0, "_absolute_error_sum": 0},
    }
    case_reports = []
    metadata_records = []
    for case in case_list:
        matched = sorted(
            (record for record in records if _record_matches(case, record)),
            key=lambda record: (
                str(_metadata(record).get("run_id", "")),
                str(_metadata(record).get("agent_name", record.get("agent_name", ""))),
                str(record.get("id", "")),
                str(record.get("content", "")),
            ),
        )
        parsed = []
        valid_records = []
        rejection_count = 0
        artifact_errors = []
        for record in matched:
            totals["parse_semantic_rejection"]["total"] += 1
            content = record.get("content")
            metadata = _metadata(record)
            metadata_records.append({field: metadata.get(field) for field in _METADATA_FIELDS})
            if not isinstance(content, str):
                rejection_count += 1
                artifact_errors.append("artifact content is missing or not a string")
                continue
            try:
                output = parse_specialist_output(content)
            except (StockAnalysisValidationError, ValueError, TypeError) as exc:
                rejection_count += 1
                artifact_errors.append(str(exc))
                continue
            parsed.append(output)
            valid_records.append(record)
        totals["parse_semantic_rejection"]["rejected"] += rejection_count
        labels = case["labels"]
        packet = _packet_for_case(case, packet_map)
        valid_sources, invalid_sources, unavailable_sources = _source_status(parsed, packet)
        totals["source_id_validity"]["valid"] += valid_sources
        totals["source_id_validity"]["invalid"] += invalid_sources
        totals["source_id_validity"]["evaluated"] += valid_sources + invalid_sources
        totals["source_id_validity"]["unavailable"] += unavailable_sources
        claim_correct = claim_incorrect = claim_skipped = claim_unavailable = 0
        claim_index = {(output.agent_name.value, claim.claim_id): claim for output in parsed for claim in _output_claims(output)}
        for label in labels.get("claims", []):
            if _na(label):
                claim_skipped += 1
                continue
            claim = claim_index.get((label["agent_name"], label["claim_id"]))
            if claim is None:
                claim_incorrect += 1
                continue
            matches = True
            if label.get("expected_direction") is not None:
                matches &= getattr(claim.direction, "value", claim.direction) == label["expected_direction"]
            if label.get("expected_value") is not None:
                matches &= claim.value == label["expected_value"]
            if matches:
                claim_correct += 1
            else:
                claim_incorrect += 1
        row_correct = row_incorrect = row_skipped = 0
        row_index = {
            row.claim_id: row
            for output in parsed
            if output.management_credibility is not None
            for row in output.management_credibility.ledger
        }
        for label in labels.get("management_rows", []):
            if _na(label):
                row_skipped += 1
            elif label["claim_id"] in row_index and getattr(row_index[label["claim_id"]].result, "value", row_index[label["claim_id"]].result) == label["expected_result"]:
                row_correct += 1
            else:
                row_incorrect += 1
        for metric, correct, incorrect, skipped in (
            (totals["claim_label_agreement"], claim_correct, claim_incorrect, claim_skipped),
            (totals["management_row_classification_agreement"], row_correct, row_incorrect, row_skipped),
        ):
            metric["correct"] += correct
            metric["incorrect"] += incorrect
            metric["skipped_not_applicable"] += skipped
            metric["evaluated"] += correct + incorrect
        actual_conflicts = {
            conflict.rule_id
            for conflict in evaluate_specialist_conflicts(parsed, final_direction=_actual_final_verdict(valid_records, parsed))
        }
        expected_conflicts = set(labels.get("conflicts", {}).get("expected_triggered", []))
        explicitly_not = set(labels.get("conflicts", {}).get("expected_not_triggered", []))
        conflict_metric = totals["conflict_precision_recall"]
        if "conflicts" not in labels or _na(labels.get("conflicts")):
            conflict_metric["skipped_not_applicable"] += len(CONFLICT_RULES)
        else:
            conflict_metric["true_positive"] += len(actual_conflicts & expected_conflicts)
            conflict_metric["false_positive"] += len((actual_conflicts - expected_conflicts) & (expected_conflicts | explicitly_not))
            conflict_metric["false_negative"] += len(expected_conflicts - actual_conflicts)
            conflict_metric["skipped_not_applicable"] += max(0, len(CONFLICT_RULES) - len(expected_conflicts) - len(explicitly_not))
        source_label = labels.get("source_validity", "not_applicable")
        source_actual = "unavailable" if unavailable_sources else ("invalid_present" if invalid_sources else "all_valid")
        if _na(source_label):
            totals["source_id_validity"]["label_skipped_not_applicable"] += 1
        elif source_actual == "unavailable":
            pass
        else:
            totals["source_id_validity"]["label_correct"] += int(source_actual == source_label)
            totals["source_id_validity"]["label_incorrect"] += int(source_actual != source_label)
        final_expected = labels.get("final_verdict", "not_applicable")
        final_actual = _actual_final_verdict(valid_records, parsed)
        final_correct = final_incorrect = final_unavailable = final_skipped = 0
        if _na(final_expected):
            final_skipped = 1
        elif final_actual is None:
            final_unavailable = 1
        elif final_actual == final_expected:
            final_correct = 1
        else:
            final_incorrect = 1
        totals["final_verdict_agreement"]["correct"] += final_correct
        totals["final_verdict_agreement"]["incorrect"] += final_incorrect
        totals["final_verdict_agreement"]["skipped_not_applicable"] += final_skipped
        totals["final_verdict_agreement"]["unavailable"] += final_unavailable
        activation_expected = labels.get("activation", "not_applicable")
        activation_actual = final_actual in {"activated_case", "investable"} if final_actual is not None else None
        if _na(activation_expected):
            pass
        elif activation_actual is None:
            totals["activation_false_positive_rate"]["unavailable"] += 1
        else:
            totals["activation_false_positive_rate"]["eligible"] += 1
            totals["activation_false_positive_rate"]["false_positives"] += int(activation_actual and not activation_expected)
        confidence_expected = labels.get("confidence", "not_applicable")
        confidence_actual = next((getattr(output.confidence, "value", output.confidence) for output in reversed(parsed)), None)
        if _na(confidence_expected):
            pass
        elif confidence_actual is None:
            totals["confidence_calibration"]["unavailable"] += 1
        else:
            confidence_metric = totals["confidence_calibration"]
            confidence_metric["evaluated"] += 1
            confidence_metric["correct"] += int(confidence_actual == confidence_expected)
            confidence_metric["_absolute_error_sum"] += abs(
                _CONFIDENCE_RANK[confidence_actual] - _CONFIDENCE_RANK[confidence_expected]
            )
        case_reports.append({
            "case_id": case["case_id"],
            "artifact_count": len(matched),
            "accepted_count": len(parsed),
            "rejected_count": rejection_count,
            "artifact_errors": artifact_errors,
            "packet_status": "available" if packet is not None and not packet.get("_packet_hash_mismatch") else "unavailable",
            "metadata": [{field: _metadata(record).get(field) for field in _METADATA_FIELDS} for record in valid_records],
        })
    for metric in totals.values():
        if isinstance(metric, dict) and "total" in metric:
            metric["rejection_rate"] = metric["rejected"] / metric["total"] if metric["total"] else None
        if isinstance(metric, dict) and "evaluated" in metric and "agreement_rate" in metric:
            metric["agreement_rate"] = metric["correct"] / metric["evaluated"] if metric["evaluated"] else None
    source = totals["source_id_validity"]
    source["validity_rate"] = source["valid"] / source["evaluated"] if source["evaluated"] else None
    source_label_evaluated = source["label_correct"] + source["label_incorrect"]
    source["label_agreement_rate"] = source["label_correct"] / source_label_evaluated if source_label_evaluated else None
    conflict = totals["conflict_precision_recall"]
    conflict["precision"] = conflict["true_positive"] / (conflict["true_positive"] + conflict["false_positive"]) if conflict["true_positive"] + conflict["false_positive"] else None
    conflict["recall"] = conflict["true_positive"] / (conflict["true_positive"] + conflict["false_negative"]) if conflict["true_positive"] + conflict["false_negative"] else None
    activation = totals["activation_false_positive_rate"]
    activation["rate"] = activation["false_positives"] / activation["eligible"] if activation["eligible"] else None
    confidence = totals["confidence_calibration"]
    confidence["mean_absolute_error"] = (
        confidence["_absolute_error_sum"] / confidence["evaluated"]
        if confidence["evaluated"]
        else None
    )
    confidence.pop("_absolute_error_sum")
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "case_count": len(case_list),
        "artifact_count": len(records),
        "metrics": totals,
        "cases": case_reports,
        "metadata_fields": {
            field: {
                "available": sum(record.get(field) is not None for record in metadata_records),
                "unavailable": sum(record.get(field) is None for record in metadata_records),
            }
            for field in _METADATA_FIELDS
        },
    }


def format_evaluation_report(report: Mapping) -> str:
    metrics = report["metrics"]
    rejection = metrics["parse_semantic_rejection"]
    source = metrics["source_id_validity"]
    claims = metrics["claim_label_agreement"]
    conflicts = metrics["conflict_precision_recall"]
    verdict = metrics["final_verdict_agreement"]
    rate = lambda value: "n/a" if value is None else f"{value:.1%}"
    return "\n".join(
        [
            f"Specialist evaluation: {report['case_count']} cases, {report['artifact_count']} artifacts",
            f"parse/semantic rejection: {rejection['rejected']}/{rejection['total']} ({rate(rejection['rejection_rate'])})",
            f"source-ID validity: {source['valid']}/{source['evaluated']} ({rate(source['validity_rate'])}); unavailable={source['unavailable']}",
            f"claim label agreement: {claims['correct']}/{claims['evaluated']} ({rate(claims['agreement_rate'])}); n/a={claims['skipped_not_applicable']}",
            f"conflicts: precision={rate(conflicts['precision'])}, recall={rate(conflicts['recall'])}",
            f"final verdict agreement: {verdict['correct']}/{verdict['evaluated']} ({rate(verdict['agreement_rate'])})",
            "Metadata unavailable fields are reported in metadata_fields; no missing values are inferred.",
        ]
    )


def specialist_evaluation_json_schema() -> dict:
    """Machine-readable top-level schema summary for fixture authors."""
    return {
        "type": "object",
        "required": ["schema_version", "cases"],
        "properties": {
            "schema_version": {"const": CASES_SCHEMA_VERSION},
            "cases": {"type": "array"},
        },
        "additionalProperties": False,
    }
