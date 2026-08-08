from kncompanyscraper.analysis.base.skill import Skill


class FundamentalKpiSkill(Skill):
    def __init__(self, valuation_repository):
        self.valuation_repository = valuation_repository

    @property
    def name(self):
        return "fundamental_kpis"

    def run(self, company):
        return self.valuation_repository.get_general_fundamentals(company.id)
