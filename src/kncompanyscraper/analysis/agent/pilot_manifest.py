"""Validation and adaptation for the first three-company shadow pilot."""

from __future__ import annotations

import json
from typing import Mapping, Sequence

from kncompanyscraper.analysis.agent.specialist_evaluation import (
    MANIFEST_SCHEMA_VERSION,
)
from kncompanyscraper.analysis.agent.output_schema import SpecialistAgentName

PILOT_MANIFEST_SCHEMA_VERSION = "specialist-three-company-pilot-v1"
_SPECIALIST_NAMES = {agent.value for agent in SpecialistAgentName}


class PilotManifestError(ValueError):
    """Raised when a pilot selection is incomplete or ambiguous."""


def validate_three_company_pilot(document: Mapping) -> dict:
    """Validate a filled pilot manifest; labels remain external human input."""
    if not isinstance(document, Mapping):
        raise PilotManifestError("pilot manifest must be an object")
    if document.get("schema_version") != PILOT_MANIFEST_SCHEMA_VERSION:
        raise PilotManifestError("unsupported three-company pilot schema version")
    companies = document.get("companies")
    if not isinstance(companies, list) or len(companies) != 3:
        raise PilotManifestError("pilot manifest must contain exactly three companies")
    seen_cases = set()
    seen_companies = set()
    normalized = []
    for index, item in enumerate(companies):
        if not isinstance(item, Mapping):
            raise PilotManifestError(f"pilot company {index} must be an object")
        required = ("case_id", "company_id", "ticker", "packet_ref", "packet_hash", "labels_ref")
        if any(not item.get(field) for field in required):
            raise PilotManifestError(f"pilot company {index} is missing a selection or labels reference")
        case_id = item["case_id"]
        company_id = item["company_id"]
        packet_hash = item["packet_hash"]
        if not isinstance(case_id, str) or case_id in seen_cases:
            raise PilotManifestError("pilot case_id values must be distinct non-empty strings")
        if not isinstance(company_id, int) or company_id in seen_companies:
            raise PilotManifestError("pilot company_id values must be distinct integers")
        if (
            not isinstance(item["ticker"], str)
            or not isinstance(item["packet_ref"], str)
            or not isinstance(item["labels_ref"], str)
            or not isinstance(packet_hash, str)
            or len(packet_hash) != 64
            or any(char not in "0123456789abcdef" for char in packet_hash)
        ):
            raise PilotManifestError(f"pilot company {index} has invalid identity fields")
        for tier in ("best_run_id", "candidate_run_id"):
            if tier in item and item[tier] is not None and (
                not isinstance(item[tier], str) or not item[tier]
            ):
                raise PilotManifestError(f"pilot company {index} has an invalid {tier}")
        seen_cases.add(case_id)
        seen_companies.add(company_id)
        normalized.append(dict(item))
    return {**document, "companies": normalized}


def build_evaluation_manifest(
    pilot: Mapping,
    cases: Sequence[Mapping],
    best_artifacts: Mapping | Sequence,
    candidate_artifacts: Mapping | Sequence,
) -> dict:
    """Adapt pilot selections to the existing per-agent paired manifest."""
    pilot = validate_three_company_pilot(pilot)
    cases_by_id = {case.get("case_id"): case for case in cases}
    records_by_tier = {
        "best": _records(best_artifacts),
        "candidate": _records(candidate_artifacts),
    }
    assignments = []
    for company in pilot["companies"]:
        case = cases_by_id.get(company["case_id"])
        if case is None:
            raise PilotManifestError(f"pilot case is not present in evaluation cases: {company['case_id']}")
        if (
            case.get("company_id") != company["company_id"]
            or case.get("ticker") != company["ticker"]
            or case.get("packet_hash") != company["packet_hash"]
        ):
            raise PilotManifestError(f"pilot identity does not match case: {company['case_id']}")
        for tier, field in (("best", "best_run_id"), ("candidate", "candidate_run_id")):
            run_id = company.get(field)
            if not run_id:
                raise PilotManifestError(f"pilot company {company['case_id']} needs {field}")
            agents = set()
            for record in records_by_tier[tier]:
                metadata = record.get("metadata") or {}
                if (
                    metadata.get("result_scope") != "case"
                    and metadata.get("run_id") == run_id
                    and _packet_hash(record) == company["packet_hash"]
                ):
                    agent = metadata.get("agent_name")
                    if agent in _SPECIALIST_NAMES:
                        agents.add(agent)
            for agent in sorted(agents):
                assignments.append({
                    "tier": tier,
                    "case_id": company["case_id"],
                    "company_id": company["company_id"],
                    "ticker": company["ticker"],
                    "packet_hash": company["packet_hash"],
                    "run_id": run_id,
                    "agent_name": agent,
                })
    if not assignments:
        raise PilotManifestError("pilot artifacts contain no specialist assignments")
    return {"schema_version": MANIFEST_SCHEMA_VERSION, "assignments": assignments}


def _records(value):
    if isinstance(value, Mapping):
        records = value.get("artifacts")
    else:
        records = value
    if not isinstance(records, list):
        raise PilotManifestError("pilot artifacts must be a list or artifact bundle")
    return [record for record in records if isinstance(record, Mapping)]


def _packet_hash(record):
    metadata = record.get("metadata") or {}
    value = metadata.get("packet_hash") or record.get("packet_hash")
    if isinstance(value, str):
        return value
    content = record.get("content")
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
        return payload.get("packet_hash") if isinstance(payload, Mapping) else None
    return None
