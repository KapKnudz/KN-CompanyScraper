from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re

from kncompanyscraper.analysis.agent.output_schema import _contract_to_json_schema
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt, AgentPromptBuilder
from kncompanyscraper.analysis.agent.result_parser import _parse_contract
from kncompanyscraper.analysis.comparative_ranking import (
    ComparativeRankingService,
    ComparativeRankingSnapshot,
)
from kncompanyscraper.analysis.valuation.forward_scenario import ForwardRank


COMPARATIVE_REVIEW_CONTRACT = {
    "ranking_run_id": "integer",
    "cases": [
        {
            "company_id": "integer",
            "calibrated_confidence": "low | medium | high",
            "confidence_change": "lowered | unchanged | raised",
            "summary": "string",
            "comparative_evidence_strengths": ["string"],
            "comparative_evidence_limitations": ["string"],
            "source_ids": ["string"],
        }
    ],
    "portfolio_level_observations": ["string"],
}


@dataclass(frozen=True)
class ComparativeConfidenceCase:
    company_id: int
    calibrated_confidence: str
    confidence_change: str
    summary: str
    comparative_evidence_strengths: tuple[str, ...]
    comparative_evidence_limitations: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ComparativeReviewResult:
    ranking_run_id: int
    cases: tuple[ComparativeConfidenceCase, ...]
    portfolio_level_observations: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PersistedComparativeReview:
    review_id: int
    created: bool
    review: ComparativeReviewResult
    final_ranking: object


class ComparativeReviewPromptBuilder:
    POLICY_NAME = "comparative-confidence-review-policy"
    POLICY_VERSION = "1.0.0"

    def build(self, ranking_run: dict, analyses_by_company: dict[int, dict]) -> AgentPrompt:
        policy = AgentPromptBuilder._read_resource("resources/analyst_policy.md")
        system = (
            f"{policy}\n\n"
            "Act as a comparative evidence calibrator across frozen individual theses. "
            "Review evidence quality and confidence consistently across companies. You "
            "may only raise, preserve, or lower confidence. Do not assert a new expected "
            "return, fair value, downside, probability, scenario, or tier. The local "
            "deterministic ranker owns all numeric aggregation and final ordering. Cite "
            "only source IDs listed for that company and return only the required JSON."
        )
        scores = {item["company_id"]: item for item in ranking_run["scores"]}
        cases = []
        ordered_company_ids = [
            item["company_id"]
            for item in ranking_run["scores"]
            if item["company_id"] in analyses_by_company
        ]
        for company_id in ordered_company_ids:
            stored = analyses_by_company[company_id]
            content = stored["content"]
            cases.append(
                {
                    "company_id": company_id,
                    "baseline_rank": scores[company_id],
                    "individual_confidence": content["confidence"],
                    "one_sentence_thesis": content["one_sentence_thesis"],
                    "confidence_limitations": content.get("confidence_limitations", []),
                    "company_fact_ledger": content.get("company_fact_ledger", {}),
                    "confirming_evidence": content.get("confirming_evidence", []),
                    "disconfirming_evidence": content.get("disconfirming_evidence", []),
                    "missing_information": content.get("missing_information", []),
                    "known_source_ids": sorted(_known_source_ids(stored)),
                }
            )
        packet = {
            "ranking_run_id": ranking_run["id"],
            "ranking_as_of": (ranking_run.get("inputs_summary") or {}).get("as_of"),
            "cases": cases,
            "output_contract": COMPARATIVE_REVIEW_CONTRACT,
        }
        return AgentPrompt(
            system=system,
            user=json.dumps(packet, ensure_ascii=False, indent=2, default=str),
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            policy_sha256=sha256(system.encode("utf-8")).hexdigest(),
            output_schema=_contract_to_json_schema(COMPARATIVE_REVIEW_CONTRACT),
            schema_name="comparative_confidence_review",
        )


