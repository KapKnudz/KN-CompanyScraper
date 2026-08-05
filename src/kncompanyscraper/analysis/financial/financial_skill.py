# analysis/financial/financial_skill.py
from kncompanyscraper.analysis.base.skill import Skill
from kncompanyscraper.analysis.financial.financial_mapper import FinancialMapper
from kncompanyscraper.analysis.financial.financial_calculator import FinancialCalculator


class FinancialSkill(Skill):

    def __init__(self, financial_repository):
        self.financial_repository = financial_repository
        self.mapper = FinancialMapper()
        self.calculator = FinancialCalculator()

    @property
    def name(self):
        return "financial"

    def run(self, company):
        latest = self.financial_repository.get_latest_report(company.id)
        if latest is None:
            return None

        historical_reports = self.financial_repository.get_historical_reports(company.id)

        current = self.mapper.to_current(latest)
        historical = self.mapper.to_historical(historical_reports)

        return self.calculator.calculate(current, historical)
