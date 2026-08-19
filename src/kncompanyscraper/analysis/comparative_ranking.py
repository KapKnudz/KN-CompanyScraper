from dataclasses import asdict, dataclass
from datetime import date

from kncompanyscraper.analysis.valuation.forward_scenario import (
    ForwardRank,
    ForwardScenarioAnalysis,
    ForwardScenarioRanker,
    RankedForwardCase,
    forward_analysis_from_dict,
)


@dataclass(frozen=True)
class ComparativeRankingSnapshot:
    as_of: str
    policy_version: str
    ranks: tuple[ForwardRank, ...]
    analysis_ids: dict[int, int]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TierHysteresisDecision:
    economic_tier_overrides: dict[int, str]
    pending_transitions: dict[str, dict]


class MonthlyTierHysteresisPolicy:
    POLICY_VERSION = "monthly-tier-hysteresis-v1"
    TOLERANCE = 0.02
    _ORDER = {"A": 0, "B": 1, "C": 2}

    def decide(
        self,
        proposed_ranks: tuple[ForwardRank, ...],
        required_returns: dict[int, float | None],
        previous_run: dict | None,
    ) -> TierHysteresisDecision:
        if previous_run is None:
            return TierHysteresisDecision({}, {})
        inputs = previous_run.get("inputs_summary") or {}
        previous_effective = {
            int(company_id): tier
            for company_id, tier in (
                inputs.get("effective_economic_tiers") or {}
            ).items()
        }
        if not previous_effective:
            previous_effective = {
                item["company_id"]: item.get("economic_tier", item["tier"])
                for item in previous_run.get("scores", [])
            }
        prior_pending = inputs.get("pending_tier_transitions") or {}
        overrides = {}
        pending = {}
        for item in proposed_ranks:
            company_id = item.company_id
            proposed = item.economic_tier
            previous = previous_effective.get(company_id)
            if item.tier not in ("A", "B", "C"):
                continue
            if not self._is_near_adjacent_move(
                previous,
                proposed,
                item.base_band,
                required_returns.get(company_id),
            ):
                continue
            prior = prior_pending.get(str(company_id)) or {}
            if prior.get("target_tier") == proposed:
                continue
            overrides[company_id] = previous
            pending[str(company_id)] = {
                "from_tier": previous,
                "target_tier": proposed,
                "observed_count": 1,
            }
        return TierHysteresisDecision(overrides, pending)

    def _is_near_adjacent_move(
        self,
        previous,
        proposed,
        base_band,
        required_return,
    ) -> bool:
        if previous not in self._ORDER or proposed not in self._ORDER:
            return False
        if previous == proposed or abs(self._ORDER[previous] - self._ORDER[proposed]) != 1:
            return False
        if base_band is None or required_return is None:
            return False
        boundary = base_band[0] if {previous, proposed} == {"A", "B"} else base_band[1]
        return abs(boundary - required_return) <= self.TOLERANCE


class ComparativeRankingService:
    """Rank latest accepted individual theses without overriding their inputs."""

    def __init__(self, ranker: ForwardScenarioRanker | None = None):
        self.ranker = ranker or ForwardScenarioRanker()

    def build(
        self,
        analyses_by_company: dict[int, dict],
        *,
        as_of: date,
        blocked_company_ids: set[int] | None = None,
        confidence_overrides: dict[int, str] | None = None,
        economic_tier_overrides: dict[int, str] | None = None,
    ) -> ComparativeRankingSnapshot:
        blocked_company_ids = blocked_company_ids or set()
        confidence_overrides = confidence_overrides or {}
        economic_tier_overrides = economic_tier_overrides or {}
        cases = []
        analysis_ids = {}
        for company_id, stored in analyses_by_company.items():
            content = stored["content"]
            payload = content.get("forward_scenario_analysis")
            if payload is None:
                analysis = self._insufficient("forward scenario analysis is missing")
            else:
                analysis = forward_analysis_from_dict(payload)

            forward_metadata = stored.get("metadata", {}).get("forward_scenario", {})
            required_return = forward_metadata.get("required_return")
            if analysis.status == "available" and required_return is None:
                analysis = self._insufficient("required return is unavailable")

            cases.append(
                RankedForwardCase(
                    company_id=company_id,
                    ticker=content["ticker"],
                    analysis=analysis,
                    required_return=required_return or 0.0,
                    evidence_confidence=confidence_overrides.get(
                        company_id, content["confidence"]
                    ),
                    unresolved_high_severity_challenge=bool(
                        forward_metadata.get("unresolved_high_severity_challenge")
                    )
                    or company_id in blocked_company_ids,
                )
            )
            analysis_ids[company_id] = stored["analysis_id"]

        return ComparativeRankingSnapshot(
            as_of=as_of.isoformat(),
            policy_version=self.ranker.POLICY_VERSION,
            ranks=self.ranker.rank(cases, economic_tier_overrides),
            analysis_ids=analysis_ids,
        )

    @staticmethod
    def _insufficient(reason: str) -> ForwardScenarioAnalysis:
        return ForwardScenarioAnalysis(
            status="insufficient_evidence",
            policy_version="forward-scenario-v2-share-growth",
            methodology_flags=(reason,),
        )
