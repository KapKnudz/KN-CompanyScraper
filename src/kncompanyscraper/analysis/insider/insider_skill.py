from datetime import date, timedelta

from kncompanyscraper.analysis.base.skill import Skill
from kncompanyscraper.analysis.insider.insider_calculator import InsiderCalculator
from kncompanyscraper.analysis.insider.insider_mapper import InsiderMapper


class InsiderSkill(Skill):

    RECENT_DAYS = 90

    def __init__(self, insider_repository):
        self.insider_repository = insider_repository
        self.mapper = InsiderMapper()
        self.calculator = InsiderCalculator()

    @property
    def name(self):
        return "insider"

    def run(self, company):
        transactions = self.insider_repository.list_for_company(company.id)
        cutoff = date.today() - timedelta(days=self.RECENT_DAYS)
        recent = [transaction for transaction in transactions if transaction.transaction_date >= cutoff]
        historical = [transaction for transaction in transactions if transaction.transaction_date < cutoff]

        return self.calculator.calculate(
            self.mapper.to_current(recent),
            self.mapper.to_historical(historical),
        )
