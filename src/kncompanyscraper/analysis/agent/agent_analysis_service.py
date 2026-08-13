from kncompanyscraper.analysis.agent.prompt_builder import AgentPromptBuilder


class AgentAnalysisService:
    def __init__(
        self,
        model_adapter,
        execution_boundary,
        prompt_builder=None,
        raw_response_repository=None,
    ):
        self.model_adapter = model_adapter
        self.execution_boundary = execution_boundary
        self.prompt_builder = prompt_builder or AgentPromptBuilder()
        self.raw_response_repository = raw_response_repository

    def analyze(self, candidates: list) -> list:
        persisted = []
        for candidate in candidates:
            prompt = self.prompt_builder.build(candidate)
            response = self.model_adapter.generate(prompt)
            metadata = {
                "model_response_id": response.response_id,
                "usage": response.usage,
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
            }
            raw_analysis_id = None
            if self.raw_response_repository is not None:
                raw_analysis_id = self.raw_response_repository.save_stock_analysis_raw(
                    candidate.company_id,
                    response.output_text,
                    created_by=response.model,
                    metadata=metadata,
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
