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
            )
            mapped += 1

        return InstrumentMappingResult(mapped=mapped, unresolved=unresolved)
