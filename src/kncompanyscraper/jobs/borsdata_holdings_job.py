from dataclasses import dataclass
from datetime import date

from kncompanyscraper.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BorsdataHoldingsJobResult:
    synced: int
    failed: int
    buyback_rows: int
    short_snapshots: int
    failures: tuple[str, ...]


class BorsdataHoldingsJob:
    JOB_TYPE = "borsdata_holdings_sync"
    BATCH_SIZE = 50

    def __init__(self, client, repository, job_repository):
        self.client = client
        self.repository = repository
        self.job_repository = job_repository

    def run(self, companies: list, observation_date: date | None = None):
        observation_date = observation_date or date.today()
        synced = buyback_rows = short_snapshots = 0
        failures = []
        job_ids = {}
        eligible = []
        for company in companies:
            job_id = self.job_repository.start(self.JOB_TYPE, company.id)
            if company.id is None or company.borsdata_id is None:
                error = "Company is missing local or Börsdata identifier"
                coverage = {"buybacks": "rejected", "shorts": "rejected"}
                self.job_repository.fail(job_id, error, {"coverage": coverage})
                failures.append(f"{company.name}: {error}")
                continue
            job_ids[company.id] = job_id
            eligible.append(company)

        short_request_error = None
        try:
            shorts = self.client.get_shorts() if eligible else {}
        except Exception as exc:
            shorts = {}
            short_request_error = str(exc)
            logger.exception("Börsdata short-universe request failed")

        for offset in range(0, len(eligible), self.BATCH_SIZE):
            batch = eligible[offset:offset + self.BATCH_SIZE]
            try:
                responses = self.client.get_buybacks(
                    [company.borsdata_id for company in batch]
                )
                batch_error = None
            except Exception as exc:
                responses = {}
                batch_error = str(exc)
                logger.exception("Börsdata buyback batch failed")

            for company in batch:
                job_id = job_ids[company.id]
                response = responses.get(company.borsdata_id)
                short = shorts.get(company.borsdata_id)
                coverage = {
                    "buybacks": "failed" if batch_error else "unknown",
                    "shorts": "failed" if short_request_error else "unknown",
                }
                errors = []

                if batch_error:
                    errors.append(f"buybacks: {batch_error}")
                elif response is None:
                    errors.append("buybacks: response omitted instrument")
                    coverage["buybacks"] = "omitted"
                elif response.error:
                    errors.append(f"buybacks: {response.error}")
                    coverage["buybacks"] = "failed"
                else:
                    try:
                        count = self.repository.save_buybacks(company.id, response.values)
                    except Exception as exc:
                        errors.append(f"buybacks: {exc}")
                        coverage["buybacks"] = "failed"
                        logger.exception(
                            "Börsdata buyback persistence failed for %s", company.name
                        )
                    else:
                        buyback_rows += count
                        coverage["buybacks"] = "available" if response.values else "empty"

                if short_request_error:
                    errors.append(f"shorts: {short_request_error}")
                elif short is None:
                    # Börsdata's local schema does not confirm whether zero-short
                    # instruments are omitted, so absence remains unknown.
                    coverage["shorts"] = "unknown"
                elif short.error:
                    errors.append(f"shorts: {short.error}")
                    coverage["shorts"] = "failed"
                else:
                    try:
                        self.repository.save_short_snapshot(
                            company.id, observation_date, short
                        )
                    except Exception as exc:
                        errors.append(f"shorts: {exc}")
                        coverage["shorts"] = "failed"
                        logger.exception(
                            "Börsdata short persistence failed for %s", company.name
                        )
                    else:
                        short_snapshots += 1
                        coverage["shorts"] = "available"

                result = {
                    "borsdata_id": company.borsdata_id,
                    "coverage": coverage,
                }
                if errors:
                    error = "; ".join(errors)
                    self.job_repository.fail(job_id, error, result)
                    failures.append(f"{company.name}: {error}")
                else:
                    synced += 1
                    self.job_repository.complete(job_id, result)
        return BorsdataHoldingsJobResult(
            synced, len(failures), buyback_rows, short_snapshots, tuple(failures)
        )
