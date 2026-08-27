from dataclasses import dataclass
from typing import Callable
from kncompanyscraper.logger import get_logger


@dataclass(frozen=True)
class ScheduledJobFailure:
    status: str
    error: str


def run_tracked(job_repository, job_type: str, callback: Callable, company_id=None):
    """Run a scheduled callback with one consistent job record and failure result."""
    job_id = job_repository.start(job_type, company_id)
    try:
        result = callback()
    except Exception as exc:
        job_repository.fail(job_id, str(exc))
        return ScheduledJobFailure("failed", str(exc))
    job_repository.complete(job_id, getattr(result, "__dict__", None))
    return result


def run_isolated(
    callback: Callable,
    *,
    logger=None,
    job_repository=None,
    job_type: str,
    company_id=None,
):
    """Run a scheduled unit with identical logging and optional persistence."""
    if job_repository is not None:
        return run_tracked(job_repository, job_type, callback, company_id)
    try:
        return callback()
    except Exception as exc:
        (logger or get_logger("scheduled-job")).exception(
            "Scheduled job %s failed; continuing.", job_type
        )
        return ScheduledJobFailure("failed", str(exc))
