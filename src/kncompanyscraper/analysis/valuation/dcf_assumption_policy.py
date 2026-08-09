"""Explicit, deterministic assumptions for the first reverse-DCF policy."""

from dataclasses import dataclass

from kncompanyscraper.analysis.valuation.reverse_dcf import DcfAssumptions
from kncompanyscraper.borsdata.report import Report


@dataclass(frozen=True)
class DcfPolicyDecision:
    available: bool
    policy_version: str
    assumptions: DcfAssumptions | None
    solve_bounds: dict[str, tuple[float, float]]
    assumption_sources: dict[str, str]
    missing_information: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class DcfAssumptionPolicy:
    """Build auditable FCFF assumptions only from stored company evidence."""

    VERSION = "reverse-dcf-v2"
    PROJECTION_YEARS = 5
    TAX_RATE = 0.21
    DISCOUNT_RATE = 0.10
    TERMINAL_GROWTH = 0.02
    GROWTH_RANGE = (-0.05, 0.15)
    NET_REINVESTMENT_RANGE = (-0.05, 0.15)
    SOLVE_BOUNDS = {
        "revenue_growth": (-0.10, 0.30),
        "ebit_margin": (0.0, 0.50),
        "terminal_growth": (-0.01, 0.04),
    }

    def build(
        self,
        current_report: Report | None,
        latest_annual_report: Report | None,
        historical_annual_reports: list[Report],
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

        growth = self._historical_revenue_growth(
            latest_annual_report,
            historical_annual_reports,
        )
        warnings: list[str] = []
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

        revenue = current_report.revenue
        ebit = current_report.ebit
        free_cash_flow = current_report.free_cash_flow
        ebit_margin = ebit / revenue
        raw_reinvestment = (ebit * (1.0 - self.TAX_RATE) - free_cash_flow) / revenue
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
            discount_rate=self.DISCOUNT_RATE,
            terminal_growth=self.TERMINAL_GROWTH,
            net_reinvestment_rate=reinvestment,
        )
        return DcfPolicyDecision(
            available=True,
            policy_version=self.VERSION,
            assumptions=assumptions,
            solve_bounds=dict(self.SOLVE_BOUNDS),
            assumption_sources={
                "projection_years": "fixed policy horizon",
                "revenue_growth": growth_source,
                "ebit_margin": "current R12 EBIT / revenue, falling back to annual",
                "tax_rate": "fixed normalized Nordic modeling rate",
                "discount_rate": "fixed required-return policy",
                "terminal_growth": "fixed mature nominal growth policy",
                "net_reinvestment_rate": (
                    "current (NOPAT - reported FCF) / revenue, clamped to policy range"
                ),
            },
            warnings=tuple(warnings),
        )

    @staticmethod
    def _missing_operating_inputs(report: Report | None) -> list[str]:
        if report is None:
            return ["current R12 or annual report unavailable"]
        missing: list[str] = []
        if report.revenue is None or report.revenue <= 0:
            missing.append("positive current revenue unavailable")
        if report.ebit is None or report.ebit <= 0:
            missing.append("positive current EBIT unavailable")
        if report.free_cash_flow is None or report.free_cash_flow <= 0:
            missing.append("positive current free cash flow unavailable")
        return missing

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
