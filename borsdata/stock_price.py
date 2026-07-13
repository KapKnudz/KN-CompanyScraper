from dataclasses import dataclass
from datetime import date


@dataclass
class StockPrice:

    date: date
    close: float