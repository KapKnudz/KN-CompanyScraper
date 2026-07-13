from analysis.valuation.current_valuation import CurrentValuation
from analysis.valuation.historical_valuation import HistoricalValuation


class ValuationMapper:

    def to_current(self, valuation) -> CurrentValuation:
        return CurrentValuation(
            market_cap=valuation.market_cap,
            enterprise_value=valuation.enterprise_value,
            pe=valuation.pe,
            ev_ebit=valuation.ev_ebit,
            ev_ebitda=valuation.ev_ebitda,
            pb=valuation.pb,
            ps=valuation.ps,
            pfcf=valuation.pfcf,
            peg=valuation.peg,
            dividend_yield=valuation.dividend_yield,
        )

    def to_historical(
        self,
        pe_history: list[float],
        ev_ebit_history: list[float],
        pb_history: list[float],
    ) -> HistoricalValuation:

        return HistoricalValuation(
            pe_history=pe_history,
            ev_ebit_history=ev_ebit_history,
            pb_history=pb_history,
            avg_pe=sum(pe_history) / len(pe_history),
            avg_ev_ebit=sum(ev_ebit_history) / len(ev_ebit_history),
            avg_pb=sum(pb_history) / len(pb_history),
            median_pe=sorted(pe_history)[len(pe_history) // 2],
            median_ev_ebit=sorted(ev_ebit_history)[len(ev_ebit_history) // 2],
            median_pb=sorted(pb_history)[len(pb_history) // 2],
        )