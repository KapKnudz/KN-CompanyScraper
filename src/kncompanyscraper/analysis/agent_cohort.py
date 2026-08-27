from dataclasses import asdict, dataclass
from datetime import date

AGENT_COHORT_POLICY_VERSION = "agent-cohort-v1"
AGENT_COHORT_TARGET_SIZE = 30
AGENT_COHORT_GRACE_MONTHS = 3


@dataclass(frozen=True)
class AgentCohortMember:
    company_id: int
    status: str
    deterministic_rank: int | None
    consecutive_misses: int
    entered_month: str


@dataclass(frozen=True)
class AgentCohortSnapshot:
    snapshot_month: str
    deterministic_run_id: int
    eligible_universe_company_ids: tuple[int, ...]
    top_company_ids: tuple[int, ...]
    members: tuple[AgentCohortMember, ...]
    policy_version: str = AGENT_COHORT_POLICY_VERSION
    target_size: int = AGENT_COHORT_TARGET_SIZE
    grace_months: int = AGENT_COHORT_GRACE_MONTHS

    def to_dict(self) -> dict:
        return asdict(self)


class AgentCohortService:
    POLICY_VERSION = AGENT_COHORT_POLICY_VERSION
    TARGET_SIZE = AGENT_COHORT_TARGET_SIZE
    GRACE_MONTHS = AGENT_COHORT_GRACE_MONTHS

    def __init__(self, repository):
        self.repository = repository

    def refresh(
        self,
        deterministic_run: dict,
        *,
        as_of: date,
    ) -> tuple[int, AgentCohortSnapshot, bool]:
        month = as_of.replace(day=1)
        existing = self.repository.get_for_month(month)
        if existing is not None:
            return existing["id"], self._from_dict(existing), False

        eligible_scores = [
            score
            for score in deterministic_run.get("scores", [])
            if score.get("rank_eligible")
        ]
        eligible_ids = tuple(score["company_id"] for score in eligible_scores)
        top_ids = eligible_ids[: self.TARGET_SIZE]
        ranks = {
            score["company_id"]: rank
            for rank, score in enumerate(eligible_scores, 1)
        }
        previous = self.repository.get_latest_before(month)
        previous_members = {
            member["company_id"]: member
            for member in (previous or {}).get("members", [])
        }
        members = []
        for company_id in top_ids:
            prior = previous_members.get(company_id)
            members.append(
                AgentCohortMember(
                    company_id=company_id,
                    status="incumbent" if prior else "entrant",
                    deterministic_rank=ranks[company_id],
                    consecutive_misses=0,
                    entered_month=(
                        prior["entered_month"] if prior else month.isoformat()
                    ),
                )
            )
        for prior in (previous or {}).get("members", []):
            company_id = prior["company_id"]
            if company_id in top_ids:
                continue
            misses = prior["consecutive_misses"] + 1
            if misses >= self.GRACE_MONTHS:
                continue
            members.append(
                AgentCohortMember(
                    company_id=company_id,
                    status="grace",
                    deterministic_rank=ranks.get(company_id),
                    consecutive_misses=misses,
                    entered_month=prior["entered_month"],
                )
            )

        snapshot = AgentCohortSnapshot(
            snapshot_month=month.isoformat(),
            deterministic_run_id=deterministic_run["id"],
            eligible_universe_company_ids=eligible_ids,
            top_company_ids=top_ids,
            members=tuple(members),
            policy_version=self.POLICY_VERSION,
            target_size=self.TARGET_SIZE,
            grace_months=self.GRACE_MONTHS,
        )
        snapshot_id, created = self.repository.save(snapshot)
        if not created:
            stored = self.repository.get_for_month(month)
            return snapshot_id, self._from_dict(stored), False
        return snapshot_id, snapshot, True

    @classmethod
    def _from_dict(cls, stored: dict) -> AgentCohortSnapshot:
        return AgentCohortSnapshot(
            snapshot_month=stored["snapshot_month"].isoformat()
            if hasattr(stored["snapshot_month"], "isoformat")
            else stored["snapshot_month"],
            deterministic_run_id=stored["deterministic_run_id"],
            eligible_universe_company_ids=tuple(
                stored["eligible_universe_company_ids"]
            ),
            top_company_ids=tuple(stored["top_company_ids"]),
            members=tuple(AgentCohortMember(**member) for member in stored["members"]),
            policy_version=stored.get("policy_version", cls.POLICY_VERSION),
            target_size=stored.get("target_size", cls.TARGET_SIZE),
            grace_months=stored.get("grace_months", cls.GRACE_MONTHS),
        )
