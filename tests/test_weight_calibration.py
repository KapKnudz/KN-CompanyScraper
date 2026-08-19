from datetime import date

import pytest

from kncompanyscraper.analysis.backtesting.weight_calibration import (
    CalibrationRow,
    calibrate_weights,
    evaluate_weights,
    load_attribution_rows,
)


def _rows():
    rows = []
    for month in range(1, 9):
        for company_id in range(1, 21):
            valuation = company_id * 5.0
            rows.append(
                CalibrationRow(
                    observation_date=date(2024, month, 28),
                    company_id=company_id,
                    sector_id=str(company_id % 3),
                    market_cap=float(company_id * 100),
                    scores=(100.0 - valuation, 50.0, valuation, 50.0),
                    realized_return=company_id / 100.0,
                    benchmark_return=0.05,
                )
            )
    return rows


def test_calibration_moves_toward_predictive_component_but_blocks_short_history():
    report = calibrate_weights(_rows())

    assert report.candidate_weights[2] > report.frozen_weights[2]
    assert report.candidate_weights[0] < report.frozen_weights[0]
    assert report.candidate_holdout.top_excess > report.frozen_holdout.top_excess
    assert report.independent_windows == 1
    assert report.recommendation_ready is False
    assert "only 1 non-overlapping" in report.readiness_reasons[0]


def test_load_attribution_rows_requires_control_and_benchmark_fields(tmp_path):
    path = tmp_path / "old.csv"
    path.write_text("observation_date,company_id,quality_score\n")

    with pytest.raises(ValueError, match="benchmark_12m_return"):
        load_attribution_rows(path)


def test_six_month_horizon_cannot_set_production_weights():
    report = calibrate_weights(_rows(), horizon_months=6)

    assert report.recommendation_ready is False
    assert "robustness evidence only" in report.readiness_reasons[0]


def test_evaluation_reports_actual_top_30_shortlist_performance():
    rows = []
    for company_id in range(1, 41):
        rows.append(
            CalibrationRow(
                observation_date=date(2024, 1, 31),
                company_id=company_id,
                sector_id="1",
                market_cap=float(company_id),
                scores=(100.0 - company_id, 0.0, 0.0, 0.0),
                realized_return=0.20 if company_id <= 30 else 0.05,
                benchmark_return=0.10,
            )
        )

    metrics = evaluate_weights(rows, (1.0, 0.0, 0.0, 0.0))

    assert metrics.shortlist_30_excess == pytest.approx(0.10)
    assert metrics.shortlist_30_rest_spread == pytest.approx(0.15)
