"""Diagnostic cohort checks for individual thesis calibration."""

from hashlib import sha256
import json

from kncompanyscraper.analysis.policy_versions import THESIS_CALIBRATION_POLICY_VERSION
from kncompanyscraper.models.stored_analysis import as_stored_analysis


VERDICT_ORDER = {
    "reject": 0,
    "watch": 1,
    "latent_case": 2,
    "activated_case": 3,
}


def build_cohort_calibration_audit(
    analyses_by_company: dict[int, dict],
    revision_history_by_company: dict[int, list[dict]] | None = None,
) -> dict:
    """Return a read-only calibration report without changing any thesis."""
    rows = [_row(company_id, stored) for company_id, stored in analyses_by_company.items()]
    rows.sort(key=lambda row: row["company_id"])
    flags = []
    flags.extend(_ordinal_flags(rows))
    flags.extend(_label_collapse_flags(rows))
    flags.extend(_same_input_instability_flags(revision_history_by_company or {}))
    review_result = "no_issue_detected"
    if flags:
        review_result = (
            "unexplained_same_input_instability"
            if any(flag["type"] == "same_input_verdict_instability" for flag in flags)
            else "review_required"
        )
    return {
        "policy_version": THESIS_CALIBRATION_POLICY_VERSION,
        "diagnostic_only": True,
        "company_count": len(rows),
        "rows": rows,
        "flags": flags,
        "review_result": review_result,
    }


def _row(company_id: int, value: dict) -> dict:
    stored = as_stored_analysis(value)
    content = stored.content
    metadata = stored.metadata
    forward = stored.forward_scenario or {}
    bands = {
        item.get("case"): item
        for item in forward.get("bands", [])
        if isinstance(item, dict)
    }
    base = bands.get("base") or {}
    details = content.get("missing_information_details") or []
    packet_hash = (
        metadata.get("deterministic_context_sha256")
        or metadata.get("packet_sha256")
        or _legacy_packet_hash(content)
    )
    return {
        "company_id": company_id,
        "ticker": content.get("ticker"),
        "verdict": content.get("verdict"),
        "verdict_label": (
            f"{content.get('latent_case_type')}-latent"
            if content.get("verdict") == "latent_case"
            and content.get("latent_case_type")
            else content.get("verdict")
        ),
        "confidence": content.get("confidence"),
        "confidence_cap": (metadata.get("confidence_cap") or {}).get("cap"),
        "latent_case_type": content.get("latent_case_type"),
        "reverse_dcf_assessment": content.get(
            "reverse_dcf_expectation_assessment", "unassessable"
        ),
        "base_return_range": (
            [base.get("low_annualized_return"), base.get("high_annualized_return")]
            if base
            else None
        ),
        "required_return": (metadata.get("forward_scenario") or {}).get(
            "required_return"
        ),
        "core_limitation_count": sum(
            item.get("limitation_class") == "core" for item in details
        ),
        "activation_trigger": content.get("activation_trigger"),
        "activation_trigger_spec": content.get("activation_trigger_spec"),
        "packet_hash": packet_hash,
        "policy_version": metadata.get("policy_version"),
        "model": value.get("created_by") or metadata.get("model"),
        "evidence_cutoff": content.get("evidence_as_of")
        or metadata.get("evidence_as_of"),
        "resilience_assessment": (content.get("revenue_resilience") or {}).get(
            "assessment"
        ),
        "revenue_resilience": (content.get("revenue_resilience") or {}).get(
            "assessment"
        ),
        "qualitative_reason": _qualitative_reason(content),
    }


def _legacy_packet_hash(content: dict) -> str:
    packet = {
        "verdict": content.get("verdict"),
        "confidence": content.get("confidence"),
        "citations": content.get("citations", []),
        "missing_information": content.get("missing_information", []),
        "reverse_dcf": content.get("reverse_dcf_expectation_assessment"),
    }
    return "legacy:" + sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _ordinal_flags(rows: list[dict]) -> list[dict]:
    flags = []
    comparable = [
        row
        for row in rows
        if row["base_return_range"] is not None
        and row["required_return"] is not None
    ]
    for left_index, left in enumerate(comparable):
        for right in comparable[left_index + 1 :]:
            left_margin = _return_margin(left)
            right_margin = _return_margin(right)
            if left_margin is None or right_margin is None or left_margin == right_margin:
                continue
            more_positive, less_positive = (
                (left, right) if left_margin > right_margin else (right, left)
            )
            if VERDICT_ORDER.get(less_positive["verdict"], 0) > VERDICT_ORDER.get(
                more_positive["verdict"], 0
            ):
                flags.append(
                    {
                        "type": "ordinal_inconsistency",
                        "company_ids": [
                            less_positive["company_id"],
                            more_positive["company_id"],
                        ],
                        "message": (
                            "A lower base-return card has a more positive verdict; "
                            "review the qualitative reason and evidence packet."
                        ),
                        "qualitative_reason": less_positive["qualitative_reason"],
                    }
                )
    return flags


