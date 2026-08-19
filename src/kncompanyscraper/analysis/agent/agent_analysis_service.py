from kncompanyscraper.analysis.agent.prompt_builder import AgentPromptBuilder
from kncompanyscraper.analysis.agent.context_provenance import (
    deterministic_context_sha256,
)
from kncompanyscraper.analysis.agent.readiness import AgentReadinessGate


class AgentAnalysisService:
    def __init__(
        self,
        model_adapter,
        execution_boundary,
        prompt_builder=None,
        raw_response_repository=None,
        readiness_gate=None,
    ):
        self.model_adapter = model_adapter
        self.execution_boundary = execution_boundary
        self.prompt_builder = prompt_builder or AgentPromptBuilder()
        self.raw_response_repository = raw_response_repository
        self.readiness_gate = readiness_gate or AgentReadinessGate()

    def analyze(self, candidates: list) -> list:
        self.readiness_gate.require_ready(candidates)
        persisted = []
        for candidate in candidates:
            prompt = self.prompt_builder.build(candidate)
            deterministic_metadata = {
                "policy_name": prompt.policy_name,
                "policy_version": prompt.policy_version,
                "policy_sha256": prompt.policy_sha256,
                "candidate_rank": candidate.rank,
                "evidence_as_of": candidate.research_evidence.get("as_of"),
                "evidence_source_ids": [
                    source["source_id"]
                    for key in ("documents", "insider_transactions")
                    for source in candidate.research_evidence.get(key, [])
                ],
                "deterministic_context_sha256": deterministic_context_sha256(candidate),
            }
            response = self.model_adapter.generate(prompt)
            metadata = {
                "model_response_id": response.response_id,
                "usage": response.usage,
                **deterministic_metadata,
            }
            raw_analysis_id = None
            if self.raw_response_repository is not None:
                raw_analysis_id = self.raw_response_repository.save_stock_analysis_raw(
                    candidate.company_id,
                    response.output_text,
                    created_by=response.model,
                    metadata={"analysis_mode": "initial", **metadata},
                )
                metadata["raw_analysis_id"] = raw_analysis_id
            try:
                accepted = self.execution_boundary.persist_response(
                    response.output_text,
                    candidate,
                    created_by=response.model,
                    metadata=metadata,
                )
            except Exception as exc:
                if raw_analysis_id is not None:
                    self.raw_response_repository.update_raw_validation(
                        raw_analysis_id,
                        "rejected",
                        str(exc),
                    )
                raise
            if raw_analysis_id is not None:
                self.raw_response_repository.update_raw_validation(
                    raw_analysis_id,
                    "accepted",
                )
            persisted.append(accepted)
        return persisted

    def revalidate_rejected(self, candidates: list) -> list:
        if self.raw_response_repository is None:
            raise ValueError("raw response repository is required for revalidation")
        rejected = self.raw_response_repository.get_latest_rejected_initial_analyses(
            [candidate.company_id for candidate in candidates]
        )
        persisted = []
        for candidate in candidates:
            raw = rejected.get(candidate.company_id)
            if raw is None:
                continue
            metadata = dict(raw.get("metadata") or {})
            for key in ("analysis_mode", "validation_status", "validation_error"):
                metadata.pop(key, None)
            metadata["raw_analysis_id"] = raw["id"]
            try:
                accepted = self.execution_boundary.persist_response(
                    raw["content"],
                    candidate,
                    created_by=raw["created_by"],
                    metadata=metadata,
                )
            except Exception as exc:
                self.raw_response_repository.update_raw_validation(
                    raw["id"], "rejected", str(exc)
                )
                raise
            self.raw_response_repository.update_raw_validation(raw["id"], "accepted")
            persisted.append(accepted)
        return persisted
