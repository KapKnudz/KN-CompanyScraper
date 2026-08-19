from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from kncompanyscraper.analysis.agent.context_provenance import (
    deterministic_context_sha256,
)
from kncompanyscraper.analysis.agent.output_schema import (
    THESIS_UPDATE_OUTPUT_CONTRACT,
    _contract_to_json_schema,
    thesis_update_json_schema,
)
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt, AgentPromptBuilder
from kncompanyscraper.analysis.agent.result_parser import _parse_contract
from kncompanyscraper.analysis.agent.thesis_update import ThesisUpdateContext


THESIS_CHALLENGE_CONTRACT = {
    "challenged_claim": "string",
    "severity": "low | medium | high",
    "verdict": "survives | revision_required | insufficient_evidence | reject",
    "summary": "string",
    "methodology_findings": ["string"],
    "evidence_findings": [
        {
            "statement": "string",
            "source_ids": ["string"],
        }
    ],
    "missing_evidence": ["string"],
    "decision_impact": "string",
}


@dataclass(frozen=True)
class ChallengeEvidenceFinding:
    statement: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ThesisChallengeResult:
    challenged_claim: str
    severity: str
    verdict: str
    summary: str
    methodology_findings: tuple[str, ...]
    evidence_findings: tuple[ChallengeEvidenceFinding, ...]
    missing_evidence: tuple[str, ...]
    decision_impact: str

    def to_dict(self) -> dict:
        return asdict(self)


class ThesisChallengePromptBuilder:
    POLICY_VERSION = "thesis-challenge-v1"

    def build(self, thesis: dict, evidence: dict, question: str) -> AgentPrompt:
        packet = {
            "question": question,
            "thesis": thesis["content"],
            "thesis_revision": thesis["revision"],
            "evidence_as_of": (
                thesis["evidence_as_of"].isoformat()
                if hasattr(thesis.get("evidence_as_of"), "isoformat")
                else thesis.get("evidence_as_of")
            ),
            "original_evidence": evidence,
            "valuation_provenance": thesis.get("metadata", {}).get(
                "valuation_provenance"
            ),
        }
        return AgentPrompt(
            system=(
                "Audit the exact stored thesis using only its original evidence packet. "
                "Do not repair it with later knowledge or invent sources. Challenge the "
                "specific claim in the user's question, including methodology where relevant. "
                "A high-severity finding is one that could change actionability, tier, or the "
                "sign of the supported return case. Return only the required JSON."
            ),
            user=json.dumps(packet, ensure_ascii=False, indent=2, default=str),
            policy_name="thesis-challenge-policy",
            policy_version=self.POLICY_VERSION,
            output_schema=_contract_to_json_schema(THESIS_CHALLENGE_CONTRACT),
            schema_name="thesis_challenge",
        )


class ThesisChallengeService:
    def __init__(self, model_adapter, repository, prompt_builder=None):
        self.model_adapter = model_adapter
        self.repository = repository
        self.prompt_builder = prompt_builder or ThesisChallengePromptBuilder()

    def challenge(
        self,
        thesis: dict,
        evidence: dict,
        question: str,
        *,
        origin: str = "human",
    ) -> tuple[int, ThesisChallengeResult]:
        prompt = self.prompt_builder.build(thesis, evidence, question)
        response = self.model_adapter.generate(prompt)
        payload = _parse_contract(
            response.output_text,
            THESIS_CHALLENGE_CONTRACT,
            "thesis-challenge",
        )
        result = ThesisChallengeResult(
            challenged_claim=payload["challenged_claim"].strip(),
            severity=payload["severity"],
            verdict=payload["verdict"],
            summary=payload["summary"].strip(),
            methodology_findings=tuple(payload["methodology_findings"]),
            evidence_findings=tuple(
                ChallengeEvidenceFinding(
                    statement=item["statement"].strip(),
                    source_ids=tuple(item["source_ids"]),
                )
                for item in payload["evidence_findings"]
            ),
            missing_evidence=tuple(payload["missing_evidence"]),
            decision_impact=payload["decision_impact"].strip(),
        )
        self._validate(result, evidence)
        challenge_id = self.repository.save(
            thesis_revision_id=thesis["id"],
            company_id=thesis["company_id"],
            question=question,
            origin=origin,
            result=result,
            created_by=response.model,
            metadata={
                "model_response_id": response.response_id,
                "usage": response.usage,
                "policy_version": prompt.policy_version,
                "original_evidence_source_ids": sorted(self._source_ids(evidence)),
            },
        )
        return challenge_id, result

    @classmethod
    def _validate(cls, result: ThesisChallengeResult, evidence: dict) -> None:
        if not result.challenged_claim or not result.summary or not result.decision_impact:
            raise ValueError("challenge claim, summary, and decision impact cannot be empty")
        known = cls._source_ids(evidence)
        cited = {
            source_id
            for finding in result.evidence_findings
            for source_id in finding.source_ids
        }
        unknown = sorted(cited - known)
        if unknown:
            raise ValueError("challenge cites unknown original evidence: " + ", ".join(unknown))

    @staticmethod
    def _source_ids(evidence: dict) -> set[str]:
        return {
            item["source_id"]
            for key in ("documents", "insider_transactions")
            for item in evidence.get(key, [])
            if item.get("source_id")
        }


