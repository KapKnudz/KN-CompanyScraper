from analysis.base.skill import Skill
from analysis.base.skillresult import SkillResult
from analysis.valuation.valuation_engine import ValuationAnalysisEngine


class ValuationSkill(Skill):

    def __init__(self, repository):
        self.repository = repository
        self.engine = ValuationAnalysisEngine()

    @property
    def name(self):
        return "valuation"

    def run(self, company) -> SkillResult:

        current = self.repository.get_current(company.borsdata_id)
        historical = self.repository.get_historical(company.borsdata_id)

        valuation = self.engine.analyze(current, historical)

        return self.evaluate(valuation)

    def evaluate(self, valuation) -> SkillResult:
        ...