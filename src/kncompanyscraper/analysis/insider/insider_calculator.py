from typing import Optional

from kncompanyscraper.analysis.insider.current_insider_activity import CurrentInsiderActivity
from kncompanyscraper.analysis.insider.historical_insider_activity import HistoricalInsiderActivity
from kncompanyscraper.analysis.insider.insider_result import InsiderResult


class InsiderCalculator:

    def calculate(
        self,
        current: CurrentInsiderActivity,
        historical: HistoricalInsiderActivity,
    ) -> InsiderResult:
        """Compute InsiderResult from current and historical activity."""
        net_buying = current.buy_value - current.sell_value

        return InsiderResult(
            net_buying=net_buying,
            buy_sell_ratio=self._ratio(current.buy_value, current.sell_value),
            average_buy_size=self._ratio(current.buy_value, current.buy_count),
            average_sell_size=self._ratio(current.sell_value, current.sell_count),
            insider_buying_trend=self._calculate_trend(net_buying, historical),
        )

    def _calculate_trend(
        self,
        net_buying: float,
        historical: HistoricalInsiderActivity,
    ) -> Optional[float]:
        """Compare current net buying to the historical monthly average.

        Returns the percentage deviation from the historical average:
        (current_net - avg_historical_net) / |avg_historical_net|.
        """
        if not historical.monthly_net_buying:
            return None

        avg_net = sum(historical.monthly_net_buying) / len(
            historical.monthly_net_buying
        )

        if avg_net == 0:
            return None

        return (net_buying - avg_net) / abs(avg_net)

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> Optional[float]:
        """Safe division — returns None when denominator is zero."""
        if denominator == 0:
            return None
        return numerator / denominator
