from __future__ import annotations
from datetime import date
from statistics import mean
from kncompanyscraper.analysis.realized_total_return import RealizedTotalReturnCalculator

class BasePerformanceEvaluator:
    MAX_PRICE_AGE_DAYS = 7

    def __init__(self, valuation_repository, benchmark_repository, dividend_repository):
        self.valuation_repository = valuation_repository
        self.benchmark_repository = benchmark_repository
        self.dividend_repository = dividend_repository
        self.total_return_calculator = RealizedTotalReturnCalculator(
            valuation_repository,
            dividend_repository,
        )

    def _company_total_return(self, company_id: int, start_date: date, target_date: date) -> dict:
        start = self.valuation_repository.get_stock_price_on_or_after(
            company_id, start_date, max_age_days=self.MAX_PRICE_AGE_DAYS
        )
        observation = self.total_return_calculator.calculate(
            company_id,
            start,
            target_date,
        )
        return {
            "price_return": observation.price_return,
            "total_return": observation.total_return,
            "issue": observation.issue,
        }

    def _benchmark_return(self, benchmark_code: str, start_date: date, target_date: date) -> float | None:
        start = self.benchmark_repository.get_value_on_or_after(
            benchmark_code, start_date, max_age_days=self.MAX_PRICE_AGE_DAYS
        )
        end = self.benchmark_repository.get_value_on_or_before(
            benchmark_code, target_date, max_age_days=self.MAX_PRICE_AGE_DAYS
        )
        if start is None or end is None or start[1] <= 0:
            return None
        return end[1] / start[1] - 1.0

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        from calendar import monthrange
        year = value.year + (value.month + months - 1) // 12
        month = (value.month + months - 1) % 12 + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)
