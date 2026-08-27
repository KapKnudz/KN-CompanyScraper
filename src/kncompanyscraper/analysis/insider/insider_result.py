from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InsiderResult:

    net_buying: float

    buy_sell_ratio: float | None

    average_buy_size: float | None
    average_sell_size: float | None

    insider_buying_trend: float | None

    # False means no transactions were available; zero net buying then means
    # “no observed activity,” not balanced insider trading.
    data_available: bool = True
