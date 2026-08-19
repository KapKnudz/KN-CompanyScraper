"""Reproducible holding-period sensitivity analysis for operating companies."""

from dataclasses import dataclass
from math import floor, isfinite
from typing import Literal
from kncompanyscraper.models.enums import RankingModel


ScenarioKind = Literal[
    "bear_multiple_compression",
    "bear_fundamental_impairment",
    "base",
    "bull",
]
EndpointSide = Literal["low", "high"]
EvidenceConfidence = Literal["low", "medium", "high"]
ForwardScenarioStatus = Literal[
    "available",
    "insufficient_evidence",
    "method_not_supported",
]
RankingTier = Literal["A", "B", "C", "IE", "RESEARCH"]


@dataclass(frozen=True)
class SourcedAssumption:
    value: float
    source_ids: tuple[str, ...]
    rationale: str
    guardrail_exception: str | None = None


@dataclass(frozen=True)
class ScenarioEndpoint:
    kind: ScenarioKind
    side: EndpointSide
    horizon_months: int
    revenue_cagr: SourcedAssumption
    ebit_margin: SourcedAssumption
    terminal_ev_ebit: SourcedAssumption
    net_debt: SourcedAssumption
    net_debt_change: SourcedAssumption
    share_count_growth: SourcedAssumption
    distributions_per_share: SourcedAssumption

    @property
    def key(self) -> str:
        return f"{self.kind}_{self.side}"


@dataclass(frozen=True)
class ForwardScenarioInputs:
    current_price: float | None
    current_revenue: float | None
    current_shares: float | None
    current_net_debt: float | None
    terminal_multiple_guardrail: tuple[float | None, float | None]
    endpoints: tuple[ScenarioEndpoint, ...]
    ranking_model: RankingModel = RankingModel.GENERAL


@dataclass(frozen=True)
class EndpointResult:
    key: str
    horizon_months: int
    revenue_at_horizon: float
    ebit_at_horizon: float
    enterprise_value_at_horizon: float
    equity_value_at_horizon: float
    value_per_share_at_horizon: float
    holding_value_per_share: float
    annualized_return: float


@dataclass(frozen=True)
class ForwardScenarioAnalysis:
    status: ForwardScenarioStatus
    policy_version: str
    results: tuple[EndpointResult, ...] = ()
    methodology_flags: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def result(self, key: str) -> EndpointResult | None:
        return next((item for item in self.results if item.key == key), None)


