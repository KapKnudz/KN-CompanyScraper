"""Reviewable specialist evaluation cases and deterministic comparison metrics.

This module is intentionally read-only: it evaluates stored artifacts against
human-authored labels and never participates in production verdict selection.
"""

from __future__ import annotations

import json
from dataclasses import is_dataclass
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
from kncompanyscraper.analysis.agent.output_schema import (
    ManagementLedgerResult,
    SpecialistAgentName,
    SpecialistClaimDirection,
)
from kncompanyscraper.analysis.agent.specialist_conflicts import (
    evaluate_specialist_conflicts,
)

CASES_SCHEMA_VERSION = "specialist-evaluation-cases-v1"
REPORT_SCHEMA_VERSION = "specialist-evaluation-report-v1"
CASE_RESULT_SCHEMA_VERSION = "specialist-case-result-v1"
PAIRED_REPORT_SCHEMA_VERSION = "specialist-evaluation-pair-v1"
MANIFEST_SCHEMA_VERSION = "specialist-evaluation-manifest-v1"
CONFLICT_RULES = (
    "margin_vs_sell_condition",
    "insider_vs_credibility_record",
    "circle_of_competence_vs_valuation",
    "multiple_expansion_vs_activation",
)
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_SPECIALIST_AGENT_NAMES = {agent.value for agent in SpecialistAgentName}
_SPECIALIST_CLAIM_DIRECTIONS = {direction.value for direction in SpecialistClaimDirection}
_MANAGEMENT_LEDGER_RESULTS = {result.value for result in ManagementLedgerResult}
_FINAL_VERDICTS = {"reject", "watch", "latent_case", "activated_case"}
_CONFLICT_REQUIRED_AGENTS = {
    "margin_vs_sell_condition": {"margin", "sell_conditions"},
    "insider_vs_credibility_record": {"management_credibility", "insider_ownership"},
    "circle_of_competence_vs_valuation": {"business_model", "growth_valuation"},
    "multiple_expansion_vs_activation": {"growth_valuation"},
}
_METADATA_FIELDS = (
    "run_id",
    "agent_name",
    "model",
    "tier",
    "prompt_hash",
    "packet_hash",
    "latency_ms",
    "tokens",
    "cost",
    "attempts",
    "repairs",
    "validation_status",
    "result_scope",
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
    seen_claim_labels = set()
    for index, label in enumerate(claims):
        _require(isinstance(label, Mapping), f"case {case_id}: claim label {index} must be an object")
        if not _na(label):
            _require(
                isinstance(label.get("agent_name"), str)
                and label["agent_name"] in _SPECIALIST_AGENT_NAMES,
                f"case {case_id}: claim label has an unknown agent_name",
            )
            _require(isinstance(label.get("claim_id"), str), f"case {case_id}: claim label needs claim_id")
            _require(
                ("expected_direction" in label and label["expected_direction"] is not None)
                or "expected_value" in label,
                f"case {case_id}: claim label needs expected_direction or expected_value",
            )
            claim_key = (label["agent_name"], label["claim_id"])
            _require(claim_key not in seen_claim_labels, f"case {case_id}: duplicate claim label")
            seen_claim_labels.add(claim_key)
            if "expected_direction" in label and label["expected_direction"] is not None:
                _require(
                    isinstance(label["expected_direction"], str)
                    and label["expected_direction"] in _SPECIALIST_CLAIM_DIRECTIONS,
                    f"case {case_id}: claim label has an unknown expected_direction",
                )
            if "expected_value" in label:
                _require(
                    label["expected_value"] is None
                    or (
                        isinstance(label["expected_value"], (str, int, float, bool))
                        and not isinstance(label["expected_value"], (list, dict))
                    ),
                    f"case {case_id}: claim label expected_value must be a scalar or null",
                )
    rows = labels.get("management_rows", [])
    _require(isinstance(rows, list), f"case {case_id}: labels.management_rows must be a list")
    seen_row_labels = set()
    for index, label in enumerate(rows):
        _require(isinstance(label, Mapping), f"case {case_id}: management row label {index} must be an object")
        if not _na(label):
            _require(isinstance(label.get("claim_id"), str), f"case {case_id}: management row needs claim_id")
            _require(label["claim_id"] not in seen_row_labels, f"case {case_id}: duplicate management row label")
            seen_row_labels.add(label["claim_id"])
            _require(
                isinstance(label.get("expected_result"), str)
                and label["expected_result"] in _MANAGEMENT_LEDGER_RESULTS,
                f"case {case_id}: management row has an unknown expected_result",
            )
    conflicts = labels.get("conflicts", {})
    _require(isinstance(conflicts, Mapping), f"case {case_id}: labels.conflicts must be an object")
    for key in ("expected_triggered", "expected_not_triggered"):
        values = conflicts.get(key, [])
        _require(isinstance(values, list), f"case {case_id}: conflicts.{key} must be a list")
        _require(
            all(isinstance(value, str) and value in CONFLICT_RULES for value in values),
            f"case {case_id}: conflicts.{key} contains an unknown rule",
        )
    expected_triggered = set(conflicts.get("expected_triggered", []))
    expected_not_triggered = set(conflicts.get("expected_not_triggered", []))
    _require(
        expected_triggered.isdisjoint(expected_not_triggered),
        f"case {case_id}: conflicts cannot be both triggered and not_triggered",
    )
    source = labels.get("source_validity", "not_applicable")
    _require(
        _na(source)
        or (isinstance(source, str) and source in {"all_valid", "invalid_present", "unavailable"}),
        f"case {case_id}: source_validity must be all_valid, invalid_present, or not_applicable",
    )
    activation = labels.get("activation", "not_applicable")
    _require(
        _na(activation) or isinstance(activation, bool),
        f"case {case_id}: activation must be boolean or not_applicable",
    )
    final_verdict = labels.get("final_verdict", "not_applicable")
    _require(
        _na(final_verdict)
        or (isinstance(final_verdict, str) and final_verdict in _FINAL_VERDICTS),
        f"case {case_id}: final_verdict is unknown",
    )
    confidence = labels.get("confidence", "not_applicable")
    if not _na(confidence):
        _require(isinstance(confidence, Mapping), f"case {case_id}: confidence must map agent names to labels")
        for agent_name, expected in confidence.items():
            _require(
                isinstance(agent_name, str) and agent_name in _SPECIALIST_AGENT_NAMES,
                f"case {case_id}: confidence contains an unknown agent",
            )
            _require(
                _na(expected)
                or (isinstance(expected, str) and expected in _CONFIDENCE_RANK),
                f"case {case_id}: confidence label must be low, medium, high, or not_applicable",
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
    if packet.get("company_id") != case["company_id"] or packet.get("ticker") != case["ticker"]:
        return {"_packet_identity_mismatch": True}
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


def _record_run_id(record: Mapping) -> Any:
    metadata_run_id = _metadata(record).get("run_id")
    if isinstance(metadata_run_id, str):
        return metadata_run_id
    content = record.get("content")
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    run_id = payload.get("run_id") if isinstance(payload, Mapping) else None
    return run_id if isinstance(run_id, str) else None


def _artifact_agent_name(record: Mapping) -> str | None:
    metadata_agent_name = _metadata(record).get("agent_name")
    if isinstance(metadata_agent_name, str) and metadata_agent_name in _SPECIALIST_AGENT_NAMES:
        return metadata_agent_name
    content = record.get("content")
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    agent_name = payload.get("agent_name") if isinstance(payload, Mapping) else None
    return agent_name if isinstance(agent_name, str) and agent_name in _SPECIALIST_AGENT_NAMES else None


def _record_matches(case: Mapping, record: Mapping) -> bool:
    if "_malformed" in record:
        return False
    metadata = _metadata(record)
    company_id = record.get("company_id", metadata.get("company_id"))
    if company_id is not None and company_id != case["company_id"]:
        return False
    if metadata.get("case_id", record.get("case_id")) not in (None, case["case_id"]):
        return False
    if case.get("run_id") is not None and _record_run_id(record) not in (None, case["run_id"]):
        return False
    return True


def _output_claims(output) -> list:
    claims = list(output.claims)
    domain = getattr(output, output.agent_name.value, None)
    if domain is not None:
        claims.extend(getattr(domain, "claims", []))
        claims.extend(getattr(domain, "event_claims", []))
    return claims


def _parse_case_level_result(record: Mapping, case: Mapping) -> tuple[dict | None, str | None]:
    metadata = _metadata(record)
    if metadata.get("validation_status") not in (None, "accepted"):
        return None, f"case-level artifact validation_status is {metadata['validation_status']!r}"
    if metadata.get("packet_hash") != case["packet_hash"]:
        return None, "case-level artifact metadata packet_hash must match evaluation case"
    if case.get("run_id") is not None and metadata.get("run_id") not in (None, case["run_id"]):
        return None, "case-level artifact metadata run_id does not match evaluation case"
    content = record.get("content")
    if not isinstance(content, str):
        return None, "case-level artifact content is missing or not a string"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None, "case-level artifact content is not valid JSON"
    if not isinstance(payload, Mapping):
        return None, "case-level artifact content must be an object"
    if payload.get("schema_version") != CASE_RESULT_SCHEMA_VERSION:
        return None, "unsupported case-level result schema version"
    if payload.get("company_id") != case["company_id"] or payload.get("ticker") != case["ticker"]:
        return None, "case-level result identity does not match evaluation case"
    if payload.get("packet_hash") != case["packet_hash"]:
        return None, "case-level result packet_hash must match evaluation case"
    final_verdict = payload.get("final_verdict")
    if not isinstance(final_verdict, str) or final_verdict not in _FINAL_VERDICTS:
        return None, "case-level result final_verdict is unknown"
    if metadata.get("final_verdict") not in (None, final_verdict):
        return None, "case-level result final_verdict disagrees with metadata"
    return dict(payload), None


def _actual_final_verdict(results: Sequence[Mapping]) -> str | None:
    if len(results) != 1:
        return None
    return results[0]["final_verdict"]


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


def _collect_source_ids(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        source_ids = []
        for key, item in value.items():
            if isinstance(key, str) and key.endswith("source_ids") and isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
                source_ids.extend(item)
            source_ids.extend(_collect_source_ids(item))
        return source_ids
    if is_dataclass(value):
        return _collect_source_ids(vars(value))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        source_ids = []
        for item in value:
            source_ids.extend(_collect_source_ids(item))
        return source_ids
    return []


def _source_status(outputs: Sequence[Any], packet: Mapping | None) -> tuple[int, int, int]:
    complete_outputs = [output for output in outputs if output.status.value == "complete"]
    unavailable_count = sum(output.status.value == "insufficient_evidence" for output in outputs)
    source_ids = _collect_source_ids(complete_outputs)
    if not source_ids:
        return 0, 0, unavailable_count + 1
    if packet is None or packet.get("_packet_hash_mismatch") or packet.get("_packet_identity_mismatch"):
        return 0, 0, unavailable_count + max(1, len(source_ids))
    catalog = packet.get("evidence_catalog") or build_evidence_catalog(packet.get("full_results", {}), packet.get("research_evidence", {}))
    valid = invalid = 0
    for source_id in source_ids:
        try:
            resolved = resolve_source_id(source_id, packet.get("full_results", {}), packet.get("research_evidence", {}), catalog=catalog)
            if (
                resolved in set(catalog.get("canonical_source_ids", []))
                or source_id.startswith("full_results.")
                or source_id.startswith("deterministic:")
            ):
                valid += 1
            else:
                invalid += 1
        except (SourcePathError, TypeError, AttributeError):
            invalid += 1
    return valid, invalid, unavailable_count


def _scalar_values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _unavailable_conflict_rules(
    outputs_by_agent: Mapping[str, Any],
    *,
    final_direction: str | None,
) -> set[str]:
    unavailable = {
        rule_id
        for rule_id, required_agents in _CONFLICT_REQUIRED_AGENTS.items()
        if any(
            outputs_by_agent.get(agent_name) is None
            or outputs_by_agent[agent_name].status.value != "complete"
            for agent_name in required_agents
        )
    }
    if final_direction is None:
        unavailable.add("multiple_expansion_vs_activation")
    return unavailable


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
    malformed_records = [record for record in records if "_malformed" in record]
    totals = {
        "parse_semantic_rejection": {"rejected": 0, "total": 0, "rejection_rate": None},
        "source_id_validity": {"valid": 0, "invalid": 0, "evaluated": 0, "unavailable": 0, "validity_rate": None, "label_correct": 0, "label_incorrect": 0, "label_skipped_not_applicable": 0, "label_agreement_rate": None},
        "claim_label_agreement": _metric(0, 0),
        "management_row_classification_agreement": _metric(0, 0),
        "conflict_precision_recall": {"true_positive": 0, "false_positive": 0, "false_negative": 0, "precision": None, "recall": None, "skipped_not_applicable": 0},
        "final_verdict_agreement": _metric(0, 0),
        "activation_false_positive_rate": {"false_positives": 0, "eligible": 0, "rate": None, "unavailable": 0},
        "activation_outcomes": {"true_positive": 0, "true_negative": 0, "false_positive": 0, "false_negative": 0, "correct": 0, "evaluated": 0, "unavailable": 0, "skipped_not_applicable": 0, "agreement_rate": None},
        "confidence_calibration": {"correct": 0, "evaluated": 0, "mean_absolute_error": None, "unavailable": 0, "by_agent": {}, "_absolute_error_sum": 0},
    }
    totals["parse_semantic_rejection"]["total"] += len(malformed_records)
    totals["parse_semantic_rejection"]["rejected"] += len(malformed_records)
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
        case_level_records = [
            record for record in matched if _metadata(record).get("result_scope") == "case"
        ]
        specialist_records = []
        invalid_case_scope_records = set()
        metadata_records.extend(
            {field: _metadata(record).get(field) for field in _METADATA_FIELDS}
            for record in matched
        )
        run_ids = {_record_run_id(record) for record in matched}
        run_ids.discard(None)
        ambiguous_run = case.get("run_id") is None and len(run_ids) > 1
        case_level_results = []
        case_level_errors = []
        if ambiguous_run:
            case_level_errors.append("multiple artifact run_ids require explicit case run_id selection")
        validated_case_level_records = []
        for record in case_level_records:
            result, error = _parse_case_level_result(record, case)
            if error is None:
                validated_case_level_records.append(record)
                case_level_results.append(result)
                continue
            try:
                parse_specialist_output(record.get("content"))
            except (StockAnalysisValidationError, ValueError, TypeError):
                case_level_errors.append(error)
                validated_case_level_records.append(record)
            else:
                specialist_records.append(record)
                invalid_case_scope_records.add(id(record))
        case_level_records = validated_case_level_records
        specialist_records.extend(
            record for record in matched if _metadata(record).get("result_scope") != "case"
        )
        if len(case_level_results) > 1:
            case_level_errors.append("multiple validated case-level results are ambiguous")
        parsed = []
        valid_records = []
        rejection_count = 0
        artifact_errors = []
        if ambiguous_run:
            artifact_errors.append("multiple artifact run_ids require explicit case run_id selection")
        for record in () if ambiguous_run else specialist_records:
            totals["parse_semantic_rejection"]["total"] += 1
            content = record.get("content")
            metadata = _metadata(record)
            if id(record) in invalid_case_scope_records:
                rejection_count += 1
                artifact_errors.append("artifact result_scope=case conflicts with specialist output content")
                continue
            if metadata.get("validation_status") not in (None, "accepted"):
                rejection_count += 1
                artifact_errors.append(f"artifact validation_status is {metadata['validation_status']!r}")
                continue
            if metadata.get("packet_hash") not in (None, case["packet_hash"]):
                rejection_count += 1
                artifact_errors.append("artifact metadata packet_hash does not match evaluation case")
                continue
            if case.get("run_id") is not None and metadata.get("run_id") not in (None, case["run_id"]):
                rejection_count += 1
                artifact_errors.append("artifact metadata run_id does not match evaluation case")
                continue
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
            if output.status.value == "failed":
                rejection_count += 1
                artifact_errors.append(f"artifact status is {output.status.value!r}")
                continue
            if (
                output.company_id != case["company_id"]
                or output.ticker != case["ticker"]
                or output.packet_hash != case["packet_hash"]
                or (case.get("run_id") is not None and output.run_id != case["run_id"])
                or (metadata.get("run_id") is not None and output.run_id != metadata["run_id"])
                or (metadata.get("agent_name") is not None and output.agent_name.value != metadata["agent_name"])
            ):
                rejection_count += 1
                artifact_errors.append("artifact identity does not match evaluation case")
                continue
            if any(existing.agent_name is output.agent_name for existing in parsed):
                rejection_count += 1
                artifact_errors.append(f"duplicate artifact for agent {output.agent_name.value!r}")
                continue
            parsed.append(output)
            valid_records.append(record)
        totals["parse_semantic_rejection"]["rejected"] += rejection_count
        labels = case["labels"]
        outputs_by_agent = {output.agent_name.value: output for output in parsed}
        available_outputs = [
            output for output in parsed if output.status.value == "complete"
        ]
        packet = _packet_for_case(case, packet_map)
        valid_sources, invalid_sources, unavailable_sources = _source_status(parsed, packet)
        totals["source_id_validity"]["valid"] += valid_sources
        totals["source_id_validity"]["invalid"] += invalid_sources
        totals["source_id_validity"]["evaluated"] += valid_sources + invalid_sources
        totals["source_id_validity"]["unavailable"] += unavailable_sources
        claim_correct = claim_incorrect = claim_skipped = claim_unavailable = 0
        claim_index = {(output.agent_name.value, claim.claim_id): claim for output in available_outputs for claim in _output_claims(output)}
        for label in labels.get("claims", []):
            if _na(label):
                claim_skipped += 1
                continue
            claim = claim_index.get((label["agent_name"], label["claim_id"]))
            if claim is None:
                if (
                    ambiguous_run
                    or label["agent_name"] not in outputs_by_agent
                    or outputs_by_agent[label["agent_name"]].status.value == "insufficient_evidence"
                ):
                    claim_unavailable += 1
                else:
                    claim_incorrect += 1
                continue
            matches = True
            if label.get("expected_direction") is not None:
                matches &= getattr(claim.direction, "value", claim.direction) == label["expected_direction"]
            if "expected_value" in label:
                matches &= _scalar_values_equal(claim.value, label["expected_value"])
            if matches:
                claim_correct += 1
            else:
                claim_incorrect += 1
        row_correct = row_incorrect = row_skipped = row_unavailable = 0
        row_index = {
            row.claim_id: row
            for output in available_outputs
            if output.management_credibility is not None
            for row in output.management_credibility.ledger
        }
        for label in labels.get("management_rows", []):
            if _na(label):
                row_skipped += 1
            elif label["claim_id"] in row_index and getattr(row_index[label["claim_id"]].result, "value", row_index[label["claim_id"]].result) == label["expected_result"]:
                row_correct += 1
            elif (
                ambiguous_run
                or SpecialistAgentName.MANAGEMENT_CREDIBILITY.value not in outputs_by_agent
                or outputs_by_agent[SpecialistAgentName.MANAGEMENT_CREDIBILITY.value].status.value == "insufficient_evidence"
            ):
                row_unavailable += 1
            else:
                row_incorrect += 1
        for metric, correct, incorrect, skipped, unavailable in (
            (totals["claim_label_agreement"], claim_correct, claim_incorrect, claim_skipped, claim_unavailable),
            (totals["management_row_classification_agreement"], row_correct, row_incorrect, row_skipped, row_unavailable),
        ):
            metric["correct"] += correct
            metric["incorrect"] += incorrect
            metric["skipped_not_applicable"] += skipped
            metric["unavailable"] += unavailable
            metric["evaluated"] += correct + incorrect
        case_final_verdict = (
            _actual_final_verdict(case_level_results)
            if not case_level_errors
            else None
        )
        unavailable_conflict_rules = _unavailable_conflict_rules(
            outputs_by_agent,
            final_direction=case_final_verdict,
        )
        if ambiguous_run:
            unavailable_conflict_rules = set(CONFLICT_RULES)
        actual_conflicts = {
            conflict.rule_id
            for conflict in evaluate_specialist_conflicts(available_outputs, final_direction=case_final_verdict)
            if conflict.rule_id not in unavailable_conflict_rules
        }
        expected_conflicts = set(labels.get("conflicts", {}).get("expected_triggered", []))
        explicitly_not = set(labels.get("conflicts", {}).get("expected_not_triggered", []))
        conflict_metric = totals["conflict_precision_recall"]
        if "conflicts" not in labels or _na(labels.get("conflicts")):
            conflict_metric["skipped_not_applicable"] += len(CONFLICT_RULES)
        else:
            scored_expected = expected_conflicts - unavailable_conflict_rules
            scored_not = explicitly_not - unavailable_conflict_rules
            conflict_metric["true_positive"] += len(actual_conflicts & scored_expected)
            conflict_metric["false_positive"] += len((actual_conflicts - scored_expected) & (scored_expected | scored_not))
            conflict_metric["false_negative"] += len(scored_expected - actual_conflicts)
            conflict_metric["skipped_not_applicable"] += len(unavailable_conflict_rules)
            conflict_metric["skipped_not_applicable"] += max(0, len(CONFLICT_RULES) - len(scored_expected) - len(scored_not) - len(unavailable_conflict_rules))
        source_label = labels.get("source_validity", "not_applicable")
        source_actual = "unavailable" if unavailable_sources else ("invalid_present" if invalid_sources else "all_valid")
        if _na(source_label):
            totals["source_id_validity"]["label_skipped_not_applicable"] += 1
        elif source_actual == "unavailable":
            totals["source_id_validity"]["label_correct"] += int(source_label == "unavailable")
        else:
            totals["source_id_validity"]["label_correct"] += int(source_actual == source_label)
            totals["source_id_validity"]["label_incorrect"] += int(source_actual != source_label)
        final_expected = labels.get("final_verdict", "not_applicable")
        final_actual = case_final_verdict
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
        activation_actual = final_actual == "activated_case" if final_actual is not None else None
        activation_outcomes = totals["activation_outcomes"]
        if _na(activation_expected):
            activation_outcomes["skipped_not_applicable"] += 1
        elif activation_actual is None:
            activation_outcomes["unavailable"] += 1
            totals["activation_false_positive_rate"]["unavailable"] += 1
        else:
            activation_outcomes["evaluated"] += 1
            if activation_expected and activation_actual:
                activation_outcomes["true_positive"] += 1
            elif not activation_expected and not activation_actual:
                activation_outcomes["true_negative"] += 1
            elif activation_actual:
                activation_outcomes["false_positive"] += 1
            else:
                activation_outcomes["false_negative"] += 1
            activation_outcomes["correct"] += int(activation_actual == activation_expected)
            if not activation_expected:
                totals["activation_false_positive_rate"]["eligible"] += 1
                totals["activation_false_positive_rate"]["false_positives"] += int(activation_actual)
        confidence_expected = labels.get("confidence", "not_applicable")
        if _na(confidence_expected):
            pass
        else:
            confidence_metric = totals["confidence_calibration"]
            for agent_name, expected in confidence_expected.items():
                if _na(expected):
                    continue
                agent_metric = confidence_metric["by_agent"].setdefault(
                    agent_name,
                    {"correct": 0, "evaluated": 0, "unavailable": 0, "mean_absolute_error": None, "_absolute_error_sum": 0},
                )
                output = outputs_by_agent.get(agent_name)
                if output is None or output.status.value != "complete":
                    confidence_metric["unavailable"] += 1
                    agent_metric["unavailable"] += 1
                    continue
                confidence_actual = getattr(output.confidence, "value", output.confidence)
                confidence_metric["evaluated"] += 1
                confidence_metric["correct"] += int(confidence_actual == expected)
                absolute_error = abs(_CONFIDENCE_RANK[confidence_actual] - _CONFIDENCE_RANK[expected])
                confidence_metric["_absolute_error_sum"] += absolute_error
                agent_metric["evaluated"] += 1
                agent_metric["correct"] += int(confidence_actual == expected)
                agent_metric["_absolute_error_sum"] += absolute_error
        agent_statuses = {
            output.agent_name.value: output.status.value for output in parsed
        }
        agent_metadata = {}
        for record in specialist_records:
            agent_name = _artifact_agent_name(record)
            if agent_name is None:
                continue
            agent_metadata.setdefault(agent_name, []).append(
                {field: _metadata(record).get(field) for field in _METADATA_FIELDS}
            )
            agent_statuses.setdefault(agent_name, "unavailable" if ambiguous_run else "rejected")
        case_reports.append({
            "case_id": case["case_id"],
            "packet_hash": case["packet_hash"],
            "artifact_count": len(matched),
            "accepted_count": len(parsed),
            "unavailable_count": sum(output.status.value == "insufficient_evidence" for output in parsed),
            "rejected_count": rejection_count,
            "rejection_status": "unavailable" if ambiguous_run else "scored",
            "artifact_errors": artifact_errors,
            "packet_status": "available" if packet is not None and not packet.get("_packet_hash_mismatch") and not packet.get("_packet_identity_mismatch") else "unavailable",
            "metadata": [{field: _metadata(record).get(field) for field in _METADATA_FIELDS} for record in specialist_records],
            "case_level_result": {
                "available": len(case_level_results) == 1 and not case_level_errors,
                "errors": case_level_errors,
                "metadata": [
                    {field: _metadata(record).get(field) for field in _METADATA_FIELDS}
                    for record in case_level_records
                ],
            },
            "agent_statuses": agent_statuses,
            "agent_metadata": agent_metadata,
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
    for agent_metric in confidence["by_agent"].values():
        agent_metric["mean_absolute_error"] = (
            agent_metric["_absolute_error_sum"] / agent_metric["evaluated"]
            if agent_metric["evaluated"]
            else None
        )
        agent_metric.pop("_absolute_error_sum")
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "case_count": len(case_list),
        "artifact_count": len(records),
        "malformed_artifact_count": len(malformed_records),
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


def _numeric_deltas(best: Any, candidate: Any) -> Any:
    if isinstance(best, Mapping) and isinstance(candidate, Mapping):
        deltas = {}
        for key in sorted(set(best) | set(candidate)):
            delta = _numeric_deltas(best.get(key), candidate.get(key))
            if delta is not None:
                deltas[key] = delta
        return deltas or None
    if (
        isinstance(best, (int, float))
        and not isinstance(best, bool)
        and isinstance(candidate, (int, float))
        and not isinstance(candidate, bool)
    ):
        return candidate - best
    return None


def _is_case_scoped_record(record: Mapping) -> bool:
    return _metadata(record).get("result_scope") == "case"


def _artifact_field(record: Mapping, field: str) -> Any:
    metadata = _metadata(record)
    value = record.get(field, metadata.get(field))
    if value is not None:
        return value
    content = record.get("content")
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    return payload.get(field) if isinstance(payload, Mapping) else None


def _artifact_packet_hash(record: Mapping) -> str | None:
    packet_hash = _artifact_field(record, "packet_hash")
    return packet_hash if isinstance(packet_hash, str) else None


def _validate_pair_manifest(
    manifest: Any,
    cases: Sequence[Mapping],
    best_records: Sequence[Mapping],
    candidate_records: Sequence[Mapping],
) -> dict:
    specialist_records = [
        ("best", record)
        for record in best_records
        if not _is_case_scoped_record(record)
    ] + [
        ("candidate", record)
        for record in candidate_records
        if not _is_case_scoped_record(record)
    ]
    if manifest is None:
        _require(not specialist_records, "paired specialist artifacts require an evaluation manifest")
        return {"agents": {"best": {}, "candidate": {}}, "runs": {"best": {}, "candidate": {}}}
    document = _load_json(manifest)
    _require(isinstance(document, Mapping), "evaluation manifest must be an object")
    _require(document.get("schema_version") == MANIFEST_SCHEMA_VERSION, "unsupported evaluation manifest schema version")
    raw_assignments = document.get("assignments")
    _require(isinstance(raw_assignments, list), "evaluation manifest must contain an assignments list")
    cases_by_id = {case["case_id"]: case for case in cases}
    assignments = []
    seen = {}
    agents = {"best": {}, "candidate": {}}
    runs = {"best": {}, "candidate": {}}
    for index, raw in enumerate(raw_assignments):
        _require(isinstance(raw, Mapping), f"manifest assignment {index} must be an object")
        tier = raw.get("tier")
        case_id = raw.get("case_id")
        run_id = raw.get("run_id")
        agent_name = raw.get("agent_name")
        _require(tier in {"best", "candidate"}, f"manifest assignment {index} has an unknown tier")
        _require(isinstance(case_id, str) and case_id in cases_by_id, f"manifest assignment {index} has an unknown case_id")
        _require(isinstance(run_id, str) and run_id, f"manifest assignment {index} needs run_id")
        _require(isinstance(agent_name, str) and agent_name in _SPECIALIST_AGENT_NAMES, f"manifest assignment {index} has an unknown agent_name")
        case = cases_by_id[case_id]
        _require(raw.get("company_id") == case["company_id"], f"manifest assignment {index} company_id does not match case")
        _require(raw.get("ticker") == case["ticker"], f"manifest assignment {index} ticker does not match case")
        _require(raw.get("packet_hash") == case["packet_hash"], f"manifest assignment {index} packet_hash does not match case")
        if case.get("run_id") is not None:
            _require(run_id == case["run_id"], f"manifest assignment {index} run_id does not match case")
        identity = (case_id, raw["packet_hash"], run_id, agent_name)
        _require(identity not in seen, f"manifest contains duplicate or conflicting assignment for {case_id}/{agent_name}/{run_id}")
        seen[identity] = tier
        selected_run = runs[tier].get(case_id)
        _require(
            selected_run in (None, run_id),
            f"manifest has conflicting {tier} run_id assignments for case {case_id}",
        )
        runs[tier][case_id] = run_id
        assignments.append(dict(raw))
        agents[tier].setdefault(case_id, set()).add(agent_name)
    cases_by_packet = {}
    for case in cases:
        cases_by_packet.setdefault(case["packet_hash"], []).append(case)
    for tier, record in specialist_records:
        packet_hash = _artifact_packet_hash(record)
        run_id = _record_run_id(record)
        agent_name = _artifact_agent_name(record)
        packet_cases = cases_by_packet.get(packet_hash, [])
        _require(
            len(packet_cases) == 1,
            f"{tier} specialist artifact must match one evaluation packet",
        )
        case_id = packet_cases[0]["case_id"]
        selected_run = runs[tier].get(case_id)
        _require(selected_run is not None, f"missing {tier} manifest run assignment for case {case_id}")
        if run_id != selected_run:
            continue
        matches = [
            assignment
            for assignment in assignments
            if assignment["tier"] == tier
            and assignment["packet_hash"] == packet_hash
            and assignment["run_id"] == run_id
            and assignment["agent_name"] == agent_name
        ]
        _require(
            len(matches) == 1,
            f"missing {tier} manifest assignment for specialist artifact {agent_name!r}/{run_id!r}/{packet_hash!r}",
        )
        metadata_tier = _metadata(record).get("tier")
        _require(metadata_tier in (None, tier), f"{tier} artifact tier metadata conflicts with manifest")
    return {"agents": agents, "runs": runs}


def compare_paired_specialist_evaluations(
    cases: str | Path | Mapping | Sequence,
    best_artifacts: str | Path | Mapping | Sequence,
    candidate_artifacts: str | Path | Mapping | Sequence,
    *,
    packets: str | Path | Mapping | Sequence | None = None,
    manifest: str | Path | Mapping | Sequence | None = None,
) -> dict:
    """Compare separate best-tier and candidate-tier evaluation runs."""
    case_list = load_cases(cases) if not isinstance(cases, list) else validate_cases_document({"schema_version": CASES_SCHEMA_VERSION, "cases": cases})
    best_records = _artifact_records(best_artifacts)
    candidate_records = _artifact_records(candidate_artifacts)
    manifest_data = _validate_pair_manifest(manifest, case_list, best_records, candidate_records)
    best_cases = [
        {**case, **({"run_id": manifest_data["runs"]["best"][case["case_id"]]} if case["case_id"] in manifest_data["runs"]["best"] else {})}
        for case in case_list
    ]
    candidate_cases = [
        {**case, **({"run_id": manifest_data["runs"]["candidate"][case["case_id"]]} if case["case_id"] in manifest_data["runs"]["candidate"] else {})}
        for case in case_list
    ]
    best_report = compare_specialist_evaluations(best_cases, best_artifacts, packets=packets)
    candidate_report = compare_specialist_evaluations(candidate_cases, candidate_artifacts, packets=packets)
    best_cases = {case["case_id"]: case for case in best_report["cases"]}
    candidate_cases = {case["case_id"]: case for case in candidate_report["cases"]}
    aligned_cases = []
    for case in case_list:
        case_id = case["case_id"]
        best_case = best_cases[case_id]
        candidate_case = candidate_cases[case_id]
        _require(best_case["packet_hash"] == case["packet_hash"], f"best-tier report packet mismatch for case {case_id}")
        _require(candidate_case["packet_hash"] == case["packet_hash"], f"candidate-tier report packet mismatch for case {case_id}")
        best_agents = set(best_case["agent_statuses"]) | manifest_data["agents"]["best"].get(case_id, set())
        candidate_agents = set(candidate_case["agent_statuses"]) | manifest_data["agents"]["candidate"].get(case_id, set())
        agent_names = sorted(best_agents | candidate_agents)
        aligned_cases.append({
            "case_id": case_id,
            "packet_hash": case["packet_hash"],
            "agents": {
                agent_name: {
                    "best_tier": best_case["agent_statuses"].get(agent_name, "unavailable"),
                    "candidate_tier": candidate_case["agent_statuses"].get(agent_name, "unavailable"),
                }
                for agent_name in agent_names
            },
        })
    return {
        "schema_version": PAIRED_REPORT_SCHEMA_VERSION,
        "case_count": len(case_list),
        "best_tier_report": best_report,
        "candidate_tier_report": candidate_report,
        "metric_deltas": _numeric_deltas(best_report["metrics"], candidate_report["metrics"]) or {},
        "cases": aligned_cases,
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
