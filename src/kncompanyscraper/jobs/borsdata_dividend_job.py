from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BorsdataDividendJobResult:
    synced: int
    failed: int
    failures: tuple[str, ...]


class BorsdataDividendJob:
    BATCH_SIZE = 50
    SOURCE = "borsdata:dividend_calendar"

    def __init__(self, client, dividend_repository, valuation_repository):
        self.client = client
        self.dividend_repository = dividend_repository
        self.valuation_repository = valuation_repository

    def run(
        self,
        companies: list,
        *,
        as_of: date | None = None,
    ) -> BorsdataDividendJobResult:
        as_of = as_of or date.today()
        synced = 0
        failures = []
        mapped = [company for company in companies if company.borsdata_id is not None]
        failures.extend(
            f"{company.name}: missing Börsdata instrument ID"
            for company in companies
            if company.borsdata_id is None
        )

        for offset in range(0, len(mapped), self.BATCH_SIZE):
            batch = mapped[offset:offset + self.BATCH_SIZE]
            instrument_ids = [company.borsdata_id for company in batch]
            try:
                calendars = self.client.get_dividends(instrument_ids)
            except Exception as exc:
                failures.extend(f"{company.name}: {exc}" for company in batch)
                continue

            for company in batch:
                if company.borsdata_id not in calendars:
                    failures.append(
                        f"{company.name}: Börsdata omitted instrument {company.borsdata_id}"
                    )
                    continue
                bounds = self.valuation_repository.get_stock_price_bounds(company.id)
                if bounds is None:
                    failures.append(f"{company.name}: no stored stock-price history")
                    continue
                covered_from, _ = bounds
                try:
                    self.dividend_repository.replace_calendar(
                        company.id,
                        calendars[company.borsdata_id],
                        covered_from=covered_from,
                        covered_through=as_of,
                        source=self.SOURCE,
                    )
                except Exception as exc:
                    failures.append(f"{company.name}: {exc}")
                    continue
                synced += 1

        return BorsdataDividendJobResult(synced, len(failures), tuple(failures))
