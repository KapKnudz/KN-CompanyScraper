from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    id: int
    name: str | None
    isin: str | None
    ticker: str | None
    stock_price_currency: str | None = None
    report_currency: str | None = None


def match_instrument(company, instruments: list[Instrument]) -> Instrument | None:
    if company.isin:
        isin = company.isin.strip().upper()
        matches = [instrument for instrument in instruments if _normalized(instrument.isin) == isin]
        return matches[0] if len(matches) == 1 else None

    ticker = _normalized(company.ticker)
    if not ticker:
        return None

    matches = [instrument for instrument in instruments if _normalized(instrument.ticker) == ticker]
    return matches[0] if len(matches) == 1 else None


def _normalized(value: str | None) -> str | None:
    return value.strip().upper() if value else None
