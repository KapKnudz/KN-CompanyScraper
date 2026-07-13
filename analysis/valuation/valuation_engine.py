from analysis.valuation.valuation_result import ValuationResult
from analysis.valuation.current_valuation import CurrentValuation
from analysis.valuation.historical_valuation import HistoricalValuation


class ValuationAnalysisEngine:

    def analyze(
            self,
            current: CurrentValuation,
            historical: HistoricalValuation,
    ) -> ValuationResult:

        return ValuationResult(
            pe=current.pe,
            ev_ebit=current.ev_ebit,
            ev_ebitda=current.ev_ebitda,
            pb=current.pb,
            ps=current.ps,
            pfcf=current.pfcf,
            peg=current.peg,
            earnings_yield=self.analyze_earnings_yield(current),
            free_cash_flow_yield=self.analyze_fcf_yield(current),
            pe_vs_5y_avg=self.analyze_pe(current, historical),
            ev_ebit_vs_5y_avg=self.analyze_ev_ebit(current, historical),
            pb_vs_5y_avg=self.analyze_pb(current, historical),
            pe_percentile=self.analyze_pe_percentile(current, historical),
            ev_ebit_percentile=self.analyze_ev_ebit_percentile(current, historical),
        )

    def analyze_earnings_yield(self, current):
        return self.calculate_ratio(1, current.pe)

    def analyze_fcf_yield(self, current):
        return self.calculate_ratio(1, current.pfcf)

    def analyze_pe(self, current, historical):
        return self.calculate_ratio(current.pe, historical.avg_pe)

    def analyze_ev_ebit(self, current, historical):
        return self.calculate_ratio(current.ev_ebit, historical.avg_ev_ebit)

    def analyze_pb(self, current, historical):
        return self.calculate_ratio(current.pb, historical.avg_pb)

    def analyze_pe_percentile(self, current, historical):
        return self.calculate_percentile(
            current.pe,
            historical.pe_history,
        )

    def analyze_ev_ebit_percentile(self, current, historical):
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