def _label_collapse_flags(rows: list[dict]) -> list[dict]:
    flags = []
    if len(rows) >= 3 and len({row["confidence"] for row in rows}) == 1:
        flags.append(
            {
                "type": "confidence_collapse",
                "message": "The cohort has one confidence label across every card.",
            }
        )
    if len(rows) >= 3:
        labels = {row["verdict_label"] for row in rows}
        if len(labels) == 1:
            flags.append(
                {
                    "type": "verdict_collapse",
                    "message": "The cohort has one displayed verdict label across every card.",
                }
            )
        resilience_labels = {row["resilience_assessment"] for row in rows}
        if len(resilience_labels) == 1:
            flags.append(
                {
                    "type": "resilience_collapse",
                    "message": "The cohort has one revenue-resilience label across every card.",
                    "label": next(iter(resilience_labels)),
                }
            )
    for left_index, left in enumerate(rows):
        for right in rows[left_index + 1 :]:
            if left["verdict_label"] != right["verdict_label"]:
                continue
            left_range = left["base_return_range"]
            right_range = right["base_return_range"]
            if (
                left_range
                and right_range
                and isinstance(left_range[0], (int, float))
                and isinstance(right_range[0], (int, float))
                and abs(left_range[0] - right_range[0]) >= 0.15
            ):
                flags.append(
                    {
                        "type": "materially_identical_label",
                        "company_ids": [left["company_id"], right["company_id"]],
                        "message": "Identical labels span materially different valuation or evidence inputs.",
                        "base_return_ranges": [left_range, right_range],
                        "reverse_dcf_assessments": [
                            left["reverse_dcf_assessment"],
                            right["reverse_dcf_assessment"],
                        ],
                    }
                )
    if (
        len(rows) >= 5
        and not any(row["verdict"] == "activated_case" for row in rows)
        and len({row["verdict_label"] for row in rows}) >= 3
        and len(
            {
                tuple(row["base_return_range"] or ())
                for row in rows
            }
        ) >= 3
    ):
        flags.append(
            {
                "type": "activated_case_absence",
                "message": (
                    "No activated case appears in a varied cohort; review whether "
                    "activation criteria or evidence coverage are over-calibrated."
                ),
                "warning_only": True,
            }
        )
    return flags


def _same_input_instability_flags(history_by_company: dict[int, list[dict]]) -> list[dict]:
    flags = []
    for company_id, revisions in history_by_company.items():
        by_packet = {}
        for revision in revisions:
            metadata = revision.get("metadata") or {}
            packet_hash = (
                revision.get("packet_hash")
                or revision.get("deterministic_context_sha256")
                or metadata.get("packet_hash")
                or metadata.get("deterministic_context_sha256")
            )
            content = revision.get("content") or {}
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    content = {}
            verdict = content.get("verdict")
            policy_version = (
                revision.get("policy_version")
                or metadata.get("policy_version")
                or metadata.get("thesis_calibration_policy_version")
            )
            if packet_hash and verdict:
                by_packet.setdefault((packet_hash, policy_version), set()).add(verdict)
        for (packet_hash, policy_version), verdicts in by_packet.items():
            if len(verdicts) > 1:
                flags.append(
                    {
                        "type": "same_input_verdict_instability",
                        "company_ids": [company_id],
                        "packet_hash": packet_hash,
                        "policy_version": policy_version,
                        "verdicts": sorted(verdicts),
                        "message": "Equivalent evidence packets produced different verdicts.",
                        "review_result": "unexplained_same_input_instability",
                    }
                )
    return flags


def _return_margin(row: dict) -> float | None:
    base = row.get("base_return_range")
    hurdle = row.get("required_return")
    if not base or hurdle is None:
        return None
    return base[0] - hurdle


def _qualitative_reason(content: dict) -> str:
    parts = [
        content.get("one_sentence_thesis"),
        content.get("reverse_dcf_expectation_rationale"),
        *(content.get("disconfirming_evidence") or []),
    ]
    return " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
