"""Company-scoped deterministic analysis before agent context construction."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Iterable

from kncompanyscraper.analysis.agent.readiness import (
    AgentReadinessAssessment,
    AgentReadinessGate,
)
from kncompanyscraper.analysis.ranking.sector_score_rules import ranking_model_for_branch


@dataclass(frozen=True)
class DeterministicCompanySnapshot:
    company_id: int
    ticker: str
    name: str
    results: dict
    readiness: AgentReadinessAssessment


@dataclass(frozen=True)
class DeterministicSnapshotRun:
    snapshots: tuple[DeterministicCompanySnapshot, ...]
    deterministic_duration_seconds: float

    @property
    def results_by_company(self) -> dict[int, dict]:
        return {snapshot.company_id: snapshot.results for snapshot in self.snapshots}

    @property
    def readiness_by_company(self) -> dict[int, AgentReadinessAssessment]:
        return {snapshot.company_id: snapshot.readiness for snapshot in self.snapshots}

    def diagnostics(
        self,
        *,
        refresh_duration_seconds: float | None = None,
        model_duration_seconds: float | None = None,
    ) -> dict[str, float | None]:
        """Return stage timings with deterministic work kept distinct."""
        return {
            "refresh_duration_seconds": refresh_duration_seconds,
            "deterministic_duration_seconds": self.deterministic_duration_seconds,
            "model_duration_seconds": model_duration_seconds,
        }


@dataclass(frozen=True)
class _ReadinessCandidate:
    company_id: int
    ticker: str
    ranking_model: object
    full_results: dict
    research_evidence: dict


class CompanyDeterministicSnapshotService:
    """Build deterministic results for an explicit company list only."""

    def __init__(
        self,
        analysis_engine,
        readiness_gate: AgentReadinessGate | None = None,
        *,
        readiness_evidence_provider: Callable | None = None,
        timer: Callable[[], float] | None = None,
    ):
        self.analysis_engine = analysis_engine
        self.readiness_gate = readiness_gate or AgentReadinessGate()
        self.readiness_evidence_provider = readiness_evidence_provider
        self.timer = timer or perf_counter

    def analyze(self, companies: Iterable) -> DeterministicSnapshotRun:
        companies = list(companies)
        self._validate_companies(companies)

        started = self.timer()
        results_by_company = self.analysis_engine.analyze_companies(companies)
        snapshots = tuple(
            self._snapshot(company, results_by_company[company.id])
            for company in companies
        )
        return DeterministicSnapshotRun(
            snapshots=snapshots,
            deterministic_duration_seconds=self.timer() - started,
        )

    run = analyze
    analyze_companies = analyze

    def _snapshot(self, company, results: dict) -> DeterministicCompanySnapshot:
        evidence = self._readiness_evidence(company)
        readiness_candidate = _ReadinessCandidate(
            company_id=company.id,
            ticker=company.ticker,
            ranking_model=ranking_model_for_branch(company.branch_id),
            full_results=results,
            research_evidence=evidence,
        )
        return DeterministicCompanySnapshot(
            company_id=company.id,
            ticker=company.ticker,
            name=company.name,
            results=results,
            readiness=self.readiness_gate.assess(readiness_candidate),
        )

    def _readiness_evidence(self, company) -> dict:
        if self.readiness_evidence_provider is None:
            return {}
        evidence = self.readiness_evidence_provider(company)
        return evidence.to_dict() if hasattr(evidence, "to_dict") else evidence

    @staticmethod
    def _validate_companies(companies) -> None:
        seen = set()
        for company in companies:
            if company.id is None:
                raise ValueError("Every company must have a local ID")
            if company.id in seen:
                raise ValueError(f"Duplicate company ID: {company.id}")
            seen.add(company.id)
