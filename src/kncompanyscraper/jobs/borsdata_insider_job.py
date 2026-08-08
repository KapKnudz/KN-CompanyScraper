from dataclasses import dataclass

from kncompanyscraper.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BorsdataInsiderJobResult:
    synced: int
    failed: int
    inserted: int
    failures: tuple[str, ...]


class BorsdataInsiderJob:

    JOB_TYPE = "borsdata_insider_sync"
    BATCH_SIZE = 50

    def __init__(self, client, insider_repository, job_repository):
        self.client = client
        self.insider_repository = insider_repository
        self.job_repository = job_repository

    def run(self, companies: list) -> BorsdataInsiderJobResult:
        synced = 0
        inserted = 0
        failures = []

        for offset in range(0, len(companies), self.BATCH_SIZE):
            batch = companies[offset:offset + self.BATCH_SIZE]
            job_ids = {
                company.id: self.job_repository.start(self.JOB_TYPE, company.id)
                for company in batch
            }
            instrument_ids = [company.borsdata_id for company in batch]

            try:
                transactions = self.client.get_insider_transactions(instrument_ids)
            except Exception as exc:
                for company in batch:
                    self.job_repository.fail(job_ids[company.id], str(exc))
                    failures.append(f"{company.name}: {exc}")
                logger.exception("Börsdata insider batch failed")
                continue

            for company in batch:
                try:
                    company_inserted = self.insider_repository.save_all(
                        transactions.get(company.borsdata_id, []),
                        company.id,
                    )
                except Exception as exc:
                    self.job_repository.fail(job_ids[company.id], str(exc))
                    failures.append(f"{company.name}: {exc}")
                    logger.exception("Börsdata insider persistence failed for %s", company.name)
                else:
                    synced += 1
                    inserted += company_inserted
                    self.job_repository.complete(
                        job_ids[company.id],
                        {
                            "borsdata_id": company.borsdata_id,
                            "transactions_inserted": company_inserted,
                        },
                    )

        result = BorsdataInsiderJobResult(synced, len(failures), inserted, tuple(failures))
        logger.info(
            "Börsdata insider sync finished: synced=%d failed=%d inserted=%d",
            result.synced,
            result.failed,
            result.inserted,
        )
        return result
