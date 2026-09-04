from dataclasses import dataclass

from kncompanyscraper.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BorsdataLiquidityBackfillResult:
    requested: int
    synced: int
    failed: int
    price_rows: int
    failures: tuple[str, ...]


class BorsdataLiquidityBackfillJob:
    JOB_TYPE = "borsdata_liquidity_backfill"

    def __init__(self, client, repository, job_repository):
        self.client = client
        self.repository = repository
        self.job_repository = job_repository

    def run(
        self,
        companies: list,
        *,
        max_count: int | None = None,
    ) -> BorsdataLiquidityBackfillResult:
        synced = price_rows = 0
        failures = []
        for company in companies:
            job_id = self.job_repository.start(self.JOB_TYPE, company.id)
            if company.id is None or company.borsdata_id is None:
                error = "Company is missing local or Börsdata identifier"
                self.job_repository.fail(
                    job_id, error, {"coverage": "rejected", "retry_required": True}
                )
                failures.append(f"{company.name}: {error}")
                continue
            try:
                if max_count is None:
                    prices = self.client.get_stock_price(company.borsdata_id)
                else:
                    prices = self.client.get_stock_price(
                        company.borsdata_id, max_count=max_count
                    )
                self.repository.save_stock_prices(
                    company.id, prices, company.listing_currency
                )
            except Exception as exc:
                error = str(exc)
                self.job_repository.fail(
                    job_id,
                    error,
                    {
                        "borsdata_id": company.borsdata_id,
                        "coverage": "failed",
                        "retry_required": True,
                    },
                )
                failures.append(f"{company.name}: {error}")
                logger.exception("Börsdata liquidity backfill failed for %s", company.name)
            else:
                synced += 1
                price_rows += len(prices)
                self.job_repository.complete(
                    job_id,
                    {
                        "borsdata_id": company.borsdata_id,
                        "coverage": "available" if prices else "empty",
                        "price_rows": len(prices),
                        "retry_required": False,
                    },
                )
        return BorsdataLiquidityBackfillResult(
            requested=len(companies),
            synced=synced,
            failed=len(failures),
            price_rows=price_rows,
            failures=tuple(failures),
        )
