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
        latest_annual = self.financial_repository.get_latest_report(company.id, "year")
        if latest_annual is None:
            return None

        latest_r12 = self.financial_repository.get_latest_report(company.id, "r12")
        current_report = latest_r12 or latest_annual
        historical_reports = self.financial_repository.get_historical_reports(company.id, "year")

        latest_quarter = self.financial_repository.get_latest_report(company.id, "quarter")
        prior_year_quarter = None
        if latest_quarter is not None:
            prior_year_quarter = next(
                (
                    report
                    for report in self.financial_repository.get_historical_reports(
                        company.id,
                        "quarter",
                    )
                    if report.period == latest_quarter.period
                    and report.year == latest_quarter.year - 1
                ),
                None,
            )

        current = self.mapper.to_current(current_report)
        annual_current = self.mapper.to_current(latest_annual)
        historical = self.mapper.to_historical(historical_reports)

        return self.calculator.calculate(
            current,
            historical,
            growth_current=annual_current,
            latest_quarter=self.mapper.to_current(latest_quarter) if latest_quarter else None,
            prior_year_quarter=(
                self.mapper.to_current(prior_year_quarter) if prior_year_quarter else None
            ),
        )
