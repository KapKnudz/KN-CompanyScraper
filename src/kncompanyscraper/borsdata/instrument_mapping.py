from dataclasses import dataclass

from kncompanyscraper.borsdata.instrument import match_instrument


@dataclass(frozen=True)
class InstrumentMappingResult:
    mapped: int
    unresolved: list[str]


class BorsdataInstrumentMappingService:
    def __init__(self, client, company_repository):
        self.client = client
        self.company_repository = company_repository

    def map_companies(self, companies: list) -> InstrumentMappingResult:
        instruments = self.client.get_instruments()
        self.company_repository.upsert_borsdata_markets(self.client.get_markets())
        mapped = 0
        unresolved: list[str] = []

        for company in companies:
            if company.id is None:
                unresolved.append(company.name)
                continue

            instrument = match_instrument(company, instruments)
            if instrument is None:
                unresolved.append(company.name)
                continue

            self.company_repository.set_borsdata_identity(
                company.id,
                instrument.id,
                instrument.stock_price_currency,
                instrument.sector_id,
                instrument.branch_id,
                report_currency=instrument.report_currency,
                market_id=instrument.market_id,
                listing_date=instrument.listing_date,
            )
            mapped += 1

        return InstrumentMappingResult(mapped=mapped, unresolved=unresolved)
