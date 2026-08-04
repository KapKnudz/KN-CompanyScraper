from __future__ import annotations

from datetime import date

import pytest

from kncompanyscraper.analysis.insider.current_insider_activity import CurrentInsiderActivity
from kncompanyscraper.analysis.insider.historical_insider_activity import HistoricalInsiderActivity
from kncompanyscraper.analysis.insider.insider_calculator import InsiderCalculator
from kncompanyscraper.analysis.insider.insider_mapper import InsiderMapper
from kncompanyscraper.models.insider_transaction import InsiderTransaction


# --- test data factory ---

def make_txn(
    person_name: str = "Andersson, Erik",
    transaction_type: str = "buy",
    total_value: float = 1000.0,
    transaction_date: date = date(2026, 6, 15),
    **overrides,
) -> InsiderTransaction:
    kwargs = dict(
        person_name=person_name,
        person_role="CEO",
        transaction_type=transaction_type,
        shares=100,
        price_per_share=total_value / 100 if total_value is not None else None,
        total_value=total_value,
        transaction_date=transaction_date,
    )
    kwargs.update(overrides)
    return InsiderTransaction(**kwargs)


# --- mapper tests ---

class TestInsiderMapper:

    def test_to_current_empty_returns_zeros(self):
        """Empty transaction list → zero values, None for largest_*."""
        mapper = InsiderMapper()
        result = mapper.to_current([])

        assert result.buy_value == 0.0
        assert result.sell_value == 0.0
        assert result.buy_count == 0
        assert result.sell_count == 0
        assert result.unique_buyers == 0
        assert result.unique_sellers == 0
        assert result.largest_buy is None
        assert result.largest_sell is None

    def test_to_current_buy_only(self):
        """Three buys, zero sells → correct buy aggregates, sell side empty."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "buy", 1000.0, date(2026, 6, 1)),
            make_txn("Bob", "buy", 500.0, date(2026, 6, 2)),
            make_txn("Alice", "buy", 200.0, date(2026, 6, 3)),
        ]

        result = mapper.to_current(txns)

        assert result.buy_value == 1700.0
        assert result.buy_count == 3
        assert result.unique_buyers == 2  # Alice, Bob
        assert result.largest_buy == 1000.0
        assert result.sell_value == 0.0
        assert result.sell_count == 0
        assert result.unique_sellers == 0
        assert result.largest_sell is None

    def test_to_current_sell_only(self):
        """Two sells, zero buys → correct sell aggregates, buy side empty."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "sell", 800.0, date(2026, 6, 1)),
            make_txn("Bob", "sell", 300.0, date(2026, 6, 2)),
        ]

        result = mapper.to_current(txns)

        assert result.sell_value == 1100.0
        assert result.sell_count == 2
        assert result.unique_sellers == 2
        assert result.largest_sell == 800.0
        assert result.buy_value == 0.0
        assert result.buy_count == 0
        assert result.unique_buyers == 0
        assert result.largest_buy is None

    def test_to_current_mixed(self):
        """Two buys, two sells → both sides computed independently."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "buy", 1000.0, date(2026, 6, 1)),
            make_txn("Bob", "buy", 600.0, date(2026, 6, 2)),
            make_txn("Charlie", "sell", 500.0, date(2026, 6, 3)),
            make_txn("Alice", "sell", 300.0, date(2026, 6, 4)),
        ]

        result = mapper.to_current(txns)

        assert result.buy_value == 1600.0
        assert result.buy_count == 2
        assert result.unique_buyers == 2  # Alice, Bob
        assert result.largest_buy == 1000.0
        assert result.sell_value == 800.0
        assert result.sell_count == 2
        assert result.unique_sellers == 2  # Charlie, Alice
        assert result.largest_sell == 500.0

    def test_to_current_same_person_multiple_buys(self):
        """Same person buying twice → unique_buyers counts distinct names."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "buy", 500.0, date(2026, 6, 1)),
            make_txn("Alice", "buy", 300.0, date(2026, 6, 2)),
        ]

        result = mapper.to_current(txns)

        assert result.buy_count == 2
        assert result.unique_buyers == 1

    def test_to_current_total_value_none_treated_as_zero(self):
        """Transactions with None total_value contribute 0 to sums."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "buy", 500.0, date(2026, 6, 1)),
            make_txn("Bob", "buy", transaction_date=date(2026, 6, 2), total_value=None),
        ]

        result = mapper.to_current(txns)

        assert result.buy_value == 500.0
        assert result.largest_buy == 500.0

    def test_to_historical_groups_by_month(self):
        """Transactions across 3 months → 3-entry parallel lists."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "buy", 100.0, date(2026, 1, 10)),
            make_txn("Bob", "sell", 50.0, date(2026, 1, 20)),
            make_txn("Alice", "buy", 200.0, date(2026, 3, 5)),
            make_txn("Charlie", "sell", 75.0, date(2026, 6, 15)),
        ]

        result = mapper.to_historical(txns)

        assert len(result.monthly_net_buying) == 3
        assert len(result.monthly_buy_value) == 3
        assert len(result.monthly_sell_value) == 3

        # Jan: buy=100, sell=50 → net=50
        assert result.monthly_net_buying[0] == 50.0
        assert result.monthly_buy_value[0] == 100.0
        assert result.monthly_sell_value[0] == 50.0

        # Mar: buy=200, sell=0 → net=200
        assert result.monthly_net_buying[1] == 200.0

        # Jun: buy=0, sell=75 → net=-75
        assert result.monthly_net_buying[2] == -75.0

    def test_to_historical_empty(self):
        """Empty transaction list → three empty lists."""
        mapper = InsiderMapper()
        result = mapper.to_historical([])

        assert result.monthly_net_buying == []
        assert result.monthly_buy_value == []
        assert result.monthly_sell_value == []

    def test_to_historical_orders_chronologically(self):
        """Out-of-order dates are sorted chronologically in the output."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "buy", 300.0, date(2026, 6, 1)),
            make_txn("Bob", "buy", 100.0, date(2026, 1, 1)),
        ]

        result = mapper.to_historical(txns)

        # January (100) before June (300)
        assert result.monthly_buy_value == [100.0, 300.0]


# --- calculator tests ---

class TestInsiderCalculator:

    # -- helpers --

    @staticmethod
    def _make_current(
        buy_value: float = 1000.0,
        sell_value: float = 500.0,
        buy_count: int = 2,
        sell_count: int = 1,
    ) -> CurrentInsiderActivity:
        return CurrentInsiderActivity(
            buy_value=buy_value,
            sell_value=sell_value,
            buy_count=buy_count,
            sell_count=sell_count,
            unique_buyers=2,
            unique_sellers=1,
            largest_buy=600.0,
            largest_sell=500.0,
        )

    @staticmethod
    def _make_historical(*monthly_net: float) -> HistoricalInsiderActivity:
        n = len(monthly_net)
        return HistoricalInsiderActivity(
            monthly_net_buying=list(monthly_net),
            monthly_buy_value=[100.0] * n,
            monthly_sell_value=[100.0 - v for v in monthly_net],
        )

    # -- net_buying --

    def test_net_buying_positive(self):
        """More buying than selling → positive net."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=2000.0, sell_value=500.0)
        historical = self._make_historical(100.0, 200.0)

        result = calc.calculate(current, historical)

        assert result.net_buying == 1500.0

    def test_net_buying_negative(self):
        """More selling than buying → negative net."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=300.0, sell_value=1000.0)
        historical = self._make_historical(100.0)

        result = calc.calculate(current, historical)

        assert result.net_buying == -700.0

    def test_net_buying_zero(self):
        """Equal buying and selling → net zero."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=500.0, sell_value=500.0)
        historical = self._make_historical(0.0)

        result = calc.calculate(current, historical)

        assert result.net_buying == 0.0

    # -- buy_sell_ratio --

    def test_buy_sell_ratio(self):
        """buy=1000, sell=500 → ratio=2.0."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=1000.0, sell_value=500.0)
        historical = self._make_historical(100.0)

        result = calc.calculate(current, historical)

        assert result.buy_sell_ratio == 2.0

    def test_buy_sell_ratio_zero_sells(self):
        """No sells → buy_sell_ratio is None."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=1000.0, sell_value=0.0, sell_count=0)
        historical = self._make_historical(100.0)

        result = calc.calculate(current, historical)

        assert result.buy_sell_ratio is None

    # -- average sizes --

    def test_average_buy_size(self):
        """buy_value=1000 / buy_count=4 → 250.0."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=1000.0, buy_count=4)
        historical = self._make_historical(100.0)

        result = calc.calculate(current, historical)

        assert result.average_buy_size == 250.0

    def test_average_sell_size_no_sells(self):
        """No sells → average_sell_size is None."""
        calc = InsiderCalculator()
        current = self._make_current(sell_value=0.0, sell_count=0)
        historical = self._make_historical(100.0)

        result = calc.calculate(current, historical)

        assert result.average_sell_size is None

    def test_average_buy_size_no_buys(self):
        """No buys → average_buy_size is None."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=0.0, buy_count=0)
        historical = self._make_historical(100.0)

        result = calc.calculate(current, historical)

        assert result.average_buy_size is None

    # -- trend --

    def test_trend_above_average(self):
        """Current net (300) > historical avg (200) → positive trend."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=500.0, sell_value=200.0)
        historical = self._make_historical(150.0, 250.0)  # avg = 200

        result = calc.calculate(current, historical)

        # net_buying = 300, avg = 200 → (300-200)/200 = 0.5
        assert result.insider_buying_trend == pytest.approx(0.5)

    def test_trend_below_average(self):
        """Current net (50) < historical avg (200) → negative trend."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=200.0, sell_value=150.0)
        historical = self._make_historical(150.0, 250.0)  # avg = 200

        result = calc.calculate(current, historical)

        # net_buying = 50, avg = 200 → (50-200)/200 = -0.75
        assert result.insider_buying_trend == pytest.approx(-0.75)

    def test_trend_no_history(self):
        """Empty historical data → trend is None."""
        calc = InsiderCalculator()
        current = self._make_current()
        historical = HistoricalInsiderActivity(
            monthly_net_buying=[],
            monthly_buy_value=[],
            monthly_sell_value=[],
        )

        result = calc.calculate(current, historical)

        assert result.insider_buying_trend is None

    def test_trend_avg_zero(self):
        """Historical average net is 0 → trend is None (no meaningful baseline)."""
        calc = InsiderCalculator()
        current = self._make_current(buy_value=500.0, sell_value=200.0)
        historical = self._make_historical(0.0, 0.0)  # avg = 0

        result = calc.calculate(current, historical)

        assert result.insider_buying_trend is None

    # -- all-fields smoke test --

    def test_all_fields_computed(self):
        """A non-trivial mixed scenario computes every field."""
        calc = InsiderCalculator()
        current = self._make_current(
            buy_value=1200.0, sell_value=400.0, buy_count=3, sell_count=2
        )
        historical = self._make_historical(100.0, 200.0, 300.0)  # avg = 200

        result = calc.calculate(current, historical)

        assert result.net_buying == 800.0
        assert result.buy_sell_ratio == 3.0
        assert result.average_buy_size == 400.0
        assert result.average_sell_size == 200.0
        assert result.insider_buying_trend == pytest.approx(3.0)  # (800-200)/200 = 3.0


