"""Explicit, deterministic assumptions for the first reverse-DCF policy."""

from dataclasses import dataclass, replace
from datetime import date
from math import isfinite
from statistics import mean, pstdev
from typing import Literal

from kncompanyscraper.analysis.valuation.reverse_dcf import DcfAssumptions
from kncompanyscraper.analysis.valuation.required_return_policy import (
    RequiredReturnDecision,
    RequiredReturnPolicy,
)
from kncompanyscraper.borsdata.report import Report


@dataclass(frozen=True)
class NormalizationWindow:
    years: int
    start_year: int | None
    end_year: int | None
    ebit_margin: float
    reported_fcf_margin: float | None
    operating_cash_flow_margin: float | None


@dataclass(frozen=True)
class NormalizationDiagnostics:
    confidence: Literal["low", "medium", "high"]
    selected_window_years: int
    three_year: NormalizationWindow | None
    five_year: NormalizationWindow | None
    annual_fcf_margin_stddev: float | None
    annual_fcf_margin_range: float | None
    negative_fcf_years: int
    fcf_sign_changes: int
    highly_volatile_fcf: bool
    material_window_disagreement: bool
    material_aggregate_investing: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DcfPolicyDecision:
    available: bool
    policy_version: str
    assumptions: DcfAssumptions | None
    solve_bounds: dict[str, tuple[float, float]]
    assumption_sources: dict[str, str]
    normalized_fcf_margin: float | None = None
    normalization: NormalizationDiagnostics | None = None
    reinvestment_roic: float | None = None
    required_return: RequiredReturnDecision | None = None
    missing_information: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class DcfAssumptionPolicy:
    """Build auditable FCFF assumptions only from stored company evidence."""

    VERSION = "reverse-dcf-v8"
    PROJECTION_YEARS = 5
    TAX_RATE = 0.21
    TERMINAL_GROWTH = 0.02
    GROWTH_RANGE = (-0.05, 0.15)
    NET_REINVESTMENT_RANGE = (-0.05, 0.15)
    FCF_MARGIN_VOLATILITY = 0.10
    FCF_MARGIN_RANGE = 0.25
    WINDOW_DISAGREEMENT = 0.05
    MATERIAL_INVESTING_MARGIN = 0.15
    EXTREME_INVESTING_YEAR = 0.30
    SOLVE_BOUNDS = {
        "revenue_growth": (-0.10, 0.30),
        "ebit_margin": (0.0, 0.50),
        "terminal_growth": (-0.01, 0.04),
    }

    def __init__(self, required_return_policy: RequiredReturnPolicy | None = None):
        self.required_return_policy = required_return_policy or RequiredReturnPolicy()

    def build(
        self,
        current_report: Report | None,
        latest_annual_report: Report | None,
        historical_annual_reports: list[Report],
        *,
        as_of: date | None = None,
        currency: str | None = "SEK",
        market_cap: float | None = None,
        roic: float | None = None,
    ) -> DcfPolicyDecision:
        missing = self._missing_operating_inputs(current_report)
        if missing:
            return DcfPolicyDecision(
                available=False,
                policy_version=self.VERSION,
                assumptions=None,
                solve_bounds=dict(self.SOLVE_BOUNDS),
                assumption_sources={},
                missing_information=tuple(missing),
            )

        required_return = self.required_return_policy.build(
            as_of=as_of or date.today(),
            currency=currency,
            market_cap=market_cap,
        )
        if not required_return.available:
            return DcfPolicyDecision(
                available=False,
                policy_version=self.VERSION,
                assumptions=None,
                solve_bounds=dict(self.SOLVE_BOUNDS),
                assumption_sources={},
                required_return=required_return,
                missing_information=required_return.missing_information,
            )

        growth = self._historical_revenue_growth(
            latest_annual_report,
            historical_annual_reports,
        )
        warnings: list[str] = list(required_return.warnings)
        if growth is None:
            growth = 0.0
            growth_source = "zero-growth fallback; historical revenue growth unavailable"
            warnings.append("historical revenue growth unavailable")
        else:
            raw_growth = growth
            growth = self._clamp(growth, *self.GROWTH_RANGE)
            growth_source = "annual revenue CAGR over up to three years"
            if growth != raw_growth:
                warnings.append(
                    f"revenue growth clamped from {raw_growth:.4f} to {growth:.4f}"
                )

        economics = self._normalized_operating_economics(
            current_report,
            latest_annual_report,
            historical_annual_reports,
        )
        if economics is None:
            return DcfPolicyDecision(
                available=False,
                policy_version=self.VERSION,
                assumptions=None,
                solve_bounds=dict(self.SOLVE_BOUNDS),
                assumption_sources={},
                required_return=required_return,
                missing_information=(
                    "normalized EBIT history unavailable",
                ),
            )
        ebit_margin, fcf_margin, normalization, economics_source, economics_warnings = economics
        warnings.extend(economics_warnings)
        roic_fraction = self._roic_fraction(roic)
        if roic_fraction is None:
            raw_reinvestment = 0.0
            warnings.append(
                "positive ROIC unavailable; net reinvestment set to 0% and confidence lowered"
            )
        else:
            reinvestment_share_of_nopat = self._clamp(
                growth / roic_fraction if growth > 0 else 0.0,
                0.0,
                1.0,
            )
            raw_reinvestment = (
                ebit_margin
                * (1.0 - self.TAX_RATE)
                * reinvestment_share_of_nopat
            )
        reinvestment = self._clamp(raw_reinvestment, *self.NET_REINVESTMENT_RANGE)
        if reinvestment != raw_reinvestment:
            warnings.append(
                "net reinvestment rate clamped "
                f"from {raw_reinvestment:.4f} to {reinvestment:.4f}"
            )

        assumptions = DcfAssumptions(
            projection_years=self.PROJECTION_YEARS,
            revenue_growth=growth,
            ebit_margin=ebit_margin,
            tax_rate=self.TAX_RATE,
            discount_rate=required_return.profiles[
                required_return.baseline_profile
            ].discount_rate,
            terminal_growth=self.TERMINAL_GROWTH,
            net_reinvestment_rate=reinvestment,
            reinvestment_return=roic_fraction,
        )
        return DcfPolicyDecision(
            available=True,
            policy_version=self.VERSION,
            assumptions=assumptions,
            solve_bounds=dict(self.SOLVE_BOUNDS),
            assumption_sources={
                "projection_years": "fixed policy horizon",
                "revenue_growth": growth_source,
                "ebit_margin": economics_source,
                "tax_rate": "fixed normalized Nordic modeling rate",
                "discount_rate": (
                    "risk-free rate + fixed equity risk premium + size adjustment "
                    f"+ {required_return.baseline_profile} business-risk adjustment"
                ),
                "terminal_growth": "fixed mature nominal growth policy",
                "net_reinvestment_rate": (
                    "normalized NOPAT margin multiplied by historical revenue growth / "
                    "Börsdata ROIC, capped at 100% of NOPAT and the policy range; "
                    "reported FCF is diagnostic only because it includes aggregate investing cash flow"
                ),
                "reinvestment_return": (
                    "positive Börsdata ROIC used to recompute mature-state "
                    "reinvestment from terminal growth"
                ),
            },
            normalized_fcf_margin=fcf_margin,
            normalization=self._with_reinvestment_confidence(
                normalization,
                roic_fraction,
            ),
            reinvestment_roic=roic_fraction,
            required_return=required_return,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _missing_operating_inputs(report: Report | None) -> list[str]:
        if report is None:
            return ["current R12 or annual report unavailable"]
        missing: list[str] = []
        if report.revenue is None or report.revenue <= 0:
            missing.append("positive current revenue unavailable")
        return missing

    @classmethod
    def _normalized_operating_economics(
        cls,
        current: Report,
        latest_annual: Report | None,
        history: list[Report],
    ) -> tuple[
        float,
        float | None,
        NormalizationDiagnostics,
        str,
        tuple[str, ...],
    ] | None:
        valid_annuals = [
            report
            for report in [*history, latest_annual]
            if cls._has_valid_operating_economics(report)
        ]
        dated = {report.year: report for report in valid_annuals if report.year is not None}
        annuals = [dated[year] for year in sorted(dated)] if dated else valid_annuals

        current_fallback = False
        if len(annuals) >= 5:
            selected = annuals[-5:]
            warning = ()
        elif len(annuals) >= 3:
            selected = annuals[-3:]
            warning = (
                "five-year operating-margin history unavailable; using three-year average",
            )
        elif cls._has_valid_operating_economics(latest_annual):
            selected = [latest_annual]
            warning = (
                "three-year operating-margin history unavailable; using latest annual margin",
            )
        else:
            if not cls._has_valid_operating_economics(current):
                return None
            selected = [current]
            current_fallback = True
            warning = ("annual operating economics unavailable; using current R12 margin",)

        three_year = cls._window(annuals[-3:]) if len(annuals) >= 3 else None
        five_year = cls._window(annuals[-5:]) if len(annuals) >= 5 else None
        selected_window = cls._window(selected)
        diagnostics = cls._normalization_diagnostics(
            annuals,
            selected_window,
            three_year,
            five_year,
        )
        years = [str(report.year) for report in selected if report.year is not None]
        if current_fallback:
            source = "current R12 EBIT margin fallback"
        elif len(years) == len(selected) == 1:
            period = f"annual year {years[0]}"
            source = f"revenue-weighted EBIT margin over {period}"
        elif len(years) == len(selected):
            period = f"annual years {years[0]}-{years[-1]}"
            source = f"revenue-weighted EBIT margin over {period}"
        else:
            period = f"latest {len(selected)} valid reports"
            source = f"revenue-weighted EBIT margin over {period}"
        return (
            selected_window.ebit_margin,
            selected_window.reported_fcf_margin,
            diagnostics,
            source,
            warning
            + (
                "reported FCF includes aggregate investing cash flow and is diagnostic only",
            )
            + diagnostics.reasons,
        )

    @staticmethod
    def _window(reports: list[Report]) -> NormalizationWindow:
        revenue = sum(report.revenue for report in reports)
        years = [report.year for report in reports if report.year is not None]
        fcf_reports = [report for report in reports if report.free_cash_flow is not None]
        ocf_reports = [report for report in reports if report.operating_cash_flow is not None]
        return NormalizationWindow(
            years=len(reports),
            start_year=min(years) if years else None,
            end_year=max(years) if years else None,
            ebit_margin=sum(report.ebit for report in reports) / revenue,
            reported_fcf_margin=(
                sum(report.free_cash_flow for report in fcf_reports)
                / sum(report.revenue for report in fcf_reports)
                if fcf_reports
                else None
            ),
            operating_cash_flow_margin=(
                sum(report.operating_cash_flow for report in ocf_reports)
                / sum(report.revenue for report in ocf_reports)
                if ocf_reports
                else None
            ),
        )

    @classmethod
    def _normalization_diagnostics(
        cls,
        annuals: list[Report],
        selected: NormalizationWindow,
        three_year: NormalizationWindow | None,
        five_year: NormalizationWindow | None,
    ) -> NormalizationDiagnostics:
        fcf_margins = [
            report.free_cash_flow / report.revenue
            for report in annuals[-5:]
            if report.free_cash_flow is not None
        ]
        negative_years = sum(value <= 0 for value in fcf_margins)
        sign_changes = sum(
            (fcf_margins[index] > 0) != (fcf_margins[index - 1] > 0)
            for index in range(1, len(fcf_margins))
        )
        stddev = pstdev(fcf_margins) if len(fcf_margins) >= 2 else None
        margin_range = (
            max(fcf_margins) - min(fcf_margins) if fcf_margins else None
        )
        average = mean(fcf_margins) if fcf_margins else None
        highly_volatile = len(fcf_margins) >= 3 and (
            stddev >= cls.FCF_MARGIN_VOLATILITY
            or margin_range >= cls.FCF_MARGIN_RANGE
            or sign_changes >= 2
            or (
                average is not None
                and abs(average) >= 0.01
                and stddev / abs(average) >= 1.0
            )
        )
        disagreement = (
            three_year is not None
            and five_year is not None
            and (
                abs(three_year.ebit_margin - five_year.ebit_margin)
                >= cls.WINDOW_DISAGREEMENT
                or (
                    three_year.reported_fcf_margin is not None
                    and five_year.reported_fcf_margin is not None
                    and abs(
                        three_year.reported_fcf_margin
                        - five_year.reported_fcf_margin
                    )
                    >= cls.WINDOW_DISAGREEMENT
                )
            )
        )
        investing_margins = [
            cls._investing_cash_flow(report) / report.revenue
            for report in annuals[-5:]
            if cls._investing_cash_flow(report) is not None
        ]
        material_investing = bool(investing_margins) and (
            abs(mean(investing_margins)) >= cls.MATERIAL_INVESTING_MARGIN
            or max(abs(value) for value in investing_margins)
            >= cls.EXTREME_INVESTING_YEAR
        )
        reasons: list[str] = []
        if selected.years < 3:
            reasons.append("fewer than three valid annual observations")
        if negative_years:
            reasons.append(f"reported FCF is non-positive in {negative_years} observed year(s)")
        if highly_volatile:
            reasons.append("annual reported FCF margins are highly volatile")
        if disagreement:
            reasons.append("three- and five-year normalized margins materially disagree")
        if material_investing:
            reasons.append(
                "aggregate investing cash flow is material and may include acquisitions or disposals"
            )
        confidence = "low" if reasons else "medium"
        return NormalizationDiagnostics(
            confidence=confidence,
            selected_window_years=selected.years,
            three_year=three_year,
            five_year=five_year,
            annual_fcf_margin_stddev=stddev,
            annual_fcf_margin_range=margin_range,
            negative_fcf_years=negative_years,
            fcf_sign_changes=sign_changes,
            highly_volatile_fcf=highly_volatile,
            material_window_disagreement=disagreement,
            material_aggregate_investing=material_investing,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _investing_cash_flow(report: Report) -> float | None:
        if report.investing_cash_flow is not None:
            return report.investing_cash_flow
        return (report.raw_payload or {}).get("cash_Flow_From_Investing_Activities")

    @staticmethod
    def _with_reinvestment_confidence(
        diagnostics: NormalizationDiagnostics,
        roic: float | None,
    ) -> NormalizationDiagnostics:
        if roic is not None:
            return diagnostics
        reason = "positive Börsdata ROIC unavailable for reinvestment calibration"
        return replace(
            diagnostics,
            confidence="low",
            reasons=diagnostics.reasons + (reason,),
        )

    @staticmethod
    def _roic_fraction(roic: float | None) -> float | None:
        if roic is None or not isfinite(roic) or roic <= 0:
            return None
        return roic / 100.0

    @staticmethod
    def _has_valid_operating_economics(report: Report | None) -> bool:
        return (
            report is not None
            and report.revenue is not None
            and report.revenue > 0
            and report.ebit is not None
        )

    @classmethod
    def _historical_revenue_growth(
        cls,
        latest: Report | None,
        history: list[Report],
    ) -> float | None:
        if latest is None or latest.revenue is None or latest.revenue <= 0:
            return None
        candidates = [
            report
            for report in history
            if report.revenue is not None and report.revenue > 0
        ]
        if not candidates:
            return None

        has_dated_history = latest.year is not None and any(
            report.year is not None for report in candidates
        )
        if has_dated_history:
            dated = [
                report
                for report in candidates
                if report.year is not None and 0 < latest.year - report.year <= 3
            ]
            if not dated:
                return None
            baseline = min(dated, key=lambda report: report.year)
            periods = latest.year - baseline.year
        else:
            periods = min(3, len(candidates))
            baseline = candidates[-periods]
        return (latest.revenue / baseline.revenue) ** (1.0 / periods) - 1.0

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return min(max(value, lower), upper)
