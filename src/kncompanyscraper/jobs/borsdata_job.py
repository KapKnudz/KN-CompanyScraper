from dataclasses import dataclass

from kncompanyscraper.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BorsdataJobResult:
    synced: int
    failed: int
    failures: tuple[str, ...]

    @property
    def attempted(self) -> int:
        return self.synced + self.failed


class BorsdataJob:

    JOB_TYPE = "borsdata_sync"

    def __init__(self, ingestion_service, job_repository):
        self.ingestion_service = ingestion_service
        self.job_repository = job_repository

    def run(self, companies: list) -> BorsdataJobResult:
        synced = 0
        failures = []

        for company in companies:
            job_id = self.job_repository.start(self.JOB_TYPE, company.id)
            try:
                self.ingestion_service.sync_company(company)
            except Exception as exc:
                error = f"{company.name}: {exc}"
                failures.append(error)
                self.job_repository.fail(job_id, str(exc))
                logger.exception("Börsdata sync failed for %s", company.name)
            else:
                synced += 1
                self.job_repository.complete(
                    job_id,
                    {"borsdata_id": company.borsdata_id},
                )

        result = BorsdataJobResult(synced, len(failures), tuple(failures))
        logger.info(
            "Börsdata sync finished: attempted=%d synced=%d failed=%d",
            result.attempted,
            result.synced,
            result.failed,
        )
        return result
