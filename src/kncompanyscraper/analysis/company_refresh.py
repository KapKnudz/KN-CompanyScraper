from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from kncompanyscraper.models.refresh import (
    CompanyRefreshResult,
    RefreshDomainResult,
    RefreshLimitation,
)


class CompanyRefreshService:
    """Refresh one or more explicitly selected companies before analysis."""

    JOB_TYPE = "company_refresh"
    MANDATORY_DOMAINS = ("reports", "prices", "dividends", "kpis", "mfn")
    OPTIONAL_DOMAINS = ("insider", "holdings")

    def __init__(
        self,
        ingestion_service,
        insider_job,
        holdings_job,
        research_document_ingestion,
        job_repository=None,
        *,
        model_invoker: Callable | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.ingestion_service = ingestion_service
        self.insider_job = insider_job
        self.holdings_job = holdings_job
        self.research_document_ingestion = research_document_ingestion
        self.job_repository = job_repository
        self.model_invoker = model_invoker
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def refresh(
        self,
        companies: Iterable,
        *,
        model_invoker: Callable | None = None,
    ) -> tuple[CompanyRefreshResult, ...]:
        companies = list(companies)
        self._validate_companies(companies)
        return tuple(
            self._refresh_company(company, model_invoker=model_invoker)
            for company in companies
        )

    run = refresh

    def _refresh_company(self, company, *, model_invoker):
        job_id = (
            self.job_repository.start(self.JOB_TYPE, company.id)
            if self.job_repository is not None
            else None
        )
        domains = []
        limitations = []

        callbacks = (
            ("reports", True, lambda: self.ingestion_service.refresh_reports([company])),
            (
                "prices",
                True,
                lambda: self.ingestion_service.refresh_prices([company]),
            ),
            (
                "dividends",
                True,
                lambda: self.ingestion_service.refresh_dividends([company]),
            ),
            ("kpis", True, lambda: self.ingestion_service.refresh_kpis([company])),
            (
                "mfn",
                True,
                lambda: self.research_document_ingestion.sync_company_delta(company),
            ),
            (
                "insider",
                False,
                lambda: self.insider_job.run([company]),
            ),
            (
                "holdings",
                False,
                lambda: self.holdings_job.run([company]),
            ),
        )

        for domain, mandatory, callback in callbacks:
            attempted_at = self.clock()
            try:
                value = callback()
                error, counts = _result_failure(value)
            except Exception as exc:
                value = None
                error = str(exc)
                counts = {}
            completed_at = self.clock()

            limitation = None
            if error is not None and not mandatory:
                limitation = RefreshLimitation(domain, error, attempted_at)
                limitations.append(limitation)
            domains.append(
                RefreshDomainResult(
                    domain=domain,
                    mandatory=mandatory,
                    status="failed" if error is not None else "success",
                    attempted_at=attempted_at,
                    completed_at=completed_at,
                    counts=counts,
                    error=error,
                    limitation=limitation,
                )
            )
            self._persist_manifest(job_id, company.id, domains, limitations)

        blocked = any(domain.mandatory and domain.status == "failed" for domain in domains)
        result = CompanyRefreshResult(
            company_id=company.id,
            domains=tuple(domains),
            limitations=tuple(limitations),
            blocked_before_model=blocked,
            job_id=job_id,
        )
        if self.job_repository is not None:
            if blocked:
                failures = "; ".join(
                    f"{domain.domain}: {domain.error}"
                    for domain in domains
                    if domain.mandatory and domain.error
                )
                self.job_repository.fail(job_id, failures, result.to_dict())
            else:
                self.job_repository.complete(job_id, result.to_dict())

        invoker = model_invoker or self.model_invoker
        if not blocked and invoker is not None:
            invoker(company, result)
        return result

    def _persist_manifest(self, job_id, company_id, domains, limitations):
        if self.job_repository is None:
            return
        self.job_repository.update_result(
            job_id,
            {
                "company_id": company_id,
                "domains": [domain.to_dict() for domain in domains],
                "limitations": [limitation.to_dict() for limitation in limitations],
            },
        )

    @staticmethod
    def _validate_companies(companies):
        seen = set()
        for company in companies:
            if company.id is None:
                raise ValueError("Every company must have a local ID")
            if company.id in seen:
                raise ValueError(f"Duplicate company ID: {company.id}")
            seen.add(company.id)


def _result_failure(value) -> tuple[str | None, dict]:
    if value is None:
        return None, {}
    failures = tuple(getattr(value, "failures", ()) or ())
    failed = getattr(value, "failed", 0) or 0
    if failed or failures:
        return "; ".join(str(failure) for failure in failures) or "refresh failed", _counts(value)
    return None, _counts(value)


def _counts(value) -> dict:
    return {
        field: getattr(value, field)
        for field in ("synced", "inserted", "documents_added", "releases_added", "price_rows", "buyback_rows", "short_snapshots")
        if hasattr(value, field)
    }
