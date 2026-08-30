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
    BATCH_SIZE = 50

    def __init__(self, ingestion_service, job_repository):
        self.ingestion_service = ingestion_service
        self.job_repository = job_repository

    def run(self, companies: list) -> BorsdataJobResult:
        synced = 0
        failures = []

        jobs = [
            (company, self.job_repository.start(self.JOB_TYPE, company.id))
            for company in companies
        ]

        eligible = []
        for company, job_id in jobs:
            if company.id is None or company.borsdata_id is None:
                error = "Company must have both id and borsdata_id before Börsdata sync"
                failures.append(f"{company.name}: {error}")
                self.job_repository.fail(job_id, error)
            else:
                eligible.append((company, job_id))

        for offset in range(0, len(eligible), self.BATCH_SIZE):
            batch = eligible[offset : offset + self.BATCH_SIZE]
            instrument_ids = [company.borsdata_id for company, _ in batch]
            try:
                bundles = self.ingestion_service.get_report_bundles(instrument_ids)
            except Exception as exc:
                for company, job_id in batch:
                    error = f"{company.name}: {exc}"
                    failures.append(error)
                    self.job_repository.fail(job_id, str(exc))
                logger.exception(
                    "Börsdata report batch failed for instruments %s",
                    instrument_ids,
                )
                continue

            for company, job_id in batch:
                try:
                    bundle = bundles.get(company.borsdata_id)
                    if bundle is None:
                        raise ValueError(
                            "Börsdata report response omitted instrument "
                            f"{company.borsdata_id}"
                        )
                    self.ingestion_service.sync_company(company, report_bundle=bundle)
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
