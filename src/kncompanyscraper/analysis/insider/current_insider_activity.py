from dataclasses import dataclass


@dataclass
class CurrentInsiderActivity:

    buy_value: float
    sell_value: float

    buy_count: int
    sell_count: int

    unique_buyers: int
    unique_sellers: int

    largest_buy: float | None
    largest_sell: float | None