from kncompanyscraper.analysis.base.skill import Skill


class SectorKpiSkill(Skill):
    def __init__(self, valuation_repository):
        self.valuation_repository = valuation_repository

    @property
    def name(self):
        return "sector_kpis"

    def run(self, company):
        return self.valuation_repository.get_sector_current(company.id, company.branch_id)
