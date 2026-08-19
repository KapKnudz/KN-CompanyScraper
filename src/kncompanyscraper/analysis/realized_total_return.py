from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from kncompanyscraper.borsdata.stock_price import StockPrice


@dataclass(frozen=True)
class RealizedReturnObservation:
    total_return: float | None
    price_return: float | None
    issue: str | None
    end_date: date | None


class RealizedTotalReturnCalculator:
    MAX_PRICE_AGE_DAYS = 7
    MAX_UNREVIEWED_EVENT_PRICE_RATIO = 1.0
    MAX_UNREVIEWED_REINVESTMENT_MULTIPLIER = 2.0

    def __init__(self, valuation_repository, dividend_repository):
        self.valuation_repository = valuation_repository
        self.dividend_repository = dividend_repository

    def calculate(
        self,
        company_id: int,
        start_price: StockPrice | None,
        target_date: date,
    ) -> RealizedReturnObservation:
        end_price = self.valuation_repository.get_stock_price_on_date(
            company_id,
            target_date,
            max_age_days=self.MAX_PRICE_AGE_DAYS,
        )
        if start_price is None or end_price is None or start_price.close <= 0:
            return RealizedReturnObservation(None, None, "missing_price", None)

        price_return = end_price.close / start_price.close - 1.0
        start_currency = (start_price.currency or "").upper()
        end_currency = (end_price.currency or "").upper()
        if not start_currency or start_currency != end_currency:
            return RealizedReturnObservation(
                None, price_return, "currency_mismatch", end_price.date
            )

        coverage = self.dividend_repository.get_coverage(company_id)
        if (
            coverage is None
            or coverage.covered_from > start_price.date
            or coverage.covered_through < end_price.date
        ):
            return RealizedReturnObservation(
                None, price_return, "incomplete_dividends", end_price.date
            )

        dividends = self.dividend_repository.get_dividends(
            company_id,
            after_date=start_price.date,
            through_date=end_price.date,
        )
        reviews = self.dividend_repository.get_reviews(
            company_id,
            after_date=start_price.date,
            through_date=end_price.date,
            source=coverage.source,
        )
        events_by_date = defaultdict(list)
        for dividend in dividends:
            review = reviews.get(
                self.dividend_repository.review_key(
                    dividend.ex_date,
                    dividend.amount,
                    dividend.currency,
                    dividend.dividend_type,
                )
            )
            if review is not None and review.status == "excluded":
                continue
            if review is not None and review.status == "pending":
                return RealizedReturnObservation(
                    None, price_return, "dividend_review_required", end_price.date
                )
            if dividend.currency.upper() != start_currency:
                return RealizedReturnObservation(
                    None, price_return, "currency_mismatch", end_price.date
                )
            events_by_date[dividend.ex_date].append((dividend, review))

        shares = 1.0
        has_unreviewed_event = False
        for ex_date, events in sorted(events_by_date.items()):
            reinvestment_price = self.valuation_repository.get_stock_price_on_or_after(
                company_id,
                ex_date,
                max_age_days=self.MAX_PRICE_AGE_DAYS,
            )
            if (
                reinvestment_price is None
                or reinvestment_price.date > end_price.date
                or reinvestment_price.close <= 0
                or (reinvestment_price.currency or "").upper() != start_currency
            ):
                return RealizedReturnObservation(
                    None, price_return, "missing_price", end_price.date
                )
            amount = sum(dividend.amount for dividend, _ in events)
            for dividend, review in events:
                if review is None:
                    has_unreviewed_event = True
                    if (
                        dividend.amount / reinvestment_price.close
                        >= self.MAX_UNREVIEWED_EVENT_PRICE_RATIO
                    ):
                        return RealizedReturnObservation(
                            None,
                            price_return,
                            "dividend_review_required",
                            end_price.date,
                        )
            shares *= 1.0 + amount / reinvestment_price.close
            if (
                has_unreviewed_event
                and shares > self.MAX_UNREVIEWED_REINVESTMENT_MULTIPLIER
            ):
                return RealizedReturnObservation(
                    None,
                    price_return,
                    "dividend_review_required",
                    end_price.date,
                )

        return RealizedReturnObservation(
            shares * end_price.close / start_price.close - 1.0,
            price_return,
            None,
            end_price.date,
        )
