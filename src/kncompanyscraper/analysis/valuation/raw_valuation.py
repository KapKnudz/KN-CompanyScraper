"""Raw valuation metrics derived from latest stock price and report data."""

from dataclasses import dataclass

from kncompanyscraper.borsdata.report import Report
from kncompanyscraper.borsdata.stock_price import StockPrice


@dataclass
class RawValuation:
    market_cap: float | None = None
    enterprise_value: float | None = None
    earnings_yield: float | None = None
    fcf_yield: float | None = None
    sales_yield: float | None = None
    book_yield: float | None = None
    pe: float | None = None
    pfcf: float | None = None
    ps: float | None = None
    pb: float | None = None
    ev_ebit: float | None = None
    ev_ebitda: float | None = None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def compute_raw_valuation(
    stock_price: StockPrice | None,
    report: Report | None,
) -> RawValuation:
    """Compute price-derived valuation metrics from latest close and fundamentals.

    Returns an empty ``RawValuation`` when the price, report, close, or share
    count is missing/zero because market-cap-derived metrics would be invalid.
    """
    if stock_price is None or report is None:
        return RawValuation()

    if stock_price.close in (None, 0) or report.shares_outstanding in (None, 0):
        return RawValuation()

    market_cap = stock_price.close * report.shares_outstanding
    enterprise_value = market_cap + (report.total_debt or 0)

    return RawValuation(
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        earnings_yield=_ratio(report.net_income, market_cap),
        fcf_yield=_ratio(report.free_cash_flow, market_cap),
        sales_yield=_ratio(report.revenue, market_cap),
        book_yield=_ratio(report.equity, market_cap),
        pe=_ratio(market_cap, report.net_income),
        pfcf=_ratio(market_cap, report.free_cash_flow),
        ps=_ratio(market_cap, report.revenue),
        pb=_ratio(market_cap, report.equity),
        ev_ebit=_ratio(enterprise_value, report.ebit),
        ev_ebitda=_ratio(enterprise_value, report.ebitda),
    )