# --- integration test ---

class TestInsiderAnalysisIntegration:

    def test_full_pipeline_mixed(self):
        """Transactions flow through mapper → calculator → InsiderResult."""
        txns = [
            make_txn("Alice", "buy", 1000.0, date(2026, 6, 1)),
            make_txn("Bob", "buy", 600.0, date(2026, 6, 2)),
            make_txn("Charlie", "sell", 500.0, date(2026, 6, 3)),
            make_txn("Alice", "sell", 300.0, date(2026, 6, 4)),
            # historical: one transaction in Jan for context
            make_txn("Alice", "buy", 200.0, date(2026, 1, 15)),
        ]

        mapper = InsiderMapper()
        current = mapper.to_current(txns)
        historical = mapper.to_historical(txns)

        # Verify mapper output
        assert current.buy_value == 1800.0  # 1000 + 600 + 200
        assert current.sell_value == 800.0  # 500 + 300
        assert current.buy_count == 3
        assert current.sell_count == 2

        # Jan: buy=200 → net=200; Jun: buy=1600, sell=800 → net=800
        assert len(historical.monthly_net_buying) == 2
        assert historical.monthly_net_buying == [200.0, 800.0]

        calculator = InsiderCalculator()
        result = calculator.calculate(current, historical)

        # net = 1800 - 800 = 1000; avg_historical = (200+800)/2 = 500
        assert result.net_buying == 1000.0
        assert result.buy_sell_ratio == 2.25  # 1800/800
        assert result.average_buy_size == 600.0  # 1800/3
        assert result.average_sell_size == 400.0  # 800/2
        assert result.insider_buying_trend == pytest.approx(1.0)  # (1000-500)/500 = 1.0

    def test_full_pipeline_empty(self):
        """Empty transaction list → zeros and Nones throughout."""
        mapper = InsiderMapper()
        current = mapper.to_current([])
        historical = mapper.to_historical([])

        calculator = InsiderCalculator()
        result = calculator.calculate(current, historical)

        assert result.net_buying == 0.0
        assert result.buy_sell_ratio is None
        assert result.average_buy_size is None
        assert result.average_sell_size is None
        assert result.insider_buying_trend is None

    def test_full_pipeline_buy_only(self):
        """Only buy transactions → no sell activity, trend still computable."""
        txns = [
            make_txn("Alice", "buy", 500.0, date(2026, 3, 10)),
            make_txn("Bob", "buy", 300.0, date(2026, 3, 12)),
            make_txn("Alice", "buy", 200.0, date(2026, 2, 5)),
        ]

        mapper = InsiderMapper()
        current = mapper.to_current(txns)
        historical = mapper.to_historical(txns)

        assert current.buy_value == 1000.0
        assert current.sell_value == 0.0
        assert current.buy_count == 3
        assert current.sell_count == 0

        calculator = InsiderCalculator()
        result = calculator.calculate(current, historical)

        assert result.net_buying == 1000.0
        assert result.buy_sell_ratio is None  # zero sells
        assert result.average_buy_size == pytest.approx(1000.0 / 3)
        assert result.average_sell_size is None
        # avg_historical = (200 + 800) / 2 = 500; trend = (1000-500)/500 = 1.0
        assert result.insider_buying_trend == pytest.approx(1.0)

    def test_full_pipeline_sell_only(self):
        """Only sell transactions → negative net, no buy activity."""
        txns = [
            make_txn("Alice", "sell", 700.0, date(2026, 5, 10)),
            make_txn("Bob", "sell", 300.0, date(2026, 5, 12)),
        ]

        mapper = InsiderMapper()
        current = mapper.to_current(txns)
        historical = mapper.to_historical(txns)

        assert current.sell_value == 1000.0
        assert current.buy_value == 0.0
        assert current.sell_count == 2
        assert current.buy_count == 0

        calculator = InsiderCalculator()
        result = calculator.calculate(current, historical)

        assert result.net_buying == -1000.0
        assert result.buy_sell_ratio == 0.0  # 0/1000
        assert result.average_buy_size is None
        assert result.average_sell_size == 500.0
        # Only one historical month: May net = -1000, avg = -1000, trend = 0
        assert result.insider_buying_trend == pytest.approx(0.0)


