from analysis.base.skill import Skill
from analysis.valuation.valuation_result import ValuationResult


class ValuationSkill(Skill):

    def evaluate(self, result: ValuationResult):
        raise NotImplementedError()