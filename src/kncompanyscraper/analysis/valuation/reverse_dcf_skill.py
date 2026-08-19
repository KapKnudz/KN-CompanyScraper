"""Analysis skill wiring stored evidence through policy into reverse DCF."""

from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

from kncompanyscraper.analysis.base.skill import Skill
from kncompanyscraper.analysis.valuation.dcf_assumption_policy import (
    DcfAssumptionPolicy,
    HistoricalOperatingBenchmarks,
    NormalizationDiagnostics,
)
from kncompanyscraper.analysis.valuation.reverse_dcf import (
    DcfAssumptions,
    DcfValue,
    ImpliedAssumption,
    ReverseDcfEngine,
    ReverseDcfInputs,
)
from kncompanyscraper.analysis.valuation.required_return_policy import (
    RequiredReturnDecision,
    RiskProfile,
)
from kncompanyscraper.borsdata.kpi_ids import KpiIds


ExpectationStatus = Literal["solved", "outside_bounds"]
OutsideDirection = Literal[
    "below_lower_bound",
    "above_upper_bound",
    "not_determined",
]
AnalysisStatus = Literal["available", "unavailable", "unsupported_model"]


@dataclass(frozen=True)
class ImpliedExpectation:
    assumption: ImpliedAssumption
    status: ExpectationStatus
    lower_bound: float
    upper_bound: float
    source_id: str | None = None
    implied_value: float | None = None
    modeled_price: float | None = None
    price_difference: float | None = None
    iterations: int | None = None
    modeled_price_range: tuple[float, float] | None = None
    outside_direction: OutsideDirection | None = None
    required_value_hint: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class DiscountRateSensitivity:
    profile: RiskProfile
    label: str
    discount_rate: float
    business_risk_adjustment: float
    implied_expectations: dict[str, ImpliedExpectation]
    expectation_curve: tuple["GrowthMarginExpectation", ...] | None = None


@dataclass(frozen=True)
class GrowthMarginExpectation:
    revenue_growth: float
    ebit_margin_expectation: ImpliedExpectation


@dataclass(frozen=True)
class PriceFundamentalAttributionPeriod:
    years: int
    start_price_date: str
    end_price_date: str
    start_report_year: int
    end_report_year: int
    price_return: float
    annualized_price_return: float
    annualized_revenue_growth: float | None
    annualized_ebit_growth: float | None
    annualized_net_income_growth: float | None
    annualized_eps_growth: float | None
    ebit_margin_change: float
    share_count_change: float | None
    pe_change: float | None