# --- mapper edge cases ---


class TestInsiderMapperEdgeCases:

    def test_unknown_transaction_type_is_ignored(self):
        """Non-"buy"/"sell" transaction_type (e.g. "grant") excluded from both sides."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "grant", 500.0, date(2026, 6, 1)),
            make_txn("Bob", "buy", 200.0, date(2026, 6, 2)),
        ]

        result = mapper.to_current(txns)

        # "grant" ignored entirely
        assert result.buy_value == 200.0
        assert result.buy_count == 1
        assert result.sell_value == 0.0
        assert result.sell_count == 0

    def test_largest_buy_all_none_values(self):
        """When every buy has total_value=None, largest_buy is None."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "buy", transaction_date=date(2026, 6, 1), total_value=None),
            make_txn("Bob", "buy", transaction_date=date(2026, 6, 2), total_value=None),
        ]

        result = mapper.to_current(txns)

        assert result.largest_buy is None
        # sums still treat None as 0
        assert result.buy_value == 0.0

    def test_largest_sell_all_none_values(self):
        """When every sell has total_value=None, largest_sell is None."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "sell", transaction_date=date(2026, 6, 1), total_value=None),
        ]

        result = mapper.to_current(txns)

        assert result.largest_sell is None

    def test_historical_same_month_buy_and_sell(self):
        """Buy and sell in the same month → netted together in one entry."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "buy", 400.0, date(2026, 4, 5)),
            make_txn("Bob", "sell", 100.0, date(2026, 4, 20)),
        ]

        result = mapper.to_historical(txns)

        assert len(result.monthly_net_buying) == 1
        assert result.monthly_net_buying[0] == 300.0
        assert result.monthly_buy_value[0] == 400.0
        assert result.monthly_sell_value[0] == 100.0

    def test_historical_sell_only_month(self):
        """A month with only sells → negative net, zero buy_value."""
        mapper = InsiderMapper()
        txns = [
            make_txn("Alice", "sell", 200.0, date(2026, 7, 10)),
        ]

        result = mapper.to_historical(txns)

        assert result.monthly_net_buying == [-200.0]
        assert result.monthly_buy_value == [0.0]
        assert result.monthly_sell_value == [200.0]


