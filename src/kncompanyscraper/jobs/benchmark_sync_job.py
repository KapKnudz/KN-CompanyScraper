from dataclasses import dataclass
from datetime import date, timedelta

from kncompanyscraper.benchmark_client import NASDAQ_OMXS30GI_SOURCE


@dataclass(frozen=True)
class BenchmarkSyncJobResult:
    synced_count: int
    requested_from: date
    requested_through: date
    stored_from: date
    stored_through: date
    omitted_zero_dates: tuple[date, ...]


class BenchmarkSyncJob:
    SERIES_CODE = "OMXS30GI"
    RETURN_BASIS = "gross_total_return"
    INCEPTION_DATE = date(2006, 5, 23)
    OVERLAP_DAYS = 7

    def __init__(self, client, benchmark_repository):
        self.client = client
        self.benchmark_repository = benchmark_repository

    def run(
        self,
        *,
        as_of: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> BenchmarkSyncJobResult:
        as_of = as_of or date.today()
        requested_through = end_date or as_of - timedelta(days=1)
        latest = self.benchmark_repository.get_latest_date(self.SERIES_CODE)
        requested_from = start_date or (
            latest - timedelta(days=self.OVERLAP_DAYS)
            if latest is not None
            else self.INCEPTION_DATE
        )
        history = self.client.get_omxs30gi(requested_from, requested_through)
        synced_count = self.benchmark_repository.save_values(
            self.SERIES_CODE,
            history.values,
            return_basis=self.RETURN_BASIS,
            source=NASDAQ_OMXS30GI_SOURCE,
        )
        return BenchmarkSyncJobResult(
            synced_count=synced_count,
            requested_from=requested_from,
            requested_through=requested_through,
            stored_from=history.values[0][0],
            stored_through=history.values[-1][0],
            omitted_zero_dates=history.omitted_zero_dates,
        )