class ForwardScenarioEngine:
    """Validate coherent bundles and calculate holding-period return bands."""

    POLICY_VERSION = "forward-scenario-v2-share-growth"
    HORIZONS = (24, 36, 48)
    KINDS: tuple[ScenarioKind, ...] = (
        "bear_multiple_compression",
        "bear_fundamental_impairment",
        "base",
        "bull",
    )
    SIDES: tuple[EndpointSide, ...] = ("low", "high")

    def analyze(self, inputs: ForwardScenarioInputs) -> ForwardScenarioAnalysis:
        if inputs.ranking_model != RankingModel.GENERAL:
            return ForwardScenarioAnalysis(
                status="method_not_supported",
                policy_version=self.POLICY_VERSION,
                methodology_flags=(
                    f"{inputs.ranking_model} requires a dedicated forward valuation method",
                ),
            )

        flags, warnings = self._validate(inputs)
        if flags:
            return ForwardScenarioAnalysis(
                status="insufficient_evidence",
                policy_version=self.POLICY_VERSION,
                methodology_flags=tuple(flags),
                warnings=tuple(warnings),
            )

        results = tuple(self._calculate(inputs, endpoint) for endpoint in inputs.endpoints)
        ordering_flags = self._validate_outputs(results)
        if ordering_flags:
            return ForwardScenarioAnalysis(
                status="insufficient_evidence",
                policy_version=self.POLICY_VERSION,
                results=results,
                methodology_flags=tuple(ordering_flags),
                warnings=tuple(warnings),
            )
        return ForwardScenarioAnalysis(
            status="available",
            policy_version=self.POLICY_VERSION,
            results=results,
            warnings=tuple(warnings),
        )

    def _validate(self, inputs: ForwardScenarioInputs) -> tuple[list[str], list[str]]:
        flags: list[str] = []
        warnings: list[str] = []
        for name, value in (
            ("current_price", inputs.current_price),
            ("current_revenue", inputs.current_revenue),
            ("current_shares", inputs.current_shares),
        ):
            if not self._positive(value):
                flags.append(f"{name} must be a finite positive number")

        guardrail_low, guardrail_high = inputs.terminal_multiple_guardrail
        if not (
            self._positive(guardrail_low)
            and self._positive(guardrail_high)
            and guardrail_low is not None
            and guardrail_high is not None
            and guardrail_low <= guardrail_high
        ):
            flags.append("terminal multiple guardrail must be finite, positive, and ordered")

        expected_keys = {
            f"{kind}_{side}" for kind in self.KINDS for side in self.SIDES
        }
        endpoints = {endpoint.key: endpoint for endpoint in inputs.endpoints}
        if len(endpoints) != len(inputs.endpoints):
            flags.append("scenario endpoint keys must be unique")
        missing = sorted(expected_keys - set(endpoints))
        unexpected = sorted(set(endpoints) - expected_keys)
        if missing:
            flags.append("missing scenario endpoints: " + ", ".join(missing))
        if unexpected:
            flags.append("unexpected scenario endpoints: " + ", ".join(unexpected))

        horizons = {endpoint.horizon_months for endpoint in inputs.endpoints}
        if len(horizons) != 1 or not horizons.issubset(self.HORIZONS):
            flags.append("all endpoints must use the same 24, 36, or 48 month horizon")

        for endpoint in inputs.endpoints:
            self._validate_endpoint(
                inputs,
                endpoint,
                guardrail_low,
                guardrail_high,
                flags,
                warnings,
            )

        if expected_keys.issubset(endpoints):
            for side in self.SIDES:
                base = endpoints[f"base_{side}"]
                compression = endpoints[f"bear_multiple_compression_{side}"]
                impairment = endpoints[f"bear_fundamental_impairment_{side}"]
                bull = endpoints[f"bull_{side}"]
                self._validate_compression(base, compression, flags)
                self._validate_impairment(base, impairment, flags)
                self._validate_bull(base, bull, flags)

        return flags, warnings

    @classmethod
    def _validate_endpoint(
        cls,
        inputs: ForwardScenarioInputs,
        endpoint: ScenarioEndpoint,
        guardrail_low: float | None,
        guardrail_high: float | None,
        flags: list[str],
        warnings: list[str],
    ) -> None:
        assumptions = {
            "revenue_cagr": endpoint.revenue_cagr,
            "ebit_margin": endpoint.ebit_margin,
            "terminal_ev_ebit": endpoint.terminal_ev_ebit,
            "net_debt": endpoint.net_debt,
            "net_debt_change": endpoint.net_debt_change,
            "share_count_growth": endpoint.share_count_growth,
            "distributions_per_share": endpoint.distributions_per_share,
        }
        for name, assumption in assumptions.items():
            if not isfinite(assumption.value):
                flags.append(f"{endpoint.key}.{name} must be finite")
            if not assumption.source_ids:
                flags.append(f"{endpoint.key}.{name} requires at least one source ID")
            if not assumption.rationale.strip():
                flags.append(f"{endpoint.key}.{name} requires a rationale")

        if endpoint.revenue_cagr.value <= -1.0:
            flags.append(f"{endpoint.key}.revenue_cagr must be greater than -100%")
        if endpoint.ebit_margin.value <= 0:
            flags.append(f"{endpoint.key}.ebit_margin must be positive for EV/EBIT")
        if endpoint.terminal_ev_ebit.value <= 0:
            flags.append(f"{endpoint.key}.terminal_ev_ebit must be positive")
        if endpoint.share_count_growth.value <= -1.0:
            flags.append(f"{endpoint.key}.share_count_growth must be greater than -100%")
        if endpoint.distributions_per_share.value < 0:
            flags.append(f"{endpoint.key}.distributions_per_share cannot be negative")
        if not cls._finite(inputs.current_net_debt):
            flags.append("current_net_debt must be finite")
        elif not cls._same_value(
            endpoint.net_debt.value,
            inputs.current_net_debt + endpoint.net_debt_change.value,
        ):
            flags.append(
                f"{endpoint.key}.net_debt must reconcile to current net debt plus net_debt_change"
            )
        multiple = endpoint.terminal_ev_ebit
        if (
            guardrail_low is not None
            and guardrail_high is not None
            and not guardrail_low <= multiple.value <= guardrail_high
        ):
            if multiple.guardrail_exception and multiple.guardrail_exception.strip():
                warnings.append(
                    f"{endpoint.key}.terminal_ev_ebit uses sourced guardrail exception: "
                    f"{multiple.guardrail_exception.strip()}"
                )
            else:
                flags.append(
                    f"{endpoint.key}.terminal_ev_ebit is outside historical guardrails"
                )

    @staticmethod
    def _values(endpoint: ScenarioEndpoint) -> tuple[float, ...]:
        return (
            endpoint.revenue_cagr.value,
            endpoint.ebit_margin.value,
            endpoint.net_debt.value,
            endpoint.share_count_growth.value,
            endpoint.distributions_per_share.value,
        )

    @classmethod
    def _validate_compression(
        cls,
        base: ScenarioEndpoint,
        compression: ScenarioEndpoint,
        flags: list[str],
    ) -> None:
        if cls._values(base) != cls._values(compression):
            flags.append(
                f"{compression.key} must copy base operating, financing, dilution, and distribution values"
            )
        if compression.terminal_ev_ebit.value >= base.terminal_ev_ebit.value:
            flags.append(f"{compression.key} terminal multiple must be below base")

    @staticmethod
    def _validate_impairment(
        base: ScenarioEndpoint,
        impairment: ScenarioEndpoint,
        flags: list[str],
    ) -> None:
        comparisons = (
            impairment.revenue_cagr.value <= base.revenue_cagr.value,
            impairment.ebit_margin.value <= base.ebit_margin.value,
            impairment.net_debt.value >= base.net_debt.value,
            impairment.share_count_growth.value >= base.share_count_growth.value,
            impairment.distributions_per_share.value <= base.distributions_per_share.value,
            impairment.terminal_ev_ebit.value <= base.terminal_ev_ebit.value,
        )
        strict = (
            impairment.revenue_cagr.value < base.revenue_cagr.value,
            impairment.ebit_margin.value < base.ebit_margin.value,
            impairment.net_debt.value > base.net_debt.value,
            impairment.share_count_growth.value > base.share_count_growth.value,
            impairment.distributions_per_share.value < base.distributions_per_share.value,
        )
        if not all(comparisons):
            flags.append(f"{impairment.key} cannot improve a driver versus base")
        if not any(strict):
            flags.append(f"{impairment.key} must impair at least one fundamental driver")

    @staticmethod
    def _validate_bull(
        base: ScenarioEndpoint,
        bull: ScenarioEndpoint,
        flags: list[str],
    ) -> None:
        comparisons = (
            bull.revenue_cagr.value >= base.revenue_cagr.value,
            bull.ebit_margin.value >= base.ebit_margin.value,
            bull.net_debt.value <= base.net_debt.value,
            bull.share_count_growth.value <= base.share_count_growth.value,
            bull.distributions_per_share.value >= base.distributions_per_share.value,
            bull.terminal_ev_ebit.value >= base.terminal_ev_ebit.value,
        )
        if not all(comparisons):
            flags.append(f"{bull.key} cannot use a less favorable driver than base")

    @staticmethod
    def _calculate(
        inputs: ForwardScenarioInputs,
        endpoint: ScenarioEndpoint,
    ) -> EndpointResult:
        if (
            inputs.current_price is None
            or inputs.current_revenue is None
            or inputs.current_shares is None
        ):
            raise ValueError("validated forward inputs unexpectedly contain missing values")
        years = endpoint.horizon_months / 12.0
        revenue = inputs.current_revenue * (1.0 + endpoint.revenue_cagr.value) ** years
        ebit = revenue * endpoint.ebit_margin.value
        enterprise_value = ebit * endpoint.terminal_ev_ebit.value
        equity_value = enterprise_value - endpoint.net_debt.value
        diluted_shares = inputs.current_shares * (1.0 + endpoint.share_count_growth.value)
        value_per_share = equity_value / diluted_shares
        holding_value = value_per_share + endpoint.distributions_per_share.value
        annualized_return = (
            (holding_value / inputs.current_price) ** (1.0 / years) - 1.0
            if holding_value > 0
            else float("nan")
        )
        return EndpointResult(
            key=endpoint.key,
            horizon_months=endpoint.horizon_months,
            revenue_at_horizon=revenue,
            ebit_at_horizon=ebit,
            enterprise_value_at_horizon=enterprise_value,
            equity_value_at_horizon=equity_value,
            value_per_share_at_horizon=value_per_share,
            holding_value_per_share=holding_value,
            annualized_return=annualized_return,
        )

    @staticmethod
    def _validate_outputs(results: tuple[EndpointResult, ...]) -> list[str]:
        flags: list[str] = []
        by_key = {result.key: result for result in results}
        for result in results:
            if not all(
                isfinite(value)
                for value in (
                    result.revenue_at_horizon,
                    result.ebit_at_horizon,
                    result.enterprise_value_at_horizon,
                    result.equity_value_at_horizon,
                    result.value_per_share_at_horizon,
                    result.holding_value_per_share,
                    result.annualized_return,
                )
            ) or result.holding_value_per_share <= 0:
                flags.append(f"{result.key} produces a non-positive or non-finite holding value")

        for side in ForwardScenarioEngine.SIDES:
            base = by_key[f"base_{side}"].holding_value_per_share
            for kind in (
                "bear_multiple_compression",
                "bear_fundamental_impairment",
            ):
                if by_key[f"{kind}_{side}"].holding_value_per_share >= base:
                    flags.append(f"{kind}_{side} must produce less value than base_{side}")
        return flags

    @staticmethod
    def _positive(value: float | None) -> bool:
        return value is not None and isfinite(value) and value > 0

    @staticmethod
    def _finite(value: float | None) -> bool:
        return value is not None and isfinite(value)

    @staticmethod
    def _same_value(left: float, right: float) -> bool:
        return abs(left - right) <= 1e-9 * max(1.0, abs(left), abs(right))


