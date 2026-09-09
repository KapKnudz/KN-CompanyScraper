"""Constrained, non-authoritative Petter Hedborg shadow aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.agent_packet import (
    AgentCandidatePacket,
    build_evidence_catalog,
    resolve_source_id,
    serialize_packet,
)
from kncompanyscraper.analysis.agent.output_schema import (
    SpecialistAgentName,
    SpecialistOutput,
    THESIS_BREAK_TYPES,
    StockAnalysisResult,
)
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_qualitative_stock_analysis_result,
)
from kncompanyscraper.analysis.agent.specialist_conflicts import (
    SpecialistConflict,
    evaluate_specialist_conflicts,
)
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt, AgentPromptBuilder
from kncompanyscraper.analysis.agent.packet_measurement import measure_packet
from kncompanyscraper.analysis.agent.output_schema import (
    v3_qualitative_stock_analysis_json_schema,
)


FIRST_WAVE_NAMES = tuple(agent.value for agent in (
    SpecialistAgentName.BUSINESS_MODEL,
    SpecialistAgentName.MANAGEMENT_CREDIBILITY,
    SpecialistAgentName.MARGIN,
    SpecialistAgentName.INSIDER_OWNERSHIP,
    SpecialistAgentName.GROWTH_VALUATION,
))
ALL_SPECIALIST_NAMES = FIRST_WAVE_NAMES + (SpecialistAgentName.SELL_CONDITIONS.value,)
PRECEDENCE_APPLIED = (
    "evidence_readiness",
    "understandability_circle_of_competence",
    "fundamental_business_growth_margin_case",
    "deterministic_valuation_reverse_dcf",
    "management_confidence_adjustment",
    "insider_ownership_flows_timing_research_priority",
    "causal_sell_discipline",
)

_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_SELL_RECORD_DOMAINS = {
    "revenue_or_demand": {"revenue", "risk"},
    "margin_or_execution": {"margin", "risk"},
    "balance_sheet_or_dilution": {"balance_sheet", "risk"},
    "management_credibility": {"management", "risk"},
    "valuation_overshoot": {"valuation", "risk"},
    "superior_evidence_or_opportunity": {"business_model", "risk"},
}


@dataclass(frozen=True)
class AggregatorInput:
    """The complete typed hand-off to the final shadow aggregator."""

    packet: AgentCandidatePacket | Mapping[str, Any]
    packet_hash: str
    run_id: str
    specialist_outputs: tuple[Any, ...] = ()
    deterministic_scenario_results: Any = None
    reverse_dcf_results: Any = None
    conflict_records: tuple[SpecialistConflict, ...] = ()

    @property
    def company_id(self) -> int:
        return _packet_value(self.packet, "company_id")

    def __post_init__(self) -> None:
        computed = sha256(serialize_packet(self.packet).encode("utf-8")).hexdigest()
        if self.packet_hash != computed:
            raise ValueError("aggregator packet_hash does not match frozen packet")
        names = []
        for item in self.specialist_outputs:
            output = _output(item)
            if output is None:
                continue
            name = _enum(_field(output, "agent_name"))
            if name in names:
                raise ValueError("duplicate specialist output in aggregator input")
            names.append(name)
            if (
                _field(output, "run_id") != self.run_id
                or _field(output, "packet_hash") != self.packet_hash
                or _field(output, "company_id") != self.company_id
            ):
                raise ValueError("specialist output identity does not match aggregator input")

    @property
    def first_wave_outputs(self) -> tuple[Any, ...]:
        return tuple(
            item for item in self.specialist_outputs
            if _enum(_field(_output(item), "agent_name")) in FIRST_WAVE_NAMES
        )

    @property
    def sell_conditions_output(self) -> Any:
        for item in self.specialist_outputs:
            if _enum(_field(_output(item), "agent_name")) == "sell_conditions":
                return item
        return None

    def to_dict(self) -> dict:
        return _aggregator_payload(self)

    @classmethod
    def from_shadow_run(
        cls,
        packet: AgentCandidatePacket | Mapping[str, Any],
        shadow_run: Any,
        *,
        deterministic_scenario_results: Any = None,
        reverse_dcf_results: Any = None,
    ) -> "AggregatorInput":
        full_results = _packet_value(packet, "full_results") or {}
        if deterministic_scenario_results is None:
            deterministic_scenario_results = _field(full_results, "forward_scenario")
        if reverse_dcf_results is None:
            reverse_dcf_results = _field(full_results, "reverse_dcf")
        return cls(
            packet=packet,
            packet_hash=shadow_run.packet_hash,
            run_id=shadow_run.run_id,
            specialist_outputs=tuple(shadow_run.results),
            deterministic_scenario_results=deterministic_scenario_results,
            reverse_dcf_results=reverse_dcf_results,
            conflict_records=tuple(shadow_run.conflicts),
        )


@dataclass(frozen=True)
class UpstreamArtifact:
    agent_name: str
    status: str
    artifact_ids: tuple[int, ...] = ()
    output_hash: str | None = None
    confidence: str | None = None
    confidence_cap: str | None = None
    missing: tuple[str, ...] = ()
    missing_information: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "status": self.status,
            "artifact_ids": list(self.artifact_ids),
            "output_hash": self.output_hash,
            "confidence": self.confidence,
            "confidence_cap": self.confidence_cap,
            "missing": list(self.missing),
            "missing_information": list(self.missing_information),
        }


@dataclass(frozen=True)
class EvidenceTrace:
    final_claim_id: str
    upstream_claim_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    limitation_codes: tuple[str, ...] = ()
    deterministic_source_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "final_claim_id": self.final_claim_id,
            "upstream_claim_ids": list(self.upstream_claim_ids),
            "source_ids": list(self.source_ids),
            "limitation_codes": list(self.limitation_codes),
            "deterministic_source_ids": list(self.deterministic_source_ids),
        }


@dataclass(frozen=True)
class ActivationDecision:
    eligible: bool
    blocked_by: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "blocked_by": list(self.blocked_by),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AggregationManifest:
    schema_version: str
    run_id: str
    agent: str
    packet_hash: str
    upstream: tuple[UpstreamArtifact, ...]
    deterministic: dict
    precedence_applied: tuple[str, ...]
    activation_decision: ActivationDecision
    must_surface_conflicts: tuple[dict, ...]
    evidence_trace: tuple[EvidenceTrace, ...]
    validation_status: str = "pending"

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "agent": self.agent,
            "packet_hash": self.packet_hash,
            "upstream": [item.to_dict() for item in self.upstream],
            "deterministic": self.deterministic,
            "precedence_applied": list(self.precedence_applied),
            "activation_decision": self.activation_decision.to_dict(),
            "must_surface_conflicts": list(self.must_surface_conflicts),
            "evidence_trace": [item.to_dict() for item in self.evidence_trace],
            "validation_status": self.validation_status,
        }


@dataclass(frozen=True)
class AggregatorArtifactResult:
    status: str
    attempts: int
    raw_artifact_ids: tuple[int, ...] = ()
    validated_artifact_ids: tuple[int, ...] = ()
    validation_errors: tuple[str, ...] = ()
    candidate: StockAnalysisResult | None = None
    manifest: AggregationManifest | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "attempts": self.attempts,
            "raw_artifact_ids": list(self.raw_artifact_ids),
            "validated_artifact_ids": list(self.validated_artifact_ids),
            "validation_errors": list(self.validation_errors),
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "manifest": self.manifest.to_dict() if self.manifest else None,
        }


class AggregatorValidationError(ValueError):
    """A model output violates a deterministic aggregation boundary."""


class PetterAggregatorPromptBuilder:
    """Build an aggregator prompt from typed claims and deterministic values."""

    CONTRACT_VERSION = "petter-aggregator-shadow-prompt-v1"
    POLICY_NAME = "petter-hedborg-aggregator-shadow"
    POLICY_VERSION = "1.0.0"

    def build(self, inputs: AggregatorInput) -> AgentPrompt:
        payload = _aggregator_payload(inputs)
        instructions = AgentPromptBuilder._read_resource(
            "prompts/petter_hedborg_aggregator_prompt.md"
        )
        user = (
            "Frozen packet identity and typed evidence hand-off:\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True)
            + "\n\nReturn only one individual-thesis-card-v3-structured-conclusions JSON object."
        )
        system = (
            "You are the non-authoritative Petter Hedborg shadow aggregator. "
            "Use only typed specialist claims, IDs, source references, limitations, "
            "and deterministic valuation values in the hand-off. Apply precedence in "
            "the supplied order: evidence/readiness; understandability/circle of "
            "competence; fundamental business, growth and margin case; deterministic "
            "valuation/reverse DCF; management as a confidence adjustment; flows only "
            "for timing/research priority; and causal sell discipline. Do not calculate "
            "prices, returns, fair value, or required-return hurdles. Do not invent or "
            "smooth missing evidence. Keep this result shadow-only and do not provide "
            "position sizing.\n\n"
            "Emit only the closed v3 structured-conclusions contract.\n\n"
            + instructions
        )
        return AgentPrompt(
            system=system,
            user=user,
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            policy_sha256=sha256(self.POLICY_VERSION.encode()).hexdigest(),
            output_schema=v3_qualitative_stock_analysis_json_schema(),
            schema_name="petter_aggregator_v3",
            packet_measurement=asdict(measure_packet(inputs.packet, pretty=False)),
            contract_version=self.CONTRACT_VERSION,
        )


class ShadowPetterAggregatorRunner:
    """Generate and validate a candidate without touching authoritative analysis."""

    def __init__(
        self,
        model_adapter,
        raw_response_repository,
        *,
        prompt_builder=None,
        execution_boundary=None,
    ):
        self.model_adapter = model_adapter
        self.raw_response_repository = raw_response_repository
        self.prompt_builder = prompt_builder or PetterAggregatorPromptBuilder()
        self.execution_boundary = execution_boundary

    def run(self, inputs: AggregatorInput) -> AggregatorArtifactResult:
        existing = self._reuse_completed(inputs)
        if existing is not None:
            return existing
        prompt = self.prompt_builder.build(inputs)
        prompt_hash = sha256(_prompt_artifact(prompt).encode()).hexdigest()
        raw_ids: list[int] = []
        errors: list[str] = []
        response = None
        for attempt in range(1, 3):
            try:
                response = (
                    self.model_adapter.generate(prompt)
                    if attempt == 1
                    else self.model_adapter.repair(
                        prompt, response.output_text, errors[-1]
                    )
                )
                raw = response.output_text
            except Exception as exc:
                errors.append(str(exc))
                break
            raw_id = _save_aggregator_artifact(
                self.raw_response_repository,
                inputs,
                raw,
                getattr(response, "model", "aggregator-model"),
                artifact_type="aggregator_raw",
                metadata={
                    "analysis_stage": "petter_aggregator",
                    "analysis_attempt": attempt,
                    "prompt_sha256": prompt_hash,
                    "prompt_contract_version": prompt.contract_version,
                    "upstream_outputs_sha256": _sha256_json(inputs.specialist_outputs),
                    "deterministic_scenario_sha256": _sha256_json(
                        inputs.deterministic_scenario_results
                    ),
                    "reverse_dcf_sha256": _sha256_json(inputs.reverse_dcf_results),
                },
            )
            if raw_id is not None:
                raw_ids.append(raw_id)
            try:
                candidate = parse_qualitative_stock_analysis_result(raw)
                candidate, decision = validate_aggregator_output(candidate, inputs)
                if self.execution_boundary is not None:
                    candidate = _validate_with_boundary(candidate, inputs, self.execution_boundary)
                manifest = build_aggregation_manifest(inputs, candidate, decision)
                validated_raw = json.dumps(
                    {"candidate": candidate.to_dict(), "manifest": manifest.to_dict()},
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                )
                validated_id = _save_aggregator_artifact(
                    self.raw_response_repository,
                    inputs,
                    validated_raw,
                    "petter-aggregator-validator",
                    artifact_type="aggregator_validated",
                    metadata={
                        "analysis_stage": "petter_aggregator",
                        "analysis_attempt": attempt,
                        "prompt_sha256": prompt_hash,
                        "upstream_outputs_sha256": _sha256_json(inputs.specialist_outputs),
                        "deterministic_scenario_sha256": _sha256_json(
                            inputs.deterministic_scenario_results
                        ),
                        "reverse_dcf_sha256": _sha256_json(inputs.reverse_dcf_results),
                        "validation_status": "accepted",
                    },
                )
                if raw_id is not None:
                    self.raw_response_repository.update_raw_validation(raw_id, "accepted")
                return AggregatorArtifactResult(
                    "accepted", attempt, tuple(raw_ids),
                    (validated_id,) if validated_id is not None else (),
                    tuple(errors), candidate, manifest,
                )
            except (StockAnalysisValidationError, AggregatorValidationError, ValueError, TypeError) as exc:
                errors.append(str(exc))
                if raw_id is not None:
                    self.raw_response_repository.update_raw_validation(raw_id, "rejected", str(exc))
                if attempt == 1 and callable(getattr(self.model_adapter, "repair", None)):
                    continue
                break
        return AggregatorArtifactResult(
            "failed", len(raw_ids) or 1, tuple(raw_ids), (), tuple(errors)
        )

    def _reuse_completed(self, inputs: AggregatorInput):
        getter = getattr(self.raw_response_repository, "get_aggregator_artifacts_for_run", None)
        if not callable(getter):
            return None
        for artifact in reversed(list(getter(inputs.company_id, inputs.run_id))):
            metadata = artifact.get("metadata") or {}
            if (
                metadata.get("artifact_type") != "aggregator_validated"
                or metadata.get("packet_hash") != inputs.packet_hash
                or metadata.get("validation_status") != "accepted"
            ):
                continue
            try:
                payload = json.loads(artifact["content"])
                candidate = parse_qualitative_stock_analysis_result(
                    json.dumps(payload["candidate"], ensure_ascii=False)
                )
                manifest = payload["manifest"]
                if manifest.get("run_id") != inputs.run_id:
                    continue
                candidate, decision = validate_aggregator_output(candidate, inputs)
                return AggregatorArtifactResult(
                    "accepted", int(metadata.get("analysis_attempt", 0)),
                    (), (artifact["id"],), (), candidate,
                    build_aggregation_manifest(inputs, candidate, decision),
                )
            except (KeyError, json.JSONDecodeError, ValueError, TypeError):
                continue
        return None


def validate_aggregator_output(
    candidate: StockAnalysisResult, inputs: AggregatorInput
) -> tuple[StockAnalysisResult, ActivationDecision]:
    """Validate provenance/arithmetic and apply deterministic activation gates."""
    _validate_no_model_arithmetic(candidate, inputs)
    _validate_aggregator_sources(candidate, inputs)
    return enforce_aggregation_constraints(candidate, inputs)


def enforce_aggregation_constraints(
    candidate: StockAnalysisResult, inputs: AggregatorInput
) -> tuple[StockAnalysisResult, ActivationDecision]:
    """Apply philosophy gates after model generation, deterministically."""
    blockers: list[str] = []
    outputs = _outputs_by_name(inputs.specialist_outputs)
    for name in ALL_SPECIALIST_NAMES:
        output = outputs.get(name)
        if output is None:
            blockers.append(f"missing_{name}")
        elif _output_status(output) != "complete":
            blockers.append(f"{name}_insufficient_or_failed")
        if output is not None and any(
            _enum(_field(item, "limitation_class")) == "core"
            for item in (_field(_output(output), "missing_information") or ())
        ):
            blockers.append(f"{name}_core_evidence_missing")

    business = _domain(outputs.get("business_model"), "business_model")
    margin = _domain(outputs.get("margin"), "margin")
    growth = _domain(outputs.get("growth_valuation"), "growth_valuation")
    management = _domain(outputs.get("management_credibility"), "management_credibility")
    sell = _domain(outputs.get("sell_conditions"), "sell_conditions")

    circle = _field(business, "circle_of_competence")
    if circle == "outside":
        blockers.append("outside_circle_of_competence")
    elif circle in (None, "unassessable"):
        blockers.append("unassessable_circle_of_competence")

    if _field(business, "profitability_state") in (None, "unassessable"):
        blockers.append("fundamental_case_unsupported")
    if _field(growth, "growth_state") in (None, "weak", "unassessable"):
        blockers.append("unsupported_growth_mechanism")
    if _field(margin, "margin_state") in (None, "unassessable"):
        blockers.append("unsupported_margin_mechanism")

    scenario_status = _deterministic_status(inputs.deterministic_scenario_results)
    if scenario_status != "available":
        blockers.append(
            "deterministic_valuation_insufficient"
            if scenario_status == "insufficient_evidence"
            else "deterministic_valuation_unavailable"
        )
    reverse_status = _deterministic_status(inputs.reverse_dcf_results)
    if reverse_status != "available":
        blockers.append(
            "reverse_dcf_insufficient"
            if reverse_status == "insufficient_evidence"
            else "reverse_dcf_unavailable"
        )
    if (
        _deterministic_status(inputs.deterministic_scenario_results) == "available"
        and _deterministic_status(inputs.reverse_dcf_results) == "available"
        and not _hurdle_is_satisfied(inputs)
    ):
        blockers.append("required_return_hurdle_unsatisfied")

    high_conflicts = [
        conflict for conflict in _effective_conflicts(inputs, candidate)
        if _field(conflict, "severity") == "high"
        and _field(conflict, "action") == "block_activation"
    ]
    if high_conflicts:
        blockers.append("high_severity_conflict")

    if _field(sell, "current_break_status") == "triggered":
        blockers.append("causal_sell_break_triggered")
    if _field(sell, "activation_blockers"):
        blockers.append("causal_activation_blocker")
    sell_tests = _field(sell, "tests") or ()
    if { _field(item, "break_type") for item in sell_tests } != set(THESIS_BREAK_TYPES):
        blockers.append("sell_conditions_incomplete")
    if any(_field(item, "current_break_status") == "triggered" for item in sell_tests):
        blockers.append("causal_sell_break_triggered")
    if any(_field(item, "current_break_status") == "unassessable" for item in sell_tests):
        blockers.append("sell_conditions_unassessable")
    if _field(growth, "engine_dependency") == "multiple_only":
        blockers.append("multiple_only_economics")
    if any(
        _is_limited_evidence_entry(claim)
        for claim, _ in _candidate_evidence_entries(candidate)
    ):
        blockers.append("unassessable_final_evidence")

    # The fundamental case is load-bearing; flow cannot promote a weak case.
    if _field(growth, "growth_state") in ("weak", "unassessable") or _field(margin, "margin_state") in ("invalidated", "stalled"):
        if _field(_domain(outputs.get("insider_ownership"), "insider_ownership"), "insider_signal") == "positive":
            blockers.append("fundamentals_override_positive_flow")

    blockers = list(dict.fromkeys(blockers))
    eligible = not blockers
    candidate = _apply_confidence_cap(candidate, outputs)
    if not eligible and candidate.verdict == "activated_case":
        candidate.verdict = "reject" if "causal_sell_break_triggered" in blockers else "watch"
        candidate.portfolio_eligibility = "not_investable"
        candidate.portfolio_reason_code = "evidence_insufficient"
    elif candidate.verdict != "activated_case":
        candidate.portfolio_eligibility = "not_investable"
    elif not eligible:
        candidate.portfolio_eligibility = "not_investable"
    return candidate, ActivationDecision(
        eligible=eligible,
        blocked_by=tuple(blockers),
        reason="eligible" if eligible else blockers[0],
    )


def build_aggregation_manifest(
    inputs: AggregatorInput,
    candidate: StockAnalysisResult,
    decision: ActivationDecision,
) -> AggregationManifest:
    outputs = _outputs_by_name(inputs.specialist_outputs)
    upstream = []
    for name in ALL_SPECIALIST_NAMES:
        item = outputs.get(name)
        output = _output(item)
        upstream.append(
            UpstreamArtifact(
                agent_name=name,
                status=_output_status(item) if item is not None else "missing",
                artifact_ids=tuple(_field(item, "artifact_ids") or ()),
                output_hash=_sha256_json(output.to_dict() if output else None),
                confidence=_enum(_field(output, "confidence")) if output else None,
                confidence_cap=_enum(_field(output, "confidence_cap")) if output else None,
                missing=tuple(
                    _field(missing, "item_code")
                    for missing in (_field(output, "missing_information") or ())
                ) if output else (),
                missing_information=tuple(
                    _json_value(missing)
                    for missing in (_field(output, "missing_information") or ())
                ) if output else (),
            )
        )
    traces = _evidence_traces(candidate, inputs)
    conflicts = tuple(
        conflict.to_dict() if hasattr(conflict, "to_dict") else dict(conflict)
        for conflict in _effective_conflicts(inputs, candidate)
    )
    return AggregationManifest(
        schema_version="petter-aggregator-v1",
        run_id=inputs.run_id,
        agent="petter_hedborg",
        packet_hash=inputs.packet_hash,
        upstream=tuple(upstream),
        deterministic={
            "scenario_status": _deterministic_status(inputs.deterministic_scenario_results),
            "reverse_dcf_status": _deterministic_status(inputs.reverse_dcf_results),
            "scenario_hash": _sha256_json(inputs.deterministic_scenario_results),
            "reverse_dcf_hash": _sha256_json(inputs.reverse_dcf_results),
        },
        precedence_applied=PRECEDENCE_APPLIED,
        activation_decision=decision,
        must_surface_conflicts=conflicts,
        evidence_trace=traces,
        validation_status="accepted",
    )


def _aggregator_payload(inputs: AggregatorInput) -> dict:
    return {
        "run_id": inputs.run_id,
        "packet_hash": inputs.packet_hash,
        "company_id": _packet_value(inputs.packet, "company_id"),
        "ticker": _packet_value(inputs.packet, "ticker"),
        "evidence_catalog": _packet_value(inputs.packet, "evidence_catalog") or build_evidence_catalog(
            _packet_value(inputs.packet, "full_results") or {},
            _packet_value(inputs.packet, "research_evidence") or {},
        ),
        "specialist_outputs": [_typed_output_payload(item) for item in inputs.specialist_outputs],
        "deterministic_scenario_results": _json_value(inputs.deterministic_scenario_results),
        "reverse_dcf_results": _json_value(inputs.reverse_dcf_results),
        "conflict_records": [
            item.to_dict() if hasattr(item, "to_dict") else _json_value(item)
            for item in inputs.conflict_records
        ],
        "precedence": list(PRECEDENCE_APPLIED),
        "sell_condition_types": list(THESIS_BREAK_TYPES),
    }


def _typed_output_payload(item: Any) -> Any:
    output = _output(item)
    payload = {
        "agent_name": _field(output, "agent_name") if output else _field(item, "agent_name"),
        "status": _output_status(item),
        "artifact_ids": list(_field(item, "artifact_ids") or ()),
        "output": output.to_dict() if output else None,
    }
    return _json_value(payload)


def _validate_aggregator_sources(candidate: StockAnalysisResult, inputs: AggregatorInput) -> None:
    conclusions = candidate.structured_conclusions
    if conclusions is None:
        raise AggregatorValidationError("aggregator requires structured_conclusions")
    catalog = _packet_value(inputs.packet, "evidence_catalog") or build_evidence_catalog(
        _packet_value(inputs.packet, "full_results") or {},
        _packet_value(inputs.packet, "research_evidence") or {},
    )
    full_results = _packet_value(inputs.packet, "full_results") or {}
    research = _packet_value(inputs.packet, "research_evidence") or {}
    references = _specialist_claim_references(
        inputs, full_results, research, catalog
    )
    for claim, claim_id in _candidate_evidence_entries(candidate):
        source_ids = claim.get("source_ids", [])
        if not source_ids:
            if _is_limited_evidence_entry(claim):
                continue
            raise AggregatorValidationError(
                f"aggregator claim requires source_ids: {claim_id}"
            )
        normalized = _normalized_source_ids(
            source_ids, full_results, research, catalog, claim_id
        )
        if claim.get("__provenance__") == "deterministic":
            if not all(
                _is_deterministic_source(source_id, resolved)
                for source_id, resolved in zip(source_ids, normalized)
            ):
                raise AggregatorValidationError(
                    "aggregator deterministic reference is not deterministic: "
                    + claim_id
                )
            continue
        matching = _matching_references(claim, normalized, references)
        matched_sources = {
            source_id
            for _, sources, _, _ in matching
            for source_id in set(normalized).intersection(sources)
        }
        if matched_sources != set(normalized):
            raise AggregatorValidationError(
                "aggregator claim requires an upstream specialist claim and complete "
                "source linkage: "
                + claim_id
            )


def _validate_no_model_arithmetic(candidate: StockAnalysisResult, inputs: AggregatorInput) -> None:
    conclusions = candidate.structured_conclusions
    if conclusions is None:
        return
    for claim, _ in _candidate_evidence_entries(candidate):
        value = claim.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        text = " ".join(
            str(claim.get(key, "")).lower()
            for key in ("domain", "claim_id", "predicate", "fact_code")
        ).replace("-", "_")
        domain = str(_enum(claim.get("domain", ""))).lower().replace("-", "_")
        domain_tokens = set(domain.split("_"))
        if domain_tokens.intersection(
            {"valuation", "price", "prices", "return", "returns", "fair", "value", "hurdle", "hurdles"}
        ) or any(
            term in text for term in ("price", "return", "fair_value", "required_return", "hurdle")
        ):
            raise AggregatorValidationError("aggregator may not author prices, returns, fair value, or hurdles")


def _validate_with_boundary(candidate, inputs, boundary):
    packet = _packet_value(inputs, "packet")
    if isinstance(packet, AgentCandidatePacket):
        packet = packet.to_dict()
    candidate_model = AgentCandidate(
        rank=packet.get("rank", 0), company_id=packet["company_id"], ticker=packet["ticker"],
        name=packet.get("name", packet["ticker"]), full_results=packet.get("full_results", {}),
        research_evidence=packet.get("research_evidence", {}),
    )
    return boundary.validate_qualitative_response(
        json.dumps(candidate.to_dict(), ensure_ascii=False), candidate_model
    )


def _apply_confidence_cap(candidate: StockAnalysisResult, outputs: dict) -> StockAnalysisResult:
    caps = [_enum(_field(_output(item), "confidence_cap")) for item in outputs.values() if _output(item)]
    management = _domain(outputs.get("management_credibility"), "management_credibility")
    coverage = _field(management, "coverage")
    if coverage is not None:
        caps.append(_enum(_field(coverage, "confidence_cap")))
    if not _output(outputs.get("management_credibility")):
        caps.append("low")
    caps = [cap for cap in caps if cap in _CONFIDENCE_RANK]
    if caps and _CONFIDENCE_RANK.get(candidate.confidence, 0) > min(_CONFIDENCE_RANK[cap] for cap in caps):
        candidate.confidence = min(caps, key=lambda cap: _CONFIDENCE_RANK[cap])
    return candidate


def _hurdle_is_satisfied(inputs: AggregatorInput) -> bool:
    scenario = inputs.deterministic_scenario_results
    reverse = inputs.reverse_dcf_results
    hurdle = _nested(reverse, "required_return", "required_return")
    if hurdle is None:
        hurdle = _nested(_packet_value(inputs.packet, "full_results") or {}, "reverse_dcf", "required_return", "required_return")
    base_low = _nested(scenario, "base", "low_annualized_return")
    if base_low is None:
        bands = _field(scenario, "bands") or _field(scenario, "results") or []
        for band in bands:
            if _field(band, "case") == "base":
                base_low = _field(band, "low_annualized_return")
                break
    try:
        return base_low is not None and hurdle is not None and float(base_low) >= float(hurdle)
    except (TypeError, ValueError):
        return False


def _evidence_traces(candidate, inputs) -> tuple[EvidenceTrace, ...]:
    full_results = _packet_value(inputs.packet, "full_results") or {}
    research = _packet_value(inputs.packet, "research_evidence") or {}
    catalog = _packet_value(inputs.packet, "evidence_catalog") or build_evidence_catalog(
        full_results, research
    )
    references = _specialist_claim_references(
        inputs, full_results, research, catalog
    )
    traces = []
    for claim, claim_id in _candidate_evidence_entries(candidate):
        limitations = tuple(dict.fromkeys(claim.get("limitation_codes", [])))
        if not claim.get("source_ids") and _is_limited_evidence_entry(claim):
            traces.append(EvidenceTrace(claim_id, (), (), limitations))
            continue
        if claim.get("__provenance__") == "deterministic":
            source_ids = _normalized_source_ids(
                claim.get("source_ids", []),
                full_results,
                research,
                catalog,
                claim_id,
            )
            if not all(
                _is_deterministic_source(source_id, resolved)
                for source_id, resolved in zip(claim["source_ids"], source_ids)
            ):
                raise AggregatorValidationError(
                    "aggregator deterministic reference is not deterministic: "
                    + claim_id
                )
            traces.append(EvidenceTrace(
                claim_id,
                (),
                source_ids,
                limitations,
                source_ids,
            ))
            continue
        source_ids = _normalized_source_ids(
            claim.get("source_ids", []),
            full_results,
            research,
            catalog,
            claim_id,
        )
        matching_references = _matching_references(claim, source_ids, references)
        matching = tuple(reference[0] for reference in matching_references)
        if not matching:
            raise AggregatorValidationError(
                "aggregator claim requires an upstream specialist claim: "
                + claim_id
            )
        matched_sources = {
            source_id
            for _, sources, _, _ in matching_references
            for source_id in set(source_ids).intersection(sources)
        }
        if matched_sources != set(source_ids):
            raise AggregatorValidationError(
                "aggregator claim requires an upstream specialist claim and complete "
                "source linkage: "
                + claim_id
            )
        limitations = tuple(dict.fromkeys(
            limitation
            for upstream_id, _, claim_limitations, _ in matching_references
            if upstream_id in matching
            for limitation in claim_limitations
        ))
        traces.append(EvidenceTrace(
            claim_id,
            matching,
            source_ids,
            tuple(dict.fromkeys((*claim.get("limitation_codes", []), *limitations))),
        ))
    return tuple(traces)


def _specialist_claim_references(inputs, full_results, research, catalog):
    references = []
    for item in inputs.specialist_outputs:
        output = _output(item)
        if output is None:
            continue
        agent = _enum(_field(output, "agent_name"))
        output_limitations = tuple(
            _field(missing, "item_code")
            for missing in (_field(output, "missing_information") or ())
        )
        for claim, upstream_id, domains in _specialist_evidence_records(output):
            source_ids = _field(claim, "source_ids") or ()
            if not source_ids or not _specialist_claim_is_assessable(claim):
                continue
            normalized = _normalized_source_ids(
                source_ids,
                full_results,
                research,
                catalog,
                upstream_id,
            )
            references.append((
                upstream_id,
                set(normalized),
                tuple(dict.fromkeys((
                    *(_field(claim, "limitation_codes") or ()),
                    *output_limitations,
                ))),
                domains,
            ))
    return tuple(references)


def _specialist_claim_is_assessable(claim):
    break_status = _enum(_field(claim, "current_break_status"))
    if break_status is not None:
        return break_status != "unassessable"
    direction = _enum(_field(claim, "direction"))
    value = _enum(_field(claim, "value"))
    if direction is not None or value is not None:
        return direction != "unassessable" and value not in ("unassessable", "unavailable")
    result = _enum(_field(claim, "result"))
    if result is not None:
        return result not in ("unverifiable", "too_vague_to_test")
    return True


def _specialist_evidence_records(output):
    agent = _enum(_field(output, "agent_name"))
    domain = _field(output, agent) if agent else None
    records = [
        (claim, f"{agent}:{_field(claim, 'claim_id')}", {_field(claim, "domain")})
        for claim in [
            *(_field(output, "claims") or ()),
            *(_field(domain, "claims") or ()),
            *(_field(domain, "event_claims") or ()),
        ]
    ]
    management = _field(output, "management_credibility")
    records.extend(
        (
            row,
            f"{agent}:{_field(row, 'claim_id')}",
            {"management"},
        )
        for row in (_field(management, "ledger") or ())
    )
    sell = _field(output, "sell_conditions")
    records.extend(
        (
            test,
            f"{agent}:sell_test:{index}",
            _SELL_RECORD_DOMAINS.get(
                _enum(_field(test, "break_type")), {"risk"}
            ),
        )
        for index, test in enumerate(_field(sell, "tests") or ())
        if _field(test, "source_ids")
    )
    records.extend(
        (
            blocker,
            f"{agent}:activation_blocker:{index}",
            _SELL_RECORD_DOMAINS.get(
                _enum(_field(blocker, "blocker_code")), {"risk"}
            ),
        )
        for index, blocker in enumerate(_field(sell, "activation_blockers") or ())
        if _field(blocker, "source_ids")
    )
    for source_field in ("supporting_source_ids", "contrary_source_ids"):
        source_ids = _field(domain, source_field) or ()
        if source_ids:
            records.append(
                (
                    {"source_ids": source_ids},
                    f"{agent}:{source_field}",
                    {_enum(_field(output, "agent_name"))},
                )
            )
    scenario_domains = {
        "revenue_cagr": {"revenue"},
        "ebit_margin": {"margin"},
        "terminal_ev_ebit_low": {"valuation"},
        "terminal_ev_ebit_high": {"valuation"},
        "net_debt_change": {"balance_sheet"},
        "share_count_growth": {"valuation"},
        "distributions_per_share": {"valuation"},
    }
    for bundle_index, bundle in enumerate(_field(domain, "scenario_bundles") or ()):
        for field_name, domains in scenario_domains.items():
            assumption = _field(bundle, field_name)
            source_ids = _field(assumption, "source_ids") or ()
            if source_ids:
                records.append((
                    assumption,
                    f"{agent}:scenario_bundle:{bundle_index}:{field_name}",
                    domains,
                ))
    return tuple(records)


def _reference_matches_domain(claim, domains):
    final_domain = _enum(claim.get("domain"))
    return not final_domain or final_domain in domains


def _matching_references(claim, source_ids, references):
    return tuple(
        reference
        for reference in references
        if set(source_ids).intersection(reference[1])
        and _reference_matches_domain(claim, reference[3])
    )


def _is_limited_evidence_entry(claim):
    value = _enum(claim.get("value"))
    return value in ("unassessable", "unavailable") or claim.get("predicate") == "source_gap"


def _normalized_source_ids(source_ids, full_results, research, catalog, claim_id):
    normalized = []
    for source_id in source_ids:
        try:
            resolved = resolve_source_id(
                source_id, full_results, research, catalog=catalog
            )
            canonical = set(catalog.get("canonical_source_ids", ()))
            if (
                resolved not in canonical
                and not source_id.startswith(("full_results.", "deterministic:"))
            ):
                raise ValueError("source is not in the frozen evidence catalog")
        except Exception as exc:
            raise AggregatorValidationError(
                f"aggregator claim references unknown source ID: {source_id}"
            ) from exc
        if resolved not in normalized:
            normalized.append(resolved)
    if not normalized:
        raise AggregatorValidationError(
            f"aggregator claim requires source_ids: {claim_id}"
        )
    return tuple(normalized)


def _all_evidence_entries(value, path=()):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        result = []
        if "source_ids" in value:
            result.append((value, str(value.get("claim_id") or ".".join(path))))
        for field_name in ("expectation_refs", "baseline_refs"):
            for index, source_id in enumerate(value.get(field_name) or ()):
                result.append((
                    {
                        "source_ids": [source_id],
                        "__provenance__": "deterministic",
                    },
                    ".".join((*path, field_name, str(index))),
                ))
        for key, child in value.items():
            result.extend(_all_evidence_entries(child, (*path, str(key))))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for index, child in enumerate(value):
            result.extend(_all_evidence_entries(child, (*path, str(index))))
        return result
    return []


def _candidate_evidence_entries(candidate):
    entries = list(_all_evidence_entries(candidate.structured_conclusions))
    for index, ownership in enumerate(candidate.ownership_claims or ()):
        ownership = _json_value(ownership)
        binding = ownership.get("binding") or {}
        entries.append((
            {
                "claim_id": f"ownership_claims.{index}",
                "domain": "insider",
                "limitation_codes": ownership.get("limitation_codes", []),
                "source_ids": binding.get("source_ids", []),
            },
            f"ownership_claims.{index}",
        ))
    return tuple(entries)


def _is_deterministic_source(source_id, resolved):
    return str(source_id).startswith((
        "valuation:reverse_dcf:", "full_results.", "deterministic:"
    )) or str(resolved).startswith((
        "valuation:reverse_dcf:", "deterministic:"
    ))


def _effective_conflicts(inputs: AggregatorInput, candidate: StockAnalysisResult):
    outputs = [output for item in inputs.specialist_outputs if (output := _output(item))]
    computed = evaluate_specialist_conflicts(outputs, final_direction=candidate.verdict)
    existing = list(inputs.conflict_records)
    keys = {
        (_field(item, "rule_id"), tuple(_field(item, "trigger_claim_ids") or ()))
        for item in existing
    }
    return tuple(existing + [
        item for item in computed
        if (_field(item, "rule_id"), tuple(_field(item, "trigger_claim_ids") or ())) not in keys
    ])


def _outputs_by_name(items):
    result = {}
    for item in items:
        output = _output(item)
        name = _enum(_field(output, "agent_name")) if output else _enum(_field(item, "agent_name"))
        if name:
            result[name] = item
    return result


def _output(item):
    value = _field(item, "output")
    return value if isinstance(value, SpecialistOutput) else item if isinstance(item, SpecialistOutput) else None


def _output_status(item):
    output = _output(item)
    status = _field(item, "status") if not isinstance(item, SpecialistOutput) else _field(output, "status")
    status = _enum(status)
    if isinstance(item, SpecialistOutput):
        return status
    return {"accepted": "complete", "limited": "insufficient_evidence", "failed": "failed"}.get(status, status or "failed")


def _domain(item, name):
    output = _output(item)
    return _field(output, name) if output else None


def _field(value, name):
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None) if value is not None else None


def _enum(value):
    return getattr(value, "value", value)


def _packet_value(packet, name):
    if isinstance(packet, Mapping):
        return packet.get(name)
    return getattr(packet, name, None)


def _nested(value, *names):
    for name in names:
        value = _field(value, name)
        if value is None:
            return None
    return value


def _deterministic_status(value):
    status = _enum(_field(value, "status"))
    if status:
        return status
    if isinstance(value, Mapping):
        return value.get("status")
    return "unavailable" if value is None else "unknown"


def _json_value(value):
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _sha256_json(value):
    return sha256(json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _prompt_artifact(prompt):
    return json.dumps({"system": prompt.system, "user": prompt.user, "schema_name": prompt.schema_name, "contract_version": prompt.contract_version}, ensure_ascii=False, sort_keys=True)


def _save_aggregator_artifact(repository, inputs, content, created_by, *, artifact_type, metadata):
    method = getattr(repository, "save_aggregator_artifact", None)
    if callable(method):
        return method(
            _packet_value(inputs.packet, "company_id"), content, created_by,
            run_id=inputs.run_id, packet_hash=inputs.packet_hash,
            artifact_type=artifact_type, metadata=metadata,
        )
    fallback = getattr(repository, "save_stock_analysis_raw", None)
    if not callable(fallback):
        return None
    return fallback(
        _packet_value(inputs.packet, "company_id"), content, created_by,
        metadata={
            **metadata, "analysis_mode": "aggregator", "agent_name": "petter_hedborg",
            "run_id": inputs.run_id, "packet_hash": inputs.packet_hash,
            "artifact_type": artifact_type,
        },
    )