class ComparativeReviewService:
    def __init__(
        self,
        model_adapter,
        repository,
        challenge_repository,
        prompt_builder=None,
    ):
        self.model_adapter = model_adapter
        self.repository = repository
        self.challenge_repository = challenge_repository
        self.prompt_builder = prompt_builder or ComparativeReviewPromptBuilder()

    def review(
        self,
        ranking_run: dict,
        analyses_by_company: dict[int, dict],
    ) -> PersistedComparativeReview:
        existing = self.repository.get_by_ranking_run(ranking_run["id"])
        if existing is not None and existing["status"] == "accepted":
            return self._accepted(existing, ranking_run, analyses_by_company, False)

        if existing is None:
            prompt = self.prompt_builder.build(ranking_run, analyses_by_company)
            response = self.model_adapter.generate(prompt)
            review_id = self.repository.save_attempt(
                ranking_run_id=ranking_run["id"],
                raw_response=response.output_text,
                created_by=response.model,
                metadata={
                    "model_response_id": response.response_id,
                    "usage": response.usage,
                    "policy_name": prompt.policy_name,
                    "policy_version": prompt.policy_version,
                    "policy_sha256": prompt.policy_sha256,
                    "analysis_ids": (ranking_run.get("inputs_summary") or {}).get(
                        "analysis_ids", {}
                    ),
                },
            )
            stored = {
                "id": review_id,
                "ranking_run_id": ranking_run["id"],
                "raw_response": response.output_text,
                "created_by": response.model,
                "metadata": {},
                "status": "pending",
            }
            created = True
        else:
            stored = existing
            created = False

        try:
            result = self._parse_and_validate(
                stored["raw_response"], ranking_run, analyses_by_company
            )
            final_ranking = self._rerank(result, ranking_run, analyses_by_company)
        except Exception as exc:
            self.repository.reject(stored["id"], str(exc))
            raise
        self.repository.accept(stored["id"], result, final_ranking)
        self.repository.attach_to_ranking_run(
            ranking_run["id"],
            review_id=stored["id"],
            final_actionable_company_ids=[
                item.company_id for item in final_ranking.ranks if item.actionable
            ],
            final_ranked_company_ids=[item.company_id for item in final_ranking.ranks],
        )
        return PersistedComparativeReview(stored["id"], created, result, final_ranking)

    def _accepted(self, stored, ranking_run, analyses_by_company, created):
        result = self._result_from_dict(stored["content"])
        final_ranking = ComparativeRankingSnapshot(
            as_of=(ranking_run.get("inputs_summary") or {})["as_of"],
            policy_version="forward-ranking-v1+comparative-confidence-v1",
            ranks=tuple(
                ForwardRank(
                    **{
                        **item,
                        "economic_tier": item.get("economic_tier", item["tier"]),
                        "base_band": (
                            tuple(item["base_band"])
                            if item.get("base_band") is not None
                            else None
                        ),
                        "flags": tuple(item.get("flags") or []),
                    }
                )
                for item in stored["final_scores"]
            ),
            analysis_ids={
                company_id: stored_analysis["analysis_id"]
                for company_id, stored_analysis in analyses_by_company.items()
            },
        )
        self.repository.attach_to_ranking_run(
            ranking_run["id"],
            review_id=stored["id"],
            final_actionable_company_ids=[
                item.company_id for item in final_ranking.ranks if item.actionable
            ],
            final_ranked_company_ids=[item.company_id for item in final_ranking.ranks],
        )
        return PersistedComparativeReview(stored["id"], created, result, final_ranking)

    def _parse_and_validate(self, raw_response, ranking_run, analyses_by_company):
        payload = _parse_contract(
            raw_response, COMPARATIVE_REVIEW_CONTRACT, "comparative-review"
        )
        result = self._result_from_dict(payload)
        if result.ranking_run_id != ranking_run["id"]:
            raise ValueError("comparative review ranking_run_id does not match")
        expected_ids = set(analyses_by_company)
        actual_ids = [case.company_id for case in result.cases]
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
            raise ValueError("comparative review must contain each frozen company exactly once")
        for case in result.cases:
            if not case.summary.strip():
                raise ValueError("comparative confidence summary cannot be empty")
            original = analyses_by_company[case.company_id]["content"]["confidence"]
            expected_change = _confidence_change(original, case.calibrated_confidence)
            if case.confidence_change != expected_change:
                raise ValueError("confidence_change does not match calibrated confidence")
            if case.confidence_change != "unchanged" and not case.source_ids:
                raise ValueError("changed confidence must cite company evidence")
            unknown = sorted(
                set(case.source_ids) - _known_source_ids(analyses_by_company[case.company_id])
            )
            if unknown:
                raise ValueError(
                    f"company {case.company_id} cites unknown sources: " + ", ".join(unknown)
                )
            self._validate_qualitative_prose(
                [
                    case.summary,
                    *case.comparative_evidence_strengths,
                    *case.comparative_evidence_limitations,
                ]
            )
        self._validate_qualitative_prose(result.portfolio_level_observations)
        return result

    def _rerank(self, result, ranking_run, analyses_by_company):
        inputs = ranking_run.get("inputs_summary") or {}
        proposed = inputs.get("proposed_economic_tiers") or {}
        effective = inputs.get("effective_economic_tiers") or {}
        economic_tier_overrides = {
            int(company_id): tier
            for company_id, tier in effective.items()
            if proposed.get(str(company_id)) != tier
        }
        snapshot = ComparativeRankingService().build(
            analyses_by_company,
            as_of=_ranking_date(ranking_run),
            blocked_company_ids=self.challenge_repository.unresolved_high_company_ids(),
            confidence_overrides={
                case.company_id: case.calibrated_confidence for case in result.cases
            },
            economic_tier_overrides=economic_tier_overrides,
        )
        return ComparativeRankingSnapshot(
            as_of=snapshot.as_of,
            policy_version="forward-ranking-v1+comparative-confidence-v1",
            ranks=snapshot.ranks,
            analysis_ids=snapshot.analysis_ids,
        )

    @staticmethod
    def _result_from_dict(payload):
        return ComparativeReviewResult(
            ranking_run_id=payload["ranking_run_id"],
            cases=tuple(
                ComparativeConfidenceCase(
                    company_id=item["company_id"],
                    calibrated_confidence=item["calibrated_confidence"],
                    confidence_change=item["confidence_change"],
                    summary=item["summary"].strip(),
                    comparative_evidence_strengths=tuple(
                        item["comparative_evidence_strengths"]
                    ),
                    comparative_evidence_limitations=tuple(
                        item["comparative_evidence_limitations"]
                    ),
                    source_ids=tuple(item["source_ids"]),
                )
                for item in payload["cases"]
            ),
            portfolio_level_observations=tuple(payload["portfolio_level_observations"]),
        )

    @staticmethod
    def _validate_qualitative_prose(texts) -> None:
        if any(re.search(r"\d", text) for text in texts):
            raise ValueError(
                "comparative review prose must remain qualitative and contain no numbers"
            )


def _known_source_ids(stored: dict) -> set[str]:
    content = stored["content"]
    source_ids = set((stored.get("metadata") or {}).get("evidence_source_ids") or [])
    source_ids.update(
        citation["source_id"]
        for citation in content.get("citations", [])
        if citation.get("source_id")
    )
    source_ids.update(content.get("risk_profile_evidence") or [])
    source_ids.update(content.get("peak_margin_evidence") or [])
    for assessment in content.get("management_credibility_ledger", []):
        source_ids.update(assessment.get("source_ids") or [])
    for entries in (content.get("company_fact_ledger") or {}).values():
        for fact in entries:
            source_ids.update(fact.get("source_ids") or [])
    for endpoint in content.get("forward_scenario_assumptions", []):
        for assumption in endpoint.values():
            if isinstance(assumption, dict):
                source_ids.update(assumption.get("source_ids") or [])
    return source_ids


def _confidence_change(original: str, calibrated: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    if order[calibrated] < order[original]:
        return "lowered"
    if order[calibrated] > order[original]:
        return "raised"
    return "unchanged"


def _ranking_date(ranking_run):
    from datetime import date

    return date.fromisoformat((ranking_run.get("inputs_summary") or {})["as_of"])
