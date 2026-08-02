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