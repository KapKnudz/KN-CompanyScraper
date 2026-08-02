from kncompanyscraper.analysis.financial.financial_result import FinancialResult, CurrentFinancials, HistoricalFinancials


class FinancialCalculator:

    def calculate(
        self,
        current: CurrentFinancials,
        historical: HistoricalFinancials,
    ) -> FinancialResult:

        return FinancialResult(
            operating_margin=self.calculate_ratio(current.operating_profit, current.revenue),
            net_margin=self.calculate_ratio(current.net_income, current.revenue),
            fcf_margin=self.calculate_ratio(current.free_cash_flow, current.revenue),
            revenue_growth=self.calculate_growth(current.revenue, historical.revenue_history),
            ebit_growth=self.calculate_growth(current.ebit, historical.ebit_history),
            net_income_growth=self.calculate_growth(current.net_income, historical.net_income_history),
            roe=self.calculate_ratio(current.net_income, current.equity),
            roa=self.calculate_ratio(current.net_income, current.total_assets),
            debt_to_equity=self.calculate_ratio(current.total_debt, current.equity),
        )

    def calculate_growth(self, current_value: float | None, history: list[float]) -> float | None:
        if current_value is None or not history:
            return None

        # Assuming history is ordered chronologically, last item is previous period
        previous_value = history[-1]

        if previous_value == 0:
            return None

        return (current_value - previous_value) / abs(previous_value)

    def calculate_ratio(self, numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None

        return numerator / denominator