@dataclass(frozen=True)
class ThesisChallengeResponseOutcome:
    challenge_id: int
    status: str
    impact: str | None = None
    analysis_id: int | None = None


class ThesisChallengeResponsePromptBuilder:
    POLICY_NAME = "thesis-challenge-response-policy"
    POLICY_VERSION = "1.0.0"

    def build(
        self,
        challenge: dict,
        context: ThesisUpdateContext,
        evidence: dict,
    ) -> AgentPrompt:
        policy = AgentPromptBuilder._read_resource("resources/analyst_policy.md")
        workflow = AgentPromptBuilder._read_resource("resources/analysis_workflow.md")
        system = (
            f"{policy}\n\n{workflow}\n\n"
            "You are the original analyst responding once to a stored challenge. "
            "Use only the thesis's original evidence packet and deterministic context. "
            "Either preserve the thesis exactly with no_material_change, revise it in "
            "direct response to the challenge, or request a full reassessment. Do not "
            "introduce later evidence. Forward numeric outputs remain calculator-derived: "
            "provide sourced bounded assumptions and set forward_scenario_analysis to null. "
            "Return only the required JSON."
        )
        packet = {
            "challenge": {
                "id": challenge["id"],
                "question": challenge["question"],
                "challenged_claim": challenge["challenged_claim"],
                "severity": challenge["severity"],
                "verdict": challenge["verdict"],
                "audit": (challenge.get("content") or {}).get("result"),
            },
            "current_thesis": context.current_thesis,
            "current_facts": context.current_facts,
            "original_evidence": evidence,
            "candidate": asdict(context.candidate),
            "output_contract": THESIS_UPDATE_OUTPUT_CONTRACT,
        }
        return AgentPrompt(
            system=system,
            user=json.dumps(packet, ensure_ascii=False, indent=2, default=str),
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            policy_sha256=sha256(system.encode("utf-8")).hexdigest(),
            output_schema=thesis_update_json_schema(),
            schema_name="thesis_update",
        )


