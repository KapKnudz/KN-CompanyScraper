from kncompanyscraper.borsdata.kpi_ids import KpiIds
from kncompanyscraper.borsdata.valuation_snapshot import ValuationSnapshot


class ValuationRepository:

    def __init__(self, client):
        self.client = client

    def get_current(self, instrument_id) -> ValuationSnapshot:
        return ValuationSnapshot(
            market_cap=self._value(instrument_id, KpiIds.MARKET_CAP),
            enterprise_value=self._value(instrument_id, KpiIds.ENTERPRISE_VALUE),
            pe=self._value(instrument_id, KpiIds.PE),
            ev_ebit=self._value(instrument_id, KpiIds.EV_EBIT),
            ev_ebitda=self._value(instrument_id, KpiIds.EV_EBITDA),
            pb=self._value(instrument_id, KpiIds.PB),
            ps=self._value(instrument_id, KpiIds.PS),
            pfcf=self._value(instrument_id, KpiIds.PFCF),
            peg=self._value(instrument_id, KpiIds.PEG),
            dividend_yield=self._value(instrument_id, KpiIds.DIVIDEND_YIELD),
        )

    def get_historical(self, instrument_id) -> tuple[list[float], list[float], list[float]]:
        return (
            self._history(instrument_id, KpiIds.PE),
            self._history(instrument_id, KpiIds.EV_EBIT),
            self._history(instrument_id, KpiIds.PB),
        )

    def _value(self, instrument_id, kpi_id) -> float | None:
        kpi = self.client.get_kpis(instrument_id, kpi_id)
        return kpi.value if kpi else None

    def _history(self, instrument_id, kpi_id) -> list[float]:
        history = self.client.get_kpi_history(instrument_id, kpi_id)
        return [point.value for point in history.values] if history else []