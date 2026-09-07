"""Shadow execution of typed specialist agents against a frozen packet."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from uuid import uuid4

from kncompanyscraper.analysis.agent.agent_packet import (
    AgentCandidatePacket,
    serialize_packet,
)
from kncompanyscraper.analysis.agent.output_schema import (
    SpecialistAgentName,
    SpecialistOutput,
    specialist_output_json_schema,
)
from kncompanyscraper.analysis.agent.packet_measurement import measure_packet
from kncompanyscraper.analysis.agent.prompt_artifact import serialize_prompt
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_specialist_output,
)


FIRST_WAVE_SPECIALISTS = (
    SpecialistAgentName.BUSINESS_MODEL,
    SpecialistAgentName.MANAGEMENT_CREDIBILITY,
    SpecialistAgentName.MARGIN,
    SpecialistAgentName.INSIDER_OWNERSHIP,
    SpecialistAgentName.GROWTH_VALUATION,
)

_SPECIALIST_INSTRUCTIONS = {
    SpecialistAgentName.BUSINESS_MODEL: "Assess business mechanics and understandability only.",
    SpecialistAgentName.MANAGEMENT_CREDIBILITY: "Assess observable management execution and the coverage-tiered ledger only.",
    SpecialistAgentName.MARGIN: "Assess current and defensible margin mechanics only.",
    SpecialistAgentName.INSIDER_OWNERSHIP: "Classify insider, ownership, liquidity, and flow evidence only.",
    SpecialistAgentName.GROWTH_VALUATION: "Assess sourced growth and valuation expectations; do not calculate prices or returns.",
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

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "company_id": self.company_id,
            "packet_hash": self.packet_hash,
            "results": [result.to_dict() for result in self.results],
        }


class SpecialistPromptBuilder:
    """Build a narrow prompt while preserving the normal adapter seam."""

    CONTRACT_VERSION = "specialist-shadow-prompt-v1"
    POLICY_NAME = "specialist-shadow-analysis"
    POLICY_VERSION = "1.0.0"

    def build(
        self, packet: AgentCandidatePacket | dict, agent_name: SpecialistAgentName
    ) -> AgentPrompt:
        packet_json = serialize_packet(packet)
        schema = specialist_output_json_schema(agent_name.value)
        return AgentPrompt(
            system=(
                "You are a non-authoritative shadow specialist. Return only the closed "
                "specialist-output-v1 JSON object. Do not emit a verdict, scenario "
                "prices, returns, fair value, position size, or prose outside JSON. "
                f"Your responsibility: {_SPECIALIST_INSTRUCTIONS[agent_name]} "
                "Use exact source IDs from the frozen packet and mark missing evidence "
                "explicitly."
            ),
            user=(
                f"Agent name: {agent_name.value}\n\n"
                "Frozen AgentCandidatePacket:\n"
                f"{packet_json}\n\n"
                "Return the specialist contract for this agent."
            ),
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            policy_sha256=sha256(self.POLICY_VERSION.encode("utf-8")).hexdigest(),
            output_schema=schema,
            schema_name=f"specialist_{agent_name.value}",
            packet_measurement=asdict(measure_packet(packet, pretty=False)),
            contract_version=self.CONTRACT_VERSION,
        )


class ShadowSpecialistRunner:
    """Run first-wave specialists without entering the authoritative analysis path."""

    def __init__(
        self,
        model_adapter,
        raw_response_repository,
        *,
        prompt_builder=None,
        specialists=FIRST_WAVE_SPECIALISTS,
    ):
        self.model_adapter = model_adapter
        self.raw_response_repository = raw_response_repository
        self.prompt_builder = prompt_builder or SpecialistPromptBuilder()
        self.specialists = tuple(SpecialistAgentName(agent) for agent in specialists)

    def run(
        self,
        packet: AgentCandidatePacket | dict,
        *,
        run_id: str | None = None,
        packet_hash: str | None = None,
    ) -> ShadowSpecialistRun:
        packet_json = serialize_packet(packet)
        computed_hash = sha256(packet_json.encode("utf-8")).hexdigest()
        if packet_hash is not None and packet_hash != computed_hash:
            raise ValueError("specialist packet hash does not match frozen packet")
        packet_hash = packet_hash or computed_hash
        run_id = run_id or f"shadow-{uuid4()}"
        company_id = packet["company_id"] if isinstance(packet, dict) else packet.company_id
        results = tuple(
            self._run_one(packet, company_id, run_id, packet_hash, agent_name)
            for agent_name in self.specialists
        )
        return ShadowSpecialistRun(run_id, company_id, packet_hash, results)

    def _run_one(self, packet, company_id, run_id, packet_hash, agent_name):
        reused = self._reuse_completed(company_id, run_id, packet_hash, agent_name)
        if reused is not None:
            return reused

        prompt = self.prompt_builder.build(packet, agent_name)
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
                "analysis_stage": "specialist",
                "analysis_attempt": attempt,
                "attempt": attempt,
                "model_response_id": getattr(response, "response_id", None),
                "usage": getattr(response, "usage", {}),
                "prompt_sha256": prompt_hash,
                "prompt_contract_version": prompt.contract_version,
                "packet_measurement": prompt.packet_measurement,
            }
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
            except (StockAnalysisValidationError, ValueError, TypeError) as exc:
                validation_errors.append(str(exc))
                if artifact_id is not None:
                    self.raw_response_repository.update_raw_validation(
                        artifact_id, "rejected", str(exc)
                    )
                if attempt == 1 and callable(getattr(self.model_adapter, "repair", None)):
                    continue
                return SpecialistArtifactResult(
                    agent_name.value,
                    "failed",
                    attempt,
                    tuple(artifact_ids),
                    tuple(validation_errors),
                )

            if artifact_id is not None:
                self.raw_response_repository.update_raw_validation(artifact_id, "accepted")
            return SpecialistArtifactResult(
                agent_name.value,
                "accepted",
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

    @staticmethod
    def _validate_identity(parsed, packet, run_id, packet_hash, agent_name):
        company_id = packet["company_id"] if isinstance(packet, dict) else packet.company_id
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
        getter = getattr(self.raw_response_repository, "get_specialist_artifacts_for_run", None)
        if not callable(getter):
            return None
        for artifact in getter(company_id, run_id):
            metadata = artifact.get("metadata") or {}
            if metadata.get("agent_name") != agent_name.value:
                continue
            if metadata.get("packet_hash") != packet_hash or metadata.get("validation_status") != "accepted":
                continue
            try:
                parsed = parse_specialist_output(artifact["content"])
                self._validate_identity(parsed, {"company_id": company_id, "ticker": parsed.ticker}, run_id, packet_hash, agent_name)
            except (KeyError, StockAnalysisValidationError, ValueError, TypeError):
                continue
            return SpecialistArtifactResult(
                agent_name.value,
                "accepted",
                int(metadata.get("analysis_attempt", metadata.get("attempt", 1))),
                (artifact["id"],),
                (),
                parsed,
            )
        return None
