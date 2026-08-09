from kncompanyscraper.analysis.base.skill import Skill
from kncompanyscraper.borsdata.kpi_ids import KpiIds

_PROPERTY_GROWTH_KPIS = (KpiIds.PROPERTY_NOI_PER_SHARE, KpiIds.PROPERTY_INCOME_PER_SHARE)


class SectorKpiSkill(Skill):
    def __init__(self, valuation_repository):
        self.valuation_repository = valuation_repository

    @property
    def name(self):
        return "sector_kpis"

    def run(self, company):
        current = self.valuation_repository.get_sector_current(company.id, company.branch_id)
        histories = {}
        if company.branch_id == 75:
            histories = self.valuation_repository.get_snapshot_history(
                company.id,
                _PROPERTY_GROWTH_KPIS,
            )
        return {"current": current, "histories": histories}