# --- calculator edge cases ---


class TestInsiderCalculatorEdgeCases:

    def test_trend_negative_historical_average(self):
        """Historical avg is negative (net selling) → trend still computable."""
        calc = InsiderCalculator()
        current = CurrentInsiderActivity(
            buy_value=100.0, sell_value=600.0,
            buy_count=1, sell_count=2,
            unique_buyers=1, unique_sellers=2,
            largest_buy=100.0, largest_sell=400.0,
        )
        # avg historical net = (-500 + -300) / 2 = -400
        historical = HistoricalInsiderActivity(
            monthly_net_buying=[-500.0, -300.0],
            monthly_buy_value=[0.0, 0.0],
            monthly_sell_value=[500.0, 300.0],
        )

        result = calc.calculate(current, historical)

        # net_buying = 100 - 600 = -500
        # trend = (-500 - (-400)) / |-400| = -100/400 = -0.25
        assert result.net_buying == -500.0
        assert result.insider_buying_trend == pytest.approx(-0.25)

    def test_trend_net_buying_matches_average(self):
        """Current net equals historical avg → trend is 0."""
        calc = InsiderCalculator()
        current = CurrentInsiderActivity(
            buy_value=300.0, sell_value=100.0,
            buy_count=1, sell_count=1,
            unique_buyers=1, unique_sellers=1,
            largest_buy=300.0, largest_sell=100.0,
        )
        historical = HistoricalInsiderActivity(
            monthly_net_buying=[200.0],
            monthly_buy_value=[300.0],
            monthly_sell_value=[100.0],
        )

        result = calc.calculate(current, historical)

        assert result.insider_buying_trend == pytest.approx(0.0)
