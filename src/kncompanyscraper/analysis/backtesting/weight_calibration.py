from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from kncompanyscraper.models.enums import RankingModel


COMPONENTS = (
    "quality_score",
    "growth_score",
    "valuation_score",
    "balance_sheet_score",
)
FROZEN_WEIGHTS = {
    RankingModel.GENERAL: (0.30, 0.25, 0.30, 0.15),
    RankingModel.PROPERTY: (0.25, 0.15, 0.30, 0.30),
    RankingModel.BANK: (0.30, 0.20, 0.25, 0.25),
}


@dataclass(frozen=True)
class CalibrationRow:
    observation_date: date
    company_id: int
    sector_id: str
    market_cap: float | None
    scores: tuple[float, float, float, float]
    realized_return: float
    benchmark_return: float


@dataclass(frozen=True)
class WeightMetrics:
    top_excess: float
    top_bottom_spread: float
    shortlist_30_excess: float
    shortlist_30_rest_spread: float
    score_return_correlation: float
    sector_neutral_correlation: float
    size_neutral_correlation: float
    positive_excess_rate: float
    periods: int


@dataclass(frozen=True)
class CalibrationReport:
    ranking_model: RankingModel
    horizon_months: int
    frozen_weights: tuple[float, float, float, float]
    candidate_weights: tuple[float, float, float, float]
    frozen_train: WeightMetrics
    candidate_train: WeightMetrics
    frozen_holdout: WeightMetrics
    candidate_holdout: WeightMetrics
    ablations: tuple[tuple[str, WeightMetrics], ...]
    independent_windows: int
    recommendation_ready: bool
    readiness_reasons: tuple[str, ...]


def load_attribution_rows(
    path: Path,
    ranking_model: RankingModel = RankingModel.GENERAL,
    horizon_months: int = 12,
) -> list[CalibrationRow]:
    return_field = f"return_{horizon_months}m"
    benchmark_field = f"benchmark_{horizon_months}m_return"
    rows = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = set(COMPONENTS) | {
            "observation_date",
            "company_id",
            "ranking_model",
            "sector_id",
            "market_cap",
            return_field,
            benchmark_field,
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                "Attribution CSV lacks calibration fields: "
                + ", ".join(sorted(missing))
            )
        for raw in reader:
            if raw["ranking_model"] != ranking_model:
                continue
            values = [raw[field] for field in COMPONENTS]
            if not raw[return_field] or not raw[benchmark_field] or not all(values):
                continue
            rows.append(
                CalibrationRow(
                    observation_date=date.fromisoformat(raw["observation_date"]),
                    company_id=int(raw["company_id"]),
                    sector_id=raw["sector_id"] or "missing",
                    market_cap=_optional_float(raw["market_cap"]),
                    scores=tuple(float(value) for value in values),
                    realized_return=float(raw[return_field]),
                    benchmark_return=float(raw[benchmark_field]),
                )
            )
    return rows


def calibrate_weights(
    rows: list[CalibrationRow],
    ranking_model: RankingModel = RankingModel.GENERAL,
    horizon_months: int = 12,
) -> CalibrationReport:
    frozen = FROZEN_WEIGHTS[ranking_model]
    dates = sorted({row.observation_date for row in rows})
    if len(dates) < 4:
        raise ValueError("At least four observation dates are required for calibration")
    split = len(dates) // 2
    train_dates = set(dates[:split])
    holdout_dates = set(dates[split:])
    train = [row for row in rows if row.observation_date in train_dates]
    holdout = [row for row in rows if row.observation_date in holdout_dates]

    candidates = _candidate_weights(frozen)
    candidate = max(
        candidates,
        key=lambda weights: _selection_key(evaluate_weights(train, weights)),
    )
    frozen_train = evaluate_weights(train, frozen)
    candidate_train = evaluate_weights(train, candidate)
    frozen_holdout = evaluate_weights(holdout, frozen)
    candidate_holdout = evaluate_weights(holdout, candidate)

    horizon_days = round(horizon_months * 365.25 / 12)
    independent_windows = _independent_window_count(dates, horizon_days)
    reasons = []
    if horizon_months == 6:
        reasons.append(
            "6-month results are robustness evidence only; 12-month calibration is primary"
        )
    elif horizon_months > 12:
        reasons.append(
            f"{horizon_months}-month results are investment-horizon evidence; "
            "12-month calibration remains the primary production gate"
        )
    if independent_windows < 4:
        reasons.append(
            f"only {independent_windows} non-overlapping {horizon_months}-month windows; 4 required"
        )
    if candidate_holdout.top_excess <= frozen_holdout.top_excess:
        reasons.append("candidate does not improve holdout benchmark excess")
    if candidate_holdout.top_bottom_spread <= frozen_holdout.top_bottom_spread:
        reasons.append("candidate does not improve holdout top-bottom spread")

    ablations = []
    for index, component in enumerate(COMPONENTS):
        weights = list(frozen)
        weights[index] = 0.0
        scale = sum(weights)
        normalized = tuple(value / scale for value in weights)
        ablations.append((component, evaluate_weights(rows, normalized)))

    return CalibrationReport(
        ranking_model=ranking_model,
        horizon_months=horizon_months,
        frozen_weights=frozen,
        candidate_weights=candidate,
        frozen_train=frozen_train,
        candidate_train=candidate_train,
        frozen_holdout=frozen_holdout,
        candidate_holdout=candidate_holdout,
        ablations=tuple(ablations),
        independent_windows=independent_windows,
        recommendation_ready=not reasons and candidate != frozen,
        readiness_reasons=tuple(reasons),
    )