@dataclass(frozen=True)
class RankedForwardCase:
    company_id: int
    ticker: str
    analysis: ForwardScenarioAnalysis
    required_return: float
    evidence_confidence: EvidenceConfidence
    unresolved_high_severity_challenge: bool = False


@dataclass(frozen=True)
class ForwardRank:
    company_id: int
    ticker: str
    economic_tier: RankingTier
    tier: RankingTier
    rank: int
    tied: bool
    actionable: bool
    worst_bear_lower_bound: float | None
    base_band: tuple[float, float] | None
    bull_lower_bound: float | None
    evidence_confidence: EvidenceConfidence
    flags: tuple[str, ...]


class ForwardScenarioRanker:
    """Apply the versioned hurdle-first, downside-first ranking policy."""

    POLICY_VERSION = "forward-ranking-v1"
    COMPARISON_TOLERANCE = 0.02
    _CONFIDENCE = {"low": 0, "medium": 1, "high": 2}
    _TIER_ORDER = {"A": 0, "B": 1, "C": 2, "IE": 3, "RESEARCH": 4}

    def rank(
        self,
        cases: list[RankedForwardCase],
        economic_tier_overrides: dict[int, RankingTier] | None = None,
    ) -> tuple[ForwardRank, ...]:
        economic_tier_overrides = economic_tier_overrides or {}
        prepared = [
            self._prepare(case, economic_tier_overrides.get(case.company_id))
            for case in cases
        ]
        prepared.sort(key=lambda item: (*item[1], item[0]["company_id"]))
        output: list[ForwardRank] = []
        previous_key = None
        current_rank = 0
        for position, (draft, tie_key) in enumerate(prepared, 1):
            if tie_key != previous_key:
                current_rank = position
            output.append(
                ForwardRank(
                    **draft,
                    rank=current_rank,
                    tied=False,
                )
            )
            previous_key = tie_key

        counts: dict[int, int] = {}
        for item in output:
            counts[item.rank] = counts.get(item.rank, 0) + 1
        return tuple(
            ForwardRank(
                **{
                    **item.__dict__,
                    "tied": counts[item.rank] > 1,
                }
            )
            for item in output
        )

    def _prepare(
        self,
        case: RankedForwardCase,
        economic_tier_override: RankingTier | None = None,
    ) -> tuple[dict, tuple]:
        flags = list(case.analysis.methodology_flags)
        if case.analysis.status != "available":
            economic_tier: RankingTier = "IE"
        else:
            base_low = self._return(case.analysis, "base_low")
            base_high = self._return(case.analysis, "base_high")
            if base_low >= case.required_return:
                economic_tier = "A"
            elif base_high >= case.required_return:
                economic_tier = "B"
            else:
                economic_tier = "C"
        if economic_tier_override is not None and economic_tier in ("A", "B", "C"):
            economic_tier = economic_tier_override
            flags.append("economic tier held by two-snapshot hysteresis")

        if case.unresolved_high_severity_challenge:
            tier: RankingTier = "RESEARCH"
            actionable = False
            flags.append("unresolved high-severity critic challenge")
        elif economic_tier == "IE":
            tier = "IE"
            actionable = False
            flags.append(case.analysis.status)
        else:
            tier = economic_tier
            if case.evidence_confidence == "low":
                tier = {"A": "B", "B": "C", "C": "C"}[tier]
                flags.append("low evidence confidence lowered tier")
            actionable = tier in ("A", "B")

        if case.analysis.status == "available":
            base_band = (
                self._return(case.analysis, "base_low"),
                self._return(case.analysis, "base_high"),
            )
            worst_bear = min(
                self._return(case.analysis, "bear_multiple_compression_low"),
                self._return(case.analysis, "bear_fundamental_impairment_low"),
            )
            bull_low = self._return(case.analysis, "bull_low")
            width = base_band[1] - base_band[0]
        else:
            base_band = None
            worst_bear = None
            bull_low = None
            width = None

        q = self._quantize
        tie_key = (
            self._TIER_ORDER[tier],
            -q(worst_bear),
            -q(base_band[0] if base_band else None),
            -self._CONFIDENCE[case.evidence_confidence],
            q(width),
            -q(bull_low),
        )
        draft = {
            "company_id": case.company_id,
            "ticker": case.ticker,
            "economic_tier": economic_tier,
            "tier": tier,
            "actionable": actionable,
            "worst_bear_lower_bound": worst_bear,
            "base_band": base_band,
            "bull_lower_bound": bull_low,
            "evidence_confidence": case.evidence_confidence,
            "flags": tuple(flags),
        }
        return draft, tie_key

    @classmethod
    def _quantize(cls, value: float | None) -> int:
        if value is None:
            return -10**9
        return floor(value / cls.COMPARISON_TOLERANCE + 0.5)

    @staticmethod
    def _return(analysis: ForwardScenarioAnalysis, key: str) -> float:
        result = analysis.result(key)
        if result is None:
            raise ValueError(f"available analysis is missing {key}")
        return result.annualized_return


def forward_analysis_from_dict(payload: dict) -> ForwardScenarioAnalysis:
    """Rebuild a persisted deterministic result for comparative ranking."""
    return ForwardScenarioAnalysis(
        status=payload["status"],
        policy_version=payload["policy_version"],
        results=tuple(EndpointResult(**item) for item in payload.get("results", [])),
        methodology_flags=tuple(payload.get("methodology_flags", [])),
        warnings=tuple(payload.get("warnings", [])),
    )
