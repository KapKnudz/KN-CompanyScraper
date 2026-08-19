from dataclasses import dataclass
from datetime import date

from kncompanyscraper.analysis.comparative_ranking import (
    ComparativeRankingService,
    MonthlyTierHysteresisPolicy,
)
from kncompanyscraper.analysis.agent_cohort import AgentCohortService


@dataclass(frozen=True)
class ComparativeRankingJobResult:
    status: str
    run_id: int | None
    company_count: int
    actionable_count: int


class ComparativeRankingJob:
    def __init__(
        self,
        analysis_repository,
        challenge_repository,
        ranking_repository,
        cohort_repository=None,
    ):
        self.analysis_repository = analysis_repository
        self.challenge_repository = challenge_repository
        self.ranking_repository = ranking_repository
        self.cohort_repository = cohort_repository

    def run(self, *, as_of: date | None = None) -> ComparativeRankingJobResult:
        as_of = as_of or date.today()
        analyses = self.analysis_repository.get_latest_validated_stock_analyses()
        if not analyses:
            return ComparativeRankingJobResult("no_analyses", None, 0, 0)

        blocked_company_ids = self.challenge_repository.unresolved_high_company_ids()
        service = ComparativeRankingService()
        proposed_snapshot = service.build(
            analyses,
            as_of=as_of,
            blocked_company_ids=blocked_company_ids,
        )
        month = as_of.replace(day=1)
        previous_run = self.ranking_repository.get_latest_monthly_run_before(month)
        required_returns = {
            company_id: stored.get("metadata", {})
            .get("forward_scenario", {})
            .get("required_return")
            for company_id, stored in analyses.items()
        }
        hysteresis_policy = MonthlyTierHysteresisPolicy()
        hysteresis = hysteresis_policy.decide(
            proposed_snapshot.ranks,
            required_returns,
            previous_run,
        )
        snapshot = service.build(
            analyses,
            as_of=as_of,
            blocked_company_ids=blocked_company_ids,
            economic_tier_overrides=hysteresis.economic_tier_overrides,
        )
        payload = snapshot.to_dict()
        proposed_economic_tiers = {
            str(item.company_id): item.economic_tier
            for item in proposed_snapshot.ranks
        }
        effective_economic_tiers = {
            str(item.company_id): item.economic_tier for item in snapshot.ranks
        }
        deterministic_run = self.ranking_repository.get_latest_deterministic_run(as_of)
        deterministic_shortlist = []
        if deterministic_run is not None:
            deterministic_shortlist = [
                score["company_id"]
                for score in deterministic_run["scores"]
                if score.get("rank_eligible")
            ][:30]
        cohort_id = None
        cohort_member_ids = []
        cohort_universe_ids = []
        if deterministic_run is not None and self.cohort_repository is not None:
            cohort_id, cohort, _ = AgentCohortService(
                self.cohort_repository
            ).refresh(deterministic_run, as_of=as_of)
            cohort_member_ids = [member.company_id for member in cohort.members]
            cohort_universe_ids = list(cohort.eligible_universe_company_ids)
        run_id, created = self.ranking_repository.save_monthly_ranking_run(
            snapshot_month=month,
            model_version=(
                f"{snapshot.policy_version}+{hysteresis_policy.POLICY_VERSION}"
            ),
            company_count=len(snapshot.ranks),
            eligible_count=sum(item.actionable for item in snapshot.ranks),
            scores=payload["ranks"],
            inputs_summary={
                "ranking_type": "combined_forward_scenario",
                "as_of": snapshot.as_of,
                "analysis_ids": snapshot.analysis_ids,
                "final_actionable_company_ids": [
                    item.company_id for item in snapshot.ranks if item.actionable
                ],
                "final_ranked_company_ids": [
                    item.company_id for item in snapshot.ranks
                ],
                "deterministic_run_id": (
                    deterministic_run["id"] if deterministic_run is not None else None
                ),
                "deterministic_shortlist_company_ids": deterministic_shortlist,
                "agent_cohort_snapshot_id": cohort_id,
                "agent_cohort_company_ids": cohort_member_ids,
                "recall_universe_company_ids": cohort_universe_ids,
                "tier_hysteresis_policy_version": hysteresis_policy.POLICY_VERSION,
                "proposed_economic_tiers": proposed_economic_tiers,
                "effective_economic_tiers": effective_economic_tiers,
                "pending_tier_transitions": hysteresis.pending_transitions,
            },
        )
        self.ranking_repository.attach_tier_hysteresis_provenance(
            run_id,
            proposed_economic_tiers=proposed_economic_tiers,
            effective_economic_tiers=effective_economic_tiers,
            pending_transitions=hysteresis.pending_transitions,
            policy_version=hysteresis_policy.POLICY_VERSION,
        )
        if cohort_id is not None:
            self.ranking_repository.attach_cohort_provenance(
                run_id,
                cohort_snapshot_id=cohort_id,
                cohort_company_ids=cohort_member_ids,
                recall_universe_company_ids=cohort_universe_ids,
            )
        return ComparativeRankingJobResult(
            "created" if created else "already_exists",
            run_id,
            len(snapshot.ranks),
            sum(item.actionable for item in snapshot.ranks),
        )
