from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path
from statistics import mean

from kncompanyscraper.analysis.ranking.score_rules import (
    _linear_score,
    compute_margin_of_safety,
)


@dataclass(frozen=True)
class MetricRow:
    observation_date: date
    company_id: int
    category: str
    metric: str
    raw_value: float | None
    normalized_score: float | None
    configured_weight: float
    effective_weight: float
    category_score: float
    total_category_weight: float
    available: bool
    transformation: str
    dependencies: tuple[str, ...]
    cross_category_dependencies: tuple[str, ...]
    realized_return: float
    benchmark_return: float

    @property
    def key(self) -> str:
        return f"{self.category}.{self.metric}"


@dataclass(frozen=True)
class RankingMetrics:
    top_excess: float
    top_bottom_spread: float
    score_return_correlation: float
    periods: int


@dataclass(frozen=True)
class MetricDiagnostic:
    key: str
    coverage: float
    average_effective_weight: float
    score_return_correlation: float
    train_excess_delta: float
    train_spread_delta: float
    holdout_excess_delta: float
    holdout_spread_delta: float


@dataclass(frozen=True)
class RedundantPair:
    first: str
    second: str
    correlation: float


@dataclass(frozen=True)
class PolicyChallenger:
    name: str
    train: RankingMetrics
    holdout: RankingMetrics


@dataclass(frozen=True)
class MetricSensitivity:
    key: str
    variant: str
    train_excess_delta: float
    train_spread_delta: float
    holdout_excess_delta: float
    holdout_spread_delta: float


@dataclass(frozen=True)
class MetricAuditReport:
    horizon_months: int
    baseline_train: RankingMetrics
    baseline_holdout: RankingMetrics
    diagnostics: tuple[MetricDiagnostic, ...]
    redundant_pairs: tuple[RedundantPair, ...]
    shared_dependencies: dict[str, tuple[str, ...]]
    cross_category_dependencies: dict[str, tuple[str, ...]]
    challengers: tuple[PolicyChallenger, ...]
    weight_sensitivities: tuple[MetricSensitivity, ...]
    threshold_sensitivities: tuple[MetricSensitivity, ...]


def load_metric_rows(path: Path, horizon_months: int = 12) -> list[MetricRow]:
    return_field = f"return_{horizon_months}m"
    benchmark_field = f"benchmark_{horizon_months}m_return"
    required = {
        "observation_date",
        "company_id",
        "category",
        "metric",
        "raw_value",
        "normalized_score",
        "configured_weight",
        "effective_weight",
        "category_score",
        "total_category_weight",
        "available",
        "transformation",
        "dependencies",
        "cross_category_dependencies",
        return_field,
        benchmark_field,
    }
    rows = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                "Scoring audit CSV lacks analysis fields: "
                + ", ".join(sorted(missing))
            )
        for raw in reader:
            if not raw[return_field] or not raw[benchmark_field]:
                continue
            rows.append(
                MetricRow(
                    observation_date=date.fromisoformat(raw["observation_date"]),
                    company_id=int(raw["company_id"]),
                    category=raw["category"],
                    metric=raw["metric"],
                    raw_value=_optional_float(raw["raw_value"]),
                    normalized_score=_optional_float(raw["normalized_score"]),
                    configured_weight=float(raw["configured_weight"]),
                    effective_weight=float(raw["effective_weight"]),
                    category_score=float(raw["category_score"]),
                    total_category_weight=float(raw["total_category_weight"]),
                    available=raw["available"].lower() == "true",
                    transformation=raw["transformation"],
                    dependencies=_split(raw["dependencies"]),
                    cross_category_dependencies=_split(
                        raw["cross_category_dependencies"]
                    ),
                    realized_return=float(raw[return_field]),
                    benchmark_return=float(raw[benchmark_field]),
                )
            )
    return rows


