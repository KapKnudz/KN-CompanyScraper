from dataclasses import dataclass
from datetime import datetime

@dataclass
class Company:
    id: int | None
    name: str
    ticker: str
    mfn_slug: str | None
    borsdata_id: int | None
    last_updated: datetime | None
    isin: str | None = None
    currency: str | None = None
    sector_id: int | None = None
    branch_id: int | None = None
    stock_price_currency: str | None = None
    report_currency: str | None = None

    @property
    def listing_currency(self) -> str | None:
        """Currency used by quoted stock prices; ``currency`` is legacy."""
        return self.stock_price_currency or self.currency

    @property
    def financial_currency(self) -> str | None:
        """Currency used by financial reports, when supplied by the source."""
        return self.report_currency or self.listing_currency