def evaluate_weights(
    rows: list[CalibrationRow],
    weights: tuple[float, float, float, float],
) -> WeightMetrics:
    by_date: dict[date, list[tuple[CalibrationRow, float]]] = {}
    for row in rows:
        score = sum(value * weight for value, weight in zip(row.scores, weights))
        by_date.setdefault(row.observation_date, []).append((row, score))

    excesses = []
    spreads = []
    shortlist_excesses = []
    shortlist_rest_spreads = []
    correlations = []
    sector_correlations = []
    size_correlations = []
    for period_rows in by_date.values():
        ranked = sorted(period_rows, key=lambda item: (-item[1], item[0].company_id))
        bucket_size = max(1, len(ranked) // 10)
        top = ranked[:bucket_size]
        bottom = ranked[-bucket_size:]
        top_return = mean(item[0].realized_return for item in top)
        excesses.append(top_return - top[0][0].benchmark_return)
        spreads.append(top_return - mean(item[0].realized_return for item in bottom))
        shortlist = ranked[:30]
        shortlist_return = mean(item[0].realized_return for item in shortlist)
        shortlist_excesses.append(
            shortlist_return - shortlist[0][0].benchmark_return
        )
        rest = ranked[30:]
        shortlist_rest_spreads.append(
            shortlist_return - mean(item[0].realized_return for item in rest)
            if rest
            else 0.0
        )
        correlations.append(
            _pearson([(score, row.realized_return) for row, score in period_rows])
        )
        sector_correlations.append(_peer_neutral_correlation(period_rows, "sector"))
        size_correlations.append(_peer_neutral_correlation(period_rows, "size"))

    return WeightMetrics(
        top_excess=mean(excesses),
        top_bottom_spread=mean(spreads),
        shortlist_30_excess=mean(shortlist_excesses),
        shortlist_30_rest_spread=mean(shortlist_rest_spreads),
        score_return_correlation=mean(correlations),
        sector_neutral_correlation=mean(sector_correlations),
        size_neutral_correlation=mean(size_correlations),
        positive_excess_rate=sum(value > 0 for value in excesses) / len(excesses),
        periods=len(by_date),
    )


def _candidate_weights(
    frozen: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    candidates = []
    for quality in range(2, 11):
        for growth in range(2, 11):
            for valuation in range(2, 11):
                balance = 20 - quality - growth - valuation
                if balance < 2 or balance > 10:
                    continue
                weights = tuple(
                    value / 20 for value in (quality, growth, valuation, balance)
                )
                if all(abs(value - base) <= 0.15 for value, base in zip(weights, frozen)):
                    candidates.append(weights)
    if frozen not in candidates:
        candidates.append(frozen)
    return candidates


def _peer_neutral_correlation(period_rows, control: str) -> float:
    if control == "sector":
        peers = [row.sector_id for row, _ in period_rows]
    else:
        ordered = sorted(
            (row.market_cap, row.company_id)
            for row, _ in period_rows
            if row.market_cap is not None
        )
        bucket_by_id = {
            company_id: str(index * 3 // max(1, len(ordered)))
            for index, (_, company_id) in enumerate(ordered)
        }
        peers = [bucket_by_id.get(row.company_id, "missing") for row, _ in period_rows]

    grouped: dict[str, list[tuple[CalibrationRow, float]]] = {}
    for peer, item in zip(peers, period_rows):
        grouped.setdefault(peer, []).append(item)
    pairs = []
    for group in grouped.values():
        if len(group) < 2:
            continue
        score_mean = mean(score for _, score in group)
        return_mean = mean(row.realized_return for row, _ in group)
        pairs.extend(
            (score - score_mean, row.realized_return - return_mean)
            for row, score in group
        )
    return _pearson(pairs)


def _pearson(pairs: list[tuple[float, float]]) -> float:
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


def _selection_key(metrics: WeightMetrics) -> tuple[float, float, float]:
    return (
        metrics.top_excess,
        metrics.top_bottom_spread,
        metrics.score_return_correlation,
    )


def _independent_window_count(dates: list[date], horizon_days: int) -> int:
    anchors = []
    for value in dates:
        if not anchors or (value - anchors[-1]).days >= horizon_days:
            anchors.append(value)
    return len(anchors)


def _optional_float(value: str) -> float | None:
    return float(value) if value else None