def analyze_metric_audit(
    rows: list[MetricRow],
    horizon_months: int = 12,
    redundancy_threshold: float = 0.75,
) -> MetricAuditReport:
    dates = sorted({row.observation_date for row in rows})
    if len(dates) < 4:
        raise ValueError("At least four observation dates are required")
    split = len(dates) // 2
    train_dates = set(dates[:split])
    holdout_dates = set(dates[split:])
    train = [row for row in rows if row.observation_date in train_dates]
    holdout = [row for row in rows if row.observation_date in holdout_dates]
    baseline_train = evaluate_metric_policy(train)
    baseline_holdout = evaluate_metric_policy(holdout)

    challenger_specs = (
        (
            "without_ev_ebit_percentile",
            frozenset({"valuation.ev_ebit_percentile"}),
            False,
        ),
        (
            "without_net_margin",
            frozenset({"quality.net_margin"}),
            False,
        ),
        (
            "without_ev_ebit_and_net_margin",
            frozenset(
                {"valuation.ev_ebit_percentile", "quality.net_margin"}
            ),
            False,
        ),
        ("margin_of_safety_without_quality_growth", frozenset(), True),
    )
    challengers = tuple(
        PolicyChallenger(
            name=name,
            train=evaluate_metric_policy(
                train,
                ablated_metrics=ablated,
                neutral_margin_of_safety=neutral_mos,
            ),
            holdout=evaluate_metric_policy(
                holdout,
                ablated_metrics=ablated,
                neutral_margin_of_safety=neutral_mos,
            ),
        )
        for name, ablated, neutral_mos in challenger_specs
    )

    diagnostics = []
    weight_sensitivities = []
    threshold_sensitivities = []
    for key in sorted({row.key for row in rows}):
        metric_rows = [row for row in rows if row.key == key]
        available = [row for row in metric_rows if row.available]
        train_without = evaluate_metric_policy(train, ablated_metric=key)
        holdout_without = evaluate_metric_policy(holdout, ablated_metric=key)
        diagnostics.append(
            MetricDiagnostic(
                key=key,
                coverage=len(available) / len(metric_rows),
                average_effective_weight=(
                    mean(row.effective_weight for row in available)
                    if available
                    else 0.0
                ),
                score_return_correlation=_average_metric_correlation(
                    available
                ),
                train_excess_delta=(
                    train_without.top_excess - baseline_train.top_excess
                ),
                train_spread_delta=(
                    train_without.top_bottom_spread
                    - baseline_train.top_bottom_spread
                ),
                holdout_excess_delta=(
                    holdout_without.top_excess - baseline_holdout.top_excess
                ),
                holdout_spread_delta=(
                    holdout_without.top_bottom_spread
                    - baseline_holdout.top_bottom_spread
                ),
            )
        )
        for multiplier in (0.5, 2.0):
            weight_sensitivities.append(
                _sensitivity(
                    key,
                    f"weight_{multiplier:g}x",
                    baseline_train,
                    baseline_holdout,
                    evaluate_metric_policy(
                        train,
                        weight_multipliers={key: multiplier},
                    ),
                    evaluate_metric_policy(
                        holdout,
                        weight_multipliers={key: multiplier},
                    ),
                )
            )
        transformation = next(
            (
                row.transformation
                for row in metric_rows
                if row.available and row.transformation
            ),
            "",
        )
        if _supports_threshold_sensitivity(transformation):
            for factor in (0.8, 1.2):
                threshold_sensitivities.append(
                    _sensitivity(
                        key,
                        f"threshold_{factor:g}x",
                        baseline_train,
                        baseline_holdout,
                        evaluate_metric_policy(
                            train,
                            threshold_factors={key: factor},
                        ),
                        evaluate_metric_policy(
                            holdout,
                            threshold_factors={key: factor},
                        ),
                    )
                )

    return MetricAuditReport(
        horizon_months=horizon_months,
        baseline_train=baseline_train,
        baseline_holdout=baseline_holdout,
        diagnostics=tuple(diagnostics),
        redundant_pairs=_redundant_pairs(rows, redundancy_threshold),
        shared_dependencies=_shared_dependencies(rows),
        cross_category_dependencies=_cross_dependencies(rows),
        challengers=challengers,
        weight_sensitivities=tuple(weight_sensitivities),
        threshold_sensitivities=tuple(threshold_sensitivities),
    )


