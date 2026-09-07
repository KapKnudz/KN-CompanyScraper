import json
from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper.analysis.agent.output_schema import (
    ManagementCredibilityCoverage,
    ManagementCredibilitySpecialistOutput,
    SpecialistAgentName,
    SpecialistConfidence,
    SpecialistOutput,
    SpecialistStatus,
    specialist_output_json_schema,
)
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_specialist_output,
)
from kncompanyscraper.repositories.analysis_repository import AnalysisRepository


def _claim(*, claim_id="margin.margin_state", direction="unassessable", source_ids=None):
    return {
        "claim_id": claim_id,
        "domain": "margin",
        "predicate": "assessment",
        "value": None,
        "direction": direction,
        "source_ids": source_ids or [],
        "limitation_codes": [],
        "depends_on_claim_ids": [],
    }


def _management_payload(quarters=0, confidence_cap=None):
    if confidence_cap is None:
        confidence_cap = "low" if quarters < 8 else "high"
    tier = "no_ledger" if quarters < 4 else "partial_coverage" if quarters < 8 else "full_coverage"
    state = (
        "insufficient_for_pattern_recognition"
        if quarters < 4
        else "partial_coverage"
        if quarters < 8
        else "full_coverage"
    )
    return {
        "schema_version": "specialist-output-v1",
        "run_id": "run-1",
        "agent_name": "management_credibility",
        "company_id": 42,
        "ticker": "TEST",
        "evidence_as_of": "2026-08-16",
        "status": "complete",
        "confidence": "low",
        "confidence_cap": confidence_cap,
        "claims": [],
        "missing_information": [],
        "packet_hash": "a" * 64,
        "management_credibility": {
            "coverage": {
                "coverage_tier": tier,
                "coverage_state": state,
                "quarters_covered": quarters,
                "data_source_type": "primary_reports",
                "eligible_claim_count": 0,
                "assessed_claim_count": 0,
                "pending_claim_count": 0,
                "omitted_claim_count": 0,
                "omission_reasons": [],
                "confidence_cap": confidence_cap,
            },
            "pattern_state": "unassessable",
            "ledger": [],
            "claims": [],
        },
    }


def test_valid_specialist_output_parses_to_typed_objects():
    parsed = parse_specialist_output(json.dumps(_management_payload()))

    assert parsed.agent_name is SpecialistAgentName.MANAGEMENT_CREDIBILITY
    assert parsed.status is SpecialistStatus.COMPLETE
    assert isinstance(parsed.management_credibility, ManagementCredibilitySpecialistOutput)
    assert parsed.management_credibility.coverage.quarters_covered == 0
    assert specialist_output_json_schema("management_credibility")["properties"][
        "management_credibility"
    ]["required"] == ["coverage", "pattern_state", "ledger", "claims"]


def _first_wave_payload(agent_name):
    if agent_name == "management_credibility":
        return _management_payload()
    payload = {
        "schema_version": "specialist-output-v1",
        "run_id": "run-1",
        "agent_name": agent_name,
        "company_id": 42,
        "ticker": "TEST",
        "evidence_as_of": "2026-08-16",
        "status": "complete",
        "confidence": "low",
        "confidence_cap": "low",
        "claims": [],
        "missing_information": [],
        "packet_hash": "a" * 64,
    }
    payload[agent_name] = {
        "business_model": {
            "revenue_model_types": ["subscription"],
            "recurring_revenue_profile": "partial",
            "operating_leverage": "credible",
            "circle_of_competence": "inside",
            "profitability_state": "profitable",
            "claims": [],
        },
        "margin": {
            "margin_state": "early_evidence",
            "current_ebit_margin": 0.08,
            "defensible_peak_ebit_margin": 0.12,
            "mechanism": "fixed-cost absorption",
            "supporting_source_ids": ["financial:margin"],
            "contrary_source_ids": [],
            "margin_dependency": "secondary",
        },
        "insider_ownership": {
            "insider_signal": "none",
            "signal_strength": "none",
            "flow_effect": "unassessable",
            "event_claims": [],
            "data_coverage": {
                "insider": "empty",
                "ownership": "partial",
                "liquidity": "available",
            },
        },
        "growth_valuation": {
            "growth_state": "supported",
            "revenue_mechanism": "recurring",
            "reverse_dcf_assessment": "demanding",
            "engine_dependency": "fundamental",
            "scenario_bundles": [],
            "claims": [],
        },
    }[agent_name]
    return payload


@pytest.mark.parametrize(
    "agent_name",
    [
        "business_model",
        "management_credibility",
        "margin",
        "insider_ownership",
        "growth_valuation",
    ],
)
def test_first_wave_representative_outputs_parse_for_their_domain(agent_name):
    parsed = parse_specialist_output(json.dumps(_first_wave_payload(agent_name)))

    assert parsed.agent_name.value == agent_name
    assert getattr(parsed, agent_name) is not None


