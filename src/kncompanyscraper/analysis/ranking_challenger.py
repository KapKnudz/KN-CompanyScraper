from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class RankingChallengerSnapshot:
    snapshot_month: date
    source_ranking_run_id: int
    source_as_of: date
    policy_version: str
    status: str
    company_count: int
    eligible_count: int
    affected_company_count: int
    scores: list[dict]
    production_top_company_ids: list[int]
    challenger_top_company_ids: list[int]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["snapshot_month"] = self.snapshot_month.isoformat()
        payload["source_as_of"] = self.source_as_of.isoformat()
        return payload


class RankingChallenger:
    """Apply one frozen evaluation policy without changing production scores."""

    POLICY_VERSION = "general-without-ev-ebit-percentile-net-margin-v1"
    STATUS = "evaluation_only"
    REMOVED_COMPONENTS = {
        "quality": frozenset({"net_margin"}),
        "valuation": frozenset({"ev_ebit_percentile"}),
    }

    def build(
        self,
        production_run: dict,
        *,
        snapshot_month: date,
        top_n: int = 30,
    ) -> RankingChallengerSnapshot:
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        scores = production_run.get("scores") or []
        if not scores:
            raise ValueError("source ranking run contains no scores")

        challenger_scores = []
        affected_count = 0
        for production_rank, original in enumerate(scores, 1):
            score = deepcopy(original)
            score["production_rank"] = production_rank
            score["production_total_score"] = original.get("total_score")
            score["challenger_policy_version"] = self.POLICY_VERSION
            score["challenger_affected"] = False
            if original.get("ranking_model", "general") == "general":
                self._rescore_general(score)
                score["challenger_affected"] = True
                affected_count += 1
            score["challenger_total_score"] = score.get("total_score")
            challenger_scores.append(score)

        challenger_scores.sort(
            key=lambda score: (
                not bool(score.get("rank_eligible", True)),
                -float(score.get("challenger_total_score") or 0.0),
                int(score["company_id"]),
            )
        )
        self._assign_tied_ranks(challenger_scores)

        production_eligible = [
            score for score in scores if score.get("rank_eligible", True)
        ]
        challenger_eligible = [
            score for score in challenger_scores if score.get("rank_eligible", True)
        ]
        source_as_of = date.fromisoformat(production_run["run_at"][:10])
        return RankingChallengerSnapshot(
            snapshot_month=snapshot_month,
            source_ranking_run_id=production_run["id"],
            source_as_of=source_as_of,
            policy_version=self.POLICY_VERSION,
            status=self.STATUS,
            company_count=len(challenger_scores),
            eligible_count=len(challenger_eligible),
            affected_company_count=affected_count,
            scores=challenger_scores,
            production_top_company_ids=[
                int(score["company_id"]) for score in production_eligible[:top_n]
            ],
            challenger_top_company_ids=[
                int(score["company_id"]) for score in challenger_eligible[:top_n]
            ],
        )

    def _rescore_general(self, score: dict) -> None:
        audit = score.get("scoring_audit") or {}
        required_categories = {"quality", "growth", "valuation", "balance_sheet"}
        if not required_categories.issubset(audit):
            company_id = score.get("company_id", "unknown")
            raise ValueError(
                f"general company {company_id} lacks a complete scoring audit; "
                "rerun rank-watchlist before snapshotting the challenger"
            )

        category_scores = {}
        for category in ("quality", "growth", "valuation", "balance_sheet"):
            removed = self.REMOVED_COMPONENTS.get(category, frozenset())
            category_scores[category] = self._category_score(audit[category], removed)

        total = sum(
            category_scores[category]
            * float(audit[category]["total_category_weight"])
            for category in category_scores
        )
        score["quality_score"] = round(category_scores["quality"], 1)
        score["growth_score"] = round(category_scores["growth"], 1)
        score["valuation_score"] = round(category_scores["valuation"], 1)
        score["balance_sheet_score"] = round(category_scores["balance_sheet"], 1)
        score["total_score"] = round(total, 1)

    @staticmethod
    def _category_score(category_audit: dict, removed: frozenset[str]) -> float:
        available = [
            component
            for component in category_audit.get("components", [])
            if component.get("available") and component.get("name") not in removed
        ]
        weight = sum(float(component["configured_weight"]) for component in available)
        if weight <= 0:
            raise ValueError("challenger removal leaves a category without evidence")
        return sum(
            float(component["normalized_score"])
            * float(component["configured_weight"])
            for component in available
        ) / weight

    @staticmethod
    def _assign_tied_ranks(scores: list[dict]) -> None:
        last_score = None
        rank = 0
        for position, score in enumerate(scores, 1):
            value = score.get("challenger_total_score")
            if value != last_score:
                rank = position
                last_score = value
            score["challenger_rank"] = rank

