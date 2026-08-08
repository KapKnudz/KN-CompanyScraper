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
