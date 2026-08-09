from dataclasses import dataclass, replace

from kncompanyscraper.analysis.valuation.reverse_dcf import DcfAssumptions


@dataclass(frozen=True)
class ForwardDcfScenarioAssumptions:
    label: str
    assumptions: DcfAssumptions
    assumption_sources: dict[str, str]


@dataclass(frozen=True)
class ForwardDcfScenarioDecision:
    policy_version: str
    scenarios: tuple[ForwardDcfScenarioAssumptions, ...]
    warnings: tuple[str, ...] = ()


class ForwardDcfScenarioPolicy:
    """Build comparable scenarios around company-specific operating history."""

    VERSION = "forward-dcf-scenarios-v1"
    GROWTH_RANGE = (-0.10, 0.20)
    MARGIN_RANGE = (0.0, 0.40)
    REINVESTMENT_RANGE = (0.0, 0.15)
    GROWTH_STRESS = 0.05
    MARGIN_STRESS = 0.03
    REINVESTMENT_STRESS = 0.02

    def build(
        self,
        base_assumptions: DcfAssumptions,
        latest_annual_report,
        historical_annual_reports: list,
    ) -> ForwardDcfScenarioDecision:
        growth_history = self._growth_history(
            latest_annual_report,
            historical_annual_reports,
        )
        margin_history = self._margin_history(
            latest_annual_report,
            historical_annual_reports,
        )

        base_growth = base_assumptions.revenue_growth
        bear_growth = min([base_growth - self.GROWTH_STRESS, *growth_history])
        bull_growth = max([base_growth + self.GROWTH_STRESS, *growth_history])

        base_margin = base_assumptions.ebit_margin
        bear_margin = min([base_margin - self.MARGIN_STRESS, *margin_history])
        bull_margin = max([base_margin + self.MARGIN_STRESS, *margin_history])

        warnings = []
        raw_reinvestment = base_assumptions.net_reinvestment_rate
        base_reinvestment = self._clamp(raw_reinvestment, *self.REINVESTMENT_RANGE)
        if base_reinvestment != raw_reinvestment:
            warnings.append(
                "forward DCF normalized net reinvestment from "
                f"{raw_reinvestment:.4f} to {base_reinvestment:.4f}; "
                "temporary negative reinvestment is not projected"
            )

        operating_source = (
            "company annual history plus standardized stress" if growth_history or margin_history
            else "company baseline plus standardized fallback stress"
        )
        shared_sources = {
            "projection_years": "fixed policy horizon",
            "tax_rate": "fixed normalized Nordic modeling rate",
            "discount_rate": "fixed required-return policy",
            "terminal_growth": "fixed mature nominal growth policy",
        }
        scenarios = (
            self._scenario(
                "bear",
                base_assumptions,
                revenue_growth=self._clamp(bear_growth, *self.GROWTH_RANGE),
                ebit_margin=self._clamp(bear_margin, *self.MARGIN_RANGE),
                net_reinvestment_rate=self._clamp(
                    base_reinvestment + self.REINVESTMENT_STRESS,
                    *self.REINVESTMENT_RANGE,
                ),
                operating_source=operating_source,
                shared_sources=shared_sources,
            ),
            self._scenario(
                "base",
                base_assumptions,
                revenue_growth=self._clamp(base_growth, *self.GROWTH_RANGE),
                ebit_margin=self._clamp(base_margin, *self.MARGIN_RANGE),
                net_reinvestment_rate=base_reinvestment,
                operating_source="company-specific reverse-DCF baseline",
                shared_sources=shared_sources,
            ),
            self._scenario(
                "bull",
                base_assumptions,
                revenue_growth=self._clamp(bull_growth, *self.GROWTH_RANGE),
                ebit_margin=self._clamp(bull_margin, *self.MARGIN_RANGE),
                net_reinvestment_rate=self._clamp(
                    base_reinvestment - self.REINVESTMENT_STRESS,
                    *self.REINVESTMENT_RANGE,
                ),
                operating_source=operating_source,
                shared_sources=shared_sources,
            ),
        )
        return ForwardDcfScenarioDecision(
            policy_version=self.VERSION,
            scenarios=scenarios,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _scenario(
        label,
        base_assumptions,
        *,
        revenue_growth,
        ebit_margin,
        net_reinvestment_rate,
        operating_source,
        shared_sources,
    ):
        return ForwardDcfScenarioAssumptions(
            label=label,
            assumptions=replace(
                base_assumptions,
                revenue_growth=revenue_growth,
                ebit_margin=ebit_margin,
                net_reinvestment_rate=net_reinvestment_rate,
            ),
            assumption_sources={
                **shared_sources,
                "revenue_growth": operating_source,
                "ebit_margin": operating_source,
                "net_reinvestment_rate": (
                    "company-implied rate normalized to zero or above, then scenario stress"
                ),
            },
        )

    @classmethod
    def _growth_history(cls, latest, history):
        reports = cls._dated_reports(latest, history)
        values = []
        for previous, current in zip(reports, reports[1:]):
            periods = current.year - previous.year
            if (
                periods > 0
                and previous.revenue is not None
                and previous.revenue > 0
                and current.revenue is not None
                and current.revenue > 0
            ):
                values.append((current.revenue / previous.revenue) ** (1 / periods) - 1)
        return values[-4:]

    @classmethod
    def _margin_history(cls, latest, history):
        values = []
        for report in cls._dated_reports(latest, history)[-5:]:
            if (
                report.revenue is not None
                and report.revenue > 0
                and report.ebit is not None
            ):
                values.append(report.ebit / report.revenue)
        return values

    @staticmethod
    def _dated_reports(latest, history):
        reports = [report for report in [*history, latest] if report is not None]
        dated = [report for report in reports if report.year is not None]
        by_year = {report.year: report for report in dated}
        return [by_year[year] for year in sorted(by_year)]

    @staticmethod
    def _clamp(value, lower, upper):
        return min(max(value, lower), upper)
