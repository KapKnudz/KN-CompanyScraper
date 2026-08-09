"""Analysis skill wiring stored evidence through policy into reverse DCF."""

from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

from kncompanyscraper.analysis.base.skill import Skill
from kncompanyscraper.analysis.valuation.dcf_assumption_policy import (
    DcfAssumptionPolicy,
)
from kncompanyscraper.analysis.valuation.reverse_dcf import (
    DcfAssumptions,
    DcfValue,
    ImpliedAssumption,
    ReverseDcfEngine,
    ReverseDcfInputs,
)


ExpectationStatus = Literal["solved", "outside_bounds"]
AnalysisStatus = Literal["available", "unavailable", "unsupported_model"]


@dataclass(frozen=True)
class ImpliedExpectation:
    assumption: ImpliedAssumption
    status: ExpectationStatus
    lower_bound: float
    upper_bound: float
    implied_value: float | None = None
    modeled_price: float | None = None
    price_difference: float | None = None
    iterations: int | None = None
    modeled_price_range: tuple[float, float] | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ReverseDcfAnalysis:
    status: AnalysisStatus
    policy_version: str
    model: str
    required_model: str | None = None
    analysis_date: str | None = None
    price_date: str | None = None
    current_price: float | None = None
    assumptions: DcfAssumptions | None = None
    assumption_sources: dict[str, str] | None = None
    baseline_valuation: DcfValue | None = None
    implied_expectations: dict[str, ImpliedExpectation] | None = None
    missing_information: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class ReverseDcfSkill(Skill):
    MAX_PRICE_AGE_DAYS = 7
    _LIMITATIONS = (
        "reported FCF calibrates aggregate net reinvestment because D&A, capex, "
        "and working-capital changes are not stored separately",
        "Report.total_debt contains the Börsdata net_Debt field",
        "the v1 model holds growth, margin, and net reinvestment constant during projection",
    )

    def __init__(
        self,
        valuation_repository,
        financial_repository,
        *,
        policy: DcfAssumptionPolicy | None = None,
        engine: ReverseDcfEngine | None = None,
        as_of: date | None = None,
    ):
        self.valuation_repository = valuation_repository
        self.financial_repository = financial_repository
        self.policy = policy or DcfAssumptionPolicy()
        self.engine = engine or ReverseDcfEngine()
        self.as_of = as_of or date.today()

    @property
    def name(self):
        return "reverse_dcf"

    def run(self, company) -> ReverseDcfAnalysis:
        if company.branch_id in (68, 69, 70):
            return self._unsupported("residual_income_or_dividend")
        if company.branch_id == 75:
            return self._unsupported("nav_or_ffo")

        latest_annual = self.financial_repository.get_latest_report(company.id, "year")
        latest_r12 = self.financial_repository.get_latest_report(company.id, "r12")
        price = self.valuation_repository.get_latest_stock_price(company.id)
        history = (
            self.financial_repository.get_historical_reports(company.id, "year")
            if latest_annual is not None
            else []
        )
        return self.analyze_reports(
            company,
            latest_annual=latest_annual,
            latest_r12=latest_r12,
            history=history,
            price=price,
            as_of=self.as_of,
        )

    def analyze_reports(
        self,
        company,
        *,
        latest_annual,
        latest_r12,
        history,
        price,
        as_of: date,
    ) -> ReverseDcfAnalysis:
        """Analyze supplied point-in-time evidence for live or historical ranking."""
        if company.branch_id in (68, 69, 70):
            return self._unsupported("residual_income_or_dividend", as_of)
        if company.branch_id == 75:
            return self._unsupported("nav_or_ffo", as_of)

        current_report = latest_r12 or latest_annual
        missing: list[str] = []
        if latest_annual is None:
            missing.append("latest annual report unavailable")
        if price is None:
            missing.append("latest stock price unavailable")
        else:
            age_days = (as_of - price.date).days
            if age_days < 0:
                missing.append("stock price date is after analysis date")
            elif age_days > self.MAX_PRICE_AGE_DAYS:
                missing.append(
                    f"stock price is older than {self.MAX_PRICE_AGE_DAYS} days"
                )
            if price.close <= 0:
                missing.append("latest stock price must be positive")
            if (
                current_report is not None
                and price.currency
                and current_report.currency
                and price.currency.upper() != current_report.currency.upper()
            ):
                missing.append("stock price and report currencies differ")

        decision = self.policy.build(current_report, latest_annual, history)
        missing.extend(decision.missing_information)

        if current_report is not None:
            if current_report.shares_outstanding is None or current_report.shares_outstanding <= 0:
                missing.append("positive shares outstanding unavailable")
            if current_report.total_debt is None:
                missing.append("Börsdata net debt unavailable")

        if missing:
            return ReverseDcfAnalysis(
                status="unavailable",
                policy_version=decision.policy_version,
                model="fcff",
                analysis_date=as_of.isoformat(),
                price_date=price.date.isoformat() if price else None,
                current_price=price.close if price else None,
                assumptions=decision.assumptions,
                assumption_sources=decision.assumption_sources,
                missing_information=tuple(dict.fromkeys(missing)),
                warnings=decision.warnings + self._LIMITATIONS,
            )

        inputs = ReverseDcfInputs(
            current_price=price.close,
            shares_outstanding=current_report.shares_outstanding,
            current_revenue=current_report.revenue,
            net_debt=current_report.total_debt,
            assumptions=decision.assumptions,
            branch_id=company.branch_id,
        )
        baseline = self.engine.value(inputs)
        expectations = {
            assumption: self._solve(inputs, assumption, bounds)
            for assumption, bounds in decision.solve_bounds.items()
        }
        return ReverseDcfAnalysis(
            status="available",
            policy_version=decision.policy_version,
            model="fcff",
            analysis_date=as_of.isoformat(),
            price_date=price.date.isoformat(),
            current_price=price.close,
            assumptions=decision.assumptions,
            assumption_sources=decision.assumption_sources,
            baseline_valuation=baseline,
            implied_expectations=expectations,
            warnings=decision.warnings + self._LIMITATIONS,
        )

    def _solve(
        self,
        inputs: ReverseDcfInputs,
        assumption: ImpliedAssumption,
        bounds: tuple[float, float],
    ) -> ImpliedExpectation:
        lower, upper = bounds
        try:
            result = self.engine.solve(inputs, assumption, lower, upper)
        except ValueError as exc:
            if "not bracketed" not in str(exc):
                raise
            lower_price = self._price_at(inputs, assumption, lower)
            upper_price = self._price_at(inputs, assumption, upper)
            return ImpliedExpectation(
                assumption=assumption,
                status="outside_bounds",
                lower_bound=lower,
                upper_bound=upper,
                modeled_price_range=tuple(sorted((lower_price, upper_price))),
                reason=str(exc),
            )
        return ImpliedExpectation(
            assumption=assumption,
            status="solved",
            lower_bound=lower,
            upper_bound=upper,
            implied_value=result.implied_assumption,
            modeled_price=result.modeled_price,
            price_difference=result.price_difference,
            iterations=result.iterations,
        )

    def _price_at(
        self,
        inputs: ReverseDcfInputs,
        assumption: ImpliedAssumption,
        value: float,
    ) -> float:
        assumptions = replace(inputs.assumptions, **{assumption: value})
        return self.engine.value(replace(inputs, assumptions=assumptions)).value_per_share

    def _unsupported(
        self,
        required_model: str,
        as_of: date | None = None,
    ) -> ReverseDcfAnalysis:
        return ReverseDcfAnalysis(
            status="unsupported_model",
            policy_version=self.policy.VERSION,
            model="fcff",
            required_model=required_model,
            analysis_date=(as_of or self.as_of).isoformat(),
            missing_information=(
                f"FCFF is not authoritative; use {required_model.replace('_', ' ')} model",
            ),
        )
