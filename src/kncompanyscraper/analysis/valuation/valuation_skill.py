# analysis/valuation/valuation_skill.py
from kncompanyscraper.analysis.base.skill import Skill
from kncompanyscraper.analysis.valuation.valuation_mapper import ValuationMapper
from kncompanyscraper.analysis.valuation.valuation_calculator import ValuationCalculator
from kncompanyscraper.analysis.valuation.raw_valuation import compute_raw_valuation


class ValuationSkill(Skill):

    def __init__(self, valuation_repository, financial_repository=None):
        self.valuation_repository = valuation_repository
        self.financial_repository = financial_repository
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

        raw = None
        if self.financial_repository is not None:
            stock_price = self.valuation_repository.get_latest_stock_price(company.id)
            report = self.financial_repository.get_latest_report(company.id)
            raw = compute_raw_valuation(stock_price, report)

        return self.calculator.calculate(current, historical, raw)