def test_specialist_agent_name_cannot_use_another_domain_payload():
    payload = _first_wave_payload("business_model")
    payload["margin"] = {
        "margin_state": "unassessable",
        "current_ebit_margin": None,
        "defensible_peak_ebit_margin": None,
        "mechanism": "",
        "supporting_source_ids": [],
        "contrary_source_ids": [],
        "margin_dependency": "none",
    }

    with pytest.raises(StockAnalysisValidationError):
        parse_specialist_output(json.dumps(payload))


def test_complete_specialist_output_requires_matching_domain_payload():
    payload = _management_payload()
    payload.pop("management_credibility")

    with pytest.raises(
        StockAnalysisValidationError,
        match="complete specialist output requires management_credibility payload",
    ):
        parse_specialist_output(json.dumps(payload))


@pytest.mark.parametrize("field", ["status", "agent_name"])
def test_specialist_closed_enums_reject_invalid_values(field):
    payload = _management_payload()
    payload[field] = "not-a-valid-enum"

    with pytest.raises(StockAnalysisValidationError):
        parse_specialist_output(json.dumps(payload))


def test_specialist_rejects_duplicate_claim_ids():
    payload = _management_payload()
    payload["claims"] = [_claim(), _claim()]

    with pytest.raises(StockAnalysisValidationError, match="duplicate specialist claim ID"):
        parse_specialist_output(json.dumps(payload))


def test_assessable_specialist_claim_requires_source_ids():
    payload = _management_payload()
    payload["claims"] = [_claim(direction="positive")]

    with pytest.raises(StockAnalysisValidationError, match="requires source_ids"):
        parse_specialist_output(json.dumps(payload))


def test_unassessable_specialist_claim_may_omit_source_ids():
    payload = _management_payload()
    payload["claims"] = [_claim()]

    assert parse_specialist_output(json.dumps(payload)).claims[0].source_ids == []


@pytest.mark.parametrize(
    ("quarters", "cap"), [(0, "low"), (3, "low"), (4, "medium"), (7, "medium"), (8, "high"), (12, "high")]
)
def test_management_coverage_enforces_quarter_confidence_caps(quarters, cap):
    parsed = parse_specialist_output(json.dumps(_management_payload(quarters, cap)))

    assert parsed.management_credibility.coverage.confidence_cap == cap


def test_management_coverage_rejects_high_cap_for_partial_history():
    with pytest.raises(StockAnalysisValidationError, match="4-7 quarters"):
        parse_specialist_output(json.dumps(_management_payload(4, "high")))


def test_management_coverage_cap_limits_specialist_confidence():
    payload = _management_payload(0, "low")
    payload["confidence"] = "high"
    payload["confidence_cap"] = "high"

    with pytest.raises(
        StockAnalysisValidationError,
        match="specialist confidence cannot exceed management coverage confidence_cap",
    ):
        parse_specialist_output(json.dumps(payload))


def _management_ledger_row(*, result, observed_outcome):
    return {
        "quarter": "2026-Q1",
        "claim_id": "management.claim",
        "claim": "Margins will improve.",
        "expected_timing": "2026-Q2",
        "observed_outcome": observed_outcome,
        "result": result,
        "claim_source_ids": ["report:claim"],
        "outcome_source_ids": ["report:outcome"],
        "source_ids": ["report:claim", "report:outcome"],
        "notes": [],
    }


def _schema_enum(schema, *path):
    value = schema
    for key in path:
        value = value["items"] if key == "items" else value["properties"][key]
    return set(value["enum"])


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (("status",), {"complete", "insufficient_evidence", "failed"}),
        (("agent_name",), {
            "business_model",
            "management_credibility",
            "margin",
            "insider_ownership",
            "growth_valuation",
            "sell_conditions",
        }),
        (
            ("management_credibility", "coverage", "coverage_tier"),
            {"no_ledger", "partial_coverage", "full_coverage"},
        ),
        (
            ("management_credibility", "coverage", "data_source_type"),
            {"none", "primary_reports", "company_releases", "mixed_primary", "secondary_only"},
        ),
        (
            ("management_credibility", "pattern_state"),
            {"supportive", "mixed", "weak", "unassessable"},
        ),
        (
            ("management_credibility", "ledger", "items", "result"),
            {"kept", "delayed", "missed", "unverifiable", "too_vague_to_test", "external_shock"},
        ),
    ],
)
def test_specialist_schema_exposes_exact_closed_enums(path, expected):
    schema = specialist_output_json_schema("management_credibility")

    assert _schema_enum(schema, *path) == expected


