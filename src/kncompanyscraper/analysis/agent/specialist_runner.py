"""Shadow execution of typed specialist agents against a frozen packet."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
from uuid import uuid4

from kncompanyscraper.analysis.agent.agent_packet import (
    AgentCandidatePacket,
    SourcePathError,
    build_evidence_catalog,
    resolve_source_id,
    serialize_packet,
)
from kncompanyscraper.analysis.agent.output_schema import (
    SellConditionAssessment,
    SellConditionActivationBlocker,
    SellConditionStatus,
    SellConditionsSpecialistOutput,
    SpecialistAgentName,
    SpecialistConfidence,
    SpecialistMissingInformation,
    SpecialistOutput,
    SpecialistStatus,
    THESIS_BREAK_TYPES,
    specialist_output_json_schema,
)
from kncompanyscraper.analysis.agent.packet_measurement import measure_packet
from kncompanyscraper.analysis.agent.prompt_artifact import serialize_prompt
from kncompanyscraper.analysis.agent.prompt_builder import (
    AgentPrompt,
    AgentPromptBuilder,
)
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_specialist_output,
)
from kncompanyscraper.analysis.agent.specialist_conflicts import (
    SpecialistConflict,
    evaluate_specialist_conflicts,
)


FIRST_WAVE_SPECIALISTS = (
    SpecialistAgentName.BUSINESS_MODEL,
    SpecialistAgentName.MANAGEMENT_CREDIBILITY,
    SpecialistAgentName.MARGIN,
    SpecialistAgentName.INSIDER_OWNERSHIP,
    SpecialistAgentName.GROWTH_VALUATION,
)

_SPECIALIST_PROMPT_RESOURCES = {
    SpecialistAgentName.BUSINESS_MODEL: "specialist_business_model_prompt.md",
    SpecialistAgentName.MANAGEMENT_CREDIBILITY: (
        "specialist_management_credibility_prompt.md"
    ),
    SpecialistAgentName.MARGIN: "specialist_margin_prompt.md",
    SpecialistAgentName.INSIDER_OWNERSHIP: "specialist_insider_ownership_prompt.md",
    SpecialistAgentName.GROWTH_VALUATION: "specialist_growth_valuation_prompt.md",
    SpecialistAgentName.SELL_CONDITIONS: "specialist_sell_conditions_prompt.md",
}

_CAUSAL_CLAIM_DOMAINS = {
    "revenue_or_demand": {"business_model", "growth_valuation", "revenue", "demand"},
    "margin_or_execution": {"business_model", "margin", "execution"},
    "balance_sheet_or_dilution": {
        "balance_sheet",
        "capital_allocation",
        "dilution",
        "growth_valuation",
        "insider_ownership",
    },
    "management_credibility": {"management", "management_credibility"},
    "valuation_overshoot": {"growth_valuation", "valuation"},
    "superior_evidence_or_opportunity": {
        "balance_sheet",
        "business_model",
        "capital_allocation",
        "demand",
        "dilution",
        "execution",
        "growth_valuation",
        "insider_ownership",
        "management",
        "management_credibility",
        "margin",
        "revenue",
        "valuation",
    },
}

@dataclass(frozen=True)
class SpecialistArtifactResult:
    agent_name: str
    status: str
    attempts: int
    artifact_ids: tuple[int, ...] = ()
    validation_errors: tuple[str, ...] = ()
    output: SpecialistOutput | None = None

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "status": self.status,
            "attempts": self.attempts,
            "artifact_ids": list(self.artifact_ids),
            "validation_errors": list(self.validation_errors),
        }


@dataclass(frozen=True)
class ShadowSpecialistRun:
    run_id: str
    company_id: int
    packet_hash: str
    results: tuple[SpecialistArtifactResult, ...]
    conflicts: tuple[SpecialistConflict, ...] = ()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "company_id": self.company_id,
            "packet_hash": self.packet_hash,
            "results": [result.to_dict() for result in self.results],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
        }


class SpecialistPromptBuilder:
    """Build a narrow prompt while preserving the normal adapter seam."""

    CONTRACT_VERSION = "specialist-shadow-prompt-v2-first-wave"
    POLICY_NAME = "specialist-shadow-analysis"
    POLICY_VERSION = "1.0.0"

    def build(
        self,
        packet: AgentCandidatePacket | dict,
        agent_name: SpecialistAgentName,
        *,
        upstream_outputs=None,
        deterministic_scenario_data=None,
    ) -> AgentPrompt:
        agent_name = SpecialistAgentName(agent_name)
        try:
            instruction_resource = _SPECIALIST_PROMPT_RESOURCES[agent_name]
        except KeyError as exc:
            raise ValueError(
                f"no specialist prompt for agent {agent_name.value!r}"
            ) from exc
        if (
            agent_name is SpecialistAgentName.SELL_CONDITIONS
            and upstream_outputs is None
            and deterministic_scenario_data is None
        ):
            raise ValueError(
                "no first-wave specialist prompt; sell-conditions prompt requires "
                "typed upstream outputs and deterministic scenario data"
            )
        instructions = AgentPromptBuilder._read_resource(
            f"prompts/{instruction_resource}"
        )
        schema = specialist_output_json_schema(agent_name.value)
        measurement = asdict(measure_packet(packet, pretty=False))
        if agent_name is SpecialistAgentName.SELL_CONDITIONS:
            instructions = instructions.replace(
                "{thesis_break_types}",
                ", ".join(f"`{break_type}`" for break_type in THESIS_BREAK_TYPES),
            )
            upstream_json = json.dumps(
                [_serialize_upstream_output(item) for item in (upstream_outputs or ())],
                ensure_ascii=False,
                sort_keys=True,
            )
            scenario_json = json.dumps(
                _json_value(deterministic_scenario_data),
                ensure_ascii=False,
                sort_keys=True,
            )
            catalog = (
                packet.get("evidence_catalog", {})
                if isinstance(packet, dict)
                else packet.evidence_catalog
            )
            user = (
                "Agent name: sell_conditions\n"
                "Domain payload: sell_conditions\n\n"
                "Typed first-wave specialist outputs (not free-form reports):\n"
                f"{upstream_json}\n\n"
                "Deterministic scenario data (authoritative, may be unavailable):\n"
                f"{scenario_json}\n\n"
                "Permitted frozen-packet source IDs:\n"
                f"{json.dumps(catalog, ensure_ascii=False, sort_keys=True)}\n\n"
                "Return only the complete specialist-output-v1 JSON object for this agent."
            )
            system = (
                "You are a non-authoritative shadow specialist. Return exactly one "
                "JSON object valid against the specialist-output-v1 schema supplied "
                "for this request. Set agent_name exactly to 'sell_conditions' and "
                "include only the sell_conditions domain payload. Do not emit markdown, "
                "prose outside JSON, a verdict, activation decision, or position size.\n\n"
                f"{instructions}\n"
                "Use only the typed inputs supplied below and mark gaps explicitly."
            )
        else:
            packet_json = serialize_packet(packet)
            user = (
                f"Agent name: {agent_name.value}\n"
                f"Domain payload: {agent_name.value}\n\n"
                "Frozen AgentCandidatePacket:\n"
                f"{packet_json}\n\n"
                "Return only the complete specialist-output-v1 JSON object for this "
                "agent and domain."
            )
            system = (
                "You are a non-authoritative shadow specialist. Return exactly one "
                "JSON object valid against the specialist-output-v1 schema supplied "
                "for this request. Set agent_name exactly to "
                f"{agent_name.value!r} and include only the "
                f"{agent_name.value!r} domain payload. Do not emit markdown, prose "
                "outside JSON, a verdict, activation decision, or position size.\n\n"
                f"{instructions}\n"
                "Use exact source IDs from the frozen packet and mark missing evidence explicitly."
            )
        return AgentPrompt(
            system=system,
            user=user,
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            policy_sha256=sha256(self.POLICY_VERSION.encode("utf-8")).hexdigest(),
            output_schema=schema,
            schema_name=f"specialist_{agent_name.value}",
            packet_measurement=measurement,
            contract_version=(
                "specialist-shadow-prompt-v3-sell-conditions"
                if agent_name is SpecialistAgentName.SELL_CONDITIONS
                else self.CONTRACT_VERSION
            ),
        )


class ShadowSpecialistRunner:
    """Run first-wave specialists without entering the authoritative analysis path."""

    def __init__(
        self,
        model_adapter,
        raw_response_repository,
        *,
        prompt_builder=None,
        specialists=None,
    ):
        self.model_adapter = model_adapter
        self.raw_response_repository = raw_response_repository
        self.prompt_builder = prompt_builder or SpecialistPromptBuilder()
        requested = FIRST_WAVE_SPECIALISTS if specialists is None else specialists
        requested = tuple(SpecialistAgentName(agent) for agent in requested)
        self.specialists = tuple(
            agent for agent in requested if agent is not SpecialistAgentName.SELL_CONDITIONS
        )
        self.sell_conditions_enabled = (
            specialists is None or SpecialistAgentName.SELL_CONDITIONS in requested
        )

    def run(
        self,
        packet: AgentCandidatePacket | dict,
        *,
        run_id: str | None = None,
        packet_hash: str | None = None,
        deterministic_scenario_data=None,
    ) -> ShadowSpecialistRun:
        packet_json = serialize_packet(packet)
        computed_hash = sha256(packet_json.encode("utf-8")).hexdigest()
        if packet_hash is not None and packet_hash != computed_hash:
            raise ValueError("specialist packet hash does not match frozen packet")
        packet_hash = packet_hash or computed_hash
        run_id = run_id or f"shadow-{uuid4()}"
        company_id = (
            packet["company_id"] if isinstance(packet, dict) else packet.company_id
        )
        results = [
            self._run_one(packet, company_id, run_id, packet_hash, agent_name)
            for agent_name in self.specialists
        ]
        if self.sell_conditions_enabled:
            scenario_data = (
                _deterministic_scenario_data(packet)
                if deterministic_scenario_data is None
                else deterministic_scenario_data
            )
            sell_result = self._run_sell_conditions(
                packet,
                company_id,
                run_id,
                packet_hash,
                tuple(results),
                scenario_data,
            )
            results.append(sell_result)
        conflicts = evaluate_specialist_conflicts(
            result.output for result in results if result.output is not None
        )
        return ShadowSpecialistRun(run_id, company_id, packet_hash, tuple(results), conflicts)

    def _run_sell_conditions(
        self, packet, company_id, run_id, packet_hash, upstream_results, scenario_data
    ):
        inputs_available = _sell_inputs_available(upstream_results, scenario_data)
        reused = self._reuse_completed(
            company_id, run_id, packet_hash, SpecialistAgentName.SELL_CONDITIONS
        )
        reuse_found = reused is not None
        if reused is not None:
            try:
                _validate_sell_traceability(reused.output, upstream_results, packet)
            except (ValueError, TypeError):
                reused = None
            else:
                if reused.status != "failed":
                    if reused.status != "limited" or not inputs_available:
                        return reused
        if not inputs_available:
            return self._unassessable_sell_result(
                packet,
                company_id,
                run_id,
                packet_hash,
                upstream_results,
                scenario_data,
            )
        result = self._run_one(
            packet,
            company_id,
            run_id,
            packet_hash,
            SpecialistAgentName.SELL_CONDITIONS,
            upstream_outputs=upstream_results,
            deterministic_scenario_data=scenario_data,
            reuse_completed=not reuse_found,
        )
        if result.status == "failed" or (
            result.output is not None
            and result.output.status is not SpecialistStatus.COMPLETE
        ):
            return self._unassessable_sell_result(
                packet,
                company_id,
                run_id,
                packet_hash,
                upstream_results,
                scenario_data,
            )
        return result

    def _run_one(
        self,
        packet,
        company_id,
        run_id,
        packet_hash,
        agent_name,
        *,
        upstream_outputs=None,
        deterministic_scenario_data=None,
        reuse_completed=True,
    ):
        if reuse_completed:
            reused = self._reuse_completed(company_id, run_id, packet_hash, agent_name)
            if reused is not None:
                return reused

        prompt = (
            self.prompt_builder.build(
                packet,
                agent_name,
                upstream_outputs=upstream_outputs,
                deterministic_scenario_data=deterministic_scenario_data,
            )
            if agent_name is SpecialistAgentName.SELL_CONDITIONS
            else self.prompt_builder.build(packet, agent_name)
        )
        prompt_artifact = serialize_prompt(prompt)
        prompt_hash = sha256(prompt_artifact.encode("utf-8")).hexdigest()
        response = None
        artifact_ids = []
        validation_errors = []
        for attempt in range(1, 3):
            try:
                response = (
                    self.model_adapter.generate(prompt)
                    if attempt == 1
                    else self.model_adapter.repair(
                        prompt, response.output_text, validation_errors[-1]
                    )
                )
            except Exception as exc:
                validation_errors.append(str(exc))
                break

            raw_response = response.output_text
            metadata = {
                "analysis_stage": (
                    "sell_conditions"
                    if agent_name is SpecialistAgentName.SELL_CONDITIONS
                    else "specialist"
                ),
                "analysis_attempt": attempt,
                "model_response_id": getattr(response, "response_id", None),
                "usage": getattr(response, "usage", {}),
                "prompt_sha256": prompt_hash,
                "prompt_contract_version": prompt.contract_version,
                "packet_measurement": prompt.packet_measurement,
            }
            if agent_name is SpecialistAgentName.SELL_CONDITIONS:
                metadata.update(
                    {
                        "upstream_outputs_sha256": _sha256_json(
                            [
                                _serialize_upstream_output(item)
                                for item in (upstream_outputs or ())
                            ]
                        ),
                        "deterministic_scenario_sha256": _sha256_json(
                            deterministic_scenario_data
                        ),
                    }
                )
            artifact_id = self.raw_response_repository.save_specialist_artifact(
                company_id,
                raw_response,
                created_by=getattr(response, "model", "specialist-model"),
                agent_name=agent_name.value,
                run_id=run_id,
                packet_hash=packet_hash,
                metadata=metadata,
            )
            if artifact_id is not None:
                artifact_ids.append(artifact_id)
            try:
                parsed = parse_specialist_output(raw_response)
                self._validate_identity(parsed, packet, run_id, packet_hash, agent_name)
                if agent_name is SpecialistAgentName.SELL_CONDITIONS:
                    _validate_sell_traceability(
                        parsed, upstream_outputs or (), packet
                    )
            except (StockAnalysisValidationError, ValueError, TypeError) as exc:
                validation_errors.append(str(exc))
                if artifact_id is not None:
                    self.raw_response_repository.update_raw_validation(
                        artifact_id, "rejected", str(exc)
                    )
                if attempt == 1 and callable(
                    getattr(self.model_adapter, "repair", None)
                ):
                    continue
                return SpecialistArtifactResult(
                    agent_name.value,
                    "failed",
                    attempt,
                    tuple(artifact_ids),
                    tuple(validation_errors),
                )

            if artifact_id is not None:
                self.raw_response_repository.update_raw_validation(
                    artifact_id, "accepted"
                )
            result_status = {
                SpecialistStatus.COMPLETE: "accepted",
                SpecialistStatus.INSUFFICIENT_EVIDENCE: "limited",
                SpecialistStatus.FAILED: "failed",
            }[parsed.status]
            return SpecialistArtifactResult(
                agent_name.value,
                result_status,
                attempt,
                tuple(artifact_ids),
                tuple(validation_errors),
                parsed,
            )

        return SpecialistArtifactResult(
            agent_name.value,
            "failed",
            len(artifact_ids) or 1,
            tuple(artifact_ids),
            tuple(validation_errors),
        )

    def _unassessable_sell_result(
        self, packet, company_id, run_id, packet_hash, upstream_results, scenario_data
    ):
        missing_agents = [
            result.agent_name
            for result in upstream_results
            if (
                result.output is None
                or result.output.status is not SpecialistStatus.COMPLETE
            )
        ]
        upstream_unavailable = not upstream_results or bool(missing_agents)
        blocker_codes = []
        if upstream_unavailable:
            blocker_codes.append("upstream_specialist_unavailable")
        if not _scenario_data_available(scenario_data):
            blocker_codes.append("deterministic_scenario_unavailable")
        claim_ids = _upstream_claim_ids(upstream_results)
        source_ids = _sell_source_ids_in_catalog(
            packet, _upstream_source_ids(upstream_results, packet)
        )
        tests = [
            SellConditionAssessment(
                break_type=break_type,
                condition="Causal evidence is unavailable for this thesis-break test.",
                observable_metric_or_event="Relevant causal metric or event",
                threshold_or_direction="Unavailable until the required evidence is present",
                current_break_status=SellConditionStatus.UNASSESSABLE,
                response="reassess",
                source_ids=list(source_ids),
                claim_ids=list(claim_ids),
            )
            for break_type in THESIS_BREAK_TYPES
        ]
        blockers = [
            SellConditionActivationBlocker(
                blocker_code=code,
                source_ids=list(source_ids),
                claim_ids=list(claim_ids),
            )
            for code in blocker_codes
        ]
        missing = []
        if upstream_unavailable:
            missing.append(
                SpecialistMissingInformation(
                    item_code="upstream_specialist_outputs",
                    limitation_class="core",
                    impact_code="sell_conditions_unassessable",
                )
            )
        if not _scenario_data_available(scenario_data):
            missing.append(
                SpecialistMissingInformation(
                    item_code="deterministic_scenario_data",
                    limitation_class="core",
                    impact_code="sell_conditions_unassessable",
                )
            )
        output = SpecialistOutput(
            schema_version="specialist-output-v1",
            run_id=run_id,
            agent_name=SpecialistAgentName.SELL_CONDITIONS,
            company_id=company_id,
            ticker=packet["ticker"] if isinstance(packet, dict) else packet.ticker,
            evidence_as_of=_packet_as_of(packet),
            status=SpecialistStatus.INSUFFICIENT_EVIDENCE,
            confidence=SpecialistConfidence.LOW,
            confidence_cap=SpecialistConfidence.LOW,
            claims=[],
            missing_information=missing,
            packet_hash=packet_hash,
            sell_conditions=SellConditionsSpecialistOutput(
                tests=tests,
                current_break_status=SellConditionStatus.UNASSESSABLE,
                activation_blockers=blockers,
            ),
        )
        raw = json.dumps(output.to_dict(), ensure_ascii=False, sort_keys=True)
        artifact_id = self.raw_response_repository.save_specialist_artifact(
            company_id,
            raw,
            "sell-conditions-limited",
            agent_name=SpecialistAgentName.SELL_CONDITIONS.value,
            run_id=run_id,
            packet_hash=packet_hash,
            metadata={
                "analysis_stage": "sell_conditions",
                "analysis_attempt": 0,
                "limited": True,
            },
        )
        if artifact_id is not None:
            self.raw_response_repository.update_raw_validation(artifact_id, "accepted")
        return SpecialistArtifactResult(
            SpecialistAgentName.SELL_CONDITIONS.value,
            "limited",
            0,
            (artifact_id,) if artifact_id is not None else (),
            tuple(blocker_codes),
            output,
        )

    @staticmethod
    def _validate_identity(parsed, packet, run_id, packet_hash, agent_name):
        company_id = (
            packet["company_id"] if isinstance(packet, dict) else packet.company_id
        )
        ticker = packet["ticker"] if isinstance(packet, dict) else packet.ticker
        if parsed.agent_name is not agent_name:
            raise ValueError("specialist agent_name does not match requested agent")
        if parsed.company_id != company_id or parsed.ticker != ticker:
            raise ValueError("specialist identity does not match frozen packet")
        if parsed.run_id != run_id:
            raise ValueError("specialist run_id does not match shadow run")
        if parsed.packet_hash != packet_hash:
            raise ValueError("specialist packet_hash does not match frozen packet")

    def _reuse_completed(self, company_id, run_id, packet_hash, agent_name):
        getter = getattr(
            self.raw_response_repository, "get_specialist_artifacts_for_run", None
        )
        if not callable(getter):
            return None
        for artifact in getter(company_id, run_id):
            metadata = artifact.get("metadata") or {}
            if metadata.get("agent_name") != agent_name.value:
                continue
            if (
                metadata.get("packet_hash") != packet_hash
                or metadata.get("validation_status") != "accepted"
            ):
                continue
            try:
                parsed = parse_specialist_output(artifact["content"])
                self._validate_identity(
                    parsed,
                    {"company_id": company_id, "ticker": parsed.ticker},
                    run_id,
                    packet_hash,
                    agent_name,
                )
            except (KeyError, StockAnalysisValidationError, ValueError, TypeError):
                continue
            return SpecialistArtifactResult(
                agent_name.value,
                {
                    SpecialistStatus.COMPLETE: "accepted",
                    SpecialistStatus.INSUFFICIENT_EVIDENCE: "limited",
                    SpecialistStatus.FAILED: "failed",
                }[parsed.status],
                int(metadata.get("analysis_attempt", 0)),
                (artifact["id"],),
                (),
                parsed,
            )
        return None


def _json_value(value):
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _sha256_json(value):
    serialized = json.dumps(
        _json_value(value), ensure_ascii=False, sort_keys=True, default=str
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _serialize_upstream_output(item):
    if isinstance(item, SpecialistArtifactResult):
        return {
            "agent_name": item.agent_name,
            "status": item.status,
            "attempts": item.attempts,
            "output": item.output.to_dict() if item.output is not None else None,
            "validation_errors": list(item.validation_errors),
        }
    if isinstance(item, SpecialistOutput):
        return {
            "agent_name": item.agent_name.value,
            "status": item.status.value,
            "output": item.to_dict(),
        }
    if isinstance(item, dict):
        return item
    return _json_value(item)


def _deterministic_scenario_data(packet):
    full_results = (
        packet.get("full_results", {})
        if isinstance(packet, dict)
        else packet.full_results
    )
    if not isinstance(full_results, dict):
        return None
    # Keep the sell prompt bounded to deterministic inputs; it never receives
    # the frozen packet or any first-wave narrative here.
    keys = ("reverse_dcf", "financial_history", "valuation", "forward_scenario")
    data = {key: full_results[key] for key in keys if key in full_results}
    # Financial history alone is not a deterministic scenario result. Keep it
    # out of the second-wave input unless the packet has scenario/valuation data.
    return data if any(key in data for key in ("reverse_dcf", "forward_scenario")) else None


def _scenario_data_available(data):
    if not data:
        return False
    status = _scenario_status(data)
    if status is not None and status != "available":
        return False
    if not isinstance(data, dict):
        return status == "available"
    scenario_values = [
        data[key]
        for key in ("reverse_dcf", "forward_scenario")
        if key in data
    ]
    if not scenario_values:
        return status == "available"
    return any(
        _scenario_status(value) == "available"
        for value in scenario_values
    )


def _scenario_status(value):
    status = (
        value.get("status")
        if isinstance(value, dict)
        else getattr(value, "status", None)
    )
    return getattr(status, "value", status)


def _sell_inputs_available(upstream_results, scenario_data):
    return bool(upstream_results) and all(
        result.output is not None
        and result.output.status is SpecialistStatus.COMPLETE
        for result in upstream_results
    ) and _scenario_data_available(scenario_data)


def _domain_claims(output):
    domain = getattr(output, output.agent_name.value, None)
    if domain is None:
        return []
    return list(getattr(domain, "claims", [])) + list(getattr(domain, "event_claims", []))


def _upstream_claim_ids(upstream_results):
    return list(_upstream_references(upstream_results))


def _validate_sell_traceability(output, upstream_results, packet=None):
    references_by_id = _upstream_references(upstream_results, packet)
    known_claim_ids = set(references_by_id)
    sell = output.sell_conditions
    if sell is None:
        return
    references = [
        claim_id
        for test in sell.tests
        for claim_id in test.claim_ids
    ] + [
        claim_id
        for blocker in sell.activation_blockers
        for claim_id in blocker.claim_ids
    ]
    unknown = sorted(set(references) - known_claim_ids)
    if unknown:
        raise ValueError(
            "sell condition references unknown upstream claim IDs: "
            + ", ".join(unknown)
        )
    source_ids = [
        source_id
        for test in sell.tests
        for source_id in test.source_ids
    ] + [
        source_id
        for blocker in sell.activation_blockers
        for source_id in blocker.source_ids
    ]
    if packet is not None:
        permitted_sources = _sell_source_ids_in_catalog(packet, source_ids)
        unknown_sources = sorted(set(source_ids) - set(permitted_sources))
        if unknown_sources:
            raise ValueError(
                "sell condition references unknown frozen-packet source IDs: "
                + ", ".join(unknown_sources)
            )
    for test in sell.tests:
        if test.current_break_status is not SellConditionStatus.TRIGGERED:
            continue
        if not any(
            _causal_reference_matches(
                test.break_type, references_by_id[claim_id]
            )
            for claim_id in test.claim_ids
        ):
            raise ValueError(
                "triggered sell conditions require a source-backed causal upstream claim"
            )


def _upstream_source_ids(upstream_results, packet=None):
    return list(
        dict.fromkeys(
            source_id
            for source_ids, *_ in _upstream_references(upstream_results, packet).values()
            for source_id in source_ids
        )
    )


def _upstream_references(upstream_results, packet=None):
    references = {}
    for result in upstream_results:
        output = result.output
        if output is None:
            continue
        for claim in [*output.claims, *_domain_claims(output)]:
            direction = getattr(claim.direction, "value", claim.direction)
            source_ids = tuple(claim.source_ids)
            source_backed = _source_ids_are_permitted(packet, source_ids)
            references[claim.claim_id] = (
                source_ids,
                "claim",
                source_backed and direction in {"negative", "mixed"},
                str(claim.domain).casefold(),
            )
        management = output.management_credibility
        if management is not None:
            for row in management.ledger:
                source_ids = row.source_ids or [
                    *row.claim_source_ids,
                    *row.outcome_source_ids,
                ]
                result = getattr(row.result, "value", row.result)
                source_backed = _source_ids_are_permitted(packet, source_ids)
                references[row.claim_id] = (
                    tuple(source_ids),
                    "ledger",
                    source_backed and result == "missed",
                    "management_credibility",
                )
    return references


def _packet_evidence_catalog(packet):
    catalog = (
        packet.get("evidence_catalog", {})
        if isinstance(packet, dict)
        else packet.evidence_catalog
    )
    if catalog:
        return catalog
    return build_evidence_catalog(
        packet.get("full_results", {})
        if isinstance(packet, dict)
        else packet.full_results,
        packet.get("research_evidence", {})
        if isinstance(packet, dict)
        else packet.research_evidence,
    )


def _sell_source_ids_in_catalog(packet, source_ids):
    catalog = _packet_evidence_catalog(packet)
    canonical_source_ids = set(catalog.get("canonical_source_ids", []))
    full_results = (
        packet.get("full_results", {})
        if isinstance(packet, dict)
        else packet.full_results
    )
    research_evidence = (
        packet.get("research_evidence", {})
        if isinstance(packet, dict)
        else packet.research_evidence
    )
    permitted = []
    for source_id in source_ids:
        try:
            resolved = resolve_source_id(
                source_id,
                full_results,
                research_evidence,
                catalog=catalog,
            )
        except SourcePathError:
            continue
        if (
            resolved in canonical_source_ids
            or source_id.startswith(("full_results.", "deterministic:"))
        ):
            permitted.append(source_id)
    return list(dict.fromkeys(permitted))


def _source_ids_are_permitted(packet, source_ids):
    if packet is None:
        return bool(source_ids)
    if not source_ids:
        return False
    permitted = _sell_source_ids_in_catalog(packet, source_ids)
    return set(source_ids) == set(permitted)


def _causal_reference_matches(break_type, reference):
    source_ids, _, causal, domain = reference
    return bool(source_ids) and causal and domain in _CAUSAL_CLAIM_DOMAINS[break_type]


def _packet_as_of(packet):
    research = (
        packet.get("research_evidence", {})
        if isinstance(packet, dict)
        else packet.research_evidence
    )
    return research.get("as_of") or "1970-01-01"
