# analysis/valuation/valuation_skill.py
from kncompanyscraper.analysis.base.skill import Skill
from kncompanyscraper.analysis.valuation.valuation_mapper import ValuationMapper
from kncompanyscraper.analysis.valuation.valuation_calculator import ValuationCalculator


class ValuationSkill(Skill):

    def __init__(self, valuation_repository):
        self.valuation_repository = valuation_repository
        self.mapper = ValuationMapper()
        self.calculator = ValuationCalculator()

    @property
    def name(self):
        return "valuation"

    def run(self, company):
        current_raw = self.valuation_repository.get_current(company.id)
        pe_hist, ev_ebit_hist, pb_hist = self.valuation_repository.get_historical(company.id)

        current = self.mapper.to_current(current_raw)
        historical = self.mapper.to_historical(pe_hist, ev_ebit_hist, pb_hist)

        return self.calculator.calculate(current, historical)
