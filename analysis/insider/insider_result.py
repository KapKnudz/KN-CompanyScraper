from dataclasses import dataclass


@dataclass
class InsiderResult:

    net_buying: float

    buy_sell_ratio: float | None

    average_buy_size: float | None
    average_sell_size: float | None

    insider_buying_trend: float | None