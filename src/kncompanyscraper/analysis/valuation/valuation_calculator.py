from kncompanyscraper.analysis.valuation.valuation_result import ValuationResult
from kncompanyscraper.analysis.valuation.current_valuation import CurrentValuation
from kncompanyscraper.analysis.valuation.historical_valuation import HistoricalValuation
from kncompanyscraper.analysis.valuation.raw_valuation import RawValuation


class ValuationCalculator:

    def calculate(
            self,
            current: CurrentValuation,
            historical: HistoricalValuation,
            raw: RawValuation | None = None,
    ) -> ValuationResult:

        return ValuationResult(
            pe=current.pe,
            ev_ebit=current.ev_ebit,
            ev_ebitda=current.ev_ebitda,
            pb=current.pb,
            ps=current.ps,
            pfcf=current.pfcf,
            peg=current.peg,
            earnings_yield=self.calculate_earnings_yield(current),
            free_cash_flow_yield=self.calculate_fcf_yield(current),
            pe_vs_5y_avg=self.calculate_pe(current, historical),
            ev_ebit_vs_5y_avg=self.calculate_ev_ebit(current, historical),
            pb_vs_5y_avg=self.calculate_pb(current, historical),
            pe_percentile=self.calculate_pe_percentile(current, historical),
            ev_ebit_percentile=self.calculate_ev_ebit_percentile(current, historical),
            raw_market_cap=raw.market_cap if raw else None,
            raw_enterprise_value=raw.enterprise_value if raw else None,
            raw_earnings_yield=raw.earnings_yield if raw else None,
            raw_fcf_yield=raw.fcf_yield if raw else None,
            raw_pe=raw.pe if raw else None,
            raw_pfcf=raw.pfcf if raw else None,
            raw_ev_ebit=raw.ev_ebit if raw else None,
            raw_ev_ebitda=raw.ev_ebitda if raw else None,
        )

    def calculate_earnings_yield(self, current):
        return self.calculate_ratio(1, current.pe)

    def calculate_fcf_yield(self, current):
        return self.calculate_ratio(1, current.pfcf)

    def calculate_pe(self, current, historical):
        return self.calculate_ratio(current.pe, historical.avg_pe)

    def calculate_ev_ebit(self, current, historical):
        return self.calculate_ratio(current.ev_ebit, historical.avg_ev_ebit)

    def calculate_pb(self, current, historical):
        return self.calculate_ratio(current.pb, historical.avg_pb)

    def calculate_pe_percentile(self, current, historical):
        return self.calculate_percentile(
            current.pe,
            historical.pe_history,
        )

    def calculate_ev_ebit_percentile(self, current, historical):
        return self.calculate_percentile(
            current.ev_ebit,
            historical.ev_ebit_history,
        )

    # Internal helpers
    def calculate_percentile(
        self,
        value: float | None,
        history: list[float],
    ) -> float | None:

        if value is None or not history:
            return None

        values_below = sum(1 for x in history if x <= value)

        return values_below / len(history) * 100

    def calculate_ratio(self, value: float | None, denominator: float | None) -> float | None:
        if value is None or denominator in (None, 0):
            return None

        return value / denominator