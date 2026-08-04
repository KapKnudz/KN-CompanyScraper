from collections import defaultdict
from typing import List

from kncompanyscraper.analysis.insider.current_insider_activity import CurrentInsiderActivity
from kncompanyscraper.analysis.insider.historical_insider_activity import HistoricalInsiderActivity
from kncompanyscraper.models.insider_transaction import InsiderTransaction


class InsiderMapper:

    def to_current(
        self, transactions: List[InsiderTransaction]
    ) -> CurrentInsiderActivity:
        """Aggregate a list of transactions into current-period insider activity."""
        buys = [t for t in transactions if t.transaction_type == "buy"]
        sells = [t for t in transactions if t.transaction_type == "sell"]

        return CurrentInsiderActivity(
            buy_value=sum(t.total_value or 0 for t in buys),
            sell_value=sum(t.total_value or 0 for t in sells),
            buy_count=len(buys),
            sell_count=len(sells),
            unique_buyers=len({t.person_name for t in buys}),
            unique_sellers=len({t.person_name for t in sells}),
            largest_buy=max(
                (t.total_value for t in buys if t.total_value is not None),
                default=None,
            ),
            largest_sell=max(
                (t.total_value for t in sells if t.total_value is not None),
                default=None,
            ),
        )

    def to_historical(
        self, transactions: List[InsiderTransaction]
    ) -> HistoricalInsiderActivity:
        """Group transactions by calendar month into historical activity series."""
        monthly: dict = defaultdict(lambda: {"buy_value": 0.0, "sell_value": 0.0})

        for t in transactions:
            key = (t.transaction_date.year, t.transaction_date.month)
            value = t.total_value or 0
            if t.transaction_type == "buy":
                monthly[key]["buy_value"] += value
            else:
                monthly[key]["sell_value"] += value

        sorted_months = sorted(monthly.keys())

        return HistoricalInsiderActivity(
            monthly_net_buying=[
                monthly[m]["buy_value"] - monthly[m]["sell_value"]
                for m in sorted_months
            ],
            monthly_buy_value=[monthly[m]["buy_value"] for m in sorted_months],
            monthly_sell_value=[monthly[m]["sell_value"] for m in sorted_months],
        )