def test_specialist_parser_rejects_nested_closed_enum_values():
    payload = _management_payload()
    payload["management_credibility"]["coverage"]["coverage_tier"] = "invalid"

    with pytest.raises(StockAnalysisValidationError):
        parse_specialist_output(json.dumps(payload))


def test_management_coverage_counts_must_match_ledger_rows():
    payload = _management_payload()
    payload["management_credibility"]["ledger"] = [
        _management_ledger_row(result="kept", observed_outcome="Margins improved.")
    ]

    with pytest.raises(
        StockAnalysisValidationError,
        match="assessed_claim_count must match ledger rows",
    ):
        parse_specialist_output(json.dumps(payload))


def test_management_ledger_rejects_blank_claims():
    payload = _management_payload()
    row = _management_ledger_row(result="kept", observed_outcome="Margins improved.")
    row["claim"] = "  "
    payload["management_credibility"]["ledger"] = [row]
    payload["management_credibility"]["coverage"].update(
        eligible_claim_count=1,
        assessed_claim_count=1,
    )

    with pytest.raises(
        StockAnalysisValidationError,
        match="management ledger claim management.claim cannot be empty",
    ):
        parse_specialist_output(json.dumps(payload))


def test_management_ledger_requires_outcome_for_assessed_rows():
    payload = _management_payload()
    payload["management_credibility"]["ledger"] = [
        _management_ledger_row(result="kept", observed_outcome=None)
    ]
    payload["management_credibility"]["coverage"].update(
        eligible_claim_count=1,
        assessed_claim_count=1,
    )

    with pytest.raises(
        StockAnalysisValidationError,
        match="requires observed_outcome",
    ):
        parse_specialist_output(json.dumps(payload))


def test_management_ledger_rejects_outcome_for_non_assessable_rows():
    payload = _management_payload()
    payload["management_credibility"]["ledger"] = [
        _management_ledger_row(
            result="too_vague_to_test", observed_outcome="Not testable."
        )
    ]
    payload["management_credibility"]["coverage"].update(
        eligible_claim_count=1,
        pending_claim_count=1,
    )

    with pytest.raises(
        StockAnalysisValidationError,
        match="cannot retain observed_outcome",
    ):
        parse_specialist_output(json.dumps(payload))


def test_management_ledger_rejects_outcome_sources_for_non_assessable_rows():
    payload = _management_payload()
    payload["management_credibility"]["ledger"] = [
        _management_ledger_row(result="too_vague_to_test", observed_outcome=None)
    ]
    payload["management_credibility"]["coverage"].update(
        eligible_claim_count=1,
        pending_claim_count=1,
    )

    with pytest.raises(
        StockAnalysisValidationError,
        match="cannot retain outcome_source_ids",
    ):
        parse_specialist_output(json.dumps(payload))


def test_management_coverage_rejects_blank_omission_reasons():
    payload = _management_payload()
    payload["management_credibility"]["coverage"].update(
        eligible_claim_count=1,
        omitted_claim_count=1,
        omission_reasons=["  "],
    )

    with pytest.raises(
        StockAnalysisValidationError,
        match="omission reasons cannot be empty",
    ):
        parse_specialist_output(json.dumps(payload))


def test_specialist_output_serializes_and_round_trips():
    parsed = parse_specialist_output(json.dumps(_management_payload()))
    serialized = json.dumps(parsed.to_dict())

    assert parse_specialist_output(serialized).packet_hash == "a" * 64


def test_specialist_artifact_uses_existing_raw_storage_metadata():
    cursor = MagicMock()
    cursor.fetchone.return_value = (77,)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection,
    ):
        artifact_id = AnalysisRepository().save_specialist_artifact(
            42,
            json.dumps(_management_payload()),
            "specialist-model",
            agent_name="management_credibility",
            run_id="run-1",
            packet_hash="a" * 64,
            metadata={"attempt": 1},
        )

    assert artifact_id == 77
    params = cursor.execute.call_args.args[1]
    assert params[3].adapted == {
        "validation_status": "pending",
        "attempt": 1,
        "analysis_mode": "specialist",
        "agent_name": "management_credibility",
        "run_id": "run-1",
        "packet_hash": "a" * 64,
        "artifact_type": "specialist_output",
    }


def test_existing_qualitative_contract_remains_separate():
    result = SpecialistOutput(
        schema_version="specialist-output-v1",
        run_id="run-1",
        agent_name=SpecialistAgentName.MANAGEMENT_CREDIBILITY,
        company_id=42,
        ticker="TEST",
        evidence_as_of="2026-08-16",
        status=SpecialistStatus.COMPLETE,
        confidence=SpecialistConfidence.LOW,
        confidence_cap=SpecialistConfidence.LOW,
        claims=[],
        missing_information=[],
        packet_hash="a" * 64,
    )
    assert "verdict" not in result.to_dict()