class ThesisChallengeResponseService:
    def __init__(
        self,
        model_adapter,
        execution_boundary,
        challenge_repository,
        raw_response_repository,
        prompt_builder=None,
    ):
        self.model_adapter = model_adapter
        self.execution_boundary = execution_boundary
        self.challenge_repository = challenge_repository
        self.raw_response_repository = raw_response_repository
        self.prompt_builder = prompt_builder or ThesisChallengeResponsePromptBuilder()

    def respond(
        self,
        challenge: dict,
        thesis: dict,
        candidate,
        evidence: dict,
        current_facts: list[dict],
    ) -> ThesisChallengeResponseOutcome:
        self._validate_target(challenge, thesis, candidate)
        if thesis["id"] != challenge["thesis_revision_id"]:
            return self._resolve_already_persisted(challenge, thesis)

        context = self._build_context(thesis, candidate, evidence, current_facts)
        raw = self._existing_raw_response(challenge)
        if raw is None:
            prompt = self.prompt_builder.build(challenge, context, evidence)
            response = self.model_adapter.generate(prompt)
            metadata = {
                "analysis_mode": "challenge_response",
                "challenge_id": challenge["id"],
                "prior_thesis_revision_id": thesis["id"],
                "policy_name": prompt.policy_name,
                "policy_version": prompt.policy_version,
                "policy_sha256": prompt.policy_sha256,
                "model_response_id": response.response_id,
                "usage": response.usage,
                "evidence_source_ids": list(context.prior_source_ids),
                "deterministic_context_sha256": context.deterministic_context_sha256,
            }
            raw_id = self.raw_response_repository.save_stock_analysis_raw(
                candidate.company_id,
                response.output_text,
                created_by=response.model,
                metadata=metadata,
            )
            self.challenge_repository.attach_response_attempt(challenge["id"], raw_id)
            raw = {
                "id": raw_id,
                "content": response.output_text,
                "created_by": response.model,
                "metadata": metadata,
            }

        metadata = dict(raw.get("metadata") or {})
        for key in ("analysis_mode", "validation_status", "validation_error"):
            metadata.pop(key, None)
        metadata.update(
            {
                "challenge_id": challenge["id"],
                "prior_thesis_revision_id": thesis["id"],
                "raw_analysis_id": raw["id"],
            }
        )
        try:
            accepted = self.execution_boundary.persist_response(
                raw["content"],
                context,
                created_by=raw["created_by"],
                metadata=metadata,
            )
        except Exception as exc:
            self.raw_response_repository.update_raw_validation(
                raw["id"], "rejected", str(exc)
            )
            raise

        self.raw_response_repository.update_raw_validation(raw["id"], "accepted")
        if accepted.persisted_analysis is None:
            return ThesisChallengeResponseOutcome(
                challenge["id"],
                "full_reassessment_required",
                accepted.update.impact,
            )

        resolution = (
            "upheld" if accepted.update.impact == "no_material_change" else "revised"
        )
        analysis_id = accepted.persisted_analysis.analysis_id
        self.challenge_repository.resolve_with_response(
            challenge["id"],
            resolution,
            accepted.update.summary,
            analysis_id,
        )
        return ThesisChallengeResponseOutcome(
            challenge["id"], resolution, accepted.update.impact, analysis_id
        )

    def _existing_raw_response(self, challenge: dict) -> dict | None:
        raw_id = challenge.get("response_raw_analysis_id")
        if raw_id is None:
            return None
        raw = self.raw_response_repository.get_stock_analysis_raw(raw_id)
        if raw is None:
            raise ValueError("stored challenge response is missing")
        return raw

    def _resolve_already_persisted(
        self, challenge: dict, thesis: dict
    ) -> ThesisChallengeResponseOutcome:
        metadata = thesis.get("metadata") or {}
        if (
            metadata.get("challenge_id") != challenge["id"]
            or metadata.get("prior_thesis_revision_id")
            != challenge["thesis_revision_id"]
        ):
            raise ValueError("challenge targets an older thesis revision")
        impact = metadata.get("thesis_update_impact")
        status = "upheld" if impact == "no_material_change" else "revised"
        analysis_id = thesis["source_analysis_id"]
        self.challenge_repository.resolve_with_response(
            challenge["id"],
            status,
            metadata.get("thesis_update_summary") or "Stored analyst response validated.",
            analysis_id,
        )
        return ThesisChallengeResponseOutcome(
            challenge["id"], status, impact, analysis_id
        )

    @staticmethod
    def _validate_target(challenge: dict, thesis: dict, candidate) -> None:
        if challenge.get("status") != "open":
            raise ValueError("thesis challenge is not open")
        company_id = challenge.get("company_id")
        if thesis.get("company_id") != company_id or candidate.company_id != company_id:
            raise ValueError("challenge, thesis, and candidate company do not match")

    @staticmethod
    def _build_context(thesis, candidate, evidence, current_facts):
        original_ids = set((thesis.get("metadata") or {}).get("evidence_source_ids") or [])
        packet_ids = ThesisChallengeService._source_ids(evidence)
        unexpected = sorted(packet_ids - original_ids)
        if unexpected:
            raise ValueError(
                "challenge response includes non-original evidence: "
                + ", ".join(unexpected)
            )
        candidate_evidence = dict(evidence)
        candidate_evidence.update(
            {
                "prior_source_ids": sorted(original_ids),
                "prior_document_source_ids": sorted(
                    item for item in original_ids if item.startswith(("document:", "news:"))
                ),
                "prior_insider_source_ids": sorted(
                    item for item in original_ids if item.startswith("insider:")
                ),
            }
        )
        response_candidate = replace(candidate, research_evidence=candidate_evidence)
        return ThesisUpdateContext(
            candidate=response_candidate,
            current_thesis=thesis,
            current_facts=current_facts,
            prior_source_ids=tuple(sorted(original_ids)),
            new_source_ids=(),
            deterministic_context_sha256=deterministic_context_sha256(candidate),
            deterministic_context_changed=False,
        )