def evaluate_metric_policy(
    rows: list[MetricRow],
    ablated_metric: str | None = None,
    ablated_metrics: frozenset[str] = frozenset(),
    neutral_margin_of_safety: bool = False,
    weight_multipliers: dict[str, float] | None = None,
    threshold_factors: dict[str, float] | None = None,
) -> RankingMetrics:
    weight_multipliers = weight_multipliers or {}
    threshold_factors = threshold_factors or {}
    if ablated_metric is not None:
        ablated_metrics = ablated_metrics | {ablated_metric}
    observations: dict[tuple[date, int], list[MetricRow]] = {}
    for row in rows:
        observations.setdefault(
            (row.observation_date, row.company_id), []
        ).append(row)

    by_date: dict[date, list[tuple[int, float, float, float]]] = {}
    for (observation_date, company_id), company_rows in observations.items():
        overrides = {}
        if neutral_margin_of_safety:
            raw_values = {row.key: row.raw_value for row in company_rows}
            margin = compute_margin_of_safety(
                raw_values.get("valuation.fcf_yield"),
                debt_to_equity=raw_values.get("balance_sheet.debt_to_equity"),
                quality_score=50.0,
                growth_score=50.0,
            )
            overrides["valuation.margin_of_safety"] = _linear_score(
                margin,
                -0.05,
                0.05,
            )
        categories: dict[str, list[MetricRow]] = {}
        for row in company_rows:
            categories.setdefault(row.category, []).append(row)
        total_score = 0.0
        for category_rows in categories.values():
            representative = category_rows[0]
            category_score = representative.category_score
            category_is_changed = any(
                row.key in ablated_metrics
                or row.key in overrides
                or row.key in weight_multipliers
                or row.key in threshold_factors
                for row in category_rows
            )
            if category_is_changed:
                remaining = []
                for row in category_rows:
                    if row.key in ablated_metrics:
                        continue
                    normalized_score = overrides.get(
                        row.key,
                        row.normalized_score,
                    )
                    if row.key in threshold_factors:
                        normalized_score = _rescore_threshold(
                            row,
                            threshold_factors[row.key],
                        )
                    if normalized_score is not None:
                        adjusted_weight = row.configured_weight * weight_multipliers.get(
                            row.key, 1.0
                        )
                        remaining.append(
                            (row, normalized_score, adjusted_weight)
                        )
                if category_is_changed:
                    total_weight = sum(
                        adjusted_weight
                        for _, _, adjusted_weight in remaining
                    )
                    category_score = (
                        sum(
                            normalized_score * adjusted_weight
                            for _, normalized_score, adjusted_weight in remaining
                        )
                        / total_weight
                        if total_weight
                        else 0.0
                    )
            total_score += category_score * representative.total_category_weight
        representative = company_rows[0]
        by_date.setdefault(observation_date, []).append(
            (
                company_id,
                total_score,
                representative.realized_return,
                representative.benchmark_return,
            )
        )

    excesses = []
    spreads = []
    correlations = []
    for observations_for_date in by_date.values():
        ranked = sorted(
            observations_for_date,
            key=lambda item: (-item[1], item[0]),
        )
        bucket_size = max(1, len(ranked) // 10)
        top = ranked[:bucket_size]
        bottom = ranked[-bucket_size:]
        top_return = mean(item[2] for item in top)
        excesses.append(top_return - top[0][3])
        spreads.append(top_return - mean(item[2] for item in bottom))
        correlations.append(_pearson([(item[1], item[2]) for item in ranked]))
    return RankingMetrics(
        top_excess=mean(excesses),
        top_bottom_spread=mean(spreads),
        score_return_correlation=mean(correlations),
        periods=len(by_date),
    )


def _sensitivity(
    key: str,
    variant: str,
    baseline_train: RankingMetrics,
    baseline_holdout: RankingMetrics,
    candidate_train: RankingMetrics,
    candidate_holdout: RankingMetrics,
) -> MetricSensitivity:
    return MetricSensitivity(
        key=key,
        variant=variant,
        train_excess_delta=candidate_train.top_excess - baseline_train.top_excess,
        train_spread_delta=(
            candidate_train.top_bottom_spread - baseline_train.top_bottom_spread
        ),
        holdout_excess_delta=(
            candidate_holdout.top_excess - baseline_holdout.top_excess
        ),
        holdout_spread_delta=(
            candidate_holdout.top_bottom_spread
            - baseline_holdout.top_bottom_spread
        ),
    )


def _supports_threshold_sensitivity(transformation: str) -> bool:
    return transformation.startswith(("linear[", "inverted_linear[", "exponential["))


def _rescore_threshold(row: MetricRow, factor: float) -> float | None:
    if row.raw_value is None:
        return None
    match = re.match(
        r"^(linear|inverted_linear)\[([^,]+),([^\]]+)\]",
        row.transformation,
    )
    if match:
        floor = float(match.group(2)) * factor
        ceiling = float(match.group(3)) * factor
        if match.group(1) == "linear":
            return _bounded_linear(row.raw_value, floor, ceiling)
        return 100.0 - _bounded_linear(row.raw_value, floor, ceiling)
    match = re.match(r"^exponential\[([^\]]+)\]", row.transformation)
    if match:
        scale = float(match.group(1)) * factor
        if row.raw_value <= 0:
            score = 0.0
        else:
            score = min(99.9, 100.0 * (1.0 - math.exp(-row.raw_value / scale)))
        if "one_off_cap_60" in row.transformation:
            score = min(score, 60.0)
        return score
    return row.normalized_score


def _bounded_linear(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        raise ValueError("threshold sensitivity produced invalid bounds")
    if value <= floor:
        return 0.0
    if value >= ceiling:
        return 100.0
    return (value - floor) / (ceiling - floor) * 100.0


def _average_metric_correlation(rows: list[MetricRow]) -> float:
    by_date: dict[date, list[MetricRow]] = {}
    for row in rows:
        by_date.setdefault(row.observation_date, []).append(row)
    values = [
        _pearson(
            [(row.normalized_score, row.realized_return) for row in period_rows]
        )
        for period_rows in by_date.values()
        if len(period_rows) >= 5
    ]
    return mean(values) if values else 0.0


def _redundant_pairs(
    rows: list[MetricRow],
    threshold: float,
) -> tuple[RedundantPair, ...]:
    values: dict[str, dict[tuple[date, int], float]] = {}
    for row in rows:
        if row.available and row.normalized_score is not None:
            values.setdefault(row.key, {})[
                (row.observation_date, row.company_id)
            ] = row.normalized_score
    pairs = []
    for first, second in combinations(sorted(values), 2):
        common = values[first].keys() & values[second].keys()
        if len(common) < 30:
            continue
        correlation = _pearson(
            [(values[first][key], values[second][key]) for key in common]
        )
        if abs(correlation) >= threshold:
            pairs.append(RedundantPair(first, second, correlation))
    return tuple(sorted(pairs, key=lambda pair: abs(pair.correlation), reverse=True))


def _shared_dependencies(rows: list[MetricRow]) -> dict[str, tuple[str, ...]]:
    metrics_by_dependency: dict[str, set[str]] = {}
    for row in rows:
        for dependency in row.dependencies:
            metrics_by_dependency.setdefault(dependency, set()).add(row.key)
    return {
        dependency: tuple(sorted(metrics))
        for dependency, metrics in sorted(metrics_by_dependency.items())
        if len(metrics) > 1
    }


def _cross_dependencies(rows: list[MetricRow]) -> dict[str, tuple[str, ...]]:
    result = {}
    for row in rows:
        if row.cross_category_dependencies:
            result[row.key] = row.cross_category_dependencies
    return dict(sorted(result.items()))


def _pearson(pairs) -> float:
    pairs = list(pairs)
    if len(pairs) < 3:
        return 0.0
    xs, ys = zip(*pairs)
    x_mean, y_mean = mean(xs), mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - x_mean) ** 2 for x in xs)
        * sum((y - y_mean) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else 0.0


def _optional_float(value: str) -> float | None:
    return float(value) if value else None


def _split(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split("|") if item)
