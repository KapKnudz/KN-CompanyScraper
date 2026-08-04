from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HistoricalInsiderActivity:

    monthly_net_buying: list[float]
    monthly_buy_value: list[float]
    monthly_sell_value: list[float]