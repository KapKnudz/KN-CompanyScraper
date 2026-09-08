"""Shadow execution of typed specialist agents against a frozen packet."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
import re
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
    "revenue_or_demand": {"business_model", "revenue", "demand"},
    "margin_or_execution": {"margin", "execution"},
    "balance_sheet_or_dilution": {
        "balance_sheet",
        "capital_allocation",
        "dilution",
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
        "evidence",
        "execution",
        "insider_ownership",
        "management",
        "management_credibility",
        "margin",
        "opportunity",
        "revenue",
        "valuation",
    },
}
_CAUSAL_CLAIM_MARKERS = {
    "revenue_or_demand": {"revenue", "demand", "sales", "customer", "churn", "retention"},
    "margin_or_execution": {"margin", "execution", "cost", "profitability"},
    "balance_sheet_or_dilution": {
        "balance",
        "debt",
        "dilution",
        "shares",
        "share",
        "count",
        "financing",
        "capital",
    },
    "management_credibility": {"management", "promise", "guidance", "milestone", "missed"},
    "valuation_overshoot": {"valuation", "multiple", "expectation", "reverse", "dcf", "unsupported", "demanding"},
    "superior_evidence_or_opportunity": {"evidence", "opportunity", "alternative"},
}
_CAUSAL_STATUS_PREDICATES = {"assessment", "result", "state", "status"}
_CAUSAL_STATUS_VALUES_BY_BREAK = {
    "revenue_or_demand": {
        "declining",
        "deteriorated",
        "deteriorating",
        "weak",
        "worsening",
    },
    "margin_or_execution": {
        "declining",
        "deteriorated",
        "deteriorating",
        "failed",
        "invalidated",
        "stalled",
        "weak",
        "worsening",
    },
    "balance_sheet_or_dilution": {
        "deteriorated",
        "deteriorating",
        "failed",
        "increasing",
        "invalidated",
        "stalled",
        "weak",
        "worsening",
    },
    "management_credibility": {
        "deteriorated",
        "deteriorating",
        "failed",
        "invalidated",
        "missed",
        "weak",
        "worsening",
    },
    "valuation_overshoot": set(),
    "superior_evidence_or_opportunity": set(),
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
                [
                    _namespace_upstream_output(item)
                    for item in (upstream_outputs or ())
                ],
                ensure_ascii=False,
                sort_keys=True,
            )
            scenario_json = json.dumps(
                _json_value(deterministic_scenario_data),
                ensure_ascii=False,
                sort_keys=True,
            )
            catalog = _packet_evidence_catalog(packet)
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
        try:
            _upstream_references(upstream_results, packet)
        except ValueError:
            return self._unassessable_sell_result(
                packet,
                company_id,
                run_id,
                packet_hash,
                upstream_results,
                scenario_data,
                additional_missing_information=("upstream_claim_ids",),
            )
        inputs_available = _sell_inputs_available(upstream_results, scenario_data)
        reused = self._reuse_completed(
            company_id,
            run_id,
            packet_hash,
            SpecialistAgentName.SELL_CONDITIONS,
            upstream_outputs=upstream_results,
            deterministic_scenario_data=scenario_data,
        )
        reuse_found = reused is not None
        if reused is not None:
            try:
                _validate_sell_traceability(reused.output, upstream_results, packet)
                _validate_sell_dependency_blockers(
                    reused.output, inputs_available, scenario_data
                )
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
        if result.status == "failed":
            return result
        if (
            result.output is not None
            and result.output.status is SpecialistStatus.INSUFFICIENT_EVIDENCE
            and result.output.sell_conditions is not None
        ):
            return result
        if result.output is not None and result.output.status is not SpecialistStatus.COMPLETE:
            return self._unassessable_sell_result(
                packet,
                company_id,
                run_id,
                packet_hash,
                upstream_results,
                scenario_data,
                additional_missing_information=("sell_conditions_graph",),
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
            reused = self._reuse_completed(
                company_id,
                run_id,
                packet_hash,
                agent_name,
                upstream_outputs=upstream_outputs,
                deterministic_scenario_data=deterministic_scenario_data,
            )
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
                                _stable_upstream_output(item)
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
                    _validate_sell_dependency_blockers(
                        parsed,
                        _sell_inputs_available(
                            upstream_outputs or (), deterministic_scenario_data
                        ),
                        deterministic_scenario_data,
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
        self,
        packet,
        company_id,
        run_id,
        packet_hash,
        upstream_results,
        scenario_data,
        additional_missing_information=(),
    ):
        missing_agents = [
            agent.value
            for agent in FIRST_WAVE_SPECIALISTS
            if not any(
                result.agent_name == agent.value
                and result.output is not None
                and result.output.status is SpecialistStatus.COMPLETE
                for result in upstream_results
            )
        ]
        upstream_unavailable = not upstream_results or bool(missing_agents)
        blocker_codes = []
        if upstream_unavailable:
            blocker_codes.append("upstream_specialist_unavailable")
        if not _scenario_data_available(scenario_data):
            blocker_codes.append("deterministic_scenario_unavailable")
        try:
            references = _upstream_references(upstream_results, packet)
        except ValueError:
            references = {}
        tests = [
            SellConditionAssessment(
                break_type=break_type,
                condition="Causal evidence is unavailable for this thesis-break test.",
                observable_metric_or_event="Relevant causal metric or event",
                threshold_or_direction="Unavailable until the required evidence is present",
                current_break_status=SellConditionStatus.UNASSESSABLE,
                response="reassess",
                source_ids=list(
                    dict.fromkeys(
                        source_id
                        for claim_id, reference in references.items()
                        if reference[2]
                        and reference[3] in _CAUSAL_CLAIM_DOMAINS[break_type]
                        for source_id in reference[0]
                    )
                ),
                claim_ids=[
                    claim_id
                    for claim_id, reference in references.items()
                    if reference[2]
                    and reference[3] in _CAUSAL_CLAIM_DOMAINS[break_type]
                ],
            )
            for break_type in THESIS_BREAK_TYPES
        ]
        blockers = [
            SellConditionActivationBlocker(blocker_code=code)
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
            missing.extend(
                SpecialistMissingInformation(
                    item_code=f"upstream_{agent_name}",
                    limitation_class="core",
                    impact_code="sell_conditions_unassessable",
                )
                for agent_name in missing_agents
            )
        if not _scenario_data_available(scenario_data):
            missing.append(
                SpecialistMissingInformation(
                    item_code="deterministic_scenario_data",
                    limitation_class="core",
                    impact_code="sell_conditions_unassessable",
                )
            )
        missing.extend(
            SpecialistMissingInformation(
                item_code=item_code,
                limitation_class="core",
                impact_code="sell_conditions_unassessable",
            )
            for item_code in additional_missing_information
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
                "upstream_outputs_sha256": _sha256_json(
                    [
                        _stable_upstream_output(item)
                        for item in (upstream_results or ())
                    ]
                ),
                "deterministic_scenario_sha256": _sha256_json(scenario_data),
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

    def _reuse_completed(
        self,
        company_id,
        run_id,
        packet_hash,
        agent_name,
        *,
        upstream_outputs=None,
        deterministic_scenario_data=None,
    ):
        getter = getattr(
            self.raw_response_repository, "get_specialist_artifacts_for_run", None
        )
        if not callable(getter):
            return None
        artifacts = list(getter(company_id, run_id))
        if agent_name is SpecialistAgentName.SELL_CONDITIONS:
            artifacts = reversed(artifacts)
        limited_reuse = None
        for artifact in artifacts:
            metadata = artifact.get("metadata") or {}
            if metadata.get("agent_name") != agent_name.value:
                continue
            if (
                metadata.get("packet_hash") != packet_hash
                or metadata.get("validation_status") != "accepted"
            ):
                continue
            if agent_name is SpecialistAgentName.SELL_CONDITIONS and (
                metadata.get("upstream_outputs_sha256")
                != _sha256_json(
                    [
                        _stable_upstream_output(item)
                        for item in (upstream_outputs or ())
                    ]
                )
                or metadata.get("deterministic_scenario_sha256")
                != _sha256_json(deterministic_scenario_data)
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
            candidate = SpecialistArtifactResult(
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
            if agent_name is SpecialistAgentName.SELL_CONDITIONS:
                if parsed.status is SpecialistStatus.FAILED:
                    continue
                if parsed.status is SpecialistStatus.INSUFFICIENT_EVIDENCE:
                    if limited_reuse is None:
                        limited_reuse = candidate
                    continue
            return candidate
        return limited_reuse


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


def _qualified_claim_id(agent_name, claim_id):
    return f"{agent_name}:{claim_id}"


def _namespace_upstream_output(item):
    serialized = _serialize_upstream_output(item)
    if not isinstance(serialized, dict):
        return serialized
    data = dict(serialized)
    output = data.get("output", data)
    if not isinstance(output, dict):
        return data
    agent_name = str(data.get("agent_name", output.get("agent_name", "")))
    if not agent_name:
        return data
    output = dict(output)

    def namespace_claim(claim):
        claim = dict(claim)
        if "claim_id" in claim:
            claim["claim_id"] = _qualified_claim_id(agent_name, claim["claim_id"])
        if "depends_on_claim_ids" in claim:
            claim["depends_on_claim_ids"] = [
                _qualified_claim_id(agent_name, claim_id)
                for claim_id in claim["depends_on_claim_ids"]
            ]
        return claim

    output["claims"] = [namespace_claim(claim) for claim in output.get("claims", [])]
    for domain_name in (
        "business_model",
        "management_credibility",
        "insider_ownership",
        "growth_valuation",
    ):
        domain = output.get(domain_name)
        if not isinstance(domain, dict):
            continue
        domain = dict(domain)
        for field_name in ("claims", "event_claims"):
            if field_name in domain:
                domain[field_name] = [
                    namespace_claim(claim) for claim in domain[field_name]
                ]
        if domain_name == "management_credibility":
            domain["ledger"] = [
                {
                    **row,
                    "claim_id": _qualified_claim_id(agent_name, row["claim_id"]),
                }
                for row in domain.get("ledger", [])
            ]
        output[domain_name] = domain
    if "output" in data:
        data["output"] = output
    else:
        data = output
    return data


def _stable_upstream_output(item):
    if isinstance(item, SpecialistArtifactResult):
        return {
            "agent_name": item.agent_name,
            "status": item.status,
            "output": item.output.to_dict() if item.output is not None else None,
        }
    serialized = _serialize_upstream_output(item)
    if isinstance(serialized, dict):
        return {
            key: value
            for key, value in serialized.items()
            if key not in {"attempts", "validation_errors"}
        }
    return serialized


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
    keys = ("reverse_dcf", "forward_scenario")
    data = {key: full_results[key] for key in keys if key in full_results}
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
    expected_agents = {agent.value for agent in FIRST_WAVE_SPECIALISTS}
    actual_agents = {result.agent_name for result in upstream_results}
    return (
        len(upstream_results) == len(expected_agents)
        and actual_agents == expected_agents
        and all(
        result.output is not None
        and result.output.status is SpecialistStatus.COMPLETE
        for result in upstream_results
        )
        and _scenario_data_available(scenario_data)
    )


def _domain_claims(output):
    domain = getattr(output, output.agent_name.value, None)
    if domain is None:
        return []
    return list(getattr(domain, "claims", [])) + list(getattr(domain, "event_claims", []))


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
    for blocker in sell.activation_blockers:
        cited_sources = {
            source_id
            for claim_id in blocker.claim_ids
            for source_id in references_by_id[claim_id][0]
        }
        if _resolved_source_ids(packet, blocker.source_ids) - _resolved_source_ids(
            packet, cited_sources
        ):
            raise ValueError(
                "sell activation blocker sources must support cited upstream claims"
            )
        expected_domains = _CAUSAL_CLAIM_DOMAINS.get(blocker.blocker_code)
        if expected_domains is not None and any(
            references_by_id[claim_id][3] not in expected_domains
            for claim_id in blocker.claim_ids
        ):
            raise ValueError(
                "sell activation blocker claims do not match blocker semantics"
            )
    for test in sell.tests:
        cited_sources = {
            source_id
            for claim_id in test.claim_ids
            for source_id in references_by_id[claim_id][0]
        }
        if _resolved_source_ids(packet, test.source_ids) - _resolved_source_ids(
            packet, cited_sources
        ):
            raise ValueError(
                "sell condition sources must support cited upstream claims"
            )
        if test.current_break_status is not SellConditionStatus.UNASSESSABLE and any(
            references_by_id[claim_id][3]
            not in _CAUSAL_CLAIM_DOMAINS[test.break_type]
            for claim_id in test.claim_ids
        ):
            raise ValueError(
                "sell condition claims do not match break semantics"
            )
        if test.current_break_status is not SellConditionStatus.TRIGGERED:
            continue
        if not any(
            _causal_reference_matches(
                test.break_type,
                references_by_id[claim_id],
                test.observable_metric_or_event,
                test.condition,
                test.threshold_or_direction,
                test.source_ids,
                packet,
            )
            for claim_id in test.claim_ids
        ):
            raise ValueError(
                "triggered sell conditions require a source-backed causal upstream claim"
            )


def _validate_sell_dependency_blockers(output, inputs_available, scenario_data):
    if output is None or output.sell_conditions is None:
        return
    blocker_codes = {
        blocker.blocker_code for blocker in output.sell_conditions.activation_blockers
    }
    if inputs_available and "upstream_specialist_unavailable" in blocker_codes:
        raise ValueError(
            "sell dependency blocker contradicts available upstream specialists"
        )
    if _scenario_data_available(scenario_data) and (
        "deterministic_scenario_unavailable" in blocker_codes
    ):
        raise ValueError(
            "sell dependency blocker contradicts available scenario data"
        )


def _upstream_references(upstream_results, packet=None):
    references = {}
    for result in upstream_results:
        output = result.output
        if output is None:
            continue
        agent_name = output.agent_name.value
        for claim in [*output.claims, *_domain_claims(output)]:
            claim_id = _qualified_claim_id(agent_name, claim.claim_id)
            if claim_id in references:
                raise ValueError(
                    "duplicate upstream specialist claim ID: " + claim_id
                )
            direction = getattr(claim.direction, "value", claim.direction)
            source_ids = tuple(claim.source_ids)
            source_backed = _source_ids_are_permitted(packet, source_ids)
            references[claim_id] = (
                source_ids,
                "claim",
                source_backed,
                str(claim.domain).casefold(),
                str(claim.predicate).casefold(),
                claim.value,
                direction,
            )
        management = output.management_credibility
        if management is not None:
            for row in management.ledger:
                claim_id = _qualified_claim_id(agent_name, row.claim_id)
                if claim_id in references:
                    raise ValueError(
                        "duplicate upstream specialist claim ID: " + claim_id
                    )
                source_ids = row.source_ids or [
                    *row.claim_source_ids,
                    *row.outcome_source_ids,
                ]
                result = getattr(row.result, "value", row.result)
                source_backed = _source_ids_are_permitted(packet, source_ids)
                references[claim_id] = (
                    tuple(source_ids),
                    "ledger",
                    source_backed,
                    "management_credibility",
                    "management_ledger_result",
                    result,
                    "negative" if result == "missed" else "neutral",
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


def _resolved_source_ids(packet, source_ids):
    if packet is None:
        return set(source_ids)
    catalog = _packet_evidence_catalog(packet)
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
    resolved_ids = set()
    for source_id in source_ids:
        try:
            resolved_ids.add(
                resolve_source_id(
                    source_id,
                    full_results,
                    research_evidence,
                    catalog=catalog,
                )
            )
        except SourcePathError:
            continue
    return resolved_ids


def _semantic_tokens(value):
    if isinstance(value, (list, tuple, set)):
        tokens = set()
        for item in value:
            tokens.update(_semantic_tokens(item))
        return tokens
    return set(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _causal_condition_direction(
    break_type,
    condition,
    threshold_or_direction,
    typed_claim_tokens=(),
    observed_metric_tokens=(),
):
    text = " ".join(
        str(value).casefold()
        for value in (condition, threshold_or_direction)
    )
    clauses = re.split(
        r"\b(?:despite|although|though|but|while)\b", text
    )
    if len(clauses) > 1:
        break_markers = (
            set(typed_claim_tokens)
            | set(observed_metric_tokens)
            | _CAUSAL_CLAIM_MARKERS[break_type]
        )
        matching_clauses = [
            clause
            for clause in clauses
            if _semantic_tokens(clause).intersection(break_markers)
        ]
        if matching_clauses:
            text = max(
                enumerate(matching_clauses),
                key=lambda item: (
                    len(_semantic_tokens(item[1]).intersection(observed_metric_tokens)),
                    len(_semantic_tokens(item[1]).intersection(typed_claim_tokens)),
                    len(_semantic_tokens(item[1]).intersection(_CAUSAL_CLAIM_MARKERS[break_type])),
                    item[0],
                ),
            )
            text = text[1]
        else:
            text = clauses[0]
    adverse_terms = r"declin\w*|decreas\w*|fall\w*|drop\w*|worsen\w*|deteriorat\w*|weaken\w*|fail\w*|miss\w*|stall\w*|below|under|shortfall|unmet|insufficient|breach"
    favorable_terms = r"improv\w*|increas\w*|grow\w*|strengthen\w*|ris\w*|higher|better|expand\w*|recover\w*"
    if break_type == "balance_sheet_or_dilution":
        negation = r"(?:does not|doesn't|did not|didn't|no|not|never|fails to|failed to)"
        balance_subjects = {
            "debt": (
                r"(?:debt|leverage)",
                r"increas\w*|ris\w*|grow\w*|deteriorat\w*|worsen\w*|weaken\w*",
                r"decreas\w*|fall\w*|drop\w*|improv\w*|strengthen\w*|reduc\w*|lower\w*",
            ),
            "share_count": (
                r"(?:share\s+count|shares?|dilution)",
                r"increas\w*|ris\w*|grow\w*|deteriorat\w*|worsen\w*|dilut\w*",
                r"decreas\w*|fall\w*|drop\w*|improv\w*|strengthen\w*|reduc\w*|lower\w*",
            ),
        }
        for subject_pattern, adverse_subject_terms, favorable_subject_terms in balance_subjects.values():
            if not re.search(rf"\b{subject_pattern}\b", text):
                continue
            if re.search(
                rf"\b{subject_pattern}\b(?:\s+\w+){{0,3}}\s+{negation}\s+(?:{adverse_subject_terms})\b",
                text,
            ):
                return "favorable"
            if re.search(
                rf"\b{subject_pattern}\b(?:\s+\w+){{0,3}}\s+{negation}\s+(?:{favorable_subject_terms})\b",
                text,
            ):
                return "adverse"
            if re.search(
                rf"\b{subject_pattern}\b(?:\s+\w+){{0,3}}\s+(?:{adverse_subject_terms})\b",
                text,
            ):
                return "adverse"
            if re.search(
                rf"\b{subject_pattern}\b(?:\s+\w+){{0,3}}\s+(?:{favorable_subject_terms})\b",
                text,
            ):
                return "favorable"
    if re.search(
        rf"\b(?:does not|doesn't|did not|didn't|no|not|never|fails to|failed to)\s+(?:{favorable_terms})\b",
        text,
    ):
        return "adverse"
    if re.search(
        rf"\b(?:does not|doesn't|did not|didn't|no|not|never|fails to|failed to)\s+(?:{adverse_terms})\b",
        text,
    ):
        return "favorable"
    if re.search(rf"\b(?:{favorable_terms})\b", text):
        return "favorable"
    if re.search(rf"\b(?:{adverse_terms})\b", text):
        return "adverse"
    return "neutral"


def _causal_reference_matches(
    break_type,
    reference,
    observable_metric_or_event,
    condition,
    threshold_or_direction,
    sell_source_ids,
    packet=None,
):
    source_ids, _, causal, domain, predicate, value, direction = reference
    if not _resolved_source_ids(packet, source_ids).intersection(
        _resolved_source_ids(packet, sell_source_ids)
    ):
        return False
    if not causal:
        return False
    expected_directions = (
        {"positive", "mixed"}
        if break_type == "superior_evidence_or_opportunity"
        else {"negative", "mixed"}
    )
    if direction not in expected_directions:
        return False
    if domain not in _CAUSAL_CLAIM_DOMAINS[break_type]:
        return False
    predicate_tokens = _semantic_tokens(predicate)
    value_tokens = _semantic_tokens(value)
    typed_claim_tokens = predicate_tokens | value_tokens
    if not (
        typed_claim_tokens.intersection(_CAUSAL_CLAIM_MARKERS[break_type])
        or (
            predicate_tokens.intersection(_CAUSAL_STATUS_PREDICATES)
            and value_tokens.intersection(_CAUSAL_STATUS_VALUES_BY_BREAK[break_type])
        )
    ):
        return False
    typed_claim_tokens.update(_semantic_tokens(domain))
    observable_tokens = _semantic_tokens(observable_metric_or_event)
    condition_direction = _causal_condition_direction(
        break_type,
        condition,
        threshold_or_direction,
        typed_claim_tokens,
        observable_tokens,
    )
    if (
        direction in {"negative", "mixed"}
        and condition_direction == "favorable"
    ) or (direction == "positive" and condition_direction == "adverse"):
        return False
    evidence_text_tokens = _semantic_tokens(
        (observable_metric_or_event, condition, threshold_or_direction)
    )
    if break_type != "valuation_overshoot" and observable_tokens.intersection(
        {"price", "quote", "quotation"}
    ):
        return False
    if not observable_tokens.intersection(typed_claim_tokens):
        if not (
            break_type == "valuation_overshoot"
            and "unsupported" in typed_claim_tokens
            and observable_tokens.intersection({"price", "share", "stock", "market"})
        ):
            return False
    if break_type != "valuation_overshoot" and evidence_text_tokens.intersection(
        {"price", "quote", "quotation"}
    ):
        expected_condition_direction = (
            "favorable" if direction == "positive" else "adverse"
        )
        observed_condition_direction = _causal_condition_direction(
            break_type,
            condition,
            "",
            typed_claim_tokens,
            observable_tokens,
        )
        if observed_condition_direction != expected_condition_direction:
            return False
    return True


def _packet_as_of(packet):
    research = (
        packet.get("research_evidence", {})
        if isinstance(packet, dict)
        else packet.research_evidence
    )
    return research.get("as_of") or "1970-01-01"
