from dataclasses import asdict, dataclass, replace
from datetime import date


@dataclass(frozen=True)
class PortfolioHolding:
    rank: int
    company_id: int
    ticker: str
    company_name: str
    analysis_id: int
    target_weight: float | None
    confidence: str
    why_now: str
    reverse_dcf_assessment: str
    risk_profile: str
    evidence_as_of: str
    thesis_breaks: tuple[str, ...]


@dataclass(frozen=True)
class ExcludedFinalist:
    rank: int
    company_id: int
    ticker: str
    company_name: str
    reason_code: str
    detail: str
    reconsideration_trigger: str | None = None


@dataclass(frozen=True)
class PortfolioSelection:
    as_of: str
    target_size: int
    status: str
    missing_slots: int
    selected: tuple[PortfolioHolding, ...]
    excluded_finalists: tuple[ExcludedFinalist, ...]
    portfolio_checks: dict[str, str]

    def to_dict(self) -> dict:
        return asdict(self)


class PortfolioSelectionService:
    MAX_EVIDENCE_AGE_DAYS = 45
    MAX_HIGH_RISK_HOLDINGS = 2
    FINALIST_LIMIT = 30

    def select(
        self,
        ranking,
        analyses_by_company: dict[int, dict],
        *,
        as_of: date,
        target_size: int = 5,
    ) -> PortfolioSelection:
        if target_size < 1:
            raise ValueError("target_size must be at least 1")

        selected = []
        excluded = []
        high_risk_count = 0

        for rank, score in enumerate(ranking.scores[: self.FINALIST_LIMIT], 1):
            if len(selected) >= target_size:
                break
            exclusion = self._exclusion(score, rank, analyses_by_company, as_of)
            if exclusion is not None:
                excluded.append(exclusion)
                continue

            analysis = analyses_by_company[score.company_id]
            content = analysis["content"]
            if (
                content["risk_profile"] == "cyclical_or_other_risk"
                and high_risk_count >= self.MAX_HIGH_RISK_HOLDINGS
            ):
                excluded.append(
                    self._excluded(
                        score,
                        rank,
                        "risk_concentration",
                        "At most two high-risk cyclical holdings are allowed.",
                    )
                )
                continue

            if content["risk_profile"] == "cyclical_or_other_risk":
                high_risk_count += 1
            selected.append(
                PortfolioHolding(
                    rank=rank,
                    company_id=score.company_id,
                    ticker=score.ticker,
                    company_name=score.name,
                    analysis_id=analysis["analysis_id"],
                    target_weight=None,
                    confidence=content["confidence"],
                    why_now=content["one_sentence_thesis"],
                    reverse_dcf_assessment=content[
                        "reverse_dcf_expectation_assessment"
                    ],
                    risk_profile=content["risk_profile"],
                    evidence_as_of=analysis["metadata"]["evidence_as_of"],
                    thesis_breaks=tuple(content["thesis_break_conditions"]),
                )
            )

        status = "ready" if len(selected) == target_size else "not_ready"
        if status == "ready":
            weight = 1.0 / target_size
            selected = [replace(holding, target_weight=weight) for holding in selected]

        return PortfolioSelection(
            as_of=as_of.isoformat(),
            target_size=target_size,
            status=status,
            missing_slots=target_size - len(selected),
            selected=tuple(selected),
            excluded_finalists=tuple(excluded),
            portfolio_checks={
                "validated_analyses": "pass",
                "evidence_freshness": "pass",
                "high_risk_concentration": "pass",
                "equal_weight_allocation": "pass" if status == "ready" else "blocked",
                "liquidity": "not_available",
                "sector_concentration": "not_available",
            },
        )

    def _exclusion(self, score, rank, analyses, as_of):
        if not score.rank_eligible:
            return self._excluded(
                score,
                rank,
                "deterministic_ineligible",
                "; ".join(score.eligibility_reasons) or "Ranking inputs are incomplete.",
            )
        analysis = analyses.get(score.company_id)
        if analysis is None:
            return self._excluded(
                score,
                rank,
                "no_validated_analysis",
                "No accepted stock analysis is available.",
            )
        content = analysis["content"]
        if "portfolio_eligibility" not in content:
            return self._excluded(
                score,
                rank,
                "analysis_contract_outdated",
                "The latest accepted analysis predates portfolio eligibility fields.",
            )
        evidence_as_of = analysis["metadata"].get("evidence_as_of")
        if evidence_as_of is None:
            return self._excluded(
                score,
                rank,
                "evidence_date_missing",
                "The accepted analysis has no evidence cutoff date.",
            )
        age_days = (as_of - date.fromisoformat(evidence_as_of)).days
        if age_days < 0 or age_days > self.MAX_EVIDENCE_AGE_DAYS:
            return self._excluded(
                score,
                rank,
                "stale_analysis",
                f"Evidence is {age_days} days old; maximum is {self.MAX_EVIDENCE_AGE_DAYS}.",
            )
        if content["portfolio_eligibility"] != "investable":
            return self._excluded(
                score,
                rank,
                content["portfolio_reason_code"],
                "The latest accepted analysis is not currently investable.",
                content.get("reconsideration_trigger"),
            )
        if content["verdict"] != "activated_case":
            return self._excluded(
                score,
                rank,
                "contract_mismatch",
                "Investable eligibility requires an activated-case verdict.",
            )
        if content["confidence"] == "low":
            return self._excluded(
                score,
                rank,
                "low_confidence",
                "Low-confidence cases cannot receive a portfolio allocation.",
            )
        if content["risk_profile"] == "unclassified":
            return self._excluded(
                score,
                rank,
                "risk_unclassified",
                "Portfolio allocation requires completed business-risk classification.",
            )
        return None

    @staticmethod
    def _excluded(
        score,
        rank,
        reason_code,
        detail,
        reconsideration_trigger=None,
    ):
        return ExcludedFinalist(
            rank=rank,
            company_id=score.company_id,
            ticker=score.ticker,
            company_name=score.name,
            reason_code=reason_code,
            detail=detail,
            reconsideration_trigger=reconsideration_trigger,
        )