@dataclass(frozen=True)
class ReverseDcfAnalysis:
    status: AnalysisStatus
    policy_version: str
    model: str
    required_model: str | None = None
    analysis_date: str | None = None
    price_date: str | None = None
    current_price: float | None = None
    current_revenue: float | None = None
    current_shares: float | None = None
    current_net_debt: float | None = None
    assumptions: DcfAssumptions | None = None
    assumption_sources: dict[str, str] | None = None
    normalized_fcf_margin: float | None = None
    normalization: NormalizationDiagnostics | None = None
    operating_history: HistoricalOperatingBenchmarks | None = None
    price_fundamental_attribution: tuple[PriceFundamentalAttributionPeriod, ...] = ()
    reinvestment_roic: float | None = None
    required_return: RequiredReturnDecision | None = None
    baseline_valuation: DcfValue | None = None
    implied_expectations: dict[str, ImpliedExpectation] | None = None
    expectation_curve: tuple[GrowthMarginExpectation, ...] | None = None
    discount_rate_sensitivities: dict[str, DiscountRateSensitivity] | None = None
    missing_information: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class ReverseDcfSkill(Skill):
    MAX_PRICE_AGE_DAYS = 7
    SHARES_TO_UNITS = 1_000_000.0
    EXPECTATION_CURVE_GROWTH_RATES = (
        -0.05,
        0.00,
        0.05,
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
    )
    _LIMITATIONS = (
        "Börsdata reported FCF equals operating cash flow plus aggregate investing "
        "cash flow and is used only as a normalization-confidence diagnostic",
        "Börsdata does not separate maintenance capex, growth capex, acquisitions, "
        "disposals, or annual working-capital changes",
        "Report.total_debt contains the Börsdata net_Debt field",
        "year-one revenue growth fades linearly to mature growth and the current "
        "EBIT margin fades linearly to the modeled final-year margin",
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
        fundamentals = self.valuation_repository.get_general_fundamentals(company.id)
        return self.analyze_reports(
            company,
            latest_annual=latest_annual,
            latest_r12=latest_r12,
            history=history,
            price=price,
            as_of=self.as_of,
            roic=fundamentals.get(KpiIds.ROIC),
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
        roic: float | None = None,
    ) -> ReverseDcfAnalysis:
        """Analyze supplied point-in-time evidence for live or historical ranking."""
        if company.branch_id in (68, 69, 70):
            return self._unsupported("residual_income_or_dividend", as_of)
        if company.branch_id == 75:
            return self._unsupported("nav_or_ffo", as_of)

        current_report = latest_r12 or latest_annual
        operating_history = self.policy.build_operating_history(latest_annual, history)
        price_fundamental_attribution = self._build_price_fundamental_attribution(
            company.id,
            price,
            current_report,
            latest_annual,
            history,
        )
        missing: list[str] = []
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

        market_cap = (
            price.close
            * current_report.shares_outstanding
            * self.SHARES_TO_UNITS
            if price is not None
            and current_report is not None
            and current_report.shares_outstanding is not None
            and current_report.shares_outstanding > 0
            else None
        )
        decision = self.policy.build(
            current_report,
            latest_annual,
            history,
            as_of=as_of,
            currency=(price.currency if price else None)
            or (current_report.currency if current_report else None),
            market_cap=market_cap,
            roic=roic,
        )
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
                current_revenue=current_report.revenue if current_report else None,
                current_shares=(
                    current_report.shares_outstanding if current_report else None
                ),
                current_net_debt=current_report.total_debt if current_report else None,
                assumptions=decision.assumptions,
                assumption_sources=decision.assumption_sources,
                normalized_fcf_margin=decision.normalized_fcf_margin,
                normalization=decision.normalization,
                operating_history=operating_history,
                price_fundamental_attribution=price_fundamental_attribution,
                reinvestment_roic=decision.reinvestment_roic,
                required_return=decision.required_return,
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
        expectation_curve = tuple(
            self._growth_margin_point(inputs, growth)
            for growth in self.EXPECTATION_CURVE_GROWTH_RATES
        )
        sensitivities = {
            profile: self._build_sensitivity(
                inputs,
                decision.solve_bounds,
                profile,
                rate_profile.label,
                rate_profile.discount_rate,
                rate_profile.business_risk_adjustment,
            )
            for profile, rate_profile in decision.required_return.profiles.items()
        }
        return ReverseDcfAnalysis(
            status="available",
            policy_version=decision.policy_version,
            model="fcff",
            analysis_date=as_of.isoformat(),
            price_date=price.date.isoformat(),
            current_price=price.close,
            current_revenue=current_report.revenue,
            current_shares=current_report.shares_outstanding,
            current_net_debt=current_report.total_debt,
            assumptions=decision.assumptions,
            assumption_sources=decision.assumption_sources,
            normalized_fcf_margin=decision.normalized_fcf_margin,
            normalization=decision.normalization,
            operating_history=operating_history,
            price_fundamental_attribution=price_fundamental_attribution,
            reinvestment_roic=decision.reinvestment_roic,
            required_return=decision.required_return,
            baseline_valuation=baseline,
            implied_expectations=expectations,
            expectation_curve=expectation_curve,
            discount_rate_sensitivities=sensitivities,
            warnings=decision.warnings + self._LIMITATIONS,
        )

    def _build_sensitivity(
        self,
        inputs: ReverseDcfInputs,
        solve_bounds: dict[str, tuple[float, float]],
        profile: RiskProfile,
        label: str,
        discount_rate: float,
        business_risk_adjustment: float,
    ) -> DiscountRateSensitivity:
        sensitivity_inputs = replace(
            inputs,
            assumptions=replace(inputs.assumptions, discount_rate=discount_rate),
        )
        expectations = {
            assumption: self._solve(
                sensitivity_inputs,
                assumption,
                bounds,
                source_prefix=f"valuation:reverse_dcf:{profile}",
            )
            for assumption, bounds in solve_bounds.items()
        }
        expectation_curve = tuple(
            self._growth_margin_point(
                sensitivity_inputs,
                growth,
                source_prefix=f"valuation:reverse_dcf:{profile}:curve",
            )
            for growth in self.EXPECTATION_CURVE_GROWTH_RATES
        )
        return DiscountRateSensitivity(
            profile=profile,
            label=label,
            discount_rate=discount_rate,
            business_risk_adjustment=business_risk_adjustment,
            implied_expectations=expectations,
            expectation_curve=expectation_curve,
        )

    def _solve(
        self,
        inputs: ReverseDcfInputs,
        assumption: ImpliedAssumption,
        bounds: tuple[float, float],
        *,
        source_prefix: str = "valuation:reverse_dcf",
    ) -> ImpliedExpectation:
        lower, upper = bounds
        try:
            result = self.engine.solve(inputs, assumption, lower, upper)
        except ValueError as exc:
            if "not bracketed" not in str(exc):
                raise
            lower_price = self._price_at(inputs, assumption, lower)
            upper_price = self._price_at(inputs, assumption, upper)
            outside_direction = self._outside_direction(
                inputs.current_price,
                lower_price,
                upper_price,
            )
            required_value_hint = self._required_value_hint(
                assumption,
                outside_direction,
                lower,
                upper,
            )
            return ImpliedExpectation(
                assumption=assumption,
                status="outside_bounds",
                lower_bound=lower,
                upper_bound=upper,
                source_id=f"{source_prefix}:{assumption}",
                modeled_price_range=tuple(sorted((lower_price, upper_price))),
                outside_direction=outside_direction,
                required_value_hint=required_value_hint,
                reason=str(exc),
            )
        return ImpliedExpectation(
            assumption=assumption,
            status="solved",
            lower_bound=lower,
            upper_bound=upper,
            source_id=f"{source_prefix}:{assumption}",
            implied_value=result.implied_assumption,
            modeled_price=result.modeled_price,
            price_difference=result.price_difference,
            iterations=result.iterations,
        )

    def _growth_margin_point(
        self,
        inputs: ReverseDcfInputs,
        revenue_growth: float,
        *,
        source_prefix: str = "valuation:reverse_dcf:curve",
    ) -> GrowthMarginExpectation:
        curve_inputs = replace(
            inputs,
            assumptions=replace(
                inputs.assumptions,
                revenue_growth=revenue_growth,
            ),
        )
        growth_label = f"{int(round(revenue_growth * 10_000)):+d}bp"
        expectation = self._solve(
            curve_inputs,
            "ebit_margin",
            self.policy.SOLVE_BOUNDS["ebit_margin"],
            source_prefix=f"{source_prefix}:{growth_label}",
        )
        if (
            expectation.status == "outside_bounds"
            and expectation.outside_direction == "not_determined"
            and curve_inputs.assumptions.reinvestment_return is not None
            and revenue_growth >= curve_inputs.assumptions.reinvestment_return
        ):
            expectation = replace(
                expectation,
                required_value_hint=(
                    "no EBIT margin within bounds can bridge price because "
                    "growth / ROIC consumes 100% of NOPAT"
                ),
                reason=(
                    "modeled price is insensitive to EBIT margin because the "
                    "growth-implied reinvestment share is capped at 100% of NOPAT"
                ),
            )
        return GrowthMarginExpectation(
            revenue_growth=revenue_growth,
            ebit_margin_expectation=expectation,
        )

    def _build_price_fundamental_attribution(
        self,
        company_id: int,
        current_price,
        current_report,
        latest_annual,
        history,
    ) -> tuple[PriceFundamentalAttributionPeriod, ...]:
        if current_price is None or current_report is None:
            return ()
        get_price = getattr(self.valuation_repository, "get_stock_price_on_date", None)
        if get_price is None:
            return ()

        annuals = {
            report.year: report
            for report in [*history, latest_annual]
            if report is not None and report.year is not None
        }
        if current_report.year is None:
            return ()

        periods = []
        for years in (1, 3, 5):
            baseline = annuals.get(current_report.year - years)
            if baseline is None:
                continue
            target_date = self._subtract_years(current_price.date, years)
            start_price = get_price(company_id, target_date, max_age_days=7)
            if (
                start_price is None
                or not isinstance(getattr(start_price, "close", None), (int, float))
                or start_price.close <= 0
            ):
                continue
            if not self._has_attribution_inputs(current_report, baseline):
                continue

            current_eps = self._eps(current_report)
            baseline_eps = self._eps(baseline)
            current_pe = (
                current_price.close / current_eps
                if current_eps is not None and current_eps > 0
                else None
            )
            baseline_pe = (
                start_price.close / baseline_eps
                if baseline_eps is not None and baseline_eps > 0
                else None
            )
            periods.append(
                PriceFundamentalAttributionPeriod(
                    years=years,
                    start_price_date=start_price.date.isoformat(),
                    end_price_date=current_price.date.isoformat(),
                    start_report_year=baseline.year,
                    end_report_year=current_report.year,
                    price_return=current_price.close / start_price.close - 1.0,
                    annualized_price_return=self._cagr(
                        start_price.close, current_price.close, years
                    ),
                    annualized_revenue_growth=self._cagr(
                        baseline.revenue, current_report.revenue, years
                    ),
                    annualized_ebit_growth=self._cagr(
                        baseline.ebit, current_report.ebit, years
                    ),
                    annualized_net_income_growth=self._cagr(
                        baseline.net_income, current_report.net_income, years
                    ),
                    annualized_eps_growth=self._cagr(
                        baseline_eps, current_eps, years
                    ),
                    ebit_margin_change=(
                        current_report.ebit / current_report.revenue
                        - baseline.ebit / baseline.revenue
                    ),
                    share_count_change=(
                        current_report.shares_outstanding
                        / baseline.shares_outstanding
                        - 1.0
                        if current_report.shares_outstanding is not None
                        and baseline.shares_outstanding is not None
                        and baseline.shares_outstanding > 0
                        else None
                    ),
                    pe_change=(
                        current_pe / baseline_pe - 1.0
                        if current_pe is not None
                        and baseline_pe is not None
                        and baseline_pe > 0
                        else None
                    ),
                )
            )
        return tuple(periods)

    @staticmethod
    def _subtract_years(value: date, years: int) -> date:
        try:
            return value.replace(year=value.year - years)
        except ValueError:
            return value.replace(year=value.year - years, day=28)

    @staticmethod
    def _has_attribution_inputs(current, baseline) -> bool:
        return all(
            value is not None and value > 0
            for value in (
                current.revenue,
                baseline.revenue,
                current.ebit,
                baseline.ebit,
            )
        )

    @staticmethod
    def _eps(report) -> float | None:
        if (
            report.net_income is None
            or report.shares_outstanding is None
            or report.shares_outstanding <= 0
        ):
            return None
        return report.net_income / report.shares_outstanding

    @staticmethod
    def _cagr(start: float | None, end: float | None, years: int) -> float | None:
        if start is None or end is None or start <= 0 or end <= 0:
            return None
        return (end / start) ** (1.0 / years) - 1.0

    @staticmethod
    def _outside_direction(
        current_price: float,
        lower_price: float,
        upper_price: float,
    ) -> OutsideDirection:
        if upper_price == lower_price:
            return "not_determined"
        increasing = upper_price > lower_price
        if current_price > max(lower_price, upper_price):
            return "above_upper_bound" if increasing else "below_lower_bound"
        if current_price < min(lower_price, upper_price):
            return "below_lower_bound" if increasing else "above_upper_bound"
        return "not_determined"

    @staticmethod
    def _required_value_hint(
        assumption: ImpliedAssumption,
        direction: OutsideDirection,
        lower: float,
        upper: float,
    ) -> str | None:
        if direction == "above_upper_bound":
            return f"{assumption} > {upper:.1%}"
        if direction == "below_lower_bound":
            return f"{assumption} < {lower:.1%}"
        return None

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
