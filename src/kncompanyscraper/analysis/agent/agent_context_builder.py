from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate


class AgentContextBuilder:

    def build(
        self,
        ranking,
        results_by_company: dict[int, dict],
    ) -> list[AgentCandidate]:
        candidates: list[AgentCandidate] = []

        for rank, cs in enumerate(ranking.scores, 1):
            full_results = results_by_company.get(cs.company_id, {})

            candidate = AgentCandidate(
                rank=rank,
                company_id=cs.company_id,
                ticker=cs.ticker,
                name=cs.name,
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
            )
            candidates.append(candidate)

        return candidates

    def build_shortlist(
        self,
        ranking,
        results_by_company: dict[int, dict],
        top_n: int = 25,
        max_total: int = 30,
    ) -> list[AgentCandidate]:
        shortlist = ranking.shortlist_for_agent(top_n=top_n, max_total=max_total)
        shortlist_ids = {cs.company_id for cs in shortlist}

        # Build candidates only for shortlisted companies, preserving shortlist order
        candidates: list[AgentCandidate] = []
        for rank, cs in enumerate(ranking.scores, 1):
            if cs.company_id not in shortlist_ids:
                continue
            full_results = results_by_company.get(cs.company_id, {})

            candidate = AgentCandidate(
                rank=rank,
                company_id=cs.company_id,
                ticker=cs.ticker,
                name=cs.name,
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
            )
            candidates.append(candidate)

        return candidates
