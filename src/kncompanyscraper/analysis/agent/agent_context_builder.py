from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate


class AgentContextBuilder:

    def __init__(
        self,
        evidence_builder=None,
        cyclicality_repository=None,
        financial_evidence_builder=None,
    ):
        self.evidence_builder = evidence_builder
        self.cyclicality_repository = cyclicality_repository
        self.financial_evidence_builder = financial_evidence_builder

    def build(
        self,
        ranking,
        results_by_company: dict[int, dict],
    ) -> list[AgentCandidate]:
        candidates: list[AgentCandidate] = []

        for rank, cs in enumerate(ranking.scores, 1):
            candidate = self._create_candidate(
                rank, cs, results_by_company.get(cs.company_id, {})
            )
            candidates.append(candidate)

        return candidates

    def build_shortlist(
        self,
        ranking,
        results_by_company: dict[int, dict],
        top_n: int = 25,
        max_total: int = 30,
        limit: int | None = None,
        company_ids: tuple[int, ...] | None = None,
    ) -> list[AgentCandidate]:
        if company_ids is None:
            shortlist = ranking.shortlist_for_agent(top_n=top_n, max_total=max_total)
            shortlist_ids = {cs.company_id for cs in shortlist}
        else:
            shortlist_ids = set(company_ids)

        # Build candidates only for shortlisted companies, preserving shortlist order
        candidates: list[AgentCandidate] = []
        for rank, cs in enumerate(ranking.scores, 1):
            if cs.company_id not in shortlist_ids:
                continue

            candidate = self._create_candidate(
                rank, cs, results_by_company.get(cs.company_id, {})
            )
            candidates.append(candidate)
            if company_ids is None and limit is not None and len(candidates) >= limit:
                break

        if company_ids is not None:
            order = {
                company_id: position for position, company_id in enumerate(company_ids)
            }
            candidates.sort(key=lambda candidate: order[candidate.company_id])
            if limit is not None:
                candidates = candidates[:limit]
        return candidates

    def _create_candidate(self, rank, cs, results) -> AgentCandidate:
        full_results = self._full_results(cs.company_id, results)

        return AgentCandidate(
            rank=rank,
            company_id=cs.company_id,
            ticker=cs.ticker,
            name=cs.name,
            ranking_model=cs.ranking_model,
            rank_eligible=cs.rank_eligible,
            eligibility_reasons=list(cs.eligibility_reasons),
            total_score=cs.total_score,
            score_breakdown={
                "quality": cs.quality_score,
                "growth": cs.growth_score,
                "valuation": cs.valuation_score,
                "balance_sheet": cs.balance_sheet_score,
            },
            data_quality=cs.data_quality,
            flags=list(cs.flags),
            candidate_reason=cs.candidate_reason,
            positives=list(cs.positives),
            negatives=list(cs.negatives),
            missing_data=list(cs.missing_data),
            full_results=full_results,
            research_evidence=self._research_evidence(cs.company_id),
        )

    def _research_evidence(self, company_id: int) -> dict:
        if self.evidence_builder is None:
            return {}
        return self.evidence_builder.build(company_id).to_dict()

    def _full_results(self, company_id: int, results: dict) -> dict:
        enriched = dict(results)
        if self.financial_evidence_builder is not None:
            enriched["financial_history"] = self.financial_evidence_builder.build(
                company_id
            )
        if self.cyclicality_repository is not None:
            consensus = self.cyclicality_repository.get_consensus(company_id)
            if consensus is not None:
                enriched["cyclicality_consensus"] = consensus
        return enriched
