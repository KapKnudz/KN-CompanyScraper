from dataclasses import dataclass
from datetime import datetime
from typing import Literal


RefreshStatus = Literal["success", "failed"]


@dataclass(frozen=True)
class RefreshLimitation:
    """A typed limitation retained when an optional refresh domain fails."""

    domain: str
    reason: str
    attempted_at: datetime

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "reason": self.reason,
            "attempted_at": self.attempted_at.isoformat(),
        }


@dataclass(frozen=True)
class RefreshDomainResult:
    domain: str
    mandatory: bool
    status: RefreshStatus
    attempted_at: datetime
    completed_at: datetime
    counts: dict
    error: str | None = None
    limitation: RefreshLimitation | None = None

    def to_dict(self) -> dict:
        result = {
            "domain": self.domain,
            "mandatory": self.mandatory,
            "status": self.status,
            "attempted_at": self.attempted_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "counts": self.counts,
        }
        if self.error is not None:
            result["error"] = self.error
        if self.limitation is not None:
            result["limitation"] = self.limitation.to_dict()
        return result


@dataclass(frozen=True)
class CompanyRefreshResult:
    company_id: int
    domains: tuple[RefreshDomainResult, ...]
    limitations: tuple[RefreshLimitation, ...]
    blocked_before_model: bool
    job_id: int | None = None

    @property
    def mandatory_failures(self) -> tuple[RefreshDomainResult, ...]:
        return tuple(
            domain
            for domain in self.domains
            if domain.mandatory and domain.status == "failed"
        )

    def to_dict(self) -> dict:
        return {
            "company_id": self.company_id,
            "domains": [domain.to_dict() for domain in self.domains],
            "limitations": [limitation.to_dict() for limitation in self.limitations],
            "blocked_before_model": self.blocked_before_model,
            "job_id": self.job_id,
        }
