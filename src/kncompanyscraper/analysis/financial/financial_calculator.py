from statistics import pstdev

from kncompanyscraper.analysis.financial.financial_result import FinancialResult, CurrentFinancials, HistoricalFinancials


class FinancialCalculator:

    def calculate(
        self,
        current: CurrentFinancials,
        historical: HistoricalFinancials,
        growth_current: CurrentFinancials | None = None,
        latest_quarter: CurrentFinancials | None = None,
        prior_year_quarter: CurrentFinancials | None = None,
    ) -> FinancialResult:

        growth_current = growth_current or current

        revenue_growth, revenue_years = self._growth(
            growth_current.revenue,
            historical.revenue_history,
        )
        ebit_growth, ebit_years = self._growth(
            growth_current.ebit,
            historical.ebit_history,
        )
        net_income_growth, net_income_years = self._growth(
            growth_current.net_income,
            historical.net_income_history,
        )

        revenue_yoy = self.calculate_yoy_change(growth_current.revenue, historical.revenue_history)
        ebit_yoy = self.calculate_yoy_change(growth_current.ebit, historical.ebit_history)
        net_income_yoy = self.calculate_yoy_change(
            growth_current.net_income,
            historical.net_income_history,
        )
        one_off_risk = self.has_earnings_one_off_risk(
            revenue_yoy,
            ebit_yoy,
            net_income_yoy,
        )

        per_share_history = {
            "revenue": self._per_share_values(
                historical.revenue_history,
                historical.shares_history,
            ),
            "ebit": self._per_share_values(
                historical.ebit_history,
                historical.shares_history,
            ),
            "net_income": self._per_share_values(
                historical.net_income_history,
                historical.shares_history,
            ),
            "fcf": self._per_share_values(
                historical.fcf_history,
                historical.shares_history,
            ),
            "equity": self._per_share_values(
                historical.equity_history,
                historical.shares_history,
            ),
        }
        revenue_per_share_growth, per_share_years = self._growth(
            self.calculate_ratio(
                growth_current.revenue,
                growth_current.shares_outstanding,
            ),
            per_share_history["revenue"],
        )
        ebit_per_share_growth, _ = self._growth(
            self.calculate_ratio(growth_current.ebit, growth_current.shares_outstanding),
            per_share_history["ebit"],
        )
        net_income_per_share_growth, _ = self._growth(
            self.calculate_ratio(
                growth_current.net_income,
                growth_current.shares_outstanding,
            ),
            per_share_history["net_income"],
        )
        fcf_per_share_growth, _ = self._growth(
            self.calculate_ratio(
                growth_current.free_cash_flow,
                growth_current.shares_outstanding,
            ),
            per_share_history["fcf"],
        )
        book_value_per_share_growth, _ = self._growth(
            self.calculate_ratio(growth_current.equity, growth_current.shares_outstanding),
            per_share_history["equity"],
        )
        share_count_growth, _ = self._growth(
            growth_current.shares_outstanding,
            historical.shares_history,
        )

        recent_revenue_growth = None
        if latest_quarter is not None and prior_year_quarter is not None:
            recent_revenue_growth = self.calculate_pair_change(
                latest_quarter.revenue,
                prior_year_quarter.revenue,
            )

        operating_margins = self._margin_history(
            growth_current.operating_profit,
            growth_current.revenue,
            historical.operating_profit_history,
            historical.revenue_history,
        )
        margin_volatility = pstdev(operating_margins) if len(operating_margins) >= 2 else None
        fcf_values = [
            value
            for value in historical.fcf_history + [growth_current.free_cash_flow]
            if value is not None
        ]
        positive_fcf_ratio = (
            sum(value > 0 for value in fcf_values) / len(fcf_values)
            if fcf_values
            else None
        )

        return FinancialResult(
            operating_margin=self.calculate_ratio(current.operating_profit, current.revenue),
            net_margin=self.calculate_ratio(current.net_income, current.revenue),
            fcf_margin=self.calculate_ratio(current.free_cash_flow, current.revenue),
            revenue_growth=revenue_growth,
            ebit_growth=ebit_growth,
            net_income_growth=net_income_growth,
            roe=self.calculate_ratio(current.net_income, current.equity),
            roa=self.calculate_ratio(current.net_income, current.total_assets),
            debt_to_equity=self.calculate_ratio(current.total_debt, current.equity),
            net_debt=current.total_debt,
            equity=current.equity,
            revenue_growth_years=revenue_years,
            ebit_growth_years=ebit_years,
            net_income_growth_years=net_income_years,
            revenue_turnaround=self.is_turnaround(
                growth_current.revenue,
                historical.revenue_history,
            ),
            ebit_turnaround=self.is_turnaround(growth_current.ebit, historical.ebit_history),
            net_income_turnaround=self.is_turnaround(
                growth_current.net_income,
                historical.net_income_history,
            ),
            revenue_deterioration=self.is_deterioration(
                growth_current.revenue,
                historical.revenue_history,
            ),
            ebit_deterioration=self.is_deterioration(
                growth_current.ebit,
                historical.ebit_history,
            ),
            net_income_deterioration=self.is_deterioration(
                growth_current.net_income,
                historical.net_income_history,
            ),
            earnings_growth_one_off_risk=one_off_risk,
            revenue_per_share_growth=revenue_per_share_growth,
            ebit_per_share_growth=ebit_per_share_growth,
            net_income_per_share_growth=net_income_per_share_growth,
            fcf_per_share_growth=fcf_per_share_growth,
            book_value_per_share_growth=book_value_per_share_growth,
            share_count_growth=share_count_growth,
            per_share_growth_years=per_share_years,
            share_dilution=bool(share_count_growth is not None and share_count_growth > 0.05),
            gross_margin=self.calculate_ratio(current.gross_income, current.revenue),
            cash_conversion=(
                self.calculate_ratio(current.operating_cash_flow, current.net_income)
                if current.net_income is not None and current.net_income > 0
                else None
            ),
            fcf_conversion=(
                self.calculate_ratio(current.free_cash_flow, current.net_income)
                if current.net_income is not None and current.net_income > 0
                else None
            ),
            operating_margin_volatility=margin_volatility,
            positive_fcf_ratio=positive_fcf_ratio,
            recent_revenue_growth=recent_revenue_growth,
            recent_growth_acceleration=bool(
                recent_revenue_growth is not None
                and revenue_growth is not None
                and recent_revenue_growth >= revenue_growth + 0.10
            ),
            recent_growth_slowdown=bool(
                recent_revenue_growth is not None
                and revenue_growth is not None
                and recent_revenue_growth <= revenue_growth - 0.10
            ),
        )

    def calculate_growth(self, current_value: float | None, history: list[float | None]) -> float | None:
        return self._growth(current_value, history)[0]

    def _growth(
        self,
        current_value: float | None,
        history: list[float | None],
    ) -> tuple[float | None, int]:
        if current_value is None or current_value <= 0 or not history:
            return None, 1

        previous_value = history[-1]
        if previous_value is None or previous_value <= 0:
            return None, 1

        periods = min(3, len(history))
        baseline = history[-periods]
        if baseline is None or baseline <= 0:
            periods = 1
            baseline = previous_value

        return (current_value / baseline) ** (1 / periods) - 1, periods

    @staticmethod
    def calculate_yoy_change(
        current_value: float | None,
        history: list[float | None],
    ) -> float | None:
        if current_value is None or not history or history[-1] in (None, 0):
            return None
        previous_value = history[-1]
        return (current_value - previous_value) / abs(previous_value)

    @staticmethod
    def calculate_pair_change(
        current_value: float | None,
        previous_value: float | None,
    ) -> float | None:
        if current_value is None or previous_value in (None, 0):
            return None
        return (current_value - previous_value) / abs(previous_value)

    def _per_share_values(
        self,
        values: list[float | None],
        shares: list[float | None],
    ) -> list[float | None]:
        return [
            self.calculate_ratio(value, share_count)
            for value, share_count in zip(values, shares)
        ]

    def _margin_history(
        self,
        current_profit: float | None,
        current_revenue: float | None,
        profit_history: list[float | None],
        revenue_history: list[float | None],
    ) -> list[float]:
        values = [
            self.calculate_ratio(profit, revenue)
            for profit, revenue in zip(profit_history, revenue_history)
        ]
        values.append(self.calculate_ratio(current_profit, current_revenue))
        return [value for value in values[-5:] if value is not None]

    @staticmethod
    def is_turnaround(current_value: float | None, history: list[float | None]) -> bool:
        return bool(
            current_value is not None
            and current_value > 0
            and history
            and history[-1] is not None
            and history[-1] <= 0
        )

    @staticmethod
    def is_deterioration(current_value: float | None, history: list[float | None]) -> bool:
        return bool(
            current_value is not None
            and current_value <= 0
            and history
            and history[-1] is not None
            and history[-1] > 0
        )

    @staticmethod
    def has_earnings_one_off_risk(
        revenue_yoy: float | None,
        ebit_yoy: float | None,
        net_income_yoy: float | None,
    ) -> bool:
        if revenue_yoy is None:
            return False
        threshold = max(0.75, max(revenue_yoy, 0) * 2)
        return any(
            growth is not None and growth > threshold
            for growth in (ebit_yoy, net_income_yoy)
        )

    def calculate_ratio(self, numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None

        return numerator / denominator